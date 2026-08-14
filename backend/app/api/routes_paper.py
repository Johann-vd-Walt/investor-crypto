"""Paper-trading endpoints (Section 11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import PaperTrade, PaperTradeStatus
from app.db.session import get_db
from app.repositories import paper as paper_repo
from app.repositories import prices as prices_repo
from app.repositories import securities as securities_repo
from app.schemas.paper import (
    EquityPointOut,
    PaperPerformanceResponse,
    PaperTradeOut,
)
from app.schemas.prices import cents_to_rand
from app.signals import paper as paper_sim
from app.signals import performance as perf

router = APIRouter(prefix="/api/paper", tags=["paper"])


def _ticker(db: Session, security_id: int, cache: dict[int, str]) -> str:
    if security_id not in cache:
        sec = securities_repo.get_by_id(db, security_id)
        cache[security_id] = sec.ticker if sec else str(security_id)
    return cache[security_id]


@router.get("/trades", response_model=list[PaperTradeOut])
def paper_trades(db: Session = Depends(get_db)) -> list[PaperTradeOut]:
    trades = paper_repo.list_all(db)
    cache: dict[int, str] = {}
    out: list[PaperTradeOut] = []
    for t in trades:
        unrealized = None
        if t.status == PaperTradeStatus.OPEN:
            latest = prices_repo.get_latest_bar(db, security_id=t.security_id)
            if latest is not None:
                unrealized = cents_to_rand(
                    paper_sim.unrealized_pnl(
                        entry_price=t.entry_price,
                        current_price=latest.close,
                        quantity=t.quantity,
                    )
                )
        out.append(
            PaperTradeOut(
                id=t.id,
                security_id=t.security_id,
                ticker=_ticker(db, t.security_id, cache),
                entry_datetime=t.entry_datetime,
                entry_price=cents_to_rand(t.entry_price),
                quantity=t.quantity,
                stop_price=cents_to_rand(t.stop_price),
                exit_datetime=t.exit_datetime,
                exit_price=cents_to_rand(t.exit_price),
                pnl=cents_to_rand(t.pnl),
                unrealized_pnl=unrealized,
                status=t.status,
            )
        )
    return out


@router.get("/performance", response_model=PaperPerformanceResponse)
def paper_performance(db: Session = Depends(get_db)) -> PaperPerformanceResponse:
    p = perf.measured_performance(db)
    return PaperPerformanceResponse(
        sample_size=p.sample_size,
        wins=p.wins,
        min_sample=perf.MIN_SAMPLE,
        has_edge_data=p.win_rate is not None,
        win_rate=p.win_rate,
        avg_return_pct=p.avg_return_pct,
        total_pnl=cents_to_rand(p.total_pnl),
        equity_curve=[
            EquityPointOut(date=pt.on_date, cumulative_pnl=cents_to_rand(pt.cumulative_pnl))
            for pt in p.equity_curve
        ],
    )
