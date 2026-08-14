"""Phase 5: deterministic indicator tests on known series (§14)."""

import numpy as np
import pandas as pd

from app.signals import indicators as ind


def test_sma_known_values():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = ind.sma(s, 3)
    assert np.isnan(out.iloc[1])
    assert out.iloc[2] == 2.0  # (1+2+3)/3
    assert out.iloc[4] == 4.0  # (3+4+5)/3


def test_rsi_all_gains_is_100():
    s = pd.Series(range(1, 30), dtype=float)  # strictly increasing
    r = ind.rsi(s, 14)
    assert r.iloc[-1] == 100.0


def test_rsi_bounded_0_100():
    rng = np.linspace(100, 50, 40) + np.sin(np.arange(40))
    r = ind.rsi(pd.Series(rng), 14).dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_macd_zero_for_constant_series():
    s = pd.Series([100.0] * 60)
    m = ind.macd(s)
    # Constant price -> fast EMA == slow EMA -> macd line 0.
    assert abs(m["macd_line"].iloc[-1]) < 1e-9
    assert abs(m["macd_hist"].iloc[-1]) < 1e-9


def test_atr_positive_and_reasonable():
    n = 30
    high = pd.Series(np.full(n, 110.0))
    low = pd.Series(np.full(n, 90.0))
    close = pd.Series(np.full(n, 100.0))
    a = ind.atr(high, low, close, 14).dropna()
    # True range each bar is 20 (high-low); ATR should converge near 20.
    assert 15 < a.iloc[-1] <= 20


def test_compute_indicators_columns():
    n = 80
    df = pd.DataFrame(
        {
            "open": np.linspace(100, 180, n),
            "high": np.linspace(101, 182, n),
            "low": np.linspace(99, 178, n),
            "close": np.linspace(100, 180, n),
            "volume": np.full(n, 1000),
        }
    )
    out = ind.compute_indicators(df)
    assert list(out.columns) == ind.INDICATOR_NAMES
    # Uptrend: SMA20 should exceed SMA50 at the end.
    assert out["sma_20"].iloc[-1] > out["sma_50"].iloc[-1]
