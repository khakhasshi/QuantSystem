from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

import duckdb_market_store as store  # noqa: E402


def write_parquet(path: Path, sql: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    con.execute(f"COPY ({sql}) TO '{path}' (FORMAT PARQUET)")


def make_config(tmp_path: Path, ashare_root: Path, usstock_root: Path) -> store.StoreConfig:
    config_path = tmp_path / "config.json"
    payload = {
        "database_path": "data/test.duckdb",
        "audit_dir": "data/audit",
        "staging_dir": "staging",
        "markets": {
            "ashare": {
                "dataset": "hs300_daily",
                "timezone": "Asia/Shanghai",
                "update_after_local": "17:30",
                "download_python": sys.executable,
                "download_script": "dummy.py",
                "download_args": [],
                "sources": {
                    "unadjusted": str(ashare_root / "canonical/daily/adjustment=unadjusted/daily.parquet"),
                    "qfq": str(ashare_root / "canonical/daily/adjustment=qfq/daily.parquet"),
                },
            },
            "usstock": {
                "dataset": "sp500_daily",
                "timezone": "America/New_York",
                "update_after_local": "17:30",
                "download_python": sys.executable,
                "download_script": "dummy.py",
                "download_args": [],
                "sources": {
                    "unadjusted": str(usstock_root / "canonical/daily/adjustment=unadjusted/daily.parquet"),
                    "qfq": str(usstock_root / "canonical/daily/adjustment=qfq/daily.parquet"),
                },
            },
        },
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    return store.load_config(config_path)


def test_full_reload_loads_four_canonical_parquets(tmp_path):
    ashare_root = tmp_path / "ashare"
    usstock_root = tmp_path / "usstock"
    for adj, close in [("unadjusted", 10.0), ("qfq", 9.5)]:
        write_parquet(
            ashare_root / f"canonical/daily/adjustment={adj}/daily.parquet",
            f"""
            SELECT
              '2024-01-02' AS trade_date, '000001.SZ' AS symbol, '000001' AS ticker, 'SZ' AS exchange,
              9.0 AS open, 11.0 AS high, 8.0 AS low, {close} AS close, 1000.0 AS volume,
              10000.0 AS amount, NULL::DOUBLE AS amplitude, NULL::DOUBLE AS pct_change,
              NULL::DOUBLE AS change, NULL::DOUBLE AS turnover, '{adj}' AS adjustment,
              'akshare.test' AS source
            """,
        )
        write_parquet(
            usstock_root / f"canonical/daily/adjustment={adj}/daily.parquet",
            f"""
            SELECT
              '2024-01-02' AS trade_date, 'AAPL.US' AS symbol, 'AAPL' AS ticker, 'AAPL' AS yahoo_symbol,
              'US' AS exchange, 190.0 AS open, 191.0 AS high, 189.0 AS low, {close + 180} AS close,
              {close + 180} AS adj_close, 2000::BIGINT AS volume, 0.0 AS dividends,
              0.0 AS stock_splits, '{adj}' AS adjustment, 'yfinance.test' AS source
            """,
        )

    config = make_config(tmp_path, ashare_root, usstock_root)
    results = store.full_reload(config, store.MARKETS)

    assert [item["status"] for item in results] == ["ok", "ok", "ok", "ok"]
    summary = store.summarize(config)
    assert {(row["market"], row["adjustment"], row["rows"]) for row in summary} == {
        ("ashare", "qfq", 1),
        ("ashare", "unadjusted", 1),
        ("usstock", "qfq", 1),
        ("usstock", "unadjusted", 1),
    }


def test_incremental_merge_replaces_existing_symbol_date(tmp_path):
    ashare_root = tmp_path / "ashare"
    usstock_root = tmp_path / "usstock"
    for adj in store.ADJUSTMENTS:
        write_parquet(
            ashare_root / f"canonical/daily/adjustment={adj}/daily.parquet",
            f"""
            SELECT '2024-01-02' AS trade_date, '000001.SZ' AS symbol, '000001' AS ticker, 'SZ' AS exchange,
              1.0 AS open, 1.0 AS high, 1.0 AS low, 1.0 AS close, 10.0 AS volume, 10.0 AS amount,
              NULL::DOUBLE AS amplitude, NULL::DOUBLE AS pct_change, NULL::DOUBLE AS change,
              NULL::DOUBLE AS turnover, '{adj}' AS adjustment, 'akshare.test' AS source
            """,
        )
        write_parquet(
            usstock_root / f"canonical/daily/adjustment={adj}/daily.parquet",
            f"""
            SELECT '2024-01-02' AS trade_date, 'AAPL.US' AS symbol, 'AAPL' AS ticker, 'AAPL' AS yahoo_symbol,
              'US' AS exchange, 1.0 AS open, 1.0 AS high, 1.0 AS low, 1.0 AS close,
              1.0 AS adj_close, 10::BIGINT AS volume, 0.0 AS dividends, 0.0 AS stock_splits,
              '{adj}' AS adjustment, 'yfinance.test' AS source
            """,
        )
    config = make_config(tmp_path, ashare_root, usstock_root)
    store.full_reload(config, ("ashare",))

    staging = tmp_path / "staging_ashare"
    for adj in store.ADJUSTMENTS:
        write_parquet(
            staging / f"canonical/daily/adjustment={adj}/daily.parquet",
            f"""
            SELECT * FROM (
              SELECT '2024-01-02' AS trade_date, '000001.SZ' AS symbol, '000001' AS ticker, 'SZ' AS exchange,
                2.0 AS open, 2.0 AS high, 2.0 AS low, 2.0 AS close, 20.0 AS volume, 20.0 AS amount,
                NULL::DOUBLE AS amplitude, NULL::DOUBLE AS pct_change, NULL::DOUBLE AS change,
                NULL::DOUBLE AS turnover, '{adj}' AS adjustment, 'akshare.test' AS source
              UNION ALL
              SELECT '2024-01-03', '000001.SZ', '000001', 'SZ', 3.0, 3.0, 3.0, 3.0, 30.0, 30.0,
                NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE, '{adj}', 'akshare.test'
            )
            """,
        )

    store.merge_staging(config, "ashare", staging)

    with store.connect(config) as con:
        rows = con.execute(
            """
            SELECT trade_date, close
            FROM daily_bars
            WHERE market = 'ashare' AND adjustment = 'qfq'
            ORDER BY trade_date
            """
        ).fetchall()
    assert rows == [(store.date(2024, 1, 2), 2.0), (store.date(2024, 1, 3), 3.0)]


def test_downloader_command_uses_market_staging_root(tmp_path):
    config = make_config(tmp_path, tmp_path / "ashare", tmp_path / "usstock")
    command = store.downloader_command(
        config,
        "ashare",
        store.date(2024, 1, 3),
        store.date(2024, 1, 5),
        tmp_path / "staging",
    )

    assert "--root" in command
    assert str(tmp_path / "staging") in command
    assert "--start-date" in command
    assert "20240103" in command
    assert "--end-date" in command
    assert "20240105" in command
