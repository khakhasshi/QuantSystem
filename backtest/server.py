#!/usr/bin/env python3
"""Local Backtrader backtest service for QuantSystem."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
import json
import os
from pathlib import Path
from typing import Any, Literal
from urllib import error as urlerror
from urllib import request as urlrequest

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from .dsl import DslError, evaluate_signal
    from .engine import BACKTRADER_IMPORT_ERROR, TEMPLATES, optimize_parameters, run_backtest, template_by_key, template_payload
except ImportError:  # pragma: no cover - supports running from the backtest directory
    from dsl import DslError, evaluate_signal
    from engine import BACKTRADER_IMPORT_ERROR, TEMPLATES, optimize_parameters, run_backtest, template_by_key, template_payload


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
STATIC_DIR = APP_DIR / "static"
DEFAULT_DB_PATH = PROJECT_ROOT / "datacenter" / "duckdb" / "data" / "quantsystem.duckdb"
MARKETS = {"ashare", "usstock"}
ADJUSTMENTS = {"unadjusted", "qfq"}
DEFAULT_DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEFAULT_DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEFAULT_DEEPSEEK_REASONER_MODEL = os.environ.get("DEEPSEEK_REASONER_MODEL", "deepseek-reasoner")


class BacktestRequest(BaseModel):
    market: Literal["ashare", "usstock"] = "ashare"
    adjustment: Literal["unadjusted", "qfq"] = "qfq"
    symbol: str = Field(min_length=1, max_length=40)
    start_date: str | None = None
    end_date: str | None = None
    template_key: str | None = None
    entry_expression: str | None = Field(default=None, max_length=800)
    exit_expression: str | None = Field(default=None, max_length=800)
    initial_capital: float = Field(default=100000.0, gt=0)
    fee_bps: float = Field(default=0.0, ge=0, le=500)
    target_percent: float = Field(default=0.98, gt=0, le=1)
    capacity_participation: float = Field(default=0.05, gt=0, le=1)
    monte_carlo_runs: int = Field(default=300, ge=0, le=2000)
    walk_forward_window: int = Field(default=504, ge=30, le=3000)
    walk_forward_step: int = Field(default=252, ge=1, le=3000)


class ParamRange(BaseModel):
    min: float
    max: float
    step: float = Field(gt=0)


class OptimizeRequest(BaseModel):
    market: Literal["ashare", "usstock"] = "ashare"
    adjustment: Literal["unadjusted", "qfq"] = "qfq"
    symbol: str = Field(min_length=1, max_length=40)
    start_date: str | None = None
    end_date: str | None = None
    template_key: str = "dual_ma"
    x_param: str = Field(default="fast", min_length=1, max_length=40)
    y_param: str = Field(default="slow", min_length=1, max_length=40)
    ranges: dict[str, ParamRange] = Field(default_factory=dict)
    objective: Literal["sharpe", "calmar", "annual_return", "total_return", "max_drawdown"] = "sharpe"
    initial_capital: float = Field(default=100000.0, gt=0)
    fee_bps: float = Field(default=0.0, ge=0, le=500)
    target_percent: float = Field(default=0.98, gt=0, le=1)
    capacity_participation: float = Field(default=0.05, gt=0, le=1)
    max_combinations: int = Field(default=400, ge=1, le=2000)


class LlmEvaluateRequest(BaseModel):
    run_request: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    thinking_mode: bool = False
    api_key: str | None = Field(default=None, max_length=300)
    base_url: str | None = Field(default=None, max_length=300)
    model: str | None = Field(default=None, max_length=120)


def create_app(database_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    app = FastAPI(title="QuantSystem Backtrader Backtest", version="1.0.0")
    app.state.database_path = Path(database_path)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.head("/")
    def index_head() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/styles.css")
    def root_styles() -> FileResponse:
        return FileResponse(STATIC_DIR / "styles.css")

    @app.get("/app.js")
    def root_app_js() -> FileResponse:
        return FileResponse(STATIC_DIR / "app.js")

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return Response(status_code=204)

    @app.head("/favicon.ico")
    def favicon_head() -> Response:
        return Response(status_code=204)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        db_path = Path(app.state.database_path)
        return {
            "ok": db_path.exists() and BACKTRADER_IMPORT_ERROR is None,
            "database_path": str(db_path),
            "database_exists": db_path.exists(),
            "backtrader_available": BACKTRADER_IMPORT_ERROR is None,
            "backtrader_error": str(BACKTRADER_IMPORT_ERROR) if BACKTRADER_IMPORT_ERROR else None,
        }

    @app.get("/api/llm/status")
    def llm_status() -> dict[str, Any]:
        return {
            "provider": "deepseek",
            "configured": bool(os.environ.get("DEEPSEEK_API_KEY")),
            "base_url": DEFAULT_DEEPSEEK_BASE_URL,
            "chat_model": DEFAULT_DEEPSEEK_MODEL,
            "reasoner_model": DEFAULT_DEEPSEEK_REASONER_MODEL,
        }

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

    @app.get("/api/templates")
    def templates() -> dict[str, Any]:
        return {
            "templates": template_payload(),
            "dsl_reference": {
                "series": ["open", "high", "low", "close", "volume", "amount"],
                "functions": [
                    "sma(series, period)",
                    "ma(series, period)",
                    "ema(series, period)",
                    "rsi(series, period)",
                    "std(series, period)",
                    "rolling_max(series, period)",
                    "rolling_min(series, period)",
                    "shift(series, periods)",
                    "pct_change(series, periods)",
                    "cross_over(left, right)",
                    "cross_under(left, right)",
                    "abs(series)",
                    "log(series)",
                    "sqrt(series)",
                ],
            },
        }

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
        records, coverage = load_records(app.state.database_path, market, adjustment, symbol, start_date, end_date)
        return bars_payload(market, adjustment, symbol, records, coverage)

    @app.post("/api/dsl/validate")
    def validate_dsl(payload: BacktestRequest) -> dict[str, Any]:
        records, _coverage = load_records(
            app.state.database_path, payload.market, payload.adjustment, payload.symbol, payload.start_date, payload.end_date
        )
        entry_expression, exit_expression = expressions_from_request(payload)
        data = {
            key: [record.get(key) for record in records]
            for key in ("open", "high", "low", "close", "volume", "amount")
            if key in records[0]
        }
        try:
            entry = evaluate_signal(entry_expression, data)
            exit_ = evaluate_signal(exit_expression, data)
        except DslError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True,
            "entry_count": int(entry.values.sum()),
            "exit_count": int(exit_.values.sum()),
            "entry_expression": entry_expression,
            "exit_expression": exit_expression,
        }

    @app.post("/api/backtest")
    def backtest(payload: BacktestRequest) -> dict[str, Any]:
        records, coverage = load_records(
            app.state.database_path, payload.market, payload.adjustment, payload.symbol, payload.start_date, payload.end_date
        )
        entry_expression, exit_expression = expressions_from_request(payload)
        try:
            result = run_backtest(
                records,
                entry_expression=entry_expression,
                exit_expression=exit_expression,
                initial_capital=payload.initial_capital,
                fee_bps=payload.fee_bps,
                target_percent=payload.target_percent,
                capacity_participation=payload.capacity_participation,
                monte_carlo_runs=payload.monte_carlo_runs,
                walk_forward_window=payload.walk_forward_window,
                walk_forward_step=payload.walk_forward_step,
            )
        except DslError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {
            "market": payload.market,
            "adjustment": payload.adjustment,
            "symbol": payload.symbol.strip().upper(),
            "coverage": coverage,
            "visible": {
                "start_date": iso_date(records[0]["trade_date"]) if records else None,
                "end_date": iso_date(records[-1]["trade_date"]) if records else None,
                "rows": len(records),
            },
            **result,
        }

    @app.post("/api/optimize")
    def optimize(payload: OptimizeRequest) -> dict[str, Any]:
        records, coverage = load_records(
            app.state.database_path, payload.market, payload.adjustment, payload.symbol, payload.start_date, payload.end_date
        )
        try:
            result = optimize_parameters(
                records,
                template_key=payload.template_key,
                x_param=payload.x_param,
                y_param=payload.y_param,
                ranges={key: value.model_dump() for key, value in payload.ranges.items()},
                objective=payload.objective,
                initial_capital=payload.initial_capital,
                fee_bps=payload.fee_bps,
                target_percent=payload.target_percent,
                capacity_participation=payload.capacity_participation,
                max_combinations=payload.max_combinations,
            )
        except (DslError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {
            "market": payload.market,
            "adjustment": payload.adjustment,
            "symbol": payload.symbol.strip().upper(),
            "coverage": coverage,
            "visible": {
                "start_date": iso_date(records[0]["trade_date"]) if records else None,
                "end_date": iso_date(records[-1]["trade_date"]) if records else None,
                "rows": len(records),
            },
            **result,
        }

    @app.post("/api/llm/evaluate")
    def llm_evaluate(payload: LlmEvaluateRequest) -> dict[str, Any]:
        api_key = (payload.api_key or os.environ.get("DEEPSEEK_API_KEY") or "").strip()
        if not api_key:
            raise HTTPException(status_code=400, detail="未配置 DeepSeek API Key: 请设置 DEEPSEEK_API_KEY 或在浮窗中临时输入")
        base_url = (payload.base_url or DEFAULT_DEEPSEEK_BASE_URL).strip()
        model = (payload.model or (DEFAULT_DEEPSEEK_REASONER_MODEL if payload.thinking_mode else DEFAULT_DEEPSEEK_MODEL)).strip()
        if not payload.result:
            raise HTTPException(status_code=400, detail="缺少可评价的回测结果")
        request_body = build_llm_request(payload, model)
        try:
            response_payload = call_openai_compatible_chat(base_url, api_key, request_body)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        markdown = extract_chat_message(response_payload)
        fallback_model = None
        if not markdown and response_has_reasoning_only(response_payload):
            fallback_model = DEFAULT_DEEPSEEK_MODEL
            fallback_body = build_llm_request(payload, fallback_model, force_final_answer=True)
            try:
                fallback_payload = call_openai_compatible_chat(base_url, api_key, fallback_body)
            except RuntimeError as exc:
                raise HTTPException(status_code=502, detail=f"DeepSeek 已返回推理字段但无最终答案，兜底生成也失败: {exc}") from exc
            markdown = extract_chat_message(fallback_payload)
        if not markdown:
            raise HTTPException(status_code=502, detail="LLM 响应缺少 message.content")
        return {
            "provider": "deepseek",
            "base_url": base_url,
            "model": fallback_model or model,
            "fallback_model": fallback_model,
            "thinking_mode": payload.thinking_mode,
            "markdown": markdown,
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


def expressions_from_request(payload: BacktestRequest) -> tuple[str, str]:
    if payload.template_key:
        try:
            template = template_by_key(payload.template_key)
        except KeyError as exc:
            valid = ", ".join(template.key for template in TEMPLATES)
            raise HTTPException(status_code=400, detail=f"Unsupported template_key. Use one of: {valid}") from exc
        return template.entry_expression, template.exit_expression
    if not payload.entry_expression or not payload.exit_expression:
        raise HTTPException(status_code=400, detail="Provide template_key or both entry_expression and exit_expression")
    return payload.entry_expression, payload.exit_expression


def load_records(
    database_path: Path,
    market: str,
    adjustment: str,
    symbol: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validate_market_adjustment(market, adjustment)
    parsed_start = parse_optional_date(start_date, "start_date")
    parsed_end = parse_optional_date(end_date, "end_date")
    if parsed_start and parsed_end and parsed_start > parsed_end:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date")
    symbol = symbol.strip().upper()
    with connect_readonly(database_path) as con:
        coverage_row = con.execute(
            """
            SELECT min(trade_date), max(trade_date), count(*)
            FROM daily_bars
            WHERE market = ? AND adjustment = ? AND symbol = ?
            """,
            [market, adjustment, symbol],
        ).fetchone()
        if not coverage_row or coverage_row[2] == 0:
            raise HTTPException(status_code=404, detail=f"No bars found for {symbol}")

        rows = con.execute(
            """
            SELECT trade_date, open, high, low, close, volume, amount
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
    records = [record_row(row) for row in rows]
    if not records:
        raise HTTPException(status_code=404, detail=f"No visible bars found for {symbol}")
    coverage = {"min_trade_date": iso_date(coverage_row[0]), "max_trade_date": iso_date(coverage_row[1]), "rows": int(coverage_row[2])}
    return records, coverage


