from datetime import date, timedelta
import math
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import histogram_bins, optimize_parameters, run_backtest


def sample_records(days: int = 80):
    records = []
    start = date(2024, 1, 1)
    price = 10.0
    for i in range(days):
        price += 0.08 if i < days // 2 else -0.04
        records.append(
            {
                "trade_date": (start + timedelta(days=i)).isoformat(),
                "open": price,
                "high": price * 1.02,
                "low": price * 0.98,
                "close": price * 1.01,
                "volume": 100000 + i,
                "amount": None,
            }
        )
    return records


def oscillating_records(days: int = 420):
    records = []
    start = date(2023, 1, 1)
    for i in range(days):
        price = 30 + 0.03 * i + 4.0 * math.sin(i / 12)
        records.append(
            {
                "trade_date": (start + timedelta(days=i)).isoformat(),
                "open": price * 0.995,
                "high": price * 1.03,
                "low": price * 0.97,
                "close": price,
                "volume": 200000 + i * 10,
                "amount": price * (200000 + i * 10),
            }
        )
    return records


def test_backtrader_dual_ma_backtest_runs():
    pytest.importorskip("backtrader")
    result = run_backtest(
        sample_records(),
        entry_expression="cross_over(sma(close, 3), sma(close, 8))",
        exit_expression="cross_under(sma(close, 3), sma(close, 8))",
        initial_capital=100000,
        fee_bps=1,
    )
    assert result["metrics"]["final_equity"] > 0
    assert "sharpe" in result["metrics"]
    assert "calmar" in result["metrics"]
    assert "max_drawdown" in result["metrics"]
    assert "turnover" in result["metrics"]
    assert "total_fees" in result["metrics"]
    assert "capacity_at_participation" in result["liquidity"]
    assert "monte_carlo" in result["robustness"]
    assert "walk_forward" in result["robustness"]
    assert result["robustness"]["monte_carlo"]["terminal_return_histogram"]
    assert result["robustness"]["monte_carlo"]["max_drawdown_histogram"]
    assert result["signals"]["entry_count"] >= 0


def test_histogram_handles_nearly_constant_values():
    bins = histogram_bins([1.0, 1.0 + 1e-14, 1.0 - 1e-14], bins=18)
    assert bins == [{"start": 1.0, "end": 1.0, "mid": 1.0, "count": 3}]


def test_dual_ma_parameter_optimization_grid_runs():
    pytest.importorskip("backtrader")
    result = optimize_parameters(
        sample_records(120),
        template_key="dual_ma",
        x_param="fast",
        y_param="slow",
        ranges={"fast": {"min": 3, "max": 6, "step": 3}, "slow": {"min": 12, "max": 18, "step": 6}},
        objective="total_return",
        initial_capital=100000,
        fee_bps=1,
        max_combinations=20,
    )
    assert result["total_combinations"] == 4
    assert result["valid_combinations"] >= 1
    assert result["best"]["ok"] is True
    assert result["heatmap"]["x_values"] == [3, 6]
    assert result["heatmap"]["y_values"] == [12, 18]
    assert len(result["heatmap"]["cells"]) == 2
    assert "entry_expression" in result["best"]


def test_walk_forward_uses_dsl_warmup_when_window_is_shorter_than_indicator():
    pytest.importorskip("backtrader")
    result = run_backtest(
        oscillating_records(),
        entry_expression="cross_over(sma(close, 32), sma(close, 140))",
        exit_expression="cross_under(sma(close, 32), sma(close, 140))",
        initial_capital=100000,
        fee_bps=1,
        monte_carlo_runs=0,
        walk_forward_window=125,
        walk_forward_step=20,
    )
    walk = result["robustness"]["walk_forward"]
    assert walk["enabled"] is True
    assert walk["warmup_bars"] == 140
    assert walk["windows"]
    assert any(row["total_return"] != 0 for row in walk["windows"] if row["ok"])
