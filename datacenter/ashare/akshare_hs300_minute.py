#!/usr/bin/env python3
"""Download current CSI 300 1-minute bars from AKShare.

AKShare's freely available A-share 1-minute providers do not expose ten years of
minute history in this environment. This downloader still records the requested
window, saves the raw per-symbol minute files that the provider can return, and
builds canonical unadjusted and qfq minute datasets with an explicit coverage
manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

from akshare_hs300_daily import (
    ADJUSTMENT_TO_AKSHARE,
    akshare_market_symbol,
    canonical_symbol,
    extract_constituent_tickers,
    fetch_constituents,
    fetch_qfq_factor,
    infer_exchange,
    normalize_qfq_factor,
    normalize_ticker,
    require_akshare,
    require_pandas,
    safe_symbol_path,
    subtract_years,
    write_dataframe_csv,
    write_dataframe_parquet,
    write_json,
)


MINUTE_CANONICAL_COLUMNS = [
    "timestamp",
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
    "adjustment",
    "source",
]

MINUTE_NUMERIC_COLUMNS = ["open", "high", "low", "close", "volume", "amount"]

MINUTE_COLUMN_ALIASES = {
    "timestamp": ("day", "时间", "timestamp", "datetime"),
    "open": ("open", "开盘"),
    "high": ("high", "最高"),
    "low": ("low", "最低"),
    "close": ("close", "收盘"),
    "volume": ("volume", "成交量"),
    "amount": ("amount", "成交额"),
}


@dataclass(frozen=True)
class MinuteDownloadConfig:
    root: Path
    index_symbol: str
    start_datetime: str
    end_datetime: str
    adjustments: tuple[str, ...]
    provider: str
    qfq_mode: str
    period: str
    sleep_seconds: float
    retries: int
    force: bool
    allow_partial: bool
    write_csv: bool
    write_parquet: bool
    symbol_limit: int | None
    quiet: bool


def log(message: str, quiet: bool = False) -> None:
    if not quiet:
        print(message, file=sys.stderr, flush=True)


def parse_datetime(value: str) -> datetime:
    clean = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d"):
        try:
            parsed = datetime.strptime(clean, fmt)
            if fmt in ("%Y-%m-%d", "%Y%m%d"):
                return parsed.replace(hour=0, minute=0, second=0)
            return parsed
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(
        f"invalid datetime {value!r}; use YYYY-MM-DD HH:MM:SS or YYYYMMDD HH:MM:SS"
    )


def format_akshare_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def datetime_partition(value: str) -> str:
    return value.replace("-", "").replace(":", "").replace(" ", "T")


def first_existing(columns, aliases: Sequence[str]) -> str | None:
    existing = set(columns)
    for alias in aliases:
        if alias in existing:
            return alias
    return None


def fetch_with_retries(label: str, retries: int, sleep_seconds: float, fn):
    last_exc: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - downloader records provider failures.
            last_exc = exc
            if attempt > retries:
                break
            time.sleep(max(sleep_seconds, 0.0) * attempt)
    raise RuntimeError(f"{label} failed after {retries + 1} attempt(s): {last_exc}") from last_exc


def fetch_minute_raw(ticker: str, period: str):
    ak = require_akshare()
    return ak.stock_zh_a_minute(symbol=akshare_market_symbol(normalize_ticker(ticker)), period=period, adjust="")


def normalize_minute_raw(raw_df, ticker: str, adjustment: str, source: str):
    pd = require_pandas()
    if adjustment not in ADJUSTMENT_TO_AKSHARE:
        raise ValueError(f"unsupported adjustment: {adjustment}")

    rename_map: dict[str, str] = {}
    for canonical, aliases in MINUTE_COLUMN_ALIASES.items():
        source_col = first_existing(raw_df.columns, aliases)
        if source_col is not None:
            rename_map[source_col] = canonical

    normalized = raw_df.rename(columns=rename_map).copy()
    if "timestamp" not in normalized.columns:
        raise ValueError(f"missing minute timestamp column for {ticker}: {list(raw_df.columns)!r}")

    normalized["timestamp_dt"] = pd.to_datetime(normalized["timestamp"], errors="coerce")
    normalized["timestamp"] = normalized["timestamp_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
    normalized["trade_date"] = normalized["timestamp_dt"].dt.strftime("%Y-%m-%d")
    normalized["ticker"] = normalize_ticker(ticker)
    normalized["exchange"] = infer_exchange(normalized["ticker"].iloc[0])
    normalized["symbol"] = canonical_symbol(normalized["ticker"].iloc[0])
    normalized["adjustment"] = adjustment
    normalized["source"] = source

    for col in MINUTE_NUMERIC_COLUMNS:
        if col not in normalized.columns:
            normalized[col] = pd.NA
        normalized[col] = pd.to_numeric(normalized[col], errors="coerce")

    normalized = normalized[MINUTE_CANONICAL_COLUMNS]
    for col in ("timestamp", "trade_date", "symbol", "ticker", "exchange", "adjustment", "source"):
        normalized[col] = normalized[col].astype("string")
    normalized = normalized.dropna(subset=["timestamp", "open", "high", "low", "close"])
    normalized = normalized.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    return normalized


def rebuild_qfq_minute_from_unadjusted(raw_minute_df, factor_df, ticker: str):
    pd = require_pandas()
    base = normalize_minute_raw(
        raw_minute_df,
        ticker,
        "unadjusted",
        source="akshare.stock_zh_a_minute",
    )
    factors = normalize_qfq_factor(factor_df)
    base = base.copy()
    base["timestamp_dt"] = pd.to_datetime(base["timestamp"], errors="coerce")
    base["trade_dt"] = pd.to_datetime(base["trade_date"], errors="coerce")
    base = base.dropna(subset=["timestamp_dt", "trade_dt"]).sort_values("trade_dt")

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
        merged[col] = (merged[col] / merged["qfq_factor"]).round(6)
    merged["adjustment"] = "qfq"
    merged["source"] = "akshare.stock_zh_a_minute+qfq_factor"
    for col in ("timestamp", "trade_date", "symbol", "ticker", "exchange", "adjustment", "source"):
        merged[col] = merged[col].astype("string")
    return merged[MINUTE_CANONICAL_COLUMNS].sort_values(["symbol", "timestamp"]).reset_index(drop=True)


def filter_requested_window(df, start_datetime: str, end_datetime: str):
    pd = require_pandas()
    if df.empty:
        return df
    timestamps = pd.to_datetime(df["timestamp"], errors="coerce")
    mask = timestamps.between(pd.Timestamp(start_datetime), pd.Timestamp(end_datetime), inclusive="both")
    return df.loc[mask].reset_index(drop=True)


def minute_raw_path(config: MinuteDownloadConfig, adjustment: str, symbol: str) -> Path:
    return (
        config.root
        / "raw"
        / "akshare"
        / config.provider
        / f"period={config.period}"
        / f"adjustment={adjustment}"
        / f"start={datetime_partition(config.start_datetime)}"
        / f"end={datetime_partition(config.end_datetime)}"
        / f"symbol={symbol}"
        / f"{safe_symbol_path(symbol)}.csv"
    )


def read_or_fetch_minute_raw(config: MinuteDownloadConfig, ticker: str):
    pd = require_pandas()
    symbol = canonical_symbol(ticker)
    raw_path = minute_raw_path(config, "unadjusted", symbol)
    source_path = raw_path.with_suffix(".source.json")
    if raw_path.exists() and not config.force:
        return pd.read_csv(raw_path)

    raw_df = fetch_minute_raw(ticker, config.period)
    write_dataframe_csv(raw_df, raw_path)
    write_json(
        source_path,
        {
            "source": "akshare.stock_zh_a_minute",
            "provider_limit": "Sina CN_MarketDataService.getKLineData returns a recent fixed-length window.",
            "configured_provider": config.provider,
            "period": config.period,
            "ticker": normalize_ticker(ticker),
            "symbol": symbol,
            "adjustment": "unadjusted",
            "requested_start_datetime": config.start_datetime,
            "requested_end_datetime": config.end_datetime,
        },
    )
    time.sleep(max(config.sleep_seconds, 0.0))
    return raw_df


def qfq_factor_raw_path(config: MinuteDownloadConfig, symbol: str) -> Path:
    return (
        config.root
        / "raw"
        / "akshare"
        / "stock_zh_a_daily"
        / "adjustment=qfq-factor"
        / f"asof={date.today().strftime('%Y%m%d')}"
        / f"symbol={symbol}"
        / f"{safe_symbol_path(symbol)}.csv"
    )


def read_or_fetch_qfq_factor(config: MinuteDownloadConfig, ticker: str):
    pd = require_pandas()
    symbol = canonical_symbol(ticker)
    raw_path = qfq_factor_raw_path(config, symbol)
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
            "ticker": normalize_ticker(ticker),
            "symbol": symbol,
            "adjustment": "qfq-factor",
            "asof_date": date.today().strftime("%Y-%m-%d"),
        },
    )
    time.sleep(max(config.sleep_seconds, 0.0))
    return factor_df


def write_minute_outputs(root: Path, period: str, adjustment: str, df, write_csv: bool, write_parquet: bool) -> dict:
    output_dir = root / "canonical" / "minute" / f"period={period}" / f"adjustment={adjustment}"
    outputs: dict[str, str] = {}
    if write_csv:
        csv_path = output_dir / "minute.csv"
        write_dataframe_csv(df, csv_path)
        outputs["csv"] = str(csv_path)
    if write_parquet:
        parquet_path = output_dir / "minute.parquet"
        write_dataframe_parquet(df, parquet_path)
        outputs["parquet"] = str(parquet_path)
    return outputs


def minute_quality_summary(df, expected_tickers: Sequence[str], failures: dict[str, str], config: MinuteDownloadConfig) -> dict:
    if df.empty:
        return {
            "rows": 0,
            "symbols_with_rows": 0,
            "expected_symbols": len(expected_tickers),
            "empty_symbols": [canonical_symbol(ticker) for ticker in expected_tickers],
            "failed_symbols": sorted(failures),
            "failure_details": failures,
            "requested_start_datetime": config.start_datetime,
            "requested_end_datetime": config.end_datetime,
            "actual_min_timestamp": None,
            "actual_max_timestamp": None,
            "duplicate_symbol_timestamp_rows": 0,
            "provider_covered_requested_start": False,
        }

    expected_symbols = {canonical_symbol(ticker) for ticker in expected_tickers}
    observed_symbols = set(df["symbol"].dropna().unique().tolist())
    duplicates = int(df.duplicated(["symbol", "timestamp"]).sum())
    actual_min = str(df["timestamp"].min())
    actual_max = str(df["timestamp"].max())
    source_counts = {
        str(source): int(count)
        for source, count in df.groupby("source", dropna=False).size().sort_index().items()
    }
    return {
        "rows": int(len(df)),
        "symbols_with_rows": int(len(observed_symbols)),
        "expected_symbols": len(expected_symbols),
        "empty_symbols": sorted(expected_symbols - observed_symbols),
        "failed_symbols": sorted(failures),
        "failure_details": failures,
        "requested_start_datetime": config.start_datetime,
        "requested_end_datetime": config.end_datetime,
        "actual_min_timestamp": actual_min,
        "actual_max_timestamp": actual_max,
        "duplicate_symbol_timestamp_rows": duplicates,
        "provider_covered_requested_start": actual_min <= config.start_datetime,
        "source_counts": source_counts,
    }


def parse_adjustments(value: str) -> tuple[str, ...]:
    adjustments = tuple(item.strip() for item in value.split(",") if item.strip())
    unknown = sorted(set(adjustments) - {"unadjusted", "qfq"})
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown adjustment(s): {', '.join(unknown)}")
    if not adjustments:
        raise argparse.ArgumentTypeError("at least one adjustment is required")
    return adjustments


def run_download(config: MinuteDownloadConfig) -> dict:
    pd = require_pandas()
    manifest_dir = config.root / "manifests"
    run_started = datetime.now().astimezone().isoformat(timespec="seconds")

    log(f"[constituents] fetching CSI index {config.index_symbol}", config.quiet)
    constituents_raw = fetch_with_retries(
        f"index constituents {config.index_symbol}",
        config.retries,
        config.sleep_seconds,
        lambda: fetch_constituents(config.index_symbol),
    )
    constituent_asof = config.end_datetime[:10].replace("-", "")
    raw_index_dir = (
        config.root
        / "raw"
        / "akshare"
        / "index_stock_cons_csindex"
        / f"index={config.index_symbol}"
        / f"asof={constituent_asof}"
    )
    write_dataframe_csv(constituents_raw, raw_index_dir / "constituents.csv")

    tickers = extract_constituent_tickers(constituents_raw)
    if config.symbol_limit is not None:
        tickers = tickers[: config.symbol_limit]
    log(
        f"[constituents] {len(tickers)} symbol(s), minute window={config.start_datetime}..{config.end_datetime}",
        config.quiet,
    )

    metadata = pd.DataFrame(
        {
            "ticker": tickers,
            "exchange": [infer_exchange(ticker) for ticker in tickers],
            "symbol": [canonical_symbol(ticker) for ticker in tickers],
            "index_symbol": config.index_symbol,
            "asof_datetime": config.end_datetime,
            "source": "akshare.index_stock_cons_csindex",
        }
    )
    write_dataframe_csv(metadata, config.root / "metadata" / f"hs300_constituents_asof_{constituent_asof}.csv")

    adjustment_results: dict[str, dict] = {}
    raw_minute_cache = {}
    for adjustment in config.adjustments:
        log(f"[{adjustment}] start", config.quiet)
        frames = []
        failures: dict[str, str] = {}
        for idx, ticker in enumerate(tickers, start=1):
            symbol = canonical_symbol(ticker)
            if idx == 1 or idx % 10 == 0 or idx == len(tickers):
                log(f"[{adjustment}] {idx}/{len(tickers)} {symbol}", config.quiet)
            try:
                if ticker in raw_minute_cache:
                    raw_minute = raw_minute_cache[ticker]
                else:
                    raw_minute = fetch_with_retries(
                        f"1min raw {ticker} ({idx}/{len(tickers)})",
                        config.retries,
                        config.sleep_seconds,
                        lambda ticker=ticker: read_or_fetch_minute_raw(config, ticker),
                    )
                    raw_minute_cache[ticker] = raw_minute
                if adjustment == "unadjusted":
                    canonical_df = normalize_minute_raw(raw_minute, ticker, "unadjusted", "akshare.stock_zh_a_minute")
                else:
                    if config.qfq_mode != "factor":
                        raise ValueError("only qfq_mode=factor is supported for minute qfq")
                    factor_df = fetch_with_retries(
                        f"qfq factor {ticker} ({idx}/{len(tickers)})",
                        config.retries,
                        config.sleep_seconds,
                        lambda ticker=ticker: read_or_fetch_qfq_factor(config, ticker),
                    )
                    canonical_df = rebuild_qfq_minute_from_unadjusted(raw_minute, factor_df, ticker)
                canonical_df = filter_requested_window(canonical_df, config.start_datetime, config.end_datetime)
                if not canonical_df.empty:
                    frames.append(canonical_df)
            except Exception as exc:  # noqa: BLE001 - keep other symbols when allowed.
                failures[ticker] = str(exc)
                log(f"[{adjustment}] failed {symbol}: {exc}", config.quiet)
                if not config.allow_partial:
                    raise

        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=MINUTE_CANONICAL_COLUMNS)
        combined = combined.drop_duplicates(["symbol", "timestamp"], keep="last")
        combined = combined.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

        outputs = write_minute_outputs(config.root, config.period, adjustment, combined, config.write_csv, config.write_parquet)
        summary = minute_quality_summary(combined, tickers, failures, config)
        summary["outputs"] = outputs
        adjustment_results[adjustment] = summary
        write_json(
            manifest_dir / f"hs300_minute_{config.period}m_{adjustment}_{constituent_asof}.manifest.json",
            summary,
        )
        log(
            f"[{adjustment}] done rows={summary['rows']} symbols={summary['symbols_with_rows']}/"
            f"{summary['expected_symbols']} failures={len(summary['failed_symbols'])} "
            f"actual={summary['actual_min_timestamp']}..{summary['actual_max_timestamp']}",
            config.quiet,
        )

    manifest = {
        "dataset": f"hs300_minute_{config.period}m",
        "run_started": run_started,
        "run_finished": datetime.now().astimezone().isoformat(timespec="seconds"),
        "provider_limit": (
            "AKShare stock_zh_a_minute/Sina returned a recent fixed-length window, "
            "not the full requested ten-year range."
        ),
        "config": {
            **asdict(config),
            "root": str(config.root),
            "adjustments": list(config.adjustments),
        },
        "constituents": {
            "raw_csv": str(raw_index_dir / "constituents.csv"),
            "metadata_csv": str(config.root / "metadata" / f"hs300_constituents_asof_{constituent_asof}.csv"),
            "count": len(tickers),
        },
        "adjustments": adjustment_results,
    }
    write_json(manifest_dir / f"hs300_minute_{config.period}m_run_{constituent_asof}.manifest.json", manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    today = date.today()
    end_dt = datetime.combine(today, datetime.strptime("15:00:00", "%H:%M:%S").time())
    start_dt = datetime.combine(subtract_years(today, 10), datetime.strptime("09:30:00", "%H:%M:%S").time())

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent / "data")
    parser.add_argument("--index-symbol", default="000300", help="CSI index code; 000300 is CSI 300.")
    parser.add_argument("--start-datetime", type=parse_datetime, default=start_dt)
    parser.add_argument("--end-datetime", type=parse_datetime, default=end_dt)
    parser.add_argument("--adjustments", type=parse_adjustments, default=("unadjusted", "qfq"))
    parser.add_argument("--provider", choices=("stock_zh_a_minute",), default="stock_zh_a_minute")
    parser.add_argument("--qfq-mode", choices=("factor",), default="factor")
    parser.add_argument("--period", choices=("1",), default="1")
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--no-csv", action="store_true")
    parser.add_argument("--no-parquet", action="store_true")
    parser.add_argument("--symbol-limit", type=int, default=None, help="Debug only: limit number of constituents.")
    parser.add_argument("--quiet", action="store_true")
    return parser


def config_from_args(args: argparse.Namespace) -> MinuteDownloadConfig:
    start_datetime = args.start_datetime
    end_datetime = args.end_datetime
    if start_datetime > end_datetime:
        raise SystemExit("--start-datetime cannot be after --end-datetime")
    if args.no_csv and args.no_parquet:
        raise SystemExit("At least one canonical output format must be enabled.")
    return MinuteDownloadConfig(
        root=args.root,
        index_symbol=args.index_symbol,
        start_datetime=format_akshare_datetime(start_datetime),
        end_datetime=format_akshare_datetime(end_datetime),
        adjustments=args.adjustments,
        provider=args.provider,
        qfq_mode=args.qfq_mode,
        period=args.period,
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
    config = config_from_args(parser.parse_args(argv))
    manifest = run_download(config)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
