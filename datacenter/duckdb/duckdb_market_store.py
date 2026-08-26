#!/usr/bin/env python3
"""DuckDB package and incremental updater for local A-share and US stock daily bars."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.json"
ADJUSTMENTS = ("unadjusted", "qfq")
MARKETS = ("ashare", "usstock")


DAILY_BARS_COLUMNS = [
    "market",
    "dataset",
    "adjustment",
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
    "adj_close",
    "amplitude",
    "pct_change",
    "change",
    "turnover",
    "dividends",
    "stock_splits",
    "yahoo_symbol",
    "source",
    "ingested_at",
]


@dataclass(frozen=True)
class StoreConfig:
    root: Path
    path: Path
    database_path: Path
    audit_dir: Path
    staging_dir: Path
    markets: dict[str, dict[str, Any]]


def require_duckdb():
    try:
        import duckdb
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: duckdb. Install with "
            "`python3 -m pip install -r datacenter/duckdb/requirements.txt`."
        ) from exc
    return duckdb


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> StoreConfig:
    path = path.resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    root = path.parent
    return StoreConfig(
        root=root,
        path=path,
        database_path=resolve_config_path(root, payload["database_path"]),
        audit_dir=resolve_config_path(root, payload.get("audit_dir", "data/audit")),
        staging_dir=resolve_config_path(root, payload.get("staging_dir", "staging")),
        markets=payload["markets"],
    )


def resolve_config_path(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (root / path).resolve()


def market_config(config: StoreConfig, market: str) -> dict[str, Any]:
    if market not in config.markets:
        raise SystemExit(f"Unknown market {market!r}; use one of {', '.join(sorted(config.markets))}.")
    return config.markets[market]


def connect(config: StoreConfig):
    duckdb = require_duckdb()
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(config.database_path))


def init_schema(con) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_bars (
            market VARCHAR NOT NULL,
            dataset VARCHAR NOT NULL,
            adjustment VARCHAR NOT NULL,
            trade_date DATE NOT NULL,
            symbol VARCHAR NOT NULL,
            ticker VARCHAR,
            exchange VARCHAR,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume DOUBLE,
            amount DOUBLE,
            adj_close DOUBLE,
            amplitude DOUBLE,
            pct_change DOUBLE,
            change DOUBLE,
            turnover DOUBLE,
            dividends DOUBLE,
            stock_splits DOUBLE,
            yahoo_symbol VARCHAR,
            source VARCHAR,
            ingested_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_runs (
            run_id VARCHAR NOT NULL,
            run_started TIMESTAMPTZ NOT NULL,
            run_finished TIMESTAMPTZ,
            mode VARCHAR NOT NULL,
            market VARCHAR,
            dataset VARCHAR,
            adjustment VARCHAR,
            source_path VARCHAR,
            start_date DATE,
            end_date DATE,
            rows_before BIGINT,
            rows_after BIGINT,
            status VARCHAR NOT NULL,
            message VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS downloader_runs (
            run_id VARCHAR NOT NULL,
            run_started TIMESTAMPTZ NOT NULL,
            run_finished TIMESTAMPTZ,
            market VARCHAR NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            staging_root VARCHAR NOT NULL,
            command VARCHAR NOT NULL,
            returncode INTEGER,
            status VARCHAR NOT NULL,
            stdout_path VARCHAR,
            stderr_path VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW v_daily_bars_summary AS
        SELECT
            market,
            dataset,
            adjustment,
            count(*) AS rows,
            count(DISTINCT symbol) AS symbols,
            min(trade_date) AS min_trade_date,
            max(trade_date) AS max_trade_date,
            sum(CASE WHEN open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL THEN 1 ELSE 0 END) AS ohlc_null_rows,
            count(*) - count(DISTINCT market || '|' || adjustment || '|' || symbol || '|' || trade_date::VARCHAR) AS duplicate_key_rows
        FROM daily_bars
        GROUP BY 1, 2, 3
        ORDER BY 1, 3
        """
    )
    con.execute("CREATE OR REPLACE VIEW v_ashare_daily AS SELECT * FROM daily_bars WHERE market = 'ashare'")
    con.execute("CREATE OR REPLACE VIEW v_usstock_daily AS SELECT * FROM daily_bars WHERE market = 'usstock'")


