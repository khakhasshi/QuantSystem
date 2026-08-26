#!/usr/bin/env python3
"""Download current US index constituents and ten years of daily bars via yfinance.

Defaults:
- current S&P 500 constituents as the as-of cross-section
- ten calendar years ending at --end-date
- one unadjusted OHLCV dataset and one qfq/forward-adjusted OHLCV dataset
"""

from __future__ import annotations

import argparse
from io import StringIO
import json
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence


CONSTITUENT_SOURCES = {
    "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
}

ADJUSTMENTS = {
    "unadjusted": {"auto_adjust": False, "source": "yfinance.download(auto_adjust=False)"},
    "qfq": {"auto_adjust": True, "source": "yfinance.download(auto_adjust=True)"},
}

CANONICAL_COLUMNS = [
    "trade_date",
    "symbol",
    "ticker",
    "yahoo_symbol",
    "exchange",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "dividends",
    "stock_splits",
    "adjustment",
    "source",
]

NUMERIC_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "dividends",
    "stock_splits",
]

YFINANCE_COLUMNS = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
    "Dividends": "dividends",
    "Stock Splits": "stock_splits",
}

CONSTITUENT_TICKER_ALIASES = (
    "Symbol",
    "Ticker",
    "ticker",
    "symbol",
)

CONSTITUENT_NAME_ALIASES = (
    "Security",
    "Name",
    "Company",
    "security",
    "name",
    "company",
)


@dataclass(frozen=True)
class DownloadConfig:
    root: Path
    universe: str
    constituents_csv: Path | None
    asof_date: str
    start_date: str
    end_date: str
    adjustments: tuple[str, ...]
    sleep_seconds: float
    retries: int
    force: bool
    allow_partial: bool
    write_csv: bool
    write_parquet: bool
    symbol_limit: int | None


def require_pandas():
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: pandas. Install with "
            "`python -m pip install -r datacenter/usstock/requirements.txt`."
        ) from exc
    return pd


def require_yfinance():
    try:
        import yfinance as yf
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: yfinance. Install with "
            "`python -m pip install -r datacenter/usstock/requirements.txt`."
        ) from exc
    return yf


def require_requests():
    try:
        import requests
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: requests. Install with "
            "`python -m pip install -r datacenter/usstock/requirements.txt`."
        ) from exc
    return requests


def parse_date(value: str) -> date:
    clean = value.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(clean, fmt).date()
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(f"invalid date {value!r}; use YYYYMMDD or YYYY-MM-DD")


def compact_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def iso_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year - years)


def yfinance_end_exclusive(end_date: str) -> str:
    return iso_date(parse_date(end_date) + timedelta(days=1))


def normalize_ticker(value: object) -> str:
    ticker = str(value).strip().upper()
    ticker = ticker.replace(" ", "")
    if not ticker or ticker == "NAN":
        return ""
    if "." in ticker:
        ticker = ticker.split()[0]
    return ticker


def yahoo_symbol_from_ticker(ticker: str) -> str:
    return normalize_ticker(ticker).replace(".", "-")


def canonical_symbol(ticker: str) -> str:
    return f"{normalize_ticker(ticker)}.US"


def safe_symbol_path(symbol: str) -> str:
    return symbol.replace(".", "_").replace("-", "_").replace("/", "_")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_json(path: Path, payload: dict) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def write_dataframe_csv(df, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8")
    tmp.replace(path)


def write_dataframe_parquet(df, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def first_existing_column(columns: Iterable[str], aliases: Sequence[str]) -> str | None:
    existing = set(columns)
    for alias in aliases:
        if alias in existing:
            return alias
    return None


def extract_constituents(df):
    pd = require_pandas()
    ticker_col = first_existing_column(df.columns, CONSTITUENT_TICKER_ALIASES)
    if ticker_col is None:
        raise ValueError(f"Cannot find ticker column. Known columns: {list(df.columns)!r}")

    name_col = first_existing_column(df.columns, CONSTITUENT_NAME_ALIASES)
    frame = df.copy()
    frame["ticker"] = frame[ticker_col].map(normalize_ticker)
    frame = frame.loc[frame["ticker"].ne("")]
    frame["yahoo_symbol"] = frame["ticker"].map(yahoo_symbol_from_ticker)
    frame["symbol"] = frame["ticker"].map(canonical_symbol)
    frame["exchange"] = "US"
    frame["security"] = frame[name_col].astype(str) if name_col is not None else pd.NA
    frame = frame.drop_duplicates("ticker", keep="first")
    keep_columns = ["ticker", "yahoo_symbol", "symbol", "exchange", "security"]
    optional_columns = [
        col
        for col in ("GICS Sector", "GICS Sub-Industry", "Headquarters Location", "Date added", "CIK", "Founded")
        if col in frame.columns
    ]
    return frame[keep_columns + optional_columns].sort_values("ticker").reset_index(drop=True)


def fetch_constituents(universe: str, constituents_csv: Path | None = None):
    pd = require_pandas()
    if constituents_csv is not None:
        return pd.read_csv(constituents_csv)
    if universe not in CONSTITUENT_SOURCES:
        raise ValueError(f"unsupported universe {universe!r}; use --constituents-csv for a custom universe")
    requests = require_requests()
    response = requests.get(
        CONSTITUENT_SOURCES[universe],
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            )
        },
        timeout=30,
    )
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    if not tables:
        raise RuntimeError(f"no constituent tables found for {universe}")
    return tables[0]


