"""Signal fusion engine (§10).

Fuses the technical, macro-regime, and sentiment layers using the configurable
weights, then derives direction, ATR-based stop, risk-sized quantity, and a
fully transparent ``rationale`` JSON. Confidence comes only from the engine's
measured hit rate (``performance.py``) — never invented.

``build_signal`` is pure (no DB); the ``generate_signals`` job supplies the data
and persists the returned draft.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

from app.config import Settings
from app.db.models import SignalDirection
from app.signals import macro_regime
from app.signals.scoring import LayerScore, clamp
from app.signals.sentiment import sentiment_score
from app.signals.technical import technical_score

_Q4 = Decimal("0.0001")


def _dec(x: float | None) -> Decimal | None:
    if x is None:
        return None
    return Decimal(str(x)).quantize(_Q4, rounding=ROUND_HALF_UP)


@dataclass
class SignalDraft:
    security_id: int
    generated_at: datetime
    horizon_days: int
    direction: SignalDirection
    score: Decimal
    confidence: Decimal | None
    technical_score: Decimal
    macro_score: Decimal
    sentiment_score: Decimal
    momentum_score: Decimal | None
    suggested_entry: Decimal | None
    suggested_stop: Decimal | None
    suggested_size: Decimal | None
    rationale: dict = field(default_factory=dict)


def _normalised_weights(s: Settings) -> tuple[float, float, float, float]:
    wt, wm, ws = s.weight_technical, s.weight_macro, s.weight_sentiment
    wmom = getattr(s, "weight_momentum", 0.0)
    total = wt + wm + ws + wmom
    if total <= 0:
        return (0.25, 0.25, 0.25, 0.25)
    return (wt / total, wm / total, ws / total, wmom / total)


def _direction(score: float, s: Settings) -> SignalDirection:
    if score >= s.buy_threshold:
        return SignalDirection.BUY
    if score <= s.sell_threshold:
        return SignalDirection.SELL
    return SignalDirection.HOLD


def compute_trade_levels(
    *,
    direction: SignalDirection,
    close_cents: float | None,
    atr_cents: float | None,
    settings: Settings,
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """Return (entry, stop, size) in native quote units. Shared by the engine and
    the backtester so live and simulated trades size identically.

    HOLD (or missing close/ATR) yields no stop/size. Size uses the risk-per-trade
    rule: risk_budget = account_size * risk_pct%, size = risk_budget / |entry-stop|.
    Size is FRACTIONAL (crypto units aren't whole). Prices are native (USDT) — the
    old ``/100`` cents conversion from the JSE era is gone (it inflated size 100x).
    """
    entry = Decimal(str(close_cents)) if close_cents is not None else None
    if entry is None or atr_cents is None or direction == SignalDirection.HOLD:
        return entry, None, None

    atr_dist = Decimal(str(atr_cents)) * settings.atr_stop_multiple
    stop = entry - atr_dist if direction == SignalDirection.BUY else entry + atr_dist

    risk_budget = settings.account_size * (settings.risk_per_trade_pct / Decimal(100))
    per_unit = abs(entry - stop)
    size: Decimal | None = None
    if per_unit > 0:
        size = risk_budget / per_unit
        # No leverage on spot: never suggest a position bigger than the account
        # can actually buy. With a tight stop the risk rule alone would imply
        # >100% notional; cap it at the affordable units.
        if entry > 0:
            max_affordable = settings.account_size / entry
            if size > max_affordable:
                size = max_affordable
        size = size.quantize(Decimal("0.00000001"))
        if size < 0:
            size = Decimal(0)
    return entry, stop, size


def build_signal(
    *,
    security_id: int,
    sector: str | None,
    price_df: pd.DataFrame,
    macro_layer: LayerScore,
    sentiment_pairs: list[tuple[float | None, float | None]],
    settings: Settings,
    generated_at: datetime,
    confidence: Decimal | None = None,
    event_flag: bool = False,
    momentum_score: float = 0.0,
) -> SignalDraft:
    tech = technical_score(price_df)
    sent = sentiment_score(sentiment_pairs, event_flag=event_flag)

    tilt = macro_regime.sector_tilt(macro_layer, sector)
    macro_component = clamp(macro_layer.score + tilt)
    momentum_component = clamp(momentum_score)

    wt, wm, ws, wmom = _normalised_weights(settings)
    fused = clamp(
        wt * tech.score
        + wm * macro_component
        + ws * sent.score
        + wmom * momentum_component
    )
    direction = _direction(fused, settings)

    # Entry / stop / size (prices in cents) — shared with the backtester.
    atr = tech.extra.get("atr")
    close = tech.extra.get("close")
    entry, stop, size = compute_trade_levels(
        direction=direction, close_cents=close, atr_cents=atr, settings=settings
    )

    rationale = {
        "fused_score": round(fused, 4),
        "weights": {
            "technical": round(wt, 4), "macro": round(wm, 4),
            "sentiment": round(ws, 4), "momentum": round(wmom, 4),
        },
        "thresholds": {"buy": settings.buy_threshold, "sell": settings.sell_threshold},
        "technical": tech.as_rationale(),
        "macro": {**macro_layer.as_rationale(), "sector": sector, "sector_tilt": round(tilt, 4),
                  "applied_component": round(macro_component, 4)},
        "sentiment": sent.as_rationale(),
        "momentum": {"score": round(momentum_component, 4),
                     "detail": "cross-sectional relative strength percentile"},
        "sizing": {
            "account_size": str(settings.account_size),
            "risk_per_trade_pct": str(settings.risk_per_trade_pct),
            "atr_stop_multiple": str(settings.atr_stop_multiple),
        },
    }

    return SignalDraft(
        security_id=security_id,
        generated_at=generated_at,
        horizon_days=settings.default_horizon_days,
        direction=direction,
        score=_dec(fused),
        confidence=confidence,
        technical_score=_dec(tech.score),
        macro_score=_dec(macro_component),
        sentiment_score=_dec(sent.score),
        momentum_score=_dec(momentum_component),
        suggested_entry=_dec(float(entry)) if entry is not None else None,
        suggested_stop=_dec(float(stop)) if stop is not None else None,
        suggested_size=size,
        rationale=rationale,
    )
