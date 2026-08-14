"""Effective settings = env/.env defaults + DB overrides (Phase 8).

The Settings page writes a whitelist of tunable fields into ``app_config``;
everything else stays under env control. ``get_effective_settings`` is what the
engine and backtester should use so the UI can tune weights/thresholds/risk
without editing .env or restarting.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import AppConfig

# field name -> coercion. Only these may be overridden at runtime.
TUNABLE: dict[str, type] = {
    "weight_technical": float,
    "weight_macro": float,
    "weight_sentiment": float,
    "weight_momentum": float,
    "buy_threshold": float,
    "sell_threshold": float,
    "default_horizon_days": int,
    "account_size": Decimal,
    "risk_per_trade_pct": Decimal,
    "atr_stop_multiple": Decimal,
    "brokerage_pct": Decimal,
    "slippage_pct": Decimal,
    "stt_pct": Decimal,
    "min_liquidity_zar": Decimal,
    "liquidity_lookback_days": int,
    "momentum_lookback_days": int,
    "momentum_skip_days": int,
    "max_open_positions": int,
    "max_positions_per_sector": int,
    "trailing_stop_pct": Decimal,
}


def _coerce(field: str, value):
    typ = TUNABLE[field]
    try:
        if typ is Decimal:
            return Decimal(str(value))
        return typ(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid value for {field!r}: {value!r}") from exc


def coerce_overrides(incoming: dict) -> dict:
    """Validate keys against the whitelist and coerce to engine types.

    Used for one-off (non-persisted) overrides, e.g. a backtest run.
    """
    unknown = set(incoming) - set(TUNABLE)
    if unknown:
        raise ValueError(f"Unknown settings: {sorted(unknown)}")
    return {k: _coerce(k, v) for k, v in incoming.items()}


def _row(db: Session) -> AppConfig | None:
    return db.scalar(select(AppConfig).limit(1))


def get_overrides(db: Session) -> dict:
    """Raw stored overrides (JSON-native types), validated to the whitelist."""
    row = _row(db)
    if row is None or not row.overrides:
        return {}
    return {k: v for k, v in row.overrides.items() if k in TUNABLE}


def set_overrides(db: Session, incoming: dict) -> dict:
    """Validate + merge overrides. Unknown keys are rejected."""
    unknown = set(incoming) - set(TUNABLE)
    if unknown:
        raise ValueError(f"Unknown settings: {sorted(unknown)}")

    # Coerce/validate, then store JSON-friendly values (Decimal -> str).
    cleaned: dict = {}
    for k, v in incoming.items():
        coerced = _coerce(k, v)
        cleaned[k] = str(coerced) if isinstance(coerced, Decimal) else coerced

    row = _row(db)
    merged = {**(row.overrides if row and row.overrides else {}), **cleaned}
    if row is None:
        row = AppConfig(overrides=merged)
        db.add(row)
    else:
        row.overrides = merged
    db.flush()
    return get_overrides(db)


def get_effective_settings(db: Session) -> Settings:
    """Env defaults with validated DB overrides applied (no .env mutation)."""
    base = get_settings()
    overrides = get_overrides(db)
    if not overrides:
        return base
    coerced = {k: _coerce(k, v) for k, v in overrides.items()}
    return base.model_copy(update=coerced)
