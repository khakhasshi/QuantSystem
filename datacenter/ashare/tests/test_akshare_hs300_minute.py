from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

import akshare_hs300_minute as minute  # noqa: E402


def test_normalize_minute_raw_maps_schema():
    raw = pd.DataFrame(
        {
            "day": ["2026-08-27 09:31:00"],
            "open": ["11.10"],
            "high": ["11.12"],
            "low": ["11.09"],
            "close": ["11.11"],
            "volume": ["1000"],
            "amount": ["11110.0"],
        }
    )

    normalized = minute.normalize_minute_raw(raw, "000001", "unadjusted", "akshare.stock_zh_a_minute")

    assert normalized.columns.tolist() == minute.MINUTE_CANONICAL_COLUMNS
    assert normalized.loc[0, "timestamp"] == "2026-08-27 09:31:00"
    assert normalized.loc[0, "trade_date"] == "2026-08-27"
    assert normalized.loc[0, "symbol"] == "000001.SZ"
    assert normalized.loc[0, "volume"] == 1000


def test_rebuild_qfq_minute_from_unadjusted_uses_factor_by_trade_date():
    raw = pd.DataFrame(
        {
            "day": ["2026-08-27 09:31:00", "2026-08-27 09:32:00"],
            "open": [10.0, 10.2],
            "high": [10.2, 10.3],
            "low": [9.9, 10.1],
            "close": [10.1, 10.2],
            "volume": [1000, 2000],
            "amount": [10000.0, 20400.0],
        }
    )
    factors = pd.DataFrame({"date": ["1900-01-01", "2026-08-01"], "qfq_factor": [3.0, 2.0]})

    rebuilt = minute.rebuild_qfq_minute_from_unadjusted(raw, factors, "600000")

    assert rebuilt["timestamp"].tolist() == ["2026-08-27 09:31:00", "2026-08-27 09:32:00"]
    assert rebuilt["symbol"].tolist() == ["600000.SH", "600000.SH"]
    assert rebuilt["open"].tolist() == [5.0, 5.1]
    assert rebuilt["close"].tolist() == [5.05, 5.1]
    assert rebuilt["source"].tolist() == [
        "akshare.stock_zh_a_minute+qfq_factor",
        "akshare.stock_zh_a_minute+qfq_factor",
    ]


def test_filter_requested_window():
    raw = pd.DataFrame(
        {
            "timestamp": [
                "2026-08-27 09:30:00",
                "2026-08-27 09:31:00",
                "2026-08-27 09:32:00",
            ],
            "trade_date": ["2026-08-27"] * 3,
            "symbol": ["000001.SZ"] * 3,
            "ticker": ["000001"] * 3,
            "exchange": ["SZ"] * 3,
            "open": [1.0, 1.0, 1.0],
            "high": [1.0, 1.0, 1.0],
            "low": [1.0, 1.0, 1.0],
            "close": [1.0, 1.0, 1.0],
            "volume": [1, 1, 1],
            "amount": [1, 1, 1],
            "adjustment": ["unadjusted"] * 3,
            "source": ["test"] * 3,
        }
    )

    filtered = minute.filter_requested_window(raw, "2026-08-27 09:31:00", "2026-08-27 09:32:00")

    assert filtered["timestamp"].tolist() == ["2026-08-27 09:31:00", "2026-08-27 09:32:00"]

