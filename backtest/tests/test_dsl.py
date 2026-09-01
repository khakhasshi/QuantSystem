from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dsl import DslError, evaluate_signal


def test_dual_ma_cross_over_signal():
    close = np.array([10, 9, 8, 9, 10, 11, 12], dtype=float)
    result = evaluate_signal("cross_over(sma(close, 2), sma(close, 3))", {"close": close})
    assert result.values.tolist() == [False, False, False, False, True, False, False]


def test_comparison_and_boolean_dsl():
    data = {"close": np.array([1, 2, 3, 4, 5], dtype=float), "volume": np.array([5, 4, 3, 2, 1], dtype=float)}
    result = evaluate_signal("close > sma(close, 3) and volume < shift(volume, 1)", data)
    assert result.values.tolist() == [False, False, True, True, True]


def test_rejects_unsafe_syntax():
    with pytest.raises(DslError):
        evaluate_signal("__import__('os').system('echo nope')", {"close": np.array([1, 2, 3], dtype=float)})
