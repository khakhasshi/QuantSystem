#!/usr/bin/env python3
"""Backtrader execution engine and performance metrics for QuantSystem."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Any

import numpy as np
import pandas as pd

try:
    import backtrader as bt
except ModuleNotFoundError as exc:  # pragma: no cover - exercised by runtime health
    bt = None
    BACKTRADER_IMPORT_ERROR = exc
else:
    BACKTRADER_IMPORT_ERROR = None

try:
    from .dsl import DslError, evaluate_signal
except ImportError:  # pragma: no cover - supports `python engine.py` style imports
    from dsl import DslError, evaluate_signal


TRADING_DAYS = 252


@dataclass(frozen=True)
class StrategyTemplate:
    key: str
    name: str
    entry_expression: str
    exit_expression: str
    description: str


TEMPLATES: list[StrategyTemplate] = [
    StrategyTemplate(
        key="dual_ma",
        name="双均线策略",
        entry_expression="cross_over(sma(close, 5), sma(close, 20))",
        exit_expression="cross_under(sma(close, 5), sma(close, 20))",
        description="快均线上穿慢均线买入，下穿慢均线卖出。",
    ),
    StrategyTemplate(
        key="bollinger_mean_reversion",
        name="布林带均值回归",
        entry_expression="close < sma(close, 20) - 2 * std(close, 20)",
        exit_expression="close >= sma(close, 20)",
        description="收盘价跌破下轨买入，回到中轨卖出。",
    ),
    StrategyTemplate(
        key="bollinger_breakout",
        name="布林带突破",
        entry_expression="close > sma(close, 20) + 2 * std(close, 20)",
        exit_expression="close < sma(close, 20)",
        description="收盘价突破上轨买入，跌回中轨下方卖出。",
    ),
    StrategyTemplate(
        key="rsi_reversal",
        name="RSI 反转",
        entry_expression="rsi(close, 14) < 30",
        exit_expression="rsi(close, 14) > 70",
        description="RSI 低于 30 买入，高于 70 卖出。",
    ),
]


OPTIMIZATION_OBJECTIVES = {"sharpe", "calmar", "annual_return", "total_return", "max_drawdown"}


OPTIMIZATION_SPECS: dict[str, dict[str, Any]] = {
    "dual_ma": {
        "params": {
            "fast": {"label": "快线周期", "default": 5, "min": 2, "max": 60, "step": 3, "type": "int"},
            "slow": {"label": "慢线周期", "default": 20, "min": 10, "max": 180, "step": 10, "type": "int"},
        },
        "x_param": "fast",
        "y_param": "slow",
    },
    "bollinger_mean_reversion": {
        "params": {
            "period": {"label": "BOLL周期", "default": 20, "min": 10, "max": 80, "step": 5, "type": "int"},
            "deviations": {"label": "标准差倍数", "default": 2.0, "min": 1.2, "max": 3.0, "step": 0.2, "type": "float"},
        },
        "x_param": "period",
        "y_param": "deviations",
    },
    "bollinger_breakout": {
        "params": {
            "period": {"label": "BOLL周期", "default": 20, "min": 10, "max": 80, "step": 5, "type": "int"},
            "deviations": {"label": "标准差倍数", "default": 2.0, "min": 1.2, "max": 3.0, "step": 0.2, "type": "float"},
        },
        "x_param": "period",
        "y_param": "deviations",
    },
    "rsi_reversal": {
        "params": {
            "entry": {"label": "入场阈值", "default": 30, "min": 10, "max": 45, "step": 5, "type": "int"},
            "exit": {"label": "出场阈值", "default": 70, "min": 55, "max": 90, "step": 5, "type": "int"},
            "period": {"label": "RSI周期", "default": 14, "min": 6, "max": 30, "step": 4, "type": "int"},
        },
        "x_param": "entry",
        "y_param": "exit",
    },
}


def template_payload() -> list[dict[str, str]]:
    rows = []
    for template in TEMPLATES:
        row = template.__dict__.copy()
        row["optimization"] = OPTIMIZATION_SPECS.get(template.key)
        rows.append(row)
    return rows


def template_by_key(key: str) -> StrategyTemplate:
    for template in TEMPLATES:
        if template.key == key:
            return template
    raise KeyError(key)


def template_expressions(template_key: str, params: dict[str, Any]) -> tuple[str, str]:
    if template_key == "dual_ma":
        fast = int(params.get("fast", 5))
        slow = int(params.get("slow", 20))
        if fast >= slow:
            raise ValueError("双均线要求 fast < slow")
        return (
            f"cross_over(sma(close, {fast}), sma(close, {slow}))",
            f"cross_under(sma(close, {fast}), sma(close, {slow}))",
        )
    if template_key in {"bollinger_mean_reversion", "bollinger_breakout"}:
        period = int(params.get("period", 20))
        deviations = float(params.get("deviations", 2.0))
        upper = f"sma(close, {period}) + {format_param(deviations)} * std(close, {period})"
        lower = f"sma(close, {period}) - {format_param(deviations)} * std(close, {period})"
        middle = f"sma(close, {period})"
        if template_key == "bollinger_mean_reversion":
            return (f"close < {lower}", f"close >= {middle}")
        return (f"close > {upper}", f"close < {middle}")
    if template_key == "rsi_reversal":
        period = int(params.get("period", 14))
        entry = float(params.get("entry", 30))
        exit_ = float(params.get("exit", 70))
        if entry >= exit_:
            raise ValueError("RSI 反转要求 entry < exit")
        return (
            f"rsi(close, {period}) < {format_param(entry)}",
            f"rsi(close, {period}) > {format_param(exit_)}",
        )
    raise ValueError(f"Unsupported optimizable template: {template_key}")


def format_param(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{float(value):.6g}"


if bt is not None:

    class SignalPandasData(bt.feeds.PandasData):
        lines = ("entry_signal", "exit_signal")
        params = (("entry_signal", -1), ("exit_signal", -1))


    class DslSignalStrategy(bt.Strategy):
        params = (
            ("target_percent", 0.98),
            ("entry_reason", "DSL entry"),
            ("exit_reason", "DSL exit"),
        )

        def __init__(self):
            self.pending_order = None
            self.equity_curve: list[dict[str, Any]] = []
            self.trades: list[dict[str, Any]] = []
            self.fills: list[dict[str, Any]] = []
            self._entry: dict[str, Any] | None = None
            self._entry_signal_date: date | None = None

        def next(self):
            current_date = self.data.datetime.date(0)
            self.equity_curve.append(
                {
                    "time": current_date.isoformat(),
                    "value": round(float(self.broker.getvalue()), 6),
                    "position": float(self.position.size),
                }
            )
            if self.pending_order:
                return
            if not self.position and bool(self.data.entry_signal[0]):
                self._entry_signal_date = current_date
                self.pending_order = self.order_target_percent(target=float(self.p.target_percent))
            elif self.position and bool(self.data.exit_signal[0]):
                self.pending_order = self.order_target_percent(target=0.0)

        def stop(self):
            if not self.equity_curve:
                current_date = self.data.datetime.date(0)
                self.equity_curve.append(
                    {"time": current_date.isoformat(), "value": round(float(self.broker.getvalue()), 6), "position": 0.0}
                )

        def notify_order(self, order):
            if order.status in (order.Submitted, order.Accepted):
                return
            if order.status == order.Completed:
                executed_date = self.data.datetime.date(0)
                if order.isbuy():
                    entry_value = abs(float(order.executed.size)) * float(order.executed.price)
                    self.fills.append(
                        {
                            "date": executed_date.isoformat(),
                            "side": "BUY",
                            "price": round(float(order.executed.price), 6),
                            "shares": round(abs(float(order.executed.size)), 6),
                            "value": round(entry_value, 6),
                            "fee": round(float(order.executed.comm), 6),
                            "signalDate": self._entry_signal_date.isoformat() if self._entry_signal_date else None,
                            "reason": str(self.p.entry_reason),
                        }
                    )
                    self._entry = {
                        "entryDate": executed_date.isoformat(),
                        "entrySignalDate": self._entry_signal_date.isoformat() if self._entry_signal_date else None,
                        "entryPrice": float(order.executed.price),
                        "shares": float(order.executed.size),
                        "entryValue": entry_value,
                        "entryFee": float(order.executed.comm),
                    }
                elif order.issell() and self._entry:
                    exit_value = abs(float(order.executed.size)) * float(order.executed.price)
                    exit_fee = float(order.executed.comm)
                    self.fills.append(
                        {
                            "date": executed_date.isoformat(),
                            "side": "SELL",
                            "price": round(float(order.executed.price), 6),
                            "shares": round(abs(float(order.executed.size)), 6),
                            "value": round(exit_value, 6),
                            "fee": round(exit_fee, 6),
                            "signalDate": executed_date.isoformat(),
                            "reason": str(self.p.exit_reason),
                        }
                    )
                    gross_pnl = exit_value - self._entry["entryValue"]
                    total_fee = self._entry["entryFee"] + exit_fee
                    net_pnl = gross_pnl - total_fee
                    denominator = self._entry["entryValue"] + self._entry["entryFee"]
                    self.trades.append(
                        {
                            "side": "LONG",
                            "entryDate": self._entry["entryDate"],
                            "entrySignalDate": self._entry["entrySignalDate"],
                            "exitDate": executed_date.isoformat(),
                            "entryPrice": round(self._entry["entryPrice"], 6),
                            "exitPrice": round(float(order.executed.price), 6),
                            "shares": round(abs(self._entry["shares"]), 6),
                            "entryValue": round(self._entry["entryValue"], 6),
                            "exitValue": round(exit_value, 6),
                            "grossPnl": round(gross_pnl, 6),
                            "fee": round(total_fee, 6),
                            "netPnl": round(net_pnl, 6),
                            "returnPct": round(net_pnl / denominator, 8) if denominator else None,
                            "reason": str(self.p.exit_reason),
                        }
                    )
                    self._entry = None
                    self._entry_signal_date = None
            self.pending_order = None


def build_backtest_frame(records: list[dict[str, Any]], entry_expression: str, exit_expression: str) -> pd.DataFrame:
    if len(records) < 3:
        raise ValueError("回测区间至少需要 3 根K线")
    df = pd.DataFrame.from_records(records)
    required = {"trade_date", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"缺少K线字段: {', '.join(missing)}")
    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.sort_values("trade_date").drop_duplicates("trade_date", keep="last")
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    if len(df) < 3:
        raise ValueError("清洗后K线数量不足")
    dsl_data = {name: df[name].to_numpy(dtype=float) for name in ["open", "high", "low", "close", "volume"] if name in df}
    if "amount" in df:
        dsl_data["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    try:
        entry = evaluate_signal(entry_expression, dsl_data).values
        exit_ = evaluate_signal(exit_expression, dsl_data).values
    except DslError:
        raise
    except Exception as exc:
        raise DslError(str(exc)) from exc
    df["entry_signal"] = entry.astype(bool)
    df["exit_signal"] = exit_.astype(bool)
    df = df.set_index("trade_date")
    return df[["open", "high", "low", "close", "volume", "entry_signal", "exit_signal"]]


def run_backtest(
    records: list[dict[str, Any]],
    *,
    entry_expression: str,
    exit_expression: str,
    initial_capital: float = 100000.0,
    fee_bps: float = 0.0,
    target_percent: float = 0.98,
    capacity_participation: float = 0.05,
    monte_carlo_runs: int = 300,
    walk_forward_window: int = 504,
    walk_forward_step: int = 252,
    include_robustness: bool = True,
) -> dict[str, Any]:
    result = _run_backtest_once(
        records,
        entry_expression=entry_expression,
        exit_expression=exit_expression,
        initial_capital=initial_capital,
        fee_bps=fee_bps,
        target_percent=target_percent,
        capacity_participation=capacity_participation,
    )
    if include_robustness:
        result["robustness"] = {
            "monte_carlo": monte_carlo_shuffle(result["equity"], runs=monte_carlo_runs),
            "walk_forward": walk_forward(
                records,
                entry_expression=entry_expression,
                exit_expression=exit_expression,
                initial_capital=initial_capital,
                fee_bps=fee_bps,
                target_percent=target_percent,
                capacity_participation=capacity_participation,
                window=walk_forward_window,
                step=walk_forward_step,
            ),
        }
    return result


def optimize_parameters(
    records: list[dict[str, Any]],
    *,
    template_key: str,
    x_param: str,
    y_param: str,
    ranges: dict[str, dict[str, float]],
    objective: str = "sharpe",
    initial_capital: float = 100000.0,
    fee_bps: float = 0.0,
    target_percent: float = 0.98,
    capacity_participation: float = 0.05,
    max_combinations: int = 400,
) -> dict[str, Any]:
    if template_key not in OPTIMIZATION_SPECS:
        raise ValueError(f"Unsupported optimizable template: {template_key}")
    if objective not in OPTIMIZATION_OBJECTIVES:
        raise ValueError(f"Unsupported objective: {objective}")
    spec = OPTIMIZATION_SPECS[template_key]
    params_spec = spec["params"]
    if x_param not in params_spec or y_param not in params_spec or x_param == y_param:
        raise ValueError("x_param and y_param must be different parameters supported by the template")

    defaults = {name: meta["default"] for name, meta in params_spec.items()}
    x_values = range_values(ranges.get(x_param, {}), params_spec[x_param])
    y_values = range_values(ranges.get(y_param, {}), params_spec[y_param])
    combinations = len(x_values) * len(y_values)
    if combinations > max_combinations:
        raise ValueError(f"参数组合过多: {combinations}; 请缩小范围或增大步长，当前上限 {max_combinations}")

    results = []
    cells = []
    best: dict[str, Any] | None = None
    for y_value in y_values:
        row = []
        for x_value in x_values:
            params = defaults.copy()
            params[x_param] = cast_param(x_value, params_spec[x_param])
            params[y_param] = cast_param(y_value, params_spec[y_param])
            result_row = run_optimization_cell(
                records,
                template_key=template_key,
                params=params,
                objective=objective,
                initial_capital=initial_capital,
                fee_bps=fee_bps,
                target_percent=target_percent,
                capacity_participation=capacity_participation,
            )
            results.append(result_row)
            row.append(
                {
                    "x": params[x_param],
                    "y": params[y_param],
                    "value": result_row.get("score"),
                    "ok": result_row.get("ok", False),
                }
            )
            if result_row.get("ok") and is_better(result_row, best, objective):
                best = result_row
        cells.append(row)

    ranked = sorted(
        [row for row in results if row.get("ok") and row.get("score") is not None],
        key=lambda row: row["score"],
        reverse=objective != "max_drawdown",
    )
    return {
        "template_key": template_key,
        "objective": objective,
        "x_param": x_param,
        "y_param": y_param,
        "param_labels": {name: meta["label"] for name, meta in params_spec.items()},
        "x_values": x_values,
        "y_values": y_values,
        "total_combinations": combinations,
        "valid_combinations": len(ranked),
        "best": best,
        "top": ranked[:20],
        "results": results,
        "heatmap": {"x_values": x_values, "y_values": y_values, "cells": cells},
    }


def run_optimization_cell(
    records: list[dict[str, Any]],
    *,
    template_key: str,
    params: dict[str, Any],
    objective: str,
    initial_capital: float,
    fee_bps: float,
    target_percent: float,
    capacity_participation: float,
) -> dict[str, Any]:
    try:
        entry_expression, exit_expression = template_expressions(template_key, params)
        result = _run_backtest_once(
            records,
            entry_expression=entry_expression,
            exit_expression=exit_expression,
            initial_capital=initial_capital,
            fee_bps=fee_bps,
            target_percent=target_percent,
            capacity_participation=capacity_participation,
        )
    except (DslError, ValueError, RuntimeError) as exc:
        return {"ok": False, "params": params.copy(), "score": None, "error": str(exc)}
    metrics = result["metrics"]
    score = metrics.get(objective)
    return {
        "ok": score is not None,
        "params": params.copy(),
        "score": score,
        "metrics": {
            "final_equity": metrics.get("final_equity"),
            "total_return": metrics.get("total_return"),
            "annual_return": metrics.get("annual_return"),
            "sharpe": metrics.get("sharpe"),
            "calmar": metrics.get("calmar"),
            "max_drawdown": metrics.get("max_drawdown"),
            "turnover": metrics.get("turnover"),
            "annualized_turnover": metrics.get("annualized_turnover"),
            "total_fees": metrics.get("total_fees"),
            "cost_drag": metrics.get("cost_drag"),
            "max_fill_participation": metrics.get("max_fill_participation"),
            "trade_count": metrics.get("trade_count"),
        },
        "entry_expression": entry_expression,
        "exit_expression": exit_expression,
    }


def range_values(payload: dict[str, float], spec: dict[str, Any]) -> list[int | float]:
    start = float(payload.get("min", spec["min"]))
    end = float(payload.get("max", spec["max"]))
    step = float(payload.get("step", spec["step"]))
    if step <= 0:
        raise ValueError("range step must be positive")
    if start > end:
        raise ValueError("range min must be <= max")
    values = []
    current = start
    guard = 0
    while current <= end + step * 1e-9:
        values.append(cast_param(current, spec))
        current += step
        guard += 1
        if guard > 2000:
            raise ValueError("range produced too many values")
    return values


def cast_param(value: float, spec: dict[str, Any]) -> int | float:
    if spec.get("type") == "int":
        return int(round(float(value)))
    return round(float(value), 6)


def is_better(row: dict[str, Any], best: dict[str, Any] | None, objective: str) -> bool:
    if best is None:
        return True
    score = row.get("score")
    best_score = best.get("score")
    if score is None:
        return False
    if best_score is None:
        return True
    return score < best_score if objective == "max_drawdown" else score > best_score


def _run_backtest_once(
    records: list[dict[str, Any]],
    *,
    entry_expression: str,
    exit_expression: str,
    initial_capital: float = 100000.0,
    fee_bps: float = 0.0,
    target_percent: float = 0.98,
    capacity_participation: float = 0.05,
) -> dict[str, Any]:
    if bt is None:
        raise RuntimeError(
            "Missing dependency: backtrader. Install with `python3 -m pip install -r backtest/requirements.txt`."
        ) from BACKTRADER_IMPORT_ERROR
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if fee_bps < 0:
        raise ValueError("fee_bps must be non-negative")
    if not 0 < target_percent <= 1:
        raise ValueError("target_percent must be in (0, 1]")
    if not 0 < capacity_participation <= 1:
        raise ValueError("capacity_participation must be in (0, 1]")

    frame = build_backtest_frame(records, entry_expression, exit_expression)
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(float(initial_capital))
    cerebro.broker.setcommission(commission=float(fee_bps) / 10000.0)
    data = SignalPandasData(dataname=frame)
    cerebro.adddata(data)
    cerebro.addstrategy(
        DslSignalStrategy,
        target_percent=float(target_percent),
        entry_reason=entry_expression,
        exit_reason=exit_expression,
    )
    strategy = cerebro.run(runonce=False)[0]
    equity = strategy.equity_curve
    if equity and equity[0]["time"] != frame.index[0].date().isoformat():
        equity.insert(0, {"time": frame.index[0].date().isoformat(), "value": round(float(initial_capital), 6), "position": 0.0})
    elif not equity:
        equity = [{"time": frame.index[0].date().isoformat(), "value": round(float(initial_capital), 6), "position": 0.0}]

    liquidity = liquidity_profile(records, target_percent=target_percent, capacity_participation=capacity_participation)
    fills = annotate_fill_participation(strategy.fills, liquidity["daily_traded_value_by_date"])
    metrics = compute_metrics(equity, strategy.trades, fills, initial_capital)
    return {
        "entry_expression": entry_expression,
        "exit_expression": exit_expression,
        "initial_capital": initial_capital,
        "fee_bps": fee_bps,
        "target_percent": target_percent,
        "capacity_participation": capacity_participation,
        "signals": {
            "entry_count": int(frame["entry_signal"].sum()),
            "exit_count": int(frame["exit_signal"].sum()),
        },
        "equity": [{"time": point["time"], "value": point["value"]} for point in equity],
        "trades": strategy.trades,
        "fills": fills,
        "metrics": metrics,
        "liquidity": {key: value for key, value in liquidity.items() if key != "daily_traded_value_by_date"},
    }


def compute_metrics(
    equity: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    initial_capital: float,
) -> dict[str, Any]:
    values = np.asarray([float(point["value"]) for point in equity], dtype=float)
    final_equity = float(values[-1]) if values.size else float(initial_capital)
    total_return = final_equity / float(initial_capital) - 1.0
    periods = max(len(values) - 1, 1)
    years = periods / TRADING_DAYS
    annual_return = (final_equity / float(initial_capital)) ** (1.0 / years) - 1.0 if final_equity > 0 else -1.0
    returns = values[1:] / values[:-1] - 1.0 if values.size > 1 else np.asarray([], dtype=float)
    returns = returns[np.isfinite(returns)]
    annual_volatility = float(np.std(returns, ddof=1) * math.sqrt(TRADING_DAYS)) if returns.size > 1 else None
    sharpe = float(np.mean(returns) / np.std(returns, ddof=1) * math.sqrt(TRADING_DAYS)) if returns.size > 1 and np.std(returns, ddof=1) > 0 else None
    negative = returns[returns < 0]
    sortino = (
        float(np.mean(returns) / np.std(negative, ddof=1) * math.sqrt(TRADING_DAYS))
        if returns.size > 1 and negative.size > 1 and np.std(negative, ddof=1) > 0
        else None
    )
    drawdown = drawdown_series(values)
    max_drawdown = abs(float(np.min(drawdown))) if drawdown.size else 0.0
    calmar = float(annual_return / max_drawdown) if max_drawdown > 0 else None
    wins = [trade for trade in trades if (trade.get("netPnl") or 0) > 0]
    losses = [trade for trade in trades if (trade.get("netPnl") or 0) < 0]
    gross_profit = sum(float(trade["netPnl"]) for trade in wins)
    gross_loss = abs(sum(float(trade["netPnl"]) for trade in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else None)
    total_traded_value = sum(float(fill.get("value") or 0.0) for fill in fills)
    total_fees = sum(float(fill.get("fee") or 0.0) for fill in fills)
    average_equity = float(np.mean(values)) if values.size else float(initial_capital)
    turnover = total_traded_value / average_equity if average_equity > 0 else None
    annualized_turnover = turnover / years if turnover is not None and years > 0 else None
    fee_rate_on_traded_value_bps = total_fees / total_traded_value * 10000.0 if total_traded_value > 0 else None
    max_fill_participation = max((float(fill.get("participation") or 0.0) for fill in fills), default=None)
    return {
        "final_equity": round(final_equity, 6),
        "total_return": clean_metric(total_return),
        "annual_return": clean_metric(annual_return),
        "annual_volatility": clean_metric(annual_volatility),
        "sharpe": clean_metric(sharpe),
        "sortino": clean_metric(sortino),
        "calmar": clean_metric(calmar),
        "max_drawdown": clean_metric(max_drawdown),
        "win_rate": clean_metric(len(wins) / len(trades)) if trades else None,
        "profit_factor": clean_metric(profit_factor),
        "trade_count": len(trades),
        "gross_profit": clean_metric(gross_profit),
        "gross_loss": clean_metric(gross_loss),
        "average_trade_return": clean_metric(np.mean([trade["returnPct"] for trade in trades if trade.get("returnPct") is not None]))
        if trades
        else None,
        "total_traded_value": clean_metric(total_traded_value),
        "total_fees": clean_metric(total_fees),
        "fee_rate_on_traded_value_bps": clean_metric(fee_rate_on_traded_value_bps),
        "cost_drag": clean_metric(total_fees / initial_capital),
        "turnover": clean_metric(turnover),
        "annualized_turnover": clean_metric(annualized_turnover),
        "max_fill_participation": clean_metric(max_fill_participation),
    }


def liquidity_profile(
    records: list[dict[str, Any]],
    *,
    target_percent: float,
    capacity_participation: float,
) -> dict[str, Any]:
    df = pd.DataFrame.from_records(records)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date.astype(str)
    close = pd.to_numeric(df["close"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce")
    amount = pd.to_numeric(df.get("amount"), errors="coerce") if "amount" in df else pd.Series(np.nan, index=df.index)
    traded_value = amount.where(amount > 0, close * volume)
    traded_value = traded_value.replace([np.inf, -np.inf], np.nan).dropna()
    by_date = dict(zip(df.loc[traded_value.index, "trade_date"], traded_value.astype(float), strict=False))
    if traded_value.empty:
        return {
            "daily_traded_value_by_date": {},
            "median_daily_traded_value": None,
            "p20_daily_traded_value": None,
            "p10_daily_traded_value": None,
            "capacity_at_participation": None,
            "capacity_participation": clean_metric(capacity_participation),
        }
    p20 = float(np.percentile(traded_value, 20))
    return {
        "daily_traded_value_by_date": by_date,
        "median_daily_traded_value": clean_metric(float(np.median(traded_value))),
        "p20_daily_traded_value": clean_metric(p20),
        "p10_daily_traded_value": clean_metric(float(np.percentile(traded_value, 10))),
        "capacity_at_participation": clean_metric((p20 * capacity_participation) / target_percent),
        "capacity_participation": clean_metric(capacity_participation),
    }


def annotate_fill_participation(fills: list[dict[str, Any]], daily_traded_value_by_date: dict[str, float]) -> list[dict[str, Any]]:
    annotated = []
    for fill in fills:
        row = fill.copy()
        daily_value = daily_traded_value_by_date.get(str(fill.get("date")))
        row["dailyTradedValue"] = clean_metric(daily_value)
        row["participation"] = clean_metric((float(fill.get("value") or 0.0) / daily_value) if daily_value and daily_value > 0 else None)
        annotated.append(row)
    return annotated


def monte_carlo_shuffle(equity: list[dict[str, Any]], *, runs: int = 300, seed: int = 20260901) -> dict[str, Any]:
    if runs <= 0:
        return {"enabled": False, "runs": 0, "reason": "monte_carlo_runs <= 0"}
    values = np.asarray([float(point["value"]) for point in equity], dtype=float)
    if values.size < 3:
        return {"enabled": False, "runs": 0, "reason": "equity curve is too short"}
    returns = values[1:] / values[:-1] - 1.0
    returns = returns[np.isfinite(returns)]
    if returns.size < 2:
        return {"enabled": False, "runs": 0, "reason": "not enough finite returns"}
    rng = np.random.default_rng(seed)
    terminal_returns = []
    max_drawdowns = []
    sharpes = []
    for _ in range(int(runs)):
        shuffled = rng.permutation(returns)
        path = np.empty(shuffled.size + 1)
        path[0] = 1.0
        path[1:] = np.cumprod(1.0 + shuffled)
        terminal_returns.append(float(path[-1] - 1.0))
        max_drawdowns.append(abs(float(np.min(drawdown_series(path)))))
        std = np.std(shuffled, ddof=1)
        sharpes.append(float(np.mean(shuffled) / std * math.sqrt(TRADING_DAYS)) if std > 0 else np.nan)
    return {
        "enabled": True,
        "runs": int(runs),
        "method": "shuffle_daily_returns_without_replacement",
        "terminal_return": percentile_summary(terminal_returns),
        "max_drawdown": percentile_summary(max_drawdowns),
        "sharpe": percentile_summary(sharpes),
        "terminal_return_histogram": histogram_bins(terminal_returns),
        "max_drawdown_histogram": histogram_bins(max_drawdowns),
        "sharpe_histogram": histogram_bins(sharpes),
    }


def walk_forward(
    records: list[dict[str, Any]],
    *,
    entry_expression: str,
    exit_expression: str,
    initial_capital: float,
    fee_bps: float,
    target_percent: float,
    capacity_participation: float,
    window: int,
    step: int,
) -> dict[str, Any]:
    if window <= 20 or step <= 0:
        return {"enabled": False, "windows": [], "reason": "invalid window or step"}
    warmup = estimate_dsl_lookback(entry_expression, exit_expression)
    required = window + warmup
    if len(records) < required:
        return {
            "enabled": False,
            "windows": [],
            "reason": f"not enough bars for requested window plus DSL warmup ({window}+{warmup})",
            "warmup_bars": int(warmup),
        }
    windows = []
    for start in range(0, len(records) - required + 1, step):
        eval_start_idx = start + warmup
        eval_end_idx = eval_start_idx + window
        subset = records[start:eval_end_idx]
        eval_start_date = records[eval_start_idx]["trade_date"]
        eval_end_date = records[eval_end_idx - 1]["trade_date"]
        try:
            result = _run_backtest_once(
                subset,
                entry_expression=entry_expression,
                exit_expression=exit_expression,
                initial_capital=initial_capital,
                fee_bps=fee_bps,
                target_percent=target_percent,
                capacity_participation=capacity_participation,
            )
        except (DslError, ValueError, RuntimeError) as exc:
            windows.append(
                {
                    "start_date": eval_start_date,
                    "end_date": eval_end_date,
                    "warmup_start_date": subset[0]["trade_date"],
                    "ok": False,
                    "error": str(exc),
                }
            )
            continue
        eval_equity = equity_window(result["equity"], eval_start_date, eval_end_date)
        eval_initial_capital = float(eval_equity[0]["value"]) if eval_equity else initial_capital
        eval_trades = [
            trade
            for trade in result["trades"]
            if eval_start_date <= str(trade.get("exitDate", "")) <= eval_end_date
        ]
        eval_fills = [
            fill
            for fill in result["fills"]
            if eval_start_date <= str(fill.get("date", "")) <= eval_end_date
        ]
        metrics = compute_metrics(eval_equity, eval_trades, eval_fills, eval_initial_capital)
        windows.append(
            {
                "start_date": eval_start_date,
                "end_date": eval_end_date,
                "warmup_start_date": subset[0]["trade_date"],
                "ok": True,
                "total_return": metrics["total_return"],
                "annual_return": metrics["annual_return"],
                "sharpe": metrics["sharpe"],
                "calmar": metrics["calmar"],
                "max_drawdown": metrics["max_drawdown"],
                "turnover": metrics["turnover"],
                "trade_count": metrics["trade_count"],
            }
        )
    ok_windows = [row for row in windows if row.get("ok")]
    returns = [row["total_return"] for row in ok_windows if row.get("total_return") is not None]
    sharpes = [row["sharpe"] for row in ok_windows if row.get("sharpe") is not None]
    drawdowns = [row["max_drawdown"] for row in ok_windows if row.get("max_drawdown") is not None]
    return {
        "enabled": True,
        "window": int(window),
        "step": int(step),
        "warmup_bars": int(warmup),
        "windows": windows,
        "summary": {
            "window_count": len(ok_windows),
            "positive_window_rate": clean_metric(sum(1 for value in returns if value > 0) / len(returns)) if returns else None,
            "median_total_return": clean_metric(np.median(returns)) if returns else None,
            "worst_total_return": clean_metric(min(returns)) if returns else None,
            "median_sharpe": clean_metric(np.median(sharpes)) if sharpes else None,
            "worst_max_drawdown": clean_metric(max(drawdowns)) if drawdowns else None,
        },
    }


def equity_window(equity: list[dict[str, Any]], start_date: str, end_date: str) -> list[dict[str, Any]]:
    rows = [point for point in equity if start_date <= str(point.get("time", "")) <= end_date]
    if not rows:
        return []
    initial = float(rows[0]["value"])
    return [
        {
            "time": point["time"],
            "value": clean_metric(float(point["value"]) / initial * initial) if initial > 0 else point["value"],
        }
        for point in rows
    ]


def estimate_dsl_lookback(*expressions: str) -> int:
    lookback = 0
    period_functions = {
        "sma",
        "ma",
        "ema",
        "rsi",
        "std",
        "rolling_mean",
        "rolling_std",
        "rolling_max",
        "rolling_min",
        "shift",
        "pct_change",
    }
    for expression in expressions:
        try:
            tree = ast.parse(expression or "", mode="eval")
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in period_functions or len(node.args) < 2:
                continue
            period = numeric_constant(node.args[1])
            if period is not None:
                lookback = max(lookback, int(abs(period)))
    return max(1, lookback)


def numeric_constant(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = numeric_constant(node.operand)
        return -value if value is not None else None
    return None


def percentile_summary(values: list[float]) -> dict[str, float | None]:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"p01": None, "p05": None, "p50": None, "p95": None, "p99": None, "min": None, "max": None}
    return {
        "p01": clean_metric(np.percentile(arr, 1)),
        "p05": clean_metric(np.percentile(arr, 5)),
        "p50": clean_metric(np.percentile(arr, 50)),
        "p95": clean_metric(np.percentile(arr, 95)),
        "p99": clean_metric(np.percentile(arr, 99)),
        "min": clean_metric(float(np.min(arr))),
        "max": clean_metric(float(np.max(arr))),
    }


def histogram_bins(values: list[float], bins: int = 18) -> list[dict[str, float | int | None]]:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return []
    min_value = float(np.min(arr))
    max_value = float(np.max(arr))
    if min_value == max_value or math.isclose(min_value, max_value, rel_tol=1e-12, abs_tol=1e-12):
        value = clean_metric(float(np.mean(arr)))
        return [{"start": value, "end": value, "mid": value, "count": int(arr.size)}]
    counts, edges = np.histogram(arr, bins=bins)
    result = []
    for idx, count in enumerate(counts):
        start = float(edges[idx])
        end = float(edges[idx + 1])
        result.append(
            {
                "start": clean_metric(start),
                "end": clean_metric(end),
                "mid": clean_metric((start + end) / 2.0),
                "count": int(count),
            }
        )
    return result


def drawdown_series(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return np.asarray([], dtype=float)
    peak = np.maximum.accumulate(values)
    with np.errstate(divide="ignore", invalid="ignore"):
        return values / peak - 1.0


def clean_metric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        return None
    return round(float(value), 8)
