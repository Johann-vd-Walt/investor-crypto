"""Technical indicators computed directly in pandas (§10).

We compute the five indicators the spec uses (SMA, EMA, RSI, MACD, ATR) here
rather than depending on pandas-ta / TA-Lib — pandas-ta's numba dependency has
no Python 3.14 wheel, and hand-rolling these keeps the maths transparent and
deterministically testable (§14).

All functions are pure and operate on pandas Series/DataFrames. Prices are in
cents (ZAc); indicator outputs are in the same unit as their input (RSI is a
0..100 oscillator).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Indicator names as stored in the ``indicator_values`` cache / API.
INDICATOR_NAMES = [
    "sma_20", "sma_50", "ema_12", "ema_26",
    "rsi_14", "macd_line", "macd_signal", "macd_hist", "atr_14",
]


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (0..100)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder smoothing via EWM alpha = 1/period.
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    out = 100 - (100 / (1 + rs))
    # avg_loss == 0 with gains -> 100 (pure uptrend); no movement at all -> 50
    # (neutral, NOT 100 — a flat series has no momentum).
    out = out.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    out = out.where(~((avg_loss == 0) & (avg_gain == 0)), 50.0)
    return out


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """Return a frame with macd_line, macd_signal, macd_hist."""
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line
    return pd.DataFrame(
        {"macd_line": macd_line, "macd_signal": signal_line, "macd_hist": hist}
    )


def atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Average True Range (Wilder). Same unit as price (cents)."""
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all indicators for an OHLCV frame indexed by bar_datetime.

    ``df`` must have columns: open, high, low, close, volume. Returns a frame
    (same index) with the INDICATOR_NAMES columns. Rows lacking enough history
    contain NaN, which the caller stores as NULL (never fabricated).
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    out = pd.DataFrame(index=df.index)
    out["sma_20"] = sma(close, 20)
    out["sma_50"] = sma(close, 50)
    out["ema_12"] = ema(close, 12)
    out["ema_26"] = ema(close, 26)
    out["rsi_14"] = rsi(close, 14)
    macd_frame = macd(close)
    out["macd_line"] = macd_frame["macd_line"]
    out["macd_signal"] = macd_frame["macd_signal"]
    out["macd_hist"] = macd_frame["macd_hist"]
    out["atr_14"] = atr(high, low, close, 14)
    return out