def bars_payload(
    market: str,
    adjustment: str,
    symbol: str,
    records: list[dict[str, Any]],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "market": market,
        "adjustment": adjustment,
        "symbol": symbol.strip().upper(),
        "coverage": coverage,
        "visible": {
            "start_date": iso_date(records[0]["trade_date"]) if records else None,
            "end_date": iso_date(records[-1]["trade_date"]) if records else None,
            "rows": len(records),
        },
        "bars": [bar_row(record) for record in records],
    }


def build_llm_request(payload: LlmEvaluateRequest, model: str, *, force_final_answer: bool = False) -> dict[str, Any]:
    user_payload = compact_backtest_for_llm(payload.run_request, payload.result)
    current_date = date.today().isoformat()
    mode_hint = (
        "使用更深入的审查模式，给出关键推理摘要、主要证据链和反证点，但不要输出隐藏思维链或逐字内心推理。"
        if payload.thinking_mode
        else "使用简洁审查模式，直接给出结论、风险和下一步验证。"
    )
    if force_final_answer:
        mode_hint = "只输出可直接展示给用户的最终 Markdown 评价，不要输出推理过程、草稿或 reasoning 字段。"
    system_prompt = (
        "你是一个严格的量化策略回测审查员。只根据用户提供的回测结果评价，不编造未给出的成交、"
        "因子或未来收益证据。重点检查收益质量、风险、回撤、换手、交易成本、容量、蒙特卡洛路径风险、"
        "步进窗口稳定性和过拟合嫌疑。输出 Markdown，结构清晰，包含可执行的改进建议。"
        f"当前日期是 {current_date}，不要把该日期之前或当天的回测结束日期误判为未来数据。"
    )
    user_prompt = (
        f"{mode_hint}\n\n"
        "请评价这次回测，输出以下 Markdown 小节：\n"
        "1. 结论\n"
        "2. 关键指标解读\n"
        "3. 成本、换手与容量\n"
        "4. 稳健性与过拟合风险\n"
        "5. 下一步复核清单\n\n"
        f"回测摘要 JSON:\n```json\n{json.dumps(user_payload, ensure_ascii=False, indent=2)}\n```"
    )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 3000,
    }


