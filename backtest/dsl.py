#!/usr/bin/env python3
"""Safe time-series factor DSL for QuantSystem backtests."""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np


class DslError(ValueError):
    """Raised when a DSL expression is invalid or cannot be evaluated."""


@dataclass(frozen=True)
class DslResult:
    values: np.ndarray
    expression: str


SERIES_NAMES = {"open", "high", "low", "close", "volume", "amount"}


def evaluate_signal(expression: str, data: dict[str, Any]) -> DslResult:
    """Evaluate a DSL expression and return a boolean vector."""
    values = evaluate(expression, data)
    if values.dtype != bool:
        values = np.asarray(values, dtype=float)
        values = np.where(np.isfinite(values), values != 0, False)
    return DslResult(values=np.asarray(values, dtype=bool), expression=expression)


def evaluate(expression: str, data: dict[str, Any]) -> np.ndarray:
    expression = expression.strip()
    if not expression:
        raise DslError("DSL expression must not be empty")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise DslError(f"Invalid DSL syntax: {exc.msg}") from exc

    length = infer_length(data)
    evaluator = _Evaluator(data, length)
    values = evaluator.visit(tree)
    return evaluator.to_series(values)


def infer_length(data: dict[str, Any]) -> int:
    for name in SERIES_NAMES:
        if name in data:
            return len(data[name])
    raise DslError("DSL data must include at least one OHLCV series")


class _Evaluator(ast.NodeVisitor):
    def __init__(self, data: dict[str, Any], length: int):
        self.data = {key: np.asarray(value, dtype=float) for key, value in data.items() if key in SERIES_NAMES}
        self.length = length
        self.functions: dict[str, Callable[..., Any]] = {
            "ma": rolling_mean,
            "sma": rolling_mean,
            "ema": ema,
            "rsi": rsi,
            "std": rolling_std,
            "rolling_mean": rolling_mean,
            "rolling_std": rolling_std,
            "rolling_max": rolling_max,
            "rolling_min": rolling_min,
            "shift": shift,
            "pct_change": pct_change,
            "cross_over": cross_over,
            "cross_under": cross_under,
            "abs": np.abs,
            "log": safe_log,
            "sqrt": safe_sqrt,
            "min": np.minimum,
            "max": np.maximum,
        }

    def generic_visit(self, node: ast.AST):
        raise DslError(f"Unsupported DSL syntax: {type(node).__name__}")

    def visit_Expression(self, node: ast.Expression):
        return self.visit(node.body)

    def visit_Name(self, node: ast.Name):
        if node.id not in self.data:
            raise DslError(f"Unknown series name: {node.id}")
        return self.data[node.id]

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise DslError("Only numeric and boolean constants are allowed")

    def visit_Call(self, node: ast.Call):
        if not isinstance(node.func, ast.Name):
            raise DslError("Only direct function calls are allowed")
        if node.keywords:
            raise DslError("Keyword arguments are not supported in DSL calls")
        func = self.functions.get(node.func.id)
        if func is None:
            raise DslError(f"Unsupported DSL function: {node.func.id}")
        args = [self.visit(arg) for arg in node.args]
        try:
            return func(*args)
        except (TypeError, ValueError, FloatingPointError) as exc:
            raise DslError(f"{node.func.id}() failed: {exc}") from exc

    def visit_UnaryOp(self, node: ast.UnaryOp):
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            return -self.to_series(operand)
        if isinstance(node.op, ast.UAdd):
            return self.to_series(operand)
        if isinstance(node.op, ast.Not):
            return ~self.to_bool_series(operand)
        raise DslError(f"Unsupported unary operator: {type(node.op).__name__}")

    def visit_BinOp(self, node: ast.BinOp):
        left = self.to_series(self.visit(node.left))
        right = self.to_series(self.visit(node.right))
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                return left**right
        raise DslError(f"Unsupported binary operator: {type(node.op).__name__}")

    def visit_BoolOp(self, node: ast.BoolOp):
        values = [self.to_bool_series(self.visit(value)) for value in node.values]
        if not values:
            raise DslError("Empty boolean expression")
        result = values[0]
        for value in values[1:]:
            if isinstance(node.op, ast.And):
                result = result & value
            elif isinstance(node.op, ast.Or):
                result = result | value
            else:
                raise DslError(f"Unsupported boolean operator: {type(node.op).__name__}")
        return result

    def visit_Compare(self, node: ast.Compare):
        left = self.to_series(self.visit(node.left))
        result = np.ones(self.length, dtype=bool)
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            right = self.to_series(self.visit(comparator))
            with np.errstate(invalid="ignore"):
                if isinstance(op, ast.Gt):
                    current = left > right
                elif isinstance(op, ast.GtE):
                    current = left >= right
                elif isinstance(op, ast.Lt):
                    current = left < right
                elif isinstance(op, ast.LtE):
                    current = left <= right
                elif isinstance(op, ast.Eq):
                    current = left == right
                elif isinstance(op, ast.NotEq):
                    current = left != right
                else:
                    raise DslError(f"Unsupported comparison operator: {type(op).__name__}")
            result = result & np.asarray(current, dtype=bool)
            left = right
        return result

    def to_series(self, value: Any) -> np.ndarray:
        if isinstance(value, np.ndarray):
            if len(value) != self.length:
                raise DslError(f"Series length mismatch: expected {self.length}, got {len(value)}")
            return value
        if isinstance(value, (int, float, bool, np.number)):
            return np.full(self.length, float(value))
        raise DslError(f"Unsupported value type: {type(value).__name__}")

    def to_bool_series(self, value: Any) -> np.ndarray:
        arr = self.to_series(value)
        if arr.dtype == bool:
            return arr
        return np.where(np.isfinite(arr), arr != 0, False)


