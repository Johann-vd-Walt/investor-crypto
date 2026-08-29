"""Market movers endpoints — top movers + most-bought-on-Luno. Keyless, read-only."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.market import MostBought, Mover, MoversResponse
from app.services import movers as movers_svc

router = APIRouter(prefix="/api/market", tags=["market"])

_NOTE = (
    "Top movers = today's move (live vs last daily close) for every coin. "
    "Most bought = recent buying pressure on Luno's public trades feed (Luno has "
    "no 'most bought' API, so this is the recent trade window, not a full 24h)."
)


@router.get("/movers", response_model=MoversResponse)
def movers(db: Session = Depends(get_db)) -> MoversResponse:
    return MoversResponse(
        top_movers=[Mover(**m) for m in movers_svc.top_movers(db)[:20]],
        most_bought=[MostBought(**m) for m in movers_svc.most_bought(db)],
        note=_NOTE,
    )
