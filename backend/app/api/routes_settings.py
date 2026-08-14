"""Settings endpoints (§12).

Exposes the effective (env + overrides) tunable settings, provider status, and
data-freshness, and lets the owner persist overrides. Weights should sum to 1.0
(a warning is surfaced, not enforced — fusion normalises).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.services import settings as settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    # Effective values (env defaults with overrides applied).
    weight_technical: float
    weight_macro: float
    weight_sentiment: float
    weight_momentum: float
    buy_threshold: float
    sell_threshold: float
    default_horizon_days: int
    account_size: float
    risk_per_trade_pct: float
    atr_stop_multiple: float
    brokerage_pct: float
    slippage_pct: float
    stt_pct: float
    min_liquidity_zar: float
    liquidity_lookback_days: int
    momentum_lookback_days: int
    momentum_skip_days: int
    max_open_positions: int
    max_positions_per_sector: int
    trailing_stop_pct: float
    weight_sum: float
    weights_ok: bool
    overrides: dict[str, Any]  # which fields are currently overridden
    providers: dict[str, bool]


class SettingsUpdate(BaseModel):
    # All optional; only provided fields are updated.
    overrides: dict[str, Any]


def _response(db: Session) -> SettingsResponse:
    eff = settings_service.get_effective_settings(db)
    return SettingsResponse(
        weight_technical=eff.weight_technical,
        weight_macro=eff.weight_macro,
        weight_sentiment=eff.weight_sentiment,
        weight_momentum=eff.weight_momentum,
        buy_threshold=eff.buy_threshold,
        sell_threshold=eff.sell_threshold,
        default_horizon_days=eff.default_horizon_days,
        account_size=float(eff.account_size),
        risk_per_trade_pct=float(eff.risk_per_trade_pct),
        atr_stop_multiple=float(eff.atr_stop_multiple),
        brokerage_pct=float(eff.brokerage_pct),
        slippage_pct=float(eff.slippage_pct),
        stt_pct=float(eff.stt_pct),
        min_liquidity_zar=float(eff.min_liquidity_zar),
        liquidity_lookback_days=eff.liquidity_lookback_days,
        momentum_lookback_days=eff.momentum_lookback_days,
        momentum_skip_days=eff.momentum_skip_days,
        max_open_positions=eff.max_open_positions,
        max_positions_per_sector=eff.max_positions_per_sector,
        trailing_stop_pct=float(eff.trailing_stop_pct),
        weight_sum=round(eff.weight_sum, 4),
        weights_ok=abs(eff.weight_sum - 1.0) <= 1e-6,
        overrides=settings_service.get_overrides(db),
        providers=get_settings().enabled_providers,
    )


@router.get("", response_model=SettingsResponse)
def get_effective(db: Session = Depends(get_db)) -> SettingsResponse:
    return _response(db)


@router.put("", response_model=SettingsResponse)
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)) -> SettingsResponse:
    try:
        settings_service.set_overrides(db, payload.overrides)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return _response(db)
