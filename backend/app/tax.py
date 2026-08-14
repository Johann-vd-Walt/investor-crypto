"""Realised-gains computation for the tax summary (§11, §15).

Record-keeping only — NOT tax advice. South African tax years run 1 March to
the end of February. Realised gains are matched FIFO per security. Short-term
frequent trading may be taxed as income rather than CGT — that is the owner's
call with a registered tax practitioner (surfaced in the UI).

All monetary inputs/outputs here are in cents (ZAc); the API converts to Rand.
Pure and deterministic (§14).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal


def tax_year_bounds(tax_year: int) -> tuple[date, date]:
    """SA tax year Y = 1 March (Y-1) .. end Feb (Y)."""
    start = date(tax_year - 1, 3, 1)
    end = date(tax_year, 3, 1) - timedelta(days=1)
    return start, end


@dataclass
class TradeRow:
    security_id: int
    ticker: str
    side: str  # "BUY" | "SELL"
    quantity: int
    price: Decimal  # per share, cents
    fees: Decimal   # total for the trade, cents
    trade_datetime: datetime


@dataclass
class Disposal:
    ticker: str
    sell_datetime: datetime
    quantity: int
    proceeds: Decimal    # cents, net of sell fees
    base_cost: Decimal   # cents, incl. allocated buy fees
    gain: Decimal        # cents = proceeds - base_cost
    unmatched_quantity: int  # sold without a matching buy lot (short/oversold)


@dataclass
class _Lot:
    quantity: int
    price: Decimal          # per share, cents
    fee_per_share: Decimal  # allocated buy fee, cents


def _fifo_disposals(trades: list[TradeRow]) -> list[Disposal]:
    """Match sells against prior buys FIFO, per security. Returns disposals in
    trade order (a disposal is recorded at each SELL)."""
    lots_by_sec: dict[int, deque[_Lot]] = defaultdict(deque)
    tickers: dict[int, str] = {}
    disposals: list[Disposal] = []

    for t in sorted(trades, key=lambda x: x.trade_datetime):
        tickers[t.security_id] = t.ticker
        if t.side == "BUY":
            fee_ps = (t.fees / t.quantity) if t.quantity else Decimal(0)
            lots_by_sec[t.security_id].append(
                _Lot(quantity=t.quantity, price=t.price, fee_per_share=fee_ps)
            )
            continue

        # SELL: consume lots FIFO.
        remaining = t.quantity
        base_cost = Decimal(0)
        lots = lots_by_sec[t.security_id]
        while remaining > 0 and lots:
            lot = lots[0]
            take = min(remaining, lot.quantity)
            base_cost += take * (lot.price + lot.fee_per_share)
            lot.quantity -= take
            remaining -= take
            if lot.quantity == 0:
                lots.popleft()

        matched_qty = t.quantity - remaining
        proceeds = t.quantity * t.price - t.fees  # sell fees reduce proceeds
        gain = proceeds - base_cost
        disposals.append(
            Disposal(
                ticker=t.ticker,
                sell_datetime=t.trade_datetime,
                quantity=t.quantity,
                proceeds=proceeds,
                base_cost=base_cost,
                gain=gain,
                unmatched_quantity=remaining,
            )
        )
    return disposals


@dataclass
class TaxSummary:
    tax_year: int
    period_start: date
    period_end: date
    disposals: list[Disposal]
    total_proceeds: Decimal
    total_base_cost: Decimal
    total_gain: Decimal


def realised_gains_for_tax_year(trades: list[TradeRow], tax_year: int) -> TaxSummary:
    """Compute disposals whose SELL falls inside the tax year.

    ``trades`` must include the full history (buys from prior years are needed
    to establish base cost) up to at least the tax-year end.
    """
    start, end = tax_year_bounds(tax_year)
    all_disposals = _fifo_disposals(trades)
    in_year = [
        d for d in all_disposals if start <= d.sell_datetime.date() <= end
    ]
    total_proceeds = sum((d.proceeds for d in in_year), Decimal(0))
    total_base = sum((d.base_cost for d in in_year), Decimal(0))
    total_gain = sum((d.gain for d in in_year), Decimal(0))
    return TaxSummary(
        tax_year=tax_year,
        period_start=start,
        period_end=end,
        disposals=in_year,
        total_proceeds=total_proceeds,
        total_base_cost=total_base,
        total_gain=total_gain,
    )
