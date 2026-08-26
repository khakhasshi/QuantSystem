#!/usr/bin/env python3
"""Download current CSI 300 daily bars from AKShare.

Outputs:
- raw per-symbol AKShare CSV files for unadjusted and qfq daily bars
- canonical daily datasets for both adjustments
- manifests with row counts, date ranges, and failures
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Sequence


ADJUSTMENT_TO_AKSHARE = {
    "unadjusted": "",
    "qfq": "qfq",
}

PROVIDERS = ("stock_zh_a_hist", "stock_zh_a_daily")

CANONICAL_COLUMNS = [
    "trade_date",
    "symbol",
    "ticker",
    "exchange",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "amplitude",
    "pct_change",
    "change",
    "turnover",
    "adjustment",
    "source",
]

NUMERIC_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "amplitude",
    "pct_change",
    "change",
    "turnover",
]

HIST_COLUMN_ALIASES = {
    "trade_date": ("日期", "date", "trade_date"),
    "ticker": ("股票代码", "证券代码", "代码", "symbol", "ticker"),
    "open": ("开盘", "open"),
    "high": ("最高", "high"),
    "low": ("最低", "low"),
    "close": ("收盘", "close"),
    "volume": ("成交量", "volume"),
    "amount": ("成交额", "amount"),
    "amplitude": ("振幅", "amplitude"),
    "pct_change": ("涨跌幅", "pct_change"),
    "change": ("涨跌额", "change"),
    "turnover": ("换手率", "turnover"),
}

CONSTITUENT_SYMBOL_ALIASES = (
    "成分券代码",
    "品种代码",
    "证券代码",
    "股票代码",
    "代码",
    "symbol",
    "ticker",
)


@dataclass(frozen=True)
class DownloadConfig:
    root: Path
    index_symbol: str
    start_date: str
    end_date: str
    adjustments: tuple[str, ...]
    provider: str
    qfq_mode: str
    sleep_seconds: float
    retries: int
    force: bool
    allow_partial: bool
    write_csv: bool
    write_parquet: bool
    symbol_limit: int | None
    quiet: bool


def require_pandas():
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: pandas. Install with "
            "`python -m pip install -r datacenter/ashare/requirements.txt`."
        ) from exc
    return pd


def require_akshare():
    try:
        import akshare as ak
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: akshare. Install with "
            "`python -m pip install -r datacenter/ashare/requirements.txt`."
        ) from exc
    return ak


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


def normalize_ticker(value: object) -> str:
    ticker = str(value).strip()
    if "." in ticker:
        ticker = ticker.split(".")[0]
    ticker = "".join(ch for ch in ticker if ch.isdigit())
    return ticker.zfill(6)


def infer_exchange(ticker: str) -> str:
    if ticker.startswith(("5", "6", "9")):
        return "SH"
    if ticker.startswith(("0", "2", "3")):
        return "SZ"
    if ticker.startswith(("4", "8")):
        return "BJ"
    return "UNKNOWN"


def akshare_market_symbol(ticker: str) -> str:
    exchange = infer_exchange(ticker).lower()
    if exchange == "unknown":
        raise ValueError(f"cannot infer exchange for ticker {ticker}")
    return f"{exchange}{ticker}"


def canonical_symbol(ticker: str) -> str:
    return f"{ticker}.{infer_exchange(ticker)}"


def safe_symbol_path(symbol: str) -> str:
    return symbol.replace(".", "_")


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
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    tmp.replace(path)


def write_dataframe_parquet(df, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def log(message: str, quiet: bool = False) -> None:
    if not quiet:
        print(message, file=sys.stderr, flush=True)


def first_existing_column(columns: Iterable[str], aliases: Sequence[str]) -> str | None:
    existing = set(columns)
    for alias in aliases:
        if alias in existing:
            return alias
    return None


def extract_constituent_tickers(df) -> list[str]:
    col = first_existing_column(df.columns, CONSTITUENT_SYMBOL_ALIASES)
    if col is None:
        raise ValueError(
            "Cannot find constituent ticker column. "
            f"Known columns: {list(df.columns)!r}"
        )
    tickers = [normalize_ticker(value) for value in df[col].tolist()]
    return sorted(dict.fromkeys(ticker for ticker in tickers if ticker and ticker != "000000"))


def provider_volume_multiplier(source: str) -> int:
    if source == "akshare.stock_zh_a_hist":
        return 100
    if source == "akshare.stock_zh_a_daily":
        return 1
    raise ValueError(f"unsupported source: {source}")


def normalize_akshare_hist(
    df,
    ticker: str,
    adjustment: str,
    source: str = "akshare.stock_zh_a_hist",
):
    pd = require_pandas()
    if adjustment not in ADJUSTMENT_TO_AKSHARE:
        raise ValueError(f"unsupported adjustment: {adjustment}")

    ticker = normalize_ticker(ticker)
    rename_map: dict[str, str] = {}
    for canonical, aliases in HIST_COLUMN_ALIASES.items():
        source_col = first_existing_column(df.columns, aliases)
        if source_col is not None:
            rename_map[source_col] = canonical

    normalized = df.rename(columns=rename_map).copy()
    if "trade_date" not in normalized.columns:
        raise ValueError(f"missing trade_date/date column for {ticker}: {list(df.columns)!r}")

    if "ticker" not in normalized.columns:
        normalized["ticker"] = ticker
    normalized["ticker"] = normalized["ticker"].map(normalize_ticker)
    normalized.loc[normalized["ticker"].eq("000000"), "ticker"] = ticker
    normalized["exchange"] = normalized["ticker"].map(infer_exchange)
    normalized["symbol"] = normalized["ticker"].map(canonical_symbol)
    normalized["adjustment"] = adjustment
    normalized["source"] = source

    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")

    for col in NUMERIC_COLUMNS:
        if col not in normalized.columns:
            normalized[col] = pd.NA
        normalized[col] = pd.to_numeric(normalized[col], errors="coerce")

    normalized["volume"] = normalized["volume"] * provider_volume_multiplier(source)
    if source == "akshare.stock_zh_a_daily":
        normalized["turnover"] = normalized["turnover"] * 100

    normalized = normalized[CANONICAL_COLUMNS]
    for col in ("trade_date", "symbol", "ticker", "exchange", "adjustment", "source"):
        normalized[col] = normalized[col].astype("string")
    normalized = normalized.dropna(subset=["trade_date", "open", "high", "low", "close"])
    normalized = normalized.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    return normalized


def normalize_qfq_factor(df):
    pd = require_pandas()
    if "date" not in df.columns or "qfq_factor" not in df.columns:
        raise ValueError(f"missing qfq factor columns: {list(df.columns)!r}")
    factors = df[["date", "qfq_factor"]].copy()
    factors["factor_date"] = pd.to_datetime(factors["date"], errors="coerce")
    factors["qfq_factor"] = pd.to_numeric(factors["qfq_factor"], errors="coerce")
    factors = factors.dropna(subset=["factor_date", "qfq_factor"])
    factors = factors.sort_values("factor_date").drop_duplicates("factor_date", keep="last")
    if factors.empty:
        raise ValueError("empty qfq factor table")
    return factors[["factor_date", "qfq_factor"]]


def rebuild_qfq_from_unadjusted(raw_unadjusted_df, factor_df, ticker: str):
    pd = require_pandas()
    base = normalize_akshare_hist(
        raw_unadjusted_df,
        ticker,
        "unadjusted",
        source="akshare.stock_zh_a_daily",
    )
    factors = normalize_qfq_factor(factor_df)
    base = base.copy()
    base["trade_dt"] = pd.to_datetime(base["trade_date"], errors="coerce")
    base = base.dropna(subset=["trade_dt"]).sort_values("trade_dt")

    merged = pd.merge_asof(
        base,
        factors,
        left_on="trade_dt",
        right_on="factor_date",
        direction="backward",
    )
    if merged["qfq_factor"].isna().any():
        missing = merged.loc[merged["qfq_factor"].isna(), "trade_date"].head(5).tolist()
        raise ValueError(f"missing qfq factor for {ticker}; sample dates={missing}")

    for col in ("open", "high", "low", "close"):
        merged[col] = (merged[col] / merged["qfq_factor"]).round(2)
    merged["adjustment"] = "qfq"
    merged["source"] = "akshare.stock_zh_a_daily+qfq_factor"
    for col in ("trade_date", "symbol", "ticker", "exchange", "adjustment", "source"):
        merged[col] = merged[col].astype("string")
    return merged[CANONICAL_COLUMNS].sort_values(["symbol", "trade_date"]).reset_index(drop=True)


def quality_summary(df, expected_tickers: Sequence[str], failures: dict[str, str]) -> dict:
    if df.empty:
        return {
            "rows": 0,
            "symbols_with_rows": 0,
            "expected_symbols": len(expected_tickers),
            "empty_symbols": len(expected_tickers),
            "failed_symbols": sorted(failures),
            "failure_details": failures,
            "min_trade_date": None,
            "max_trade_date": None,
            "duplicate_symbol_trade_date_rows": 0,
        }

    expected_symbols = {canonical_symbol(ticker) for ticker in expected_tickers}
    observed_symbols = set(df["symbol"].dropna().unique().tolist())
    empty_symbols = sorted(expected_symbols - observed_symbols)
    duplicates = int(df.duplicated(["symbol", "trade_date"]).sum())
    source_counts = {
        str(source): int(count)
        for source, count in df.groupby("source", dropna=False).size().sort_index().items()
    }
    return {
        "rows": int(len(df)),
        "symbols_with_rows": int(len(observed_symbols)),
        "expected_symbols": len(expected_symbols),
        "empty_symbols": empty_symbols,
        "failed_symbols": sorted(failures),
        "failure_details": failures,
        "min_trade_date": str(df["trade_date"].min()),
        "max_trade_date": str(df["trade_date"].max()),
        "duplicate_symbol_trade_date_rows": duplicates,
        "source_counts": source_counts,
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


def fetch_constituents(index_symbol: str):
    ak = require_akshare()
    return ak.index_stock_cons_csindex(symbol=index_symbol)


def fetch_daily_hist_from_provider(
    provider: str,
    ticker: str,
    start_date: str,
    end_date: str,
    adjustment: str,
):
    ak = require_akshare()
    if provider == "stock_zh_a_hist":
        return ak.stock_zh_a_hist(
            symbol=normalize_ticker(ticker),
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust=ADJUSTMENT_TO_AKSHARE[adjustment],
        )
    if provider == "stock_zh_a_daily":
        return ak.stock_zh_a_daily(
            symbol=akshare_market_symbol(normalize_ticker(ticker)),
            start_date=start_date,
            end_date=end_date,
            adjust=ADJUSTMENT_TO_AKSHARE[adjustment],
        )
    raise ValueError(f"unsupported provider: {provider}")


def fetch_qfq_factor(ticker: str):
    ak = require_akshare()
    return ak.stock_zh_a_daily(symbol=akshare_market_symbol(normalize_ticker(ticker)), adjust="qfq-factor")


def provider_candidates(provider: str) -> tuple[str, ...]:
    if provider == "auto":
        return PROVIDERS
    if provider not in PROVIDERS:
        raise ValueError(f"unsupported provider: {provider}")
    return (provider,)


def fetch_daily_hist(ticker: str, start_date: str, end_date: str, adjustment: str, provider: str):
    errors: dict[str, str] = {}
    for candidate in provider_candidates(provider):
        try:
            df = fetch_daily_hist_from_provider(candidate, ticker, start_date, end_date, adjustment)
            return f"akshare.{candidate}", df
        except Exception as exc:  # noqa: BLE001 - try the configured fallback provider.
            errors[candidate] = str(exc)
    raise RuntimeError(f"all AKShare providers failed for {ticker} {adjustment}: {errors}")


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


def raw_symbol_path(config: DownloadConfig, raw_hist_root: Path, adjustment: str, symbol: str) -> Path:
    return (
        raw_hist_root
        / config.provider
        / f"adjustment={adjustment}"
        / f"start={config.start_date}"
        / f"end={config.end_date}"
        / f"symbol={symbol}"
        / f"{safe_symbol_path(symbol)}.csv"
    )


def read_or_fetch_daily_raw(
    config: DownloadConfig,
    raw_hist_root: Path,
    ticker: str,
    adjustment: str,
):
    pd = require_pandas()
    symbol = canonical_symbol(ticker)
    raw_path = raw_symbol_path(config, raw_hist_root, adjustment, symbol)
    source_path = raw_path.with_suffix(".source.json")
    if raw_path.exists() and not config.force:
        raw_df = pd.read_csv(raw_path)
        if source_path.exists():
            source = json.loads(source_path.read_text(encoding="utf-8"))["source"]
        else:
            source = "akshare.stock_zh_a_hist"
        return source, raw_df

    source, raw_df = fetch_daily_hist(ticker, config.start_date, config.end_date, adjustment, config.provider)
    write_dataframe_csv(raw_df, raw_path)
    write_json(
        source_path,
        {
            "source": source,
            "configured_provider": config.provider,
            "ticker": ticker,
            "symbol": symbol,
            "adjustment": adjustment,
            "start_date": config.start_date,
            "end_date": config.end_date,
        },
    )
    time.sleep(max(config.sleep_seconds, 0.0))
    return source, raw_df


def read_or_fetch_qfq_factor_raw(config: DownloadConfig, raw_hist_root: Path, ticker: str):
    pd = require_pandas()
    symbol = canonical_symbol(ticker)
    raw_path = raw_symbol_path(config, raw_hist_root, "qfq-factor", symbol)
    source_path = raw_path.with_suffix(".source.json")
    if raw_path.exists() and not config.force:
        return pd.read_csv(raw_path)

    factor_df = fetch_qfq_factor(ticker)
    write_dataframe_csv(factor_df, raw_path)
    write_json(
        source_path,
        {
            "source": "akshare.stock_zh_a_daily(qfq-factor)",
            "configured_provider": config.provider,
            "ticker": ticker,
            "symbol": symbol,
            "adjustment": "qfq-factor",
            "start_date": config.start_date,
            "end_date": config.end_date,
        },
    )
    time.sleep(max(config.sleep_seconds, 0.0))
    return factor_df


def run_download(config: DownloadConfig) -> dict:
    pd = require_pandas()
    root = config.root
    run_started = datetime.now().astimezone().isoformat(timespec="seconds")
    manifest_dir = root / "manifests"
    raw_index_dir = root / "raw" / "akshare" / "index_stock_cons_csindex" / f"index={config.index_symbol}" / f"asof={config.end_date}"
    raw_hist_root = root / "raw" / "akshare"

    log(f"[constituents] fetching CSI index {config.index_symbol}", config.quiet)
    constituents_raw = fetch_with_retries(
        f"index constituents {config.index_symbol}",
        config.retries,
        config.sleep_seconds,
        lambda: fetch_constituents(config.index_symbol),
    )
    write_dataframe_csv(constituents_raw, raw_index_dir / "constituents.csv")

    tickers = extract_constituent_tickers(constituents_raw)
    if config.symbol_limit is not None:
        tickers = tickers[: config.symbol_limit]
    log(
        f"[constituents] {len(tickers)} symbol(s), window={config.start_date}-{config.end_date}, "
        f"provider={config.provider}",
        config.quiet,
    )

    metadata = pd.DataFrame(
        {
            "ticker": tickers,
            "exchange": [infer_exchange(ticker) for ticker in tickers],
            "symbol": [canonical_symbol(ticker) for ticker in tickers],
            "index_symbol": config.index_symbol,
            "asof_date": iso_date(parse_date(config.end_date)),
            "source": "akshare.index_stock_cons_csindex",
        }
    )
    write_dataframe_csv(metadata, root / "metadata" / f"hs300_constituents_asof_{config.end_date}.csv")

    adjustment_results: dict[str, dict] = {}
    for adjustment in config.adjustments:
        log(f"[{adjustment}] start", config.quiet)
        frames = []
        failures: dict[str, str] = {}
        for idx, ticker in enumerate(tickers, start=1):
            symbol = canonical_symbol(ticker)
            if idx == 1 or idx % 10 == 0 or idx == len(tickers):
                log(f"[{adjustment}] {idx}/{len(tickers)} {symbol}", config.quiet)
            try:
                if adjustment == "qfq" and config.qfq_mode == "factor":
                    if config.provider != "stock_zh_a_daily":
                        raise ValueError("qfq_mode=factor requires --provider stock_zh_a_daily")
                    _, raw_unadjusted_df = fetch_with_retries(
                        f"unadjusted base for qfq {ticker} ({idx}/{len(tickers)})",
                        config.retries,
                        config.sleep_seconds,
                        lambda ticker=ticker: read_or_fetch_daily_raw(
                            config,
                            raw_hist_root,
                            ticker,
                            "unadjusted",
                        ),
                    )
                    factor_df = fetch_with_retries(
                        f"qfq factor {ticker} ({idx}/{len(tickers)})",
                        config.retries,
                        config.sleep_seconds,
                        lambda ticker=ticker: read_or_fetch_qfq_factor_raw(config, raw_hist_root, ticker),
                    )
                    canonical_df = rebuild_qfq_from_unadjusted(raw_unadjusted_df, factor_df, ticker)
                else:
                    source, raw_df = fetch_with_retries(
                        f"{adjustment} daily {ticker} ({idx}/{len(tickers)})",
                        config.retries,
                        config.sleep_seconds,
                        lambda ticker=ticker, adjustment=adjustment: read_or_fetch_daily_raw(
                            config,
                            raw_hist_root,
                            ticker,
                            adjustment,
                        ),
                    )
                    canonical_df = normalize_akshare_hist(raw_df, ticker, adjustment, source=source)
                if not canonical_df.empty:
                    frames.append(canonical_df)
            except Exception as exc:  # noqa: BLE001 - keep downloading other symbols when allowed.
                failures[ticker] = str(exc)
                log(f"[{adjustment}] failed {symbol}: {exc}", config.quiet)
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
        summary = quality_summary(combined, tickers, failures)
        summary["outputs"] = outputs
        adjustment_results[adjustment] = summary
        write_json(manifest_dir / f"hs300_daily_{adjustment}_{config.end_date}.manifest.json", summary)
        log(
            f"[{adjustment}] done rows={summary['rows']} symbols={summary['symbols_with_rows']}/"
            f"{summary['expected_symbols']} failures={len(summary['failed_symbols'])}",
            config.quiet,
        )

    manifest = {
        "dataset": "hs300_daily",
        "run_started": run_started,
        "run_finished": datetime.now().astimezone().isoformat(timespec="seconds"),
        "config": {
            **asdict(config),
            "root": str(config.root),
            "adjustments": list(config.adjustments),
        },
        "constituents": {
            "raw_csv": str(raw_index_dir / "constituents.csv"),
            "metadata_csv": str(root / "metadata" / f"hs300_constituents_asof_{config.end_date}.csv"),
            "count": len(tickers),
        },
        "adjustments": adjustment_results,
    }
    write_json(manifest_dir / f"hs300_daily_run_{config.end_date}.manifest.json", manifest)
    return manifest


def parse_adjustments(value: str) -> tuple[str, ...]:
    adjustments = tuple(item.strip() for item in value.split(",") if item.strip())
    unknown = sorted(set(adjustments) - set(ADJUSTMENT_TO_AKSHARE))
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown adjustment(s): {', '.join(unknown)}")
    if not adjustments:
        raise argparse.ArgumentTypeError("at least one adjustment is required")
    return adjustments


def build_parser() -> argparse.ArgumentParser:
    today = date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent / "data")
    parser.add_argument("--index-symbol", default="000300", help="CSI index code; 000300 is CSI 300.")
    parser.add_argument("--years", type=int, default=10, help="Calendar years to download when --start-date is omitted.")
    parser.add_argument("--start-date", type=parse_date, default=None, help="YYYYMMDD or YYYY-MM-DD.")
    parser.add_argument("--end-date", type=parse_date, default=today, help="YYYYMMDD or YYYY-MM-DD.")
    parser.add_argument("--adjustments", type=parse_adjustments, default=("unadjusted", "qfq"))
    parser.add_argument(
        "--provider",
        choices=("auto", *PROVIDERS),
        default="stock_zh_a_daily",
        help="AKShare daily provider. auto tries stock_zh_a_hist, then stock_zh_a_daily.",
    )
    parser.add_argument(
        "--qfq-mode",
        choices=("factor", "direct"),
        default="factor",
        help="Build qfq from unadjusted bars plus qfq-factor, or use direct adjusted bars.",
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--force", action="store_true", help="Redownload raw files even if present.")
    parser.add_argument("--allow-partial", action="store_true", help="Write successful symbols even when some fail.")
    parser.add_argument("--no-csv", action="store_true", help="Skip canonical CSV output.")
    parser.add_argument("--no-parquet", action="store_true", help="Skip canonical Parquet output.")
    parser.add_argument("--symbol-limit", type=int, default=None, help="Debug only: limit number of constituents.")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress logs on stderr.")
    return parser


def config_from_args(args: argparse.Namespace) -> DownloadConfig:
    end_date = args.end_date
    start_date = args.start_date or subtract_years(end_date, args.years)
    if start_date > end_date:
        raise SystemExit("--start-date cannot be after --end-date")
    if args.no_csv and args.no_parquet:
        raise SystemExit("At least one canonical output format must be enabled.")
    return DownloadConfig(
        root=args.root,
        index_symbol=args.index_symbol,
        start_date=compact_date(start_date),
        end_date=compact_date(end_date),
        adjustments=args.adjustments,
        provider=args.provider,
        qfq_mode=args.qfq_mode,
        sleep_seconds=args.sleep_seconds,
        retries=args.retries,
        force=args.force,
        allow_partial=args.allow_partial,
        write_csv=not args.no_csv,
        write_parquet=not args.no_parquet,
        symbol_limit=args.symbol_limit,
        quiet=args.quiet,
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