def as_period(value: Any, name: str = "period") -> int:
    if isinstance(value, np.ndarray):
        if value.size != 1 and not np.all(value == value[0]):
            raise ValueError(f"{name} must be a scalar")
        value = value.flat[0]
    period = int(value)
    if period < 1:
        raise ValueError(f"{name} must be >= 1")
    return period


def rolling_mean(series: Any, period: Any) -> np.ndarray:
    arr = np.asarray(series, dtype=float)
    window = as_period(period)
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        values = arr[i - window + 1 : i + 1]
        if np.isfinite(values).all():
            out[i] = float(values.mean())
    return out


def rolling_std(series: Any, period: Any) -> np.ndarray:
    arr = np.asarray(series, dtype=float)
    window = as_period(period)
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        values = arr[i - window + 1 : i + 1]
        if np.isfinite(values).all():
            out[i] = float(values.std(ddof=0))
    return out


def rolling_max(series: Any, period: Any) -> np.ndarray:
    arr = np.asarray(series, dtype=float)
    window = as_period(period)
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        values = arr[i - window + 1 : i + 1]
        if np.isfinite(values).all():
            out[i] = float(values.max())
    return out


def rolling_min(series: Any, period: Any) -> np.ndarray:
    arr = np.asarray(series, dtype=float)
    window = as_period(period)
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        values = arr[i - window + 1 : i + 1]
        if np.isfinite(values).all():
            out[i] = float(values.min())
    return out


def ema(series: Any, period: Any) -> np.ndarray:
    arr = np.asarray(series, dtype=float)
    window = as_period(period)
    out = np.full(len(arr), np.nan)
    if len(arr) < window:
        return out
    alpha = 2.0 / (window + 1.0)
    first = arr[:window]
    if not np.isfinite(first).all():
        return out
    out[window - 1] = first.mean()
    for i in range(window, len(arr)):
        if not math.isfinite(arr[i]) or not math.isfinite(out[i - 1]):
            continue
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out


def rsi(series: Any, period: Any = 14) -> np.ndarray:
    arr = np.asarray(series, dtype=float)
    window = as_period(period)
    out = np.full(len(arr), np.nan)
    if len(arr) <= window:
        return out
    delta = np.diff(arr)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_gain = gains[:window].mean()
    avg_loss = losses[:window].mean()
    out[window] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    for i in range(window + 1, len(arr)):
        avg_gain = (avg_gain * (window - 1) + gains[i - 1]) / window
        avg_loss = (avg_loss * (window - 1) + losses[i - 1]) / window
        out[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return out


def shift(series: Any, periods: Any = 1) -> np.ndarray:
    arr = np.asarray(series, dtype=float)
    steps = as_period(abs(periods), "periods")
    if float(periods) < 0:
        out = np.full(len(arr), np.nan)
        out[:-steps] = arr[steps:]
        return out
    out = np.full(len(arr), np.nan)
    out[steps:] = arr[:-steps]
    return out


def pct_change(series: Any, periods: Any = 1) -> np.ndarray:
    arr = np.asarray(series, dtype=float)
    prev = shift(arr, periods)
    with np.errstate(divide="ignore", invalid="ignore"):
        return arr / prev - 1.0


def cross_over(left: Any, right: Any) -> np.ndarray:
    a = np.asarray(left, dtype=float)
    b = np.asarray(right, dtype=float)
    prev_a = shift(a, 1)
    prev_b = shift(b, 1)
    with np.errstate(invalid="ignore"):
        return (prev_a <= prev_b) & (a > b)


def cross_under(left: Any, right: Any) -> np.ndarray:
    a = np.asarray(left, dtype=float)
    b = np.asarray(right, dtype=float)
    prev_a = shift(a, 1)
    prev_b = shift(b, 1)
    with np.errstate(invalid="ignore"):
        return (prev_a >= prev_b) & (a < b)


def safe_log(series: Any) -> np.ndarray:
    arr = np.asarray(series, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(arr > 0, np.log(arr), np.nan)


def safe_sqrt(series: Any) -> np.ndarray:
    arr = np.asarray(series, dtype=float)
    with np.errstate(invalid="ignore"):
        return np.where(arr >= 0, np.sqrt(arr), np.nan)