def relation_sql_for_parquet(path: Path, market: str, dataset: str, adjustment: str) -> str:
    path_sql = escape_sql_string(str(path))
    ingested_at = "current_timestamp"
    if market == "ashare":
        return f"""
            SELECT
                '{market}'::VARCHAR AS market,
                '{dataset}'::VARCHAR AS dataset,
                COALESCE(adjustment, '{adjustment}')::VARCHAR AS adjustment,
                trade_date::DATE AS trade_date,
                symbol::VARCHAR AS symbol,
                ticker::VARCHAR AS ticker,
                exchange::VARCHAR AS exchange,
                open::DOUBLE AS open,
                high::DOUBLE AS high,
                low::DOUBLE AS low,
                close::DOUBLE AS close,
                volume::DOUBLE AS volume,
                amount::DOUBLE AS amount,
                NULL::DOUBLE AS adj_close,
                amplitude::DOUBLE AS amplitude,
                pct_change::DOUBLE AS pct_change,
                change::DOUBLE AS change,
                turnover::DOUBLE AS turnover,
                NULL::DOUBLE AS dividends,
                NULL::DOUBLE AS stock_splits,
                NULL::VARCHAR AS yahoo_symbol,
                source::VARCHAR AS source,
                {ingested_at} AS ingested_at
            FROM read_parquet('{path_sql}')
            WHERE trade_date IS NOT NULL AND symbol IS NOT NULL
        """
    if market == "usstock":
        return f"""
            SELECT
                '{market}'::VARCHAR AS market,
                '{dataset}'::VARCHAR AS dataset,
                COALESCE(adjustment, '{adjustment}')::VARCHAR AS adjustment,
                trade_date::DATE AS trade_date,
                symbol::VARCHAR AS symbol,
                ticker::VARCHAR AS ticker,
                exchange::VARCHAR AS exchange,
                open::DOUBLE AS open,
                high::DOUBLE AS high,
                low::DOUBLE AS low,
                close::DOUBLE AS close,
                volume::DOUBLE AS volume,
                NULL::DOUBLE AS amount,
                adj_close::DOUBLE AS adj_close,
                NULL::DOUBLE AS amplitude,
                NULL::DOUBLE AS pct_change,
                NULL::DOUBLE AS change,
                NULL::DOUBLE AS turnover,
                dividends::DOUBLE AS dividends,
                stock_splits::DOUBLE AS stock_splits,
                yahoo_symbol::VARCHAR AS yahoo_symbol,
                source::VARCHAR AS source,
                {ingested_at} AS ingested_at
            FROM read_parquet('{path_sql}')
            WHERE trade_date IS NOT NULL AND symbol IS NOT NULL
        """
    raise ValueError(f"unsupported market: {market}")


def escape_sql_string(value: str) -> str:
    return value.replace("'", "''")


def source_path(config: StoreConfig, market: str, adjustment: str, root_override: Path | None = None) -> Path:
    cfg = market_config(config, market)
    if root_override is None:
        return resolve_config_path(config.root, cfg["sources"][adjustment])
    return root_override / "canonical" / "daily" / f"adjustment={adjustment}" / "daily.parquet"