def flatten_yfinance_columns(df, yahoo_symbol: str):
    if not hasattr(df.columns, "nlevels") or df.columns.nlevels == 1:
        return df

    wanted = set(YFINANCE_COLUMNS)
    renamed = []
    for col in df.columns:
        parts = [str(part) for part in col if str(part) and str(part) != "nan"]
        matching = [part for part in parts if part in wanted]
        if not matching:
            matching = [part for part in parts if part.upper() != yahoo_symbol.upper()]
        renamed.append(matching[0] if matching else "_".join(parts))

    flattened = df.copy()
    flattened.columns = renamed
    return flattened.loc[:, ~flattened.columns.duplicated()]


def normalize_yfinance_hist(df, ticker: str, adjustment: str):
    pd = require_pandas()
    if adjustment not in ADJUSTMENTS:
        raise ValueError(f"unsupported adjustment: {adjustment}")

    ticker = normalize_ticker(ticker)
    yahoo_symbol = yahoo_symbol_from_ticker(ticker)
    normalized = flatten_yfinance_columns(df, yahoo_symbol).copy()
    if normalized.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    if "Date" not in normalized.columns:
        normalized = normalized.reset_index()
    if "Date" not in normalized.columns and "Datetime" in normalized.columns:
        normalized = normalized.rename(columns={"Datetime": "Date"})
    if "Date" not in normalized.columns:
        raise ValueError(f"missing Date column for {ticker}: {list(normalized.columns)!r}")

    normalized = normalized.rename(columns=YFINANCE_COLUMNS)
    normalized["trade_date"] = pd.to_datetime(normalized["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    normalized["ticker"] = ticker
    normalized["yahoo_symbol"] = yahoo_symbol
    normalized["symbol"] = canonical_symbol(ticker)
    normalized["exchange"] = "US"
    normalized["adjustment"] = adjustment
    normalized["source"] = ADJUSTMENTS[adjustment]["source"]

    for col in NUMERIC_COLUMNS:
        if col not in normalized.columns:
            normalized[col] = 0.0 if col in ("dividends", "stock_splits") else pd.NA
        normalized[col] = pd.to_numeric(normalized[col], errors="coerce")

    if adjustment == "qfq":
        normalized["adj_close"] = normalized["close"]

    normalized = normalized[CANONICAL_COLUMNS]
    normalized = normalized.dropna(subset=["trade_date", "open", "high", "low", "close"])
    normalized = normalized.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    return normalized


def filter_history_window(df, start_date: str, end_date: str):
    start_iso = iso_date(parse_date(start_date))
    end_iso = iso_date(parse_date(end_date))
    return df.loc[df["trade_date"].between(start_iso, end_iso)].reset_index(drop=True)


def quality_summary(df, expected_tickers: Sequence[str], failed_tickers: Sequence[str]) -> dict:
    expected_symbols = {canonical_symbol(ticker) for ticker in expected_tickers}
    if df.empty:
        return {
            "rows": 0,
            "symbols_with_rows": 0,
            "expected_symbols": len(expected_symbols),
            "empty_symbols": sorted(expected_symbols),
            "failed_symbols": sorted(failed_tickers),
            "min_trade_date": None,
            "max_trade_date": None,
            "duplicate_symbol_trade_date_rows": 0,
        }

    observed_symbols = set(df["symbol"].dropna().unique().tolist())
    return {
        "rows": int(len(df)),
        "symbols_with_rows": int(len(observed_symbols)),
        "expected_symbols": len(expected_symbols),
        "empty_symbols": sorted(expected_symbols - observed_symbols),
        "failed_symbols": sorted(failed_tickers),
        "min_trade_date": str(df["trade_date"].min()),
        "max_trade_date": str(df["trade_date"].max()),
        "duplicate_symbol_trade_date_rows": int(df.duplicated(["symbol", "trade_date"]).sum()),
    }


def fetch_with_retries(label: str, retries: int, sleep_seconds: float, fn):
    last_exc: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - downloader should record provider failures.
            last_exc = exc
            if attempt > retries:
                break
            time.sleep(max(sleep_seconds, 0.0) * attempt)
    raise RuntimeError(f"{label} failed after {retries + 1} attempt(s): {last_exc}") from last_exc


def fetch_daily_hist(ticker: str, start_date: str, end_date: str, adjustment: str):
    yf = require_yfinance()
    yahoo_symbol = yahoo_symbol_from_ticker(ticker)
    return yf.download(
        yahoo_symbol,
        start=iso_date(parse_date(start_date)),
        end=yfinance_end_exclusive(end_date),
        interval="1d",
        auto_adjust=bool(ADJUSTMENTS[adjustment]["auto_adjust"]),
        actions=True,
        progress=False,
        threads=False,
    )


def write_standardized_outputs(root: Path, adjustment: str, df, write_csv: bool, write_parquet: bool) -> dict:
    output_dir = root / "canonical" / "daily" / f"adjustment={adjustment}"
    outputs: dict[str, str] = {}
    if write_csv:
        csv_path = output_dir / "daily.csv"
        write_dataframe_csv(df, csv_path)
        outputs["csv"] = str(csv_path)
    if write_parquet:
        parquet_path = output_dir / "daily.parquet"
        write_dataframe_parquet(df, parquet_path)
        outputs["parquet"] = str(parquet_path)
    return outputs


def run_download(config: DownloadConfig) -> dict:
    pd = require_pandas()
    root = config.root
    run_started = datetime.now().astimezone().isoformat(timespec="seconds")
    manifest_dir = root / "manifests"
    raw_constituent_dir = root / "raw" / "constituents" / f"universe={config.universe}" / f"asof={config.asof_date}"
    raw_hist_root = root / "raw" / "yfinance" / "download"

    constituents_raw = fetch_with_retries(
        f"{config.universe} constituents",
        config.retries,
        config.sleep_seconds,
        lambda: fetch_constituents(config.universe, config.constituents_csv),
    )
    write_dataframe_csv(constituents_raw, raw_constituent_dir / "constituents_raw.csv")

    constituents = extract_constituents(constituents_raw)
    if config.symbol_limit is not None:
        constituents = constituents.head(config.symbol_limit).copy()
    tickers = constituents["ticker"].tolist()
    metadata_path = root / "metadata" / f"{config.universe}_constituents_asof_{config.asof_date}.csv"
    constituents = constituents.assign(
        universe=config.universe,
        asof_date=iso_date(parse_date(config.asof_date)),
        source=("custom_csv" if config.constituents_csv is not None else CONSTITUENT_SOURCES[config.universe]),
    )
    write_dataframe_csv(constituents, metadata_path)

    adjustment_results: dict[str, dict] = {}
    for adjustment in config.adjustments:
        frames = []
        failures: dict[str, str] = {}
        for idx, row in enumerate(constituents.itertuples(index=False), start=1):
            ticker = row.ticker
            symbol = canonical_symbol(ticker)
            raw_path = (
                raw_hist_root
                / f"adjustment={adjustment}"
                / f"symbol={symbol}"
                / f"{safe_symbol_path(symbol)}.csv"
            )
            try:
                if raw_path.exists() and not config.force:
                    raw_df = pd.read_csv(raw_path)
                else:
                    raw_df = fetch_with_retries(
                        f"{adjustment} daily {ticker} ({idx}/{len(tickers)})",
                        config.retries,
                        config.sleep_seconds,
                        lambda ticker=ticker, adjustment=adjustment: fetch_daily_hist(
                            ticker,
                            config.start_date,
                            config.end_date,
                            adjustment,
                        ),
                    )
                    write_dataframe_csv(flatten_yfinance_columns(raw_df.reset_index(), row.yahoo_symbol), raw_path)
                    time.sleep(max(config.sleep_seconds, 0.0))

                canonical_df = filter_history_window(
                    normalize_yfinance_hist(raw_df, ticker, adjustment),
                    config.start_date,
                    config.end_date,
                )
                if not canonical_df.empty:
                    frames.append(canonical_df)
            except Exception as exc:  # noqa: BLE001 - keep downloading other symbols when allowed.
                failures[ticker] = str(exc)
                if not config.allow_partial:
                    raise

        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=CANONICAL_COLUMNS)
        combined = combined.drop_duplicates(["symbol", "trade_date"], keep="last")
        combined = combined.sort_values(["symbol", "trade_date"]).reset_index(drop=True)

        outputs = write_standardized_outputs(
            root=root,
            adjustment=adjustment,
            df=combined,
            write_csv=config.write_csv,
            write_parquet=config.write_parquet,
        )
        summary = quality_summary(combined, tickers, failures.keys())
        summary["outputs"] = outputs
        adjustment_results[adjustment] = summary
        write_json(manifest_dir / f"{config.universe}_daily_{adjustment}_{config.end_date}.manifest.json", summary)

    manifest = {
        "dataset": f"{config.universe}_daily",
        "run_started": run_started,
        "run_finished": datetime.now().astimezone().isoformat(timespec="seconds"),
        "config": {
            **asdict(config),
            "root": str(config.root),
            "constituents_csv": str(config.constituents_csv) if config.constituents_csv else None,
            "adjustments": list(config.adjustments),
        },
        "constituents": {
            "raw_csv": str(raw_constituent_dir / "constituents_raw.csv"),
            "metadata_csv": str(metadata_path),
            "count": len(tickers),
        },
        "adjustments": adjustment_results,
    }
    write_json(manifest_dir / f"{config.universe}_daily_run_{config.end_date}.manifest.json", manifest)
    return manifest


def parse_adjustments(value: str) -> tuple[str, ...]:
    adjustments = tuple(item.strip() for item in value.split(",") if item.strip())
    unknown = sorted(set(adjustments) - set(ADJUSTMENTS))
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown adjustment(s): {', '.join(unknown)}")
    if not adjustments:
        raise argparse.ArgumentTypeError("at least one adjustment is required")
    return adjustments


def build_parser() -> argparse.ArgumentParser:
    today = date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent / "data")
    parser.add_argument("--universe", default="sp500", choices=sorted(CONSTITUENT_SOURCES))
    parser.add_argument("--constituents-csv", type=Path, default=None, help="Optional custom constituent CSV.")
    parser.add_argument("--asof-date", type=parse_date, default=None, help="Constituent snapshot date; defaults to --end-date.")
    parser.add_argument("--years", type=int, default=10, help="Calendar years to download when --start-date is omitted.")
    parser.add_argument("--start-date", type=parse_date, default=None, help="YYYYMMDD or YYYY-MM-DD.")
    parser.add_argument("--end-date", type=parse_date, default=today, help="YYYYMMDD or YYYY-MM-DD.")
    parser.add_argument("--adjustments", type=parse_adjustments, default=("unadjusted", "qfq"))
    parser.add_argument("--sleep-seconds", type=float, default=0.1)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--force", action="store_true", help="Redownload raw files even if present.")
    parser.add_argument("--allow-partial", action="store_true", help="Write successful symbols even when some fail.")
    parser.add_argument("--no-csv", action="store_true", help="Skip canonical CSV output.")
    parser.add_argument("--no-parquet", action="store_true", help="Skip canonical Parquet output.")
    parser.add_argument("--symbol-limit", type=int, default=None, help="Debug only: limit number of constituents.")
    return parser


def config_from_args(args: argparse.Namespace) -> DownloadConfig:
    end_date = args.end_date
    start_date = args.start_date or subtract_years(end_date, args.years)
    asof_date = args.asof_date or end_date
    if start_date > end_date:
        raise SystemExit("--start-date cannot be after --end-date")
    if args.no_csv and args.no_parquet:
        raise SystemExit("At least one canonical output format must be enabled.")
    return DownloadConfig(
        root=args.root,
        universe=args.universe,
        constituents_csv=args.constituents_csv,
        asof_date=compact_date(asof_date),
        start_date=compact_date(start_date),
        end_date=compact_date(end_date),
        adjustments=args.adjustments,
        sleep_seconds=args.sleep_seconds,
        retries=args.retries,
        force=args.force,
        allow_partial=args.allow_partial,
        write_csv=not args.no_csv,
        write_parquet=not args.no_parquet,
        symbol_limit=args.symbol_limit,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = config_from_args(args)
    manifest = run_download(config)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
