from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

import akshare_hs300_daily as hs300  # noqa: E402


def test_extract_constituent_tickers_deduplicates_and_normalizes():
    frame = pd.DataFrame({"成分券代码": ["1", "000001.SZ", "600000", "600000.SH"]})

    assert hs300.extract_constituent_tickers(frame) == ["000001", "600000"]


def test_normalize_akshare_hist_maps_schema_and_volume_to_shares():
    raw = pd.DataFrame(
        {
            "日期": ["2024-01-02", "2024-01-03"],
            "股票代码": ["000001", "000001"],
            "开盘": [10.0, 10.5],
            "收盘": [10.4, 10.1],
            "最高": [10.8, 10.6],
            "最低": [9.9, 10.0],
            "成交量": [123, 456],
            "成交额": [123000.0, 456000.0],
            "振幅": [1.1, 1.2],
            "涨跌幅": [0.5, -0.2],
            "涨跌额": [0.04, -0.03],
            "换手率": [0.8, 0.9],
        }
    )

    normalized = hs300.normalize_akshare_hist(raw, "000001", "qfq")

    assert normalized.columns.tolist() == hs300.CANONICAL_COLUMNS
    assert normalized["symbol"].tolist() == ["000001.SZ", "000001.SZ"]
    assert normalized["trade_date"].tolist() == ["2024-01-02", "2024-01-03"]
    assert normalized["volume"].tolist() == [12300, 45600]
    assert normalized["adjustment"].tolist() == ["qfq", "qfq"]


def test_normalize_akshare_daily_keeps_share_volume_and_turnover_percent():
    raw = pd.DataFrame(
        {
            "date": ["2024-01-02"],
            "open": [9.39],
            "high": [9.42],
            "low": [9.21],
            "close": [9.21],
            "volume": [115836645],
            "amount": [1075742252.0],
            "turnover": [0.005969],
        }
    )

    normalized = hs300.normalize_akshare_hist(
        raw,
        "000001",
        "unadjusted",
        source="akshare.stock_zh_a_daily",
    )

    assert normalized.loc[0, "volume"] == 115836645
    assert round(normalized.loc[0, "turnover"], 6) == 0.5969
    assert normalized.loc[0, "source"] == "akshare.stock_zh_a_daily"


def test_rebuild_qfq_from_unadjusted_aligns_to_raw_trade_dates():
    raw = pd.DataFrame(
        {
            "date": ["2016-09-12", "2016-10-10"],
            "open": [26.60, 25.98],
            "high": [28.27, 26.31],
            "low": [26.10, 23.68],
            "close": [26.41, 23.99],
            "volume": [27671648, 21865411],
            "amount": [754302023.0, 535381921.0],
            "turnover": [0.047081, 0.037202],
        }
    )
    factors = pd.DataFrame(
        {
            "date": ["1900-01-01", "2015-06-18", "2016-09-30"],
            "qfq_factor": [9.7650961993474, 3.1332126594194, 3.1213489234882],
        }
    )

    rebuilt = hs300.rebuild_qfq_from_unadjusted(raw, factors, "002602")

    assert rebuilt["trade_date"].tolist() == ["2016-09-12", "2016-10-10"]
    assert rebuilt["close"].tolist() == [8.43, 7.69]
    assert rebuilt["adjustment"].tolist() == ["qfq", "qfq"]
    assert rebuilt["source"].tolist() == [
        "akshare.stock_zh_a_daily+qfq_factor",
        "akshare.stock_zh_a_daily+qfq_factor",
    ]


def test_config_defaults_to_ten_calendar_year_window():
    parser = hs300.build_parser()
    args = parser.parse_args(["--end-date", "2026-08-26", "--no-parquet"])

    config = hs300.config_from_args(args)

    assert config.start_date == "20160826"
    assert config.end_date == "20260826"
    assert config.provider == "stock_zh_a_daily"
    assert config.qfq_mode == "factor"
    assert config.write_csv is True
    assert config.write_parquet is False


def test_write_standardized_outputs(tmp_path):
    frame = pd.DataFrame(
        {
            "trade_date": ["2024-01-02"],
            "symbol": ["600000.SH"],
            "ticker": ["600000"],
            "exchange": ["SH"],
            "open": [1.0],
            "high": [2.0],
            "low": [0.5],
            "close": [1.5],
            "volume": [1000],
            "amount": [1500.0],
            "amplitude": [1.0],
            "pct_change": [2.0],
            "change": [0.1],
            "turnover": [0.2],
            "adjustment": ["unadjusted"],
            "source": ["akshare.stock_zh_a_hist"],
        }
    )

    outputs = hs300.write_standardized_outputs(tmp_path, "unadjusted", frame, write_csv=True, write_parquet=False)

    csv_path = Path(outputs["csv"])
    assert csv_path.exists()
    assert "600000.SH" in csv_path.read_text(encoding="utf-8-sig")
