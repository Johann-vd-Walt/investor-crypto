"""Build human-readable positioning snapshots from stored derivatives metrics.

Every flag is a PERCENTILE of the asset's own recent history (not a fixed
threshold), because funding/OI/flow regimes drift over time. Honesty first:
each signal is labelled with a confidence-appropriate tone and never presented
as a trade trigger. Pure logic given the loaded series — easy to unit-test.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Security
from app.repositories import derivatives as deriv_repo
from app.repositories import prices as prices_repo
from app.schemas.positioning import PositioningSignal, PositioningSnapshot

_HIGH = 0.90
_LOW = 0.10


def _percentile(values: list[float], x: float) -> float | None:
    if not values:
        return None
    below = sum(1 for v in values if v <= x)
    return below / len(values)


def _pct_change(series: list[float], lookback: int) -> float | None:
    if len(series) <= lookback:
        return None
    old = series[-lookback - 1]
    if old == 0:
        return None
    return (series[-1] - old) / abs(old)


def _funding_signal(pts: list[tuple[datetime, float]]) -> PositioningSignal | None:
    if not pts:
        return None
    vals = [v for _, v in pts]
    latest = vals[-1]
    pct = _percentile(vals, latest)
    # funding is a per-interval rate; show as %.
    pct_disp = f"{latest * 100:.4f}%"
    if pct is not None and pct >= _HIGH and latest > 0:
        tone, label = "warn", "Crowded longs"
        detail = f"Funding is in the top {round((1-pct)*100)}% of its range ({pct_disp}) — leverage is one-sided long; elevated flush/​reversal risk. Be cautious adding longs."
    elif pct is not None and pct <= _LOW and latest < 0:
        tone, label = "bull", "Crowded shorts"
        detail = f"Funding is in the bottom {round(pct*100)}% ({pct_disp}) and negative — shorts are crowded and pay longs; short-squeeze fuel (contrarian bullish)."
    else:
        tone, label = "neutral", "Funding normal"
        detail = f"Funding rate {pct_disp} — no extreme leverage skew."
    return PositioningSignal(
        metric="funding", label=label, detail=detail,
        value=latest, percentile=pct, tone=tone, sample=len(vals),
    )


def _oi_signal(
    oi_pts: list[tuple[datetime, float]], closes: list[float]
) -> PositioningSignal | None:
    if len(oi_pts) < 2:
        return None
    oi_vals = [v for _, v in oi_pts]
    lookback = min(7, len(oi_vals) - 1)
    oi_chg = _pct_change(oi_vals, lookback)
    px_chg = _pct_change(closes, lookback) if len(closes) > lookback else None
    if oi_chg is None or px_chg is None:
        return None
    up_px, up_oi = px_chg > 0, oi_chg > 0
    if up_px and up_oi:
        tone, label = "bull", "New money behind move"
        detail = f"Over ~{lookback}d price rose {px_chg*100:.1f}% with open interest up {oi_chg*100:.1f}% — fresh positions supporting the trend."
    elif up_px and not up_oi:
        tone, label = "warn", "Rally on short-covering"
        detail = f"Price rose {px_chg*100:.1f}% but open interest fell {oi_chg*100:.1f}% — move is closing shorts, not new demand; less durable."
    elif not up_px and up_oi:
        tone, label = "bear", "New shorts building"
        detail = f"Price fell {px_chg*100:.1f}% while open interest rose {oi_chg*100:.1f}% — fresh shorts (bearish, but squeeze fuel if it reverses)."
    else:
        tone, label = "neutral", "De-leveraging"
        detail = f"Price fell {px_chg*100:.1f}% and open interest fell {oi_chg*100:.1f}% — positions unwinding/capitulation."
    return PositioningSignal(
        metric="open_interest", label=label, detail=detail,
        value=oi_vals[-1], percentile=None, tone=tone, sample=len(oi_vals),
    )


def _taker_signal(pts: list[tuple[datetime, float]]) -> PositioningSignal | None:
    if not pts:
        return None
    vals = [v for _, v in pts]
    latest = vals[-1]
    pct = _percentile(vals, latest)
    if pct is not None and pct >= _HIGH:
        tone, label = "bull", "Aggressive buying"
        detail = f"Taker buy/sell ratio {latest:.2f} is in the top {round((1-pct)*100)}% — market buyers pressing (short-horizon)."
    elif pct is not None and pct <= _LOW:
        tone, label = "bear", "Aggressive selling"
        detail = f"Taker buy/sell ratio {latest:.2f} is in the bottom {round(pct*100)}% — market sellers pressing."
    else:
        tone, label = "neutral", "Balanced flow"
        detail = f"Taker buy/sell ratio {latest:.2f} — no aggressor extreme."
    return PositioningSignal(
        metric="taker_ratio", label=label, detail=detail,
        value=latest, percentile=pct, tone=tone, sample=len(vals),
    )


def _ls_signal(pts: list[tuple[datetime, float]]) -> PositioningSignal | None:
    if not pts:
        return None
    latest = pts[-1][1]
    lean = "net long" if latest > 1 else "net short"
    return PositioningSignal(
        metric="long_short_pos",
        label=f"Top traders {lean}",
        detail=f"Largest-account position ratio {latest:.2f} ({lean}). Low-confidence colour only — coarse exchange bucket, easily overweighted.",
        value=latest, percentile=None, tone="neutral", sample=len(pts),
    )


def build_snapshot(db: Session, security: Security) -> PositioningSnapshot:
    def series(metric: str) -> list[tuple[datetime, float]]:
        return [(r.ts, float(r.value)) for r in deriv_repo.get_series(db, security_id=security.id, metric=metric)]

    funding = series("funding")
    oi = series("open_interest")
    taker = series("taker_ratio")
    ls = series("long_short_pos")

    closes = [float(b.close) for b in prices_repo.get_bars(db, security_id=security.id)]

    signals = [
        s for s in (
            _funding_signal(funding),
            _oi_signal(oi, closes),
            _taker_signal(taker),
            _ls_signal(ls),
        ) if s is not None
    ]

    all_ts = [t for pts in (funding, oi, taker, ls) for t, _ in pts]
    as_of = max(all_ts) if all_ts else None
    available = bool(signals)
    note = (
        "Free Binance futures positioning. Percentile flags are relative to this "
        "asset's own recent history and are context, not entry triggers."
        if available else
        "No futures positioning data yet for this asset (no perp market, the "
        "collector hasn't run, or the futures host is unreachable from the server)."
    )
    return PositioningSnapshot(
        ticker=security.ticker, name=security.name, as_of=as_of,
        available=available, signals=signals, note=note,
    )
