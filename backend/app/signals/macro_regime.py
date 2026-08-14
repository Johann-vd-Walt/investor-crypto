"""Crypto market-regime score (§10) — replaces the JSE macro layer.

Crypto is highly correlated to Bitcoin, so the 'market' is BTC. A market-wide
score in [-1, 1] and a named regime come from the BTC trend. Sector tilts don't
apply to crypto, so they're empty (the engine's per-asset macro component is
just the market score). Pure and deterministic.

Input ``series`` maps a code to its chronological value list (oldest -> newest);
we use "BTC" (Bitcoin close). Missing/short series -> neutral (no fabrication).
"""

from __future__ import annotations

from app.signals.scoring import LayerScore, SubSignal, clamp

_TREND_PCT = 0.03          # >3% move over the lookback counts as a trend
_MARKET_LOOKBACK = 20      # ~3 weeks of daily bars


def _pct_change(values: list[float] | None, lookback: int) -> float | None:
    if not values or len(values) < lookback + 1:
        return None
    past = values[-1 - lookback]
    if past == 0:
        return None
    return (values[-1] - past) / abs(past)


def macro_regime_score(series: dict[str, list[float]]) -> LayerScore:
    btc = series.get("BTC") or []
    lookback = min(_MARKET_LOOKBACK, max(1, len(btc) - 1))
    pct = _pct_change(btc, lookback)

    subs: list[SubSignal] = []
    score = 0.0
    regime = "neutral / insufficient data"
    if pct is not None:
        if pct > _TREND_PCT:
            score = 0.5
            regime = "risk-on (BTC uptrend)"
            subs.append(SubSignal("btc_trend", f"BTC up {pct * 100:.1f}% over lookback", 0.5))
        elif pct < -_TREND_PCT:
            score = -0.5
            regime = "risk-off (BTC downtrend)"
            subs.append(SubSignal("btc_trend", f"BTC down {pct * 100:.1f}% over lookback", -0.5))
        else:
            regime = "range-bound (BTC flat)"
            subs.append(SubSignal("btc_trend", "BTC roughly flat over lookback", 0.0))

    return LayerScore(
        score=clamp(score),
        subsignals=subs,
        extra={"regime": regime, "sector_tilts": {}},
    )


def sector_tilt(layer: LayerScore, sector: str | None) -> float:
    """No sector tilts in the crypto regime (kept for engine compatibility)."""
    return 0.0
