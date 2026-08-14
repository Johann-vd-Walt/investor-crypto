"""Cross-sectional momentum + liquidity filter (Phase B).

Two cheap, price-only improvements that tend to matter more than absolute
technical thresholds on their own:

- **Liquidity filter**: skip securities whose average daily traded value is too
  low to trade without moving the price (critical on the JSE's long tail of
  thin small-caps).
- **Cross-sectional momentum**: rank securities by trailing return (lookback,
  skipping the most recent few days to dodge short-term reversal) and score each
  by its percentile — trade relative strength, not an absolute number.

Pure and deterministic (§14). Prices are in cents; liquidity is returned in Rand.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd


def average_daily_value_zar(
    closes_cents: list[float], volumes: list[float], lookback: int = 20
) -> Decimal | None:
    """Mean daily traded value in RAND over the last ``lookback`` bars."""
    n = min(len(closes_cents), len(volumes))
    if n == 0:
        return None
    closes = closes_cents[-lookback:]
    vols = volumes[-lookback:]
    # Crypto prices are native (quote currency); traded value = close * volume.
    pairs = [
        c * v
        for c, v in zip(closes, vols)
        if c is not None and v is not None and not pd.isna(v)
    ]
    if not pairs:
        return None
    return Decimal(str(sum(pairs) / len(pairs)))


def is_liquid(
    closes_cents: list[float], volumes: list[float], *, min_zar: Decimal, lookback: int = 20
) -> bool:
    adv = average_daily_value_zar(closes_cents, volumes, lookback)
    return adv is not None and adv >= min_zar


def momentum_value(
    closes: list[float], *, lookback: int = 90, skip: int = 5
) -> float | None:
    """Trailing return from (t-skip-lookback) to (t-skip). None if too short."""
    need = lookback + skip + 1
    if len(closes) < need:
        return None
    recent = closes[-1 - skip]
    past = closes[-1 - skip - lookback]
    if past == 0:
        return None
    return recent / past - 1.0


def cross_sectional_scores(values: dict) -> dict:
    """Map each key's momentum value to a percentile score in [-1, 1].

    Keys with a None value are scored 0.0 (neutral — not ranked). With a single
    ranked value the score is 0.0 (no cross-section to rank against).
    """
    ranked = {k: v for k, v in values.items() if v is not None}
    out = {k: 0.0 for k in values}
    m = len(ranked)
    if m <= 1:
        return out
    ordered = sorted(ranked.items(), key=lambda kv: kv[1])
    for i, (k, _v) in enumerate(ordered):
        percentile = i / (m - 1)  # 0..1
        out[k] = round(2.0 * percentile - 1.0, 4)  # -1..1
    return out
