"""Realised performance of the bot's OWN closed positions, split by venue.

'luno' rows are REAL trades; 'paper' rows are simulated. This is what the bot
actually did — used to show a true track record and (once there are enough real
trades) to drive the signal confidence, so 'confidence' reflects reality.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BotPosition


def venue_stats(db: Session, venue: str) -> dict:
    rows = list(db.scalars(
        select(BotPosition).where(
            BotPosition.status == "CLOSED",
            BotPosition.venue == venue,
            BotPosition.pnl.is_not(None),
        )
    ).all())
    n = len(rows)
    if n == 0:
        return {"venue": venue, "sample": 0, "wins": 0, "win_rate": None,
                "avg_return_pct": None, "total_pnl": 0.0}
    wins = sum(1 for r in rows if r.pnl and r.pnl > 0)
    rets = [float(r.pnl) / float(r.cost_basis) * 100.0 for r in rows if r.cost_basis]
    total = float(sum((r.pnl for r in rows), start=type(rows[0].pnl)(0)))
    return {
        "venue": venue, "sample": n, "wins": wins, "win_rate": wins / n,
        "avg_return_pct": (sum(rets) / len(rets)) if rets else None,
        "total_pnl": total,
    }


def all_stats(db: Session) -> dict:
    return {"paper": venue_stats(db, "paper"), "luno": venue_stats(db, "luno")}
