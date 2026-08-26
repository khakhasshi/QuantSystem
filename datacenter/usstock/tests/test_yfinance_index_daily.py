from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

import yfinance_index_daily as usdaily  # noqa: E402


def test_extract_constituents_normalizes_yahoo_symbols_and_metadata():
    frame = pd.DataFrame(
        {
            "Symbol": ["AAPL", "BRK.B", "BRK.B"],
            "Security": ["Apple", "Berkshire", "Duplicate"],
            "GICS Sector": ["Information Technology", "Financials", "Financials"],
        }
    )

    constituents = usdaily.extract_constituents(frame)

    assert constituents["ticker"].tolist() == ["AAPL", "BRK.B"]
    assert constituents["yahoo_symbol"].tolist() == ["AAPL", "BRK-B"]
    assert constituents["symbol"].tolist() == ["AAPL.US", "BRK.B.US"]
    assert constituents["exchange"].tolist() == ["US", "US"]


def test_normalize_yfinance_hist_unadjusted_maps_schema():
    raw = pd.DataFrame(
        {
            "Date": ["2024-01-02", "2024-01-03"],
            "Open": [10.0, 10.5],
            "High": [10.8, 10.6],
            "Low": [9.9, 10.0],
            "Close": [10.4, 10.1],
            "Adj Close": [10.2, 10.0],
            "Volume": [123, 456],
            "Dividends": [0.0, 0.1],
            "Stock Splits": [0.0, 0.0],
        }
    )

    normalized = usdaily.normalize_yfinance_hist(raw, "BRK.B", "unadjusted")

    assert normalized.columns.tolist() == usdaily.CANONICAL_COLUMNS
    assert normalized["symbol"].tolist() == ["BRK.B.US", "BRK.B.US"]
    assert normalized["yahoo_symbol"].tolist() == ["BRK-B", "BRK-B"]
    assert normalized["trade_date"].tolist() == ["2024-01-02", "2024-01-03"]
    assert normalized["adj_close"].tolist() == [10.2, 10.0]
    assert normalized["adjustment"].tolist() == ["unadjusted", "unadjusted"]


def test_normalize_yfinance_hist_qfq_sets_adj_close_to_adjusted_close():
    raw = pd.DataFrame(
        {
            "Date": ["2024-01-02"],
            "Open": [9.8],
            "High": [10.2],
            "Low": [9.6],
            "Close": [10.0],
            "Volume": [1000],
        }
    )

    normalized = usdaily.normalize_yfinance_hist(raw, "AAPL", "qfq")

    assert normalized["close"].tolist() == [10.0]
    assert normalized["adj_close"].tolist() == [10.0]
    assert normalized["dividends"].tolist() == [0.0]
    assert normalized["stock_splits"].tolist() == [0.0]
    assert normalized["source"].tolist() == ["yfinance.download(auto_adjust=True)"]


def test_normalize_yfinance_hist_accepts_yfinance_multiindex_columns():
    columns = pd.MultiIndex.from_tuples(
        [
            ("Open", "AAPL"),
            ("High", "AAPL"),
            ("Low", "AAPL"),
            ("Close", "AAPL"),
            ("Adj Close", "AAPL"),
            ("Volume", "AAPL"),
        ]
    )
    raw = pd.DataFrame(
        [[10.0, 10.8, 9.9, 10.4, 10.2, 123]],
        index=pd.to_datetime(["2024-01-02"]),
        columns=columns,
    )
    raw.index.name = "Date"

    normalized = usdaily.normalize_yfinance_hist(raw, "AAPL", "unadjusted")

    assert normalized["trade_date"].tolist() == ["2024-01-02"]
    assert normalized["open"].tolist() == [10.0]
    assert normalized["adj_close"].tolist() == [10.2]


def test_filter_history_window_drops_provider_rows_outside_requested_dates():
    frame = pd.DataFrame(
        {
            "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "symbol": ["AAPL.US", "AAPL.US", "AAPL.US"],
        }
    )

    filtered = usdaily.filter_history_window(frame, "20240102", "20240102")

    assert filtered["trade_date"].tolist() == ["2024-01-02"]


def test_config_defaults_to_ten_calendar_year_window_and_csv_only_option():
    parser = usdaily.build_parser()
    args = parser.parse_args(["--end-date", "2026-08-26", "--asof-date", "2026-08-27", "--no-parquet"])

    config = usdaily.config_from_args(args)

    assert config.start_date == "20160826"
    assert config.end_date == "20260826"
    assert config.asof_date == "20260827"
    assert config.adjustments == ("unadjusted", "qfq")
    assert config.write_csv is True
    assert config.write_parquet is False


def test_write_standardized_outputs(tmp_path):
    frame = pd.DataFrame(
        {
            "trade_date": ["2024-01-02"],
            "symbol": ["AAPL.US"],
            "ticker": ["AAPL"],
            "yahoo_symbol": ["AAPL"],
            "exchange": ["US"],
            "open": [1.0],
            "high": [2.0],
            "low": [0.5],
            "close": [1.5],
            "adj_close": [1.4],
            "volume": [1000],
            "dividends": [0.0],
            "stock_splits": [0.0],
            "adjustment": ["unadjusted"],
            "source": ["yfinance.download(auto_adjust=False)"],
        }
    )

    outputs = usdaily.write_standardized_outputs(tmp_path, "unadjusted", frame, write_csv=True, write_parquet=False)

    csv_path = Path(outputs["csv"])
    assert csv_path.exists()
    assert "AAPL.US" in csv_path.read_text(encoding="utf-8")