def insert_ingest_run(
    con,
    *,
    run_id: str,
    mode: str,
    market: str,
    dataset: str,
    adjustment: str,
    path: Path,
    status: str,
    message: str | None = None,
    rows_before: int | None = None,
    rows_after: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    con.execute(
        """
        INSERT INTO ingest_runs
        VALUES (?, current_timestamp, current_timestamp, ?, ?, ?, ?, ?, ?::DATE, ?::DATE, ?, ?, ?, ?)
        """,
        [
            run_id,
            mode,
            market,
            dataset,
            adjustment,
            str(path),
            start_date,
            end_date,
            rows_before,
            rows_after,
            status,
            message,
        ],
    )


def load_parquet(
    con,
    config: StoreConfig,
    *,
    market: str,
    adjustment: str,
    path: Path,
    mode: str,
    replace_scope: bool,
) -> dict[str, Any]:
    cfg = market_config(config, market)
    dataset = cfg["dataset"]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if not path.exists():
        insert_ingest_run(
            con,
            run_id=run_id,
            mode=mode,
            market=market,
            dataset=dataset,
            adjustment=adjustment,
            path=path,
            status="missing",
            message="source parquet does not exist",
        )
        return {"market": market, "adjustment": adjustment, "status": "missing", "path": str(path)}

    relation_sql = relation_sql_for_parquet(path, market, dataset, adjustment)
    stats = con.execute(
        f"""
        SELECT count(*) AS rows, min(trade_date) AS start_date, max(trade_date) AS end_date
        FROM ({relation_sql})
        """
    ).fetchone()
    source_rows, start_date, end_date = stats
    if source_rows == 0:
        insert_ingest_run(
            con,
            run_id=run_id,
            mode=mode,
            market=market,
            dataset=dataset,
            adjustment=adjustment,
            path=path,
            status="empty",
            message="source parquet contains no rows",
        )
        return {"market": market, "adjustment": adjustment, "status": "empty", "path": str(path)}

    rows_before = con.execute(
        "SELECT count(*) FROM daily_bars WHERE market = ? AND adjustment = ?",
        [market, adjustment],
    ).fetchone()[0]
    con.execute("BEGIN TRANSACTION")
    try:
        if replace_scope:
            con.execute("DELETE FROM daily_bars WHERE market = ? AND adjustment = ?", [market, adjustment])
        else:
            con.execute(
                f"""
                DELETE FROM daily_bars AS existing
                USING ({relation_sql}) AS incoming
                WHERE existing.market = incoming.market
                  AND existing.adjustment = incoming.adjustment
                  AND existing.symbol = incoming.symbol
                  AND existing.trade_date = incoming.trade_date
                """
            )
        con.execute(f"INSERT INTO daily_bars ({', '.join(DAILY_BARS_COLUMNS)}) {relation_sql}")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    rows_after = con.execute(
        "SELECT count(*) FROM daily_bars WHERE market = ? AND adjustment = ?",
        [market, adjustment],
    ).fetchone()[0]
    insert_ingest_run(
        con,
        run_id=run_id,
        mode=mode,
        market=market,
        dataset=dataset,
        adjustment=adjustment,
        path=path,
        status="ok",
        rows_before=int(rows_before),
        rows_after=int(rows_after),
        start_date=str(start_date),
        end_date=str(end_date),
    )
    return {
        "market": market,
        "dataset": dataset,
        "adjustment": adjustment,
        "status": "ok",
        "source_rows": int(source_rows),
        "rows_before": int(rows_before),
        "rows_after": int(rows_after),
        "start_date": str(start_date),
        "end_date": str(end_date),
        "path": str(path),
    }


def full_reload(config: StoreConfig, markets: Sequence[str]) -> list[dict[str, Any]]:
    with connect(config) as con:
        init_schema(con)
        results = []
        for market in markets:
            for adjustment in ADJUSTMENTS:
                path = source_path(config, market, adjustment)
                results.append(
                    load_parquet(
                        con,
                        config,
                        market=market,
                        adjustment=adjustment,
                        path=path,
                        mode="full_reload",
                        replace_scope=True,
                    )
                )
        return results


def merge_staging(config: StoreConfig, market: str, staging_root: Path) -> list[dict[str, Any]]:
    with connect(config) as con:
        init_schema(con)
        return [
            load_parquet(
                con,
                config,
                market=market,
                adjustment=adjustment,
                path=source_path(config, market, adjustment, root_override=staging_root),
                mode="incremental_merge",
                replace_scope=False,
            )
            for adjustment in ADJUSTMENTS
        ]


def latest_trade_date(config: StoreConfig, market: str) -> date | None:
    with connect(config) as con:
        init_schema(con)
        row = con.execute(
            "SELECT max(trade_date) FROM daily_bars WHERE market = ?",
            [market],
        ).fetchone()
    value = row[0] if row else None
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def previous_weekday(value: date) -> date:
    current = value - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def last_closed_target_date(market: str, cfg: dict[str, Any], now_utc: datetime | None = None) -> date:
    now_utc = now_utc or datetime.now(timezone.utc)
    local_tz = ZoneInfo(cfg["timezone"])
    local_now = now_utc.astimezone(local_tz)
    cutoff = parse_hhmm(cfg["update_after_local"])
    candidate = local_now.date()
    if local_now.time() < cutoff or candidate.weekday() >= 5:
        candidate = previous_weekday(candidate)
    if market == "usstock":
        while candidate.weekday() >= 5:
            candidate = previous_weekday(candidate + timedelta(days=1))
    return candidate


def compact(value: date) -> str:
    return value.strftime("%Y%m%d")


def iso(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def downloader_command(
    config: StoreConfig,
    market: str,
    start_date: date,
    end_date: date,
    staging_root: Path,
) -> list[str]:
    cfg = market_config(config, market)
    python_path = resolve_config_path(config.root, cfg["download_python"])
    script_path = resolve_config_path(config.root, cfg["download_script"])
    command = [
        str(python_path),
        str(script_path),
        "--root",
        str(staging_root),
        "--start-date",
        compact(start_date),
        "--end-date",
        compact(end_date),
    ]
    if market == "usstock":
        command.extend(["--asof-date", compact(datetime.now().date())])
    command.extend(str(item) for item in cfg.get("download_args", []))
    return command


def run_downloader(
    config: StoreConfig,
    market: str,
    start_date: date,
    end_date: date,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    staging_root = config.staging_dir / market / f"{compact(start_date)}_{compact(end_date)}"
    command = downloader_command(config, market, start_date, end_date, staging_root)
    result = {
        "market": market,
        "start_date": iso(start_date),
        "end_date": iso(end_date),
        "staging_root": str(staging_root),
        "command": command,
    }
    if dry_run:
        result["status"] = "dry_run"
        return result

    config.audit_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = config.audit_dir / f"{run_id}_{market}_downloader.stdout.log"
    stderr_path = config.audit_dir / f"{run_id}_{market}_downloader.stderr.log"
    started = datetime.now(timezone.utc)
    completed = subprocess.run(command, cwd=config.root.parent.parent, text=True, capture_output=True, check=False)
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    status = "ok" if completed.returncode == 0 else "failed"

    with connect(config) as con:
        init_schema(con)
        con.execute(
            """
            INSERT INTO downloader_runs
            VALUES (?, ?, current_timestamp, ?, ?::DATE, ?::DATE, ?, ?, ?, ?, ?, ?)
            """,
            [
                run_id,
                started.isoformat(),
                market,
                iso(start_date),
                iso(end_date),
                str(staging_root),
                " ".join(command),
                completed.returncode,
                status,
                str(stdout_path),
                str(stderr_path),
            ],
        )

    if completed.returncode != 0:
        raise RuntimeError(
            f"{market} downloader failed with return code {completed.returncode}; "
            f"stderr saved to {stderr_path}"
        )
    result.update({"status": status, "stdout_path": str(stdout_path), "stderr_path": str(stderr_path)})
    result["merge"] = merge_staging(config, market, staging_root)
    return result


def incremental_update(
    config: StoreConfig,
    markets: Sequence[str],
    *,
    now_utc: datetime | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    results = []
    for market in markets:
        cfg = market_config(config, market)
        latest = latest_trade_date(config, market)
        target = last_closed_target_date(market, cfg, now_utc)
        if latest is None:
            results.append(
                {
                    "market": market,
                    "status": "needs_full_reload",
                    "message": "daily_bars has no rows for this market; run full-reload first",
                    "target_end_date": iso(target),
                }
            )
            continue
        start = latest + timedelta(days=1)
        if start > target:
            results.append(
                {
                    "market": market,
                    "status": "up_to_date",
                    "latest_trade_date": iso(latest),
                    "target_end_date": iso(target),
                }
            )
            continue
        results.append(run_downloader(config, market, start, target, dry_run=dry_run))
    return results


def summarize(config: StoreConfig) -> list[dict[str, Any]]:
    with connect(config) as con:
        init_schema(con)
        rows = con.execute("SELECT * FROM v_daily_bars_summary").fetchall()
        columns = [desc[0] for desc in con.description]
    return [dict(zip(columns, row)) for row in rows]


def parse_markets(value: str) -> tuple[str, ...]:
    if value == "all":
        return MARKETS
    markets = tuple(item.strip() for item in value.split(",") if item.strip())
    unknown = sorted(set(markets) - set(MARKETS))
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown market(s): {', '.join(unknown)}")
    return markets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create DuckDB schema.")
    init_parser.set_defaults(func=cmd_init)

    reload_parser = subparsers.add_parser("full-reload", help="Reload existing canonical Parquet files into DuckDB.")
    reload_parser.add_argument("--markets", type=parse_markets, default=MARKETS)
    reload_parser.set_defaults(func=cmd_full_reload)

    update_parser = subparsers.add_parser("incremental", help="Run downloader increments and merge them into DuckDB.")
    update_parser.add_argument("--markets", type=parse_markets, default=MARKETS)
    update_parser.add_argument("--dry-run", action="store_true")
    update_parser.set_defaults(func=cmd_incremental)

    summary_parser = subparsers.add_parser("summary", help="Print DuckDB row/date coverage.")
    summary_parser.set_defaults(func=cmd_summary)

    command_parser = subparsers.add_parser("print-launchd-command", help="Print the command used by launchd.")
    command_parser.set_defaults(func=cmd_print_launchd_command)
    return parser


def cmd_init(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    with connect(config) as con:
        init_schema(con)
    print(json.dumps({"database_path": str(config.database_path), "status": "ok"}, ensure_ascii=False, indent=2))
    return 0


def cmd_full_reload(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    results = full_reload(config, args.markets)
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_incremental(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    results = incremental_update(config, args.markets, dry_run=args.dry_run)
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    failed = [item for item in results if item.get("status") == "failed"]
    return 1 if failed else 0


def cmd_summary(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print(json.dumps(summarize(config), ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_print_launchd_command(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    command = [sys.executable, str(Path(__file__).resolve()), "--config", str(config.path), "incremental"]
    print(" ".join(command))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
