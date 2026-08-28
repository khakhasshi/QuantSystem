#!/usr/bin/env python3
"""Local market data visualization service for QuantSystem."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
import os
from pathlib import Path
from typing import Any

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
STATIC_DIR = APP_DIR / "static"
DEFAULT_DB_PATH = PROJECT_ROOT / "datacenter" / "duckdb" / "data" / "quantsystem.duckdb"
MARKETS = {"ashare", "usstock"}
ADJUSTMENTS = {"unadjusted", "qfq"}


def create_app(database_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    app = FastAPI(title="QuantSystem Market Visualization", version="1.0.0")
    app.state.database_path = Path(database_path)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.head("/")
    def index_head() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return Response(status_code=204)

    @app.head("/favicon.ico")
    def favicon_head() -> Response:
        return Response(status_code=204)

    @app.get("/apple-touch-icon.png")
    def apple_touch_icon() -> Response:
        return Response(status_code=204)

    @app.head("/apple-touch-icon.png")
    def apple_touch_icon_head() -> Response:
        return Response(status_code=204)

    @app.get("/apple-touch-icon-precomposed.png")
    def apple_touch_icon_precomposed() -> Response:
        return Response(status_code=204)

    @app.head("/apple-touch-icon-precomposed.png")
    def apple_touch_icon_precomposed_head() -> Response:
        return Response(status_code=204)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        db_path = Path(app.state.database_path)
        return {"ok": db_path.exists(), "database_path": str(db_path)}

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        with connect_readonly(app.state.database_path) as con:
            rows = con.execute(
                """
                SELECT market, dataset, adjustment, rows, symbols, min_trade_date, max_trade_date,
                       ohlc_null_rows, duplicate_key_rows
                FROM v_daily_bars_summary
                ORDER BY market, adjustment
                """
            ).fetchall()
        return {"summary": [summary_row(row) for row in rows]}

    @app.get("/api/symbols")
    def symbols(
        market: str = Query("ashare"),
        adjustment: str = Query("qfq"),
        q: str = Query("", max_length=80),
        limit: int = Query(200, ge=1, le=1000),
    ) -> dict[str, Any]:
        validate_market_adjustment(market, adjustment)
        query = f"%{q.strip().upper()}%"
        with connect_readonly(app.state.database_path) as con:
            rows = con.execute(
                """
                SELECT
                    symbol,
                    any_value(ticker) AS ticker,
                    any_value(exchange) AS exchange,
                    min(trade_date) AS min_trade_date,
                    max(trade_date) AS max_trade_date,
                    count(*) AS rows
                FROM daily_bars
                WHERE market = ?
                  AND adjustment = ?
                  AND (
                    ? = '%%'
                    OR upper(symbol) LIKE ?
                    OR upper(coalesce(ticker, '')) LIKE ?
                    OR upper(coalesce(exchange, '')) LIKE ?
                  )
                GROUP BY symbol
                ORDER BY
                  CASE WHEN upper(symbol) LIKE replace(?, '%%', '') || '%%' THEN 0 ELSE 1 END,
                  symbol
                LIMIT ?
                """,
                [market, adjustment, query, query, query, query, query, limit],
            ).fetchall()
        return {"symbols": [symbol_row(row) for row in rows]}

    @app.get("/api/bars")
    def bars(
        market: str = Query("ashare"),
        adjustment: str = Query("qfq"),
        symbol: str = Query(..., min_length=1, max_length=40),
        start_date: str | None = Query(None),
        end_date: str | None = Query(None),
    ) -> dict[str, Any]:
        validate_market_adjustment(market, adjustment)
        parsed_start = parse_optional_date(start_date, "start_date")
        parsed_end = parse_optional_date(end_date, "end_date")
        if parsed_start and parsed_end and parsed_start > parsed_end:
            raise HTTPException(status_code=400, detail="start_date must be on or before end_date")
        symbol = symbol.strip().upper()

        with connect_readonly(app.state.database_path) as con:
            coverage = con.execute(
                """
                SELECT min(trade_date), max(trade_date), count(*)
                FROM daily_bars
                WHERE market = ? AND adjustment = ? AND symbol = ?
                """,
                [market, adjustment, symbol],
            ).fetchone()
            if not coverage or coverage[2] == 0:
                raise HTTPException(status_code=404, detail=f"No bars found for {symbol}")

            rows = con.execute(
                """
                SELECT trade_date, open, high, low, close, volume
                FROM daily_bars
                WHERE market = ?
                  AND adjustment = ?
                  AND symbol = ?
                  AND (?::DATE IS NULL OR trade_date >= ?::DATE)
                  AND (?::DATE IS NULL OR trade_date <= ?::DATE)
                  AND open IS NOT NULL
                  AND high IS NOT NULL
                  AND low IS NOT NULL
                  AND close IS NOT NULL
                ORDER BY trade_date
                """,
                [market, adjustment, symbol, parsed_start, parsed_start, parsed_end, parsed_end],
            ).fetchall()

        return {
            "market": market,
            "adjustment": adjustment,
            "symbol": symbol,
            "coverage": {
                "min_trade_date": iso_date(coverage[0]),
                "max_trade_date": iso_date(coverage[1]),
                "rows": int(coverage[2]),
            },
            "visible": {
                "start_date": iso_date(rows[0][0]) if rows else None,
                "end_date": iso_date(rows[-1][0]) if rows else None,
                "rows": len(rows),
            },
            "bars": [bar_row(row) for row in rows],
        }

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


@contextmanager
def connect_readonly(database_path: Path):
    if not Path(database_path).exists():
        raise HTTPException(status_code=500, detail=f"Database not found: {database_path}")
    con = duckdb.connect(str(database_path), read_only=True)
    try:
        yield con
    finally:
        con.close()


def validate_market_adjustment(market: str, adjustment: str) -> None:
    if market not in MARKETS:
        raise HTTPException(status_code=400, detail=f"Unsupported market: {market}")
    if adjustment not in ADJUSTMENTS:
        raise HTTPException(status_code=400, detail=f"Unsupported adjustment: {adjustment}")


def parse_optional_date(value: str | None, field_name: str) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must use YYYY-MM-DD") from exc


def iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value)


def clean_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def summary_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "market": row[0],
        "dataset": row[1],
        "adjustment": row[2],
        "rows": int(row[3]),
        "symbols": int(row[4]),
        "min_trade_date": iso_date(row[5]),
        "max_trade_date": iso_date(row[6]),
        "ohlc_null_rows": int(row[7]),
        "duplicate_key_rows": int(row[8]),
    }


def symbol_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "symbol": row[0],
        "ticker": row[1],
        "exchange": row[2],
        "min_trade_date": iso_date(row[3]),
        "max_trade_date": iso_date(row[4]),
        "rows": int(row[5]),
    }


def bar_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "time": iso_date(row[0]),
        "open": clean_float(row[1]),
        "high": clean_float(row[2]),
        "low": clean_float(row[3]),
        "close": clean_float(row[4]),
        "volume": clean_float(row[5]),
    }


app = create_app()


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "1010"))
    uvicorn.run("server:app", host=host, port=port, reload=False, app_dir=str(APP_DIR))
