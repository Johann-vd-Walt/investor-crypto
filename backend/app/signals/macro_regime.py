"""Crypto market-regime score (§10) — replaces the JSE macro layer.

Crypto is highly correlated to Bitcoin, so the 'market' is BTC. A market-wide
score in [-1, 1] and a named regime come from the BTC trend. Sector tilts don't
apply to crypto, so they're empty (the engine's per-asset macro component is
just the market score). Pure and deterministic.

Input ``series`` maps a code to its chronological value list (oldest -> newest);
we use "BTC" (Bitcoin close). Missing/short series -> neutral (no fabrication).

Two modes:
  - ``classic``  : BTC 20-day change only (>+3% risk-on, <-3% risk-off).
  - ``two_speed``: long-term trend (BTC vs its N-day SMA) sets the side, the
    20-day move sets the phase. A pullback inside a long-term uptrend is a
    dip-buy window (mildly positive), not risk-off. Falls back to classic when
    there isn't enough history for the long SMA.
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


# two_speed scores: (above long SMA?, 20-day phase) -> (score, regime label)
_TWO_SPEED: dict[tuple[bool, str], tuple[float, str]] = {
    (True, "up"): (0.5, "risk-on (long-term uptrend, rising)"),
    (True, "flat"): (0.25, "uptrend, consolidating"),
    (True, "down"): (0.3, "pullback in uptrend (dip-buy window)"),
    (False, "up"): (0.0, "bear-market rally (below long-term trend)"),
    (False, "flat"): (-0.25, "below long-term trend, flat"),
    (False, "down"): (-0.5, "risk-off (long-term downtrend, falling)"),
}


def macro_regime_score(
    series: dict[str, list[float]], *, mode: str = "classic", long_sma_days: int = 200
) -> LayerScore:
    btc = series.get("BTC") or []
    lookback = min(_MARKET_LOOKBACK, max(1, len(btc) - 1))
    pct = _pct_change(btc, lookback)

    if mode == "two_speed" and pct is not None and long_sma_days > 0 and len(btc) >= long_sma_days:
        window = btc[-long_sma_days:]
        sma = sum(window) / len(window)
        above = btc[-1] > sma
        phase = "up" if pct > _TREND_PCT else ("down" if pct < -_TREND_PCT else "flat")
        score, regime = _TWO_SPEED[(above, phase)]
        vs_sma = (btc[-1] / sma - 1.0) * 100.0 if sma else 0.0
        subs = [
            SubSignal("btc_long_trend",
                      f"BTC {'above' if above else 'below'} its {long_sma_days}-day SMA ({vs_sma:+.1f}%)", 0.0),
            SubSignal("btc_trend", f"BTC {pct * 100:+.1f}% over {lookback} days", score),
        ]
        return LayerScore(
            score=clamp(score),
            subsignals=subs,
            extra={"regime": regime, "sector_tilts": {}, "mode": "two_speed",
                   "above_long_sma": above, "pullback": above and phase == "down"},
        )

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
        extra={"regime": regime, "sector_tilts": {}, "mode": "classic"},
    )


def sector_tilt(layer: LayerScore, sector: str | None) -> float:
    """No sector tilts in the crypto regime (kept for engine compatibility)."""
    return 0.0