def compact_backtest_for_llm(run_request: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("metrics") or {}
    robustness = result.get("robustness") or {}
    monte_carlo = robustness.get("monte_carlo") or {}
    walk_forward = robustness.get("walk_forward") or {}
    liquidity = result.get("liquidity") or {}
    trades = result.get("trades") or []
    return {
        "request": {
            "market": run_request.get("market") or result.get("market"),
            "adjustment": run_request.get("adjustment") or result.get("adjustment"),
            "symbol": run_request.get("symbol") or result.get("symbol"),
            "start_date": run_request.get("start_date"),
            "end_date": run_request.get("end_date"),
            "entry_expression": run_request.get("entry_expression") or result.get("entry_expression"),
            "exit_expression": run_request.get("exit_expression") or result.get("exit_expression"),
            "initial_capital": run_request.get("initial_capital") or result.get("initial_capital"),
            "fee_bps": run_request.get("fee_bps") or result.get("fee_bps"),
            "target_percent": run_request.get("target_percent") or result.get("target_percent"),
            "capacity_participation": run_request.get("capacity_participation") or result.get("capacity_participation"),
        },
        "visible": result.get("visible"),
        "signals": result.get("signals"),
        "metrics": {
            key: metrics.get(key)
            for key in [
                "final_equity",
                "total_return",
                "annual_return",
                "annual_volatility",
                "sharpe",
                "sortino",
                "calmar",
                "max_drawdown",
                "win_rate",
                "profit_factor",
                "trade_count",
                "turnover",
                "annualized_turnover",
                "total_fees",
                "cost_drag",
                "fee_rate_on_traded_value_bps",
                "max_fill_participation",
            ]
        },
        "liquidity": {
            key: liquidity.get(key)
            for key in [
                "median_daily_traded_value",
                "p20_daily_traded_value",
                "p10_daily_traded_value",
                "capacity_at_participation",
                "capacity_participation",
            ]
        },
        "monte_carlo": {
            "enabled": monte_carlo.get("enabled"),
            "runs": monte_carlo.get("runs"),
            "terminal_return": monte_carlo.get("terminal_return"),
            "max_drawdown": monte_carlo.get("max_drawdown"),
            "sharpe": monte_carlo.get("sharpe"),
        },
        "walk_forward": {
            "enabled": walk_forward.get("enabled"),
            "window": walk_forward.get("window"),
            "step": walk_forward.get("step"),
            "summary": walk_forward.get("summary"),
        },
        "trade_sample": trades[:5],
    }


def call_openai_compatible_chat(base_url: str, api_key: str, request_body: dict[str, Any]) -> dict[str, Any]:
    endpoint = chat_completions_endpoint(base_url)
    raw_body = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    request = urlrequest.Request(
        endpoint,
        data=raw_body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"DeepSeek 连接失败: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("DeepSeek 请求超时") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("DeepSeek 响应不是有效 JSON") from exc


def chat_completions_endpoint(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if not clean:
        clean = DEFAULT_DEEPSEEK_BASE_URL.rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    return f"{clean}/chat/completions"


def extract_chat_message(response_payload: dict[str, Any]) -> str | None:
    choices = response_payload.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    return None


def response_has_reasoning_only(response_payload: dict[str, Any]) -> bool:
    choices = response_payload.get("choices") or []
    if not choices:
        return False
    message = choices[0].get("message") or {}
    content = message.get("content")
    reasoning = message.get("reasoning_content")
    return not (isinstance(content, str) and content.strip()) and isinstance(reasoning, str) and bool(reasoning.strip())


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
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
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


def record_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "trade_date": iso_date(row[0]),
        "open": clean_float(row[1]),
        "high": clean_float(row[2]),
        "low": clean_float(row[3]),
        "close": clean_float(row[4]),
        "volume": clean_float(row[5]),
        "amount": clean_float(row[6]),
    }


def bar_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "time": iso_date(record["trade_date"]),
        "open": clean_float(record["open"]),
        "high": clean_float(record["high"]),
        "low": clean_float(record["low"]),
        "close": clean_float(record["close"]),
        "volume": clean_float(record["volume"]),
    }


app = create_app()


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "10110"))
    uvicorn.run("server:app", host="127.0.0.1", port=port, reload=False)
