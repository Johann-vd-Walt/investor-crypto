"""Trade journal + tax-summary endpoints (Section 11)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import tax
from app.db.models import Trade
from app.db.session import get_db
from app.repositories import securities as securities_repo
from app.repositories import signals as signals_repo
from app.repositories import trades as trades_repo
from app.schemas.prices import cents_to_rand, rand_to_cents
from app.schemas.trades import (
    DisposalOut,
    TaxSummaryResponse,
    TradeCreate,
    TradeListResponse,
    TradeOut,
)

router = APIRouter(prefix="/api/trades", tags=["trades"])

_TAX_DISCLAIMER = (
    "Record-keeping only, not tax advice. Short-term frequent trading may be "
    "taxed as income rather than capital gains in South Africa — confirm your "
    "situation with a registered tax practitioner. Gains are FIFO-matched."
)


def _to_out(t: Trade, ticker: str) -> TradeOut:
    return TradeOut(
        id=t.id,
        security_id=t.security_id,
        ticker=ticker,
        side=t.side,
        quantity=t.quantity,
        price=cents_to_rand(t.price),
        fees=cents_to_rand(t.fees),
        trade_datetime=t.trade_datetime,
        linked_signal_id=t.linked_signal_id,
        rationale=t.rationale,
        created_at=t.created_at,
    )


def _default_tax_year(today: date) -> int:
    # SA tax year Y covers 1 Mar (Y-1) .. end Feb (Y).
    return today.year + 1 if today.month >= 3 else today.year


@router.get("", response_model=TradeListResponse)
def list_trades(
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> TradeListResponse:
    items, total = trades_repo.list_trades(db, limit=limit, offset=offset)
    cache: dict[int, str] = {}

    def ticker_for(sid: int) -> str:
        if sid not in cache:
            sec = securities_repo.get_by_id(db, sid)
            cache[sid] = sec.ticker if sec else str(sid)
        return cache[sid]

    return TradeListResponse(
        items=[_to_out(t, ticker_for(t.security_id)) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TradeOut, status_code=status.HTTP_201_CREATED)
def create_trade(payload: TradeCreate, db: Session = Depends(get_db)) -> TradeOut:
    sec = securities_repo.get_by_ticker(db, payload.ticker)
    if sec is None:
        raise HTTPException(status_code=404, detail=f"Unknown ticker: {payload.ticker}")

    if payload.linked_signal_id is not None and signals_repo.get(db, payload.linked_signal_id) is None:
        raise HTTPException(status_code=404, detail="linked_signal_id not found.")

    trade = trades_repo.create(
        db,
        security_id=sec.id,
        side=payload.side,
        quantity=payload.quantity,
        price=rand_to_cents(payload.price),
        fees=rand_to_cents(payload.fees),
        trade_datetime=payload.trade_datetime,
        linked_signal_id=payload.linked_signal_id,
        rationale=payload.rationale,
    )
    db.commit()
    return _to_out(trade, sec.ticker)


@router.get("/tax-summary", response_model=TaxSummaryResponse)
def tax_summary(
    tax_year: int | None = Query(default=None, description="SA tax year, e.g. 2026 = Mar 2025–Feb 2026"),
    db: Session = Depends(get_db),
) -> TaxSummaryResponse:
    year = tax_year or _default_tax_year(date.today())
    _start, end = tax.tax_year_bounds(year)

    from datetime import datetime, time

    rows = trades_repo.list_all_through(db, end=datetime.combine(end, time.max))
    cache: dict[int, str] = {}

    def ticker_for(sid: int) -> str:
        if sid not in cache:
            sec = securities_repo.get_by_id(db, sid)
            cache[sid] = sec.ticker if sec else str(sid)
        return cache[sid]

    trade_rows = [
        tax.TradeRow(
            security_id=t.security_id,
            ticker=ticker_for(t.security_id),
            side=t.side.value,
            quantity=t.quantity,
            price=t.price,
            fees=t.fees,
            trade_datetime=t.trade_datetime,
        )
        for t in rows
    ]
    summary = tax.realised_gains_for_tax_year(trade_rows, year)

    return TaxSummaryResponse(
        tax_year=summary.tax_year,
        period_start=summary.period_start,
        period_end=summary.period_end,
        disposals=[
            DisposalOut(
                ticker=d.ticker,
                sell_datetime=d.sell_datetime,
                quantity=d.quantity,
                proceeds=cents_to_rand(d.proceeds),
                base_cost=cents_to_rand(d.base_cost),
                gain=cents_to_rand(d.gain),
                unmatched_quantity=d.unmatched_quantity,
            )
            for d in summary.disposals
        ],
        total_proceeds=cents_to_rand(summary.total_proceeds),
        total_base_cost=cents_to_rand(summary.total_base_cost),
        total_realised_gain=cents_to_rand(summary.total_gain),
        disclaimer=_TAX_DISCLAIMER,
    )


@router.delete("/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trade(trade_id: int, db: Session = Depends(get_db)) -> None:
    trade = trades_repo.get(db, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found.")
    trades_repo.delete(db, trade)
    db.commit()
