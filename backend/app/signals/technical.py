"""Per-stock technical score (§10).

Combines a days-to-weeks toolkit — SMA/EMA trend, RSI, MACD, and a volume-
confirmed breakout — into a score in [-1, 1], recording each sub-signal that
fired. Also surfaces the latest ATR (for volatility-based stops) and close.

Pure function of an OHLCV DataFrame; deterministic and unit-tested (§14).
"""

from __future__ import annotations

import math

import pandas as pd

from app.signals import indicators as ind
from app.signals.scoring import LayerScore, SubSignal, clamp

# Sub-signal weights (pre-clamp). Tuned to be transparent, not magic.
_W_TREND_CROSS = 0.30
_W_PRICE_VS_SMA = 0.10
_W_RSI = 0.25
_W_MACD = 0.20
_W_BREAKOUT = 0.25

_BREAKOUT_LOOKBACK = 20
_BREAKOUT_VOL_MULT = 1.5

# Relative neutral band so a flat / near-equal series scores neutral, not
# spuriously bearish (values within this fraction are treated as "equal").
_EPS = 1e-6


def _valid(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def technical_score(df: pd.DataFrame) -> LayerScore:
    """Score the latest bar of ``df`` (OHLCV, ascending by date)."""
    if df is None or len(df) < 50:
        return LayerScore(score=0.0, subsignals=[], extra={"note": "insufficient history (<50 bars)"})

    ci = ind.compute_indicators(df)
    last = ci.iloc[-1]
    close = float(df["close"].iloc[-1])

    subs: list[SubSignal] = []
    score = 0.0

    # 1) Trend: SMA20 vs SMA50 (golden/death cross state). Near-equal = neutral.
    if _valid(last["sma_20"]) and _valid(last["sma_50"]) and last["sma_50"]:
        diff = (last["sma_20"] - last["sma_50"]) / abs(last["sma_50"])
        if diff > _EPS:
            subs.append(SubSignal("sma_cross", "SMA20 above SMA50 (uptrend)", _W_TREND_CROSS))
            score += _W_TREND_CROSS
        elif diff < -_EPS:
            subs.append(SubSignal("sma_cross", "SMA20 below SMA50 (downtrend)", -_W_TREND_CROSS))
            score -= _W_TREND_CROSS

    # 2) Price vs SMA50. Near-equal = neutral.
    if _valid(last["sma_50"]) and last["sma_50"]:
        diff = (close - last["sma_50"]) / abs(last["sma_50"])
        if diff > _EPS:
            subs.append(SubSignal("price_vs_sma50", "Price above SMA50", _W_PRICE_VS_SMA))
            score += _W_PRICE_VS_SMA
        elif diff < -_EPS:
            subs.append(SubSignal("price_vs_sma50", "Price below SMA50", -_W_PRICE_VS_SMA))
            score -= _W_PRICE_VS_SMA

    # 3) RSI (mean-reversion bias for swing horizon).
    if _valid(last["rsi_14"]):
        r = float(last["rsi_14"])
        if r < 30:
            subs.append(SubSignal("rsi", f"RSI {r:.0f} oversold", _W_RSI))
            score += _W_RSI
        elif r > 70:
            subs.append(SubSignal("rsi", f"RSI {r:.0f} overbought", -_W_RSI))
            score -= _W_RSI

    # 4) MACD histogram sign. Exactly-flat (hist ~ 0) = neutral.
    if _valid(last["macd_hist"]):
        if last["macd_hist"] > _EPS:
            subs.append(SubSignal("macd", "MACD above signal", _W_MACD))
            score += _W_MACD
        elif last["macd_hist"] < -_EPS:
            subs.append(SubSignal("macd", "MACD below signal", -_W_MACD))
            score -= _W_MACD

    # 5) Breakout with volume confirmation.
    if len(df) > _BREAKOUT_LOOKBACK and "volume" in df:
        prior = df.iloc[-(_BREAKOUT_LOOKBACK + 1):-1]
        prior_high = float(prior["high"].max())
        vol = df["volume"].iloc[-1]
        avg_vol = prior["volume"].mean()
        if _valid(vol) and _valid(avg_vol) and avg_vol and close >= prior_high and vol > _BREAKOUT_VOL_MULT * avg_vol:
            subs.append(
                SubSignal("breakout", f"{_BREAKOUT_LOOKBACK}-day high breakout on volume", _W_BREAKOUT)
            )
            score += _W_BREAKOUT

    atr_val = last["atr_14"] if _valid(last["atr_14"]) else None
    return LayerScore(
        score=clamp(score),
        subsignals=subs,
        extra={
            "atr": round(float(atr_val), 4) if atr_val is not None else None,
            "close": round(close, 4),
            "rsi_14": round(float(last["rsi_14"]), 2) if _valid(last["rsi_14"]) else None,
        },
    )
