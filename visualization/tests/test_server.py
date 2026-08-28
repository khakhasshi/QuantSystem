from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import duckdb
from fastapi.testclient import TestClient


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import create_app  # noqa: E402


class ServerApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.duckdb"
        con = duckdb.connect(str(self.db_path))
        con.execute(
            """
            CREATE TABLE daily_bars (
                market VARCHAR,
                dataset VARCHAR,
                adjustment VARCHAR,
                trade_date DATE,
                symbol VARCHAR,
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
                ingested_at TIMESTAMPTZ
            )
            """
        )
        con.execute(
            """
            INSERT INTO daily_bars VALUES
            ('ashare', 'hs300_daily', 'qfq', '2024-01-02', '000001.SZ', '000001', 'SZ', 10, 11, 9, 10.5, 1000, 2000, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'test', current_timestamp),
            ('ashare', 'hs300_daily', 'qfq', '2024-01-03', '000001.SZ', '000001', 'SZ', 10.5, 12, 10, 11.5, 1200, 2200, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'test', current_timestamp),
            ('ashare', 'hs300_daily', 'qfq', '2024-01-04', '000001.SZ', '000001', 'SZ', 11.5, 13, 11, 12.5, 1300, 2300, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'test', current_timestamp),
            ('usstock', 'sp500_daily', 'qfq', '2024-01-02', 'AAPL.US', 'AAPL', 'US', 180, 182, 178, 181, 5000, NULL, 181, NULL, NULL, NULL, NULL, 0, 0, 'AAPL', 'test', current_timestamp)
            """
        )
        con.execute(
            """
            CREATE VIEW v_daily_bars_summary AS
            SELECT
                market,
                dataset,
                adjustment,
                count(*) AS rows,
                count(DISTINCT symbol) AS symbols,
                min(trade_date) AS min_trade_date,
                max(trade_date) AS max_trade_date,
                0 AS ohlc_null_rows,
                0 AS duplicate_key_rows
            FROM daily_bars
            GROUP BY 1, 2, 3
            """
        )
        con.close()
        self.client = TestClient(create_app(self.db_path))

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_meta_lists_market_summary(self) -> None:
        response = self.client.get("/api/meta")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["summary"]), 2)
        self.assertEqual(payload["summary"][0]["adjustment"], "qfq")

    def test_symbols_searches_by_symbol(self) -> None:
        response = self.client.get("/api/symbols", params={"market": "ashare", "adjustment": "qfq", "q": "000001"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["symbols"][0]["symbol"], "000001.SZ")

    def test_bars_honors_start_date(self) -> None:
        response = self.client.get(
            "/api/bars",
            params={"market": "ashare", "adjustment": "qfq", "symbol": "000001.SZ", "start_date": "2024-01-03"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["visible"]["rows"], 2)
        self.assertEqual(payload["bars"][0]["time"], "2024-01-03")

    def test_bars_honors_end_date(self) -> None:
        response = self.client.get(
            "/api/bars",
            params={
                "market": "ashare",
                "adjustment": "qfq",
                "symbol": "000001.SZ",
                "start_date": "2024-01-02",
                "end_date": "2024-01-03",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["visible"]["rows"], 2)
        self.assertEqual(payload["bars"][-1]["time"], "2024-01-03")

    def test_rejects_inverted_date_range(self) -> None:
        response = self.client.get(
            "/api/bars",
            params={
                "market": "ashare",
                "adjustment": "qfq",
                "symbol": "000001.SZ",
                "start_date": "2024-01-04",
                "end_date": "2024-01-03",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_bad_market(self) -> None:
        response = self.client.get(
            "/api/bars",
            params={"market": "crypto", "adjustment": "qfq", "symbol": "BTC"},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
