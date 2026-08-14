"""Pine Script generation endpoint (compare app backtest vs TradingView)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import pinescript
from app.services import settings as settings_service

router = APIRouter(prefix="/api/pinescript", tags=["pinescript"])


class PineResponse(BaseModel):
    pine: str
    params: dict
    notes: list[str]


@router.get("", response_model=PineResponse)
def get_pinescript(db: Session = Depends(get_db)) -> PineResponse:
    eff = settings_service.get_effective_settings(db)
    pine = pinescript.build_pine(eff)
    return PineResponse(
        pine=pine,
        params={
            "buy_threshold": eff.buy_threshold,
            "sell_threshold": eff.sell_threshold,
            "atr_stop_multiple": float(eff.atr_stop_multiple),
            "horizon_days": eff.default_horizon_days,
            "brokerage_pct": float(eff.brokerage_pct),
            "slippage_pct": float(eff.slippage_pct),
            "stt_pct": float(eff.stt_pct),
        },
        notes=[
            "Reproduces the app's TECHNICAL strategy only (market regime / "
            "sentiment / momentum are not single-symbol constructs).",
            "Both the app and TradingView can use Binance data, but fills/fees "
            "differ — expect directional agreement, not identical numbers.",
            "commission_value = exchange fee% + slippage% (per side).",
            "Set the TradingView chart to daily (1D) and match the date range to "
            "your app backtest for a fair comparison.",
        ],
    )
