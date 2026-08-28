"""Real-time trading bot — PAPER by default, optional LIVE on Luno.

A continuous tick loop that acts on the strategy's fresh BUY signals: it marks
open positions to live Binance prices, exits on stop/horizon, and opens new
positions, sized to a budget, subject to caps.

Two modes, controlled by BotState:
  - mode='paper' (default): everything simulated. No exchange, no real money.
  - mode='live'           : trades REAL money on Luno — but ONLY when dry_run is
                            off AND Luno keys are configured AND per-order/daily
                            caps allow AND the coin is tradeable on Luno. With
                            dry_run on (the default for live), it logs the exact
                            order it WOULD send and simulates the fill.

Safety is layered so real orders can't happen by accident: keys live only in the
environment, dry_run defaults on, caps are enforced before every order, and the
kill switch is simply flipping mode back to 'paper' (or stopping the bot).

Honest note: the backtests show no established edge (Deflated Sharpe ~22%) and
buy-and-hold beat the strategy, so live trading is expected to lose money.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.brokers.luno import LunoBroker, LunoError
from app.brokers.mapping import to_luno_pair
from app.config import get_settings
from app.db.models import (
    BotEquity, BotEvent, BotPosition, BotState, Security, Signal,
    SignalDirection, SignalStatus,
)
from app.db.session import SessionLocal
from app.services import settings as settings_service

logger = logging.getLogger("app.bot")

_EQUITY_RETENTION_DAYS = 7
_EVENT_RETENTION_DAYS = 30
_SIGNAL_MAX_AGE_DAYS = 2
_MIN_POSITION_USD = Decimal("10")  # skip dust-sized positions
_QUOTE = "USDT"


# --------------------------------------------------------------- live prices ---
def fetch_live_prices(symbols: list[str], base_url: str) -> dict[str, Decimal]:
    """Current price per symbol from Binance ticker/price (batch, keyless)."""
    if not symbols:
        return {}
    url = f"{base_url.rstrip('/')}/api/v3/ticker/price"
    try:
        payload = json.dumps(sorted(set(symbols)), separators=(",", ":"))
        resp = httpx.get(url, params={"symbols": payload}, timeout=15.0)
        resp.raise_for_status()
        out: dict[str, Decimal] = {}
        for row in resp.json():
            try:
                out[row["symbol"].upper()] = Decimal(str(row["price"]))
            except Exception:  # noqa: BLE001
                continue
        return out
    except httpx.HTTPError as exc:
        logger.warning("bot: live price fetch failed: %s", exc)
        return {}


# ------------------------------------------------------------------ broker -----
def get_broker() -> LunoBroker | None:
    """Luno client from env keys, or None if live trading isn't configured."""
    s = get_settings()
    if not s.luno_api_key_id or not s.luno_api_key_secret:
        return None
    return LunoBroker(s.luno_api_key_id, s.luno_api_key_secret)


def _reconcile(broker: LunoBroker, order_id: str, *, tries: int = 6) -> tuple[Decimal, Decimal, Decimal, str]:
    """Poll a just-placed order until filled. Returns (base, counter, fee_counter, status)."""
    last: dict = {}
    for _ in range(tries):
        try:
            last = broker.get_order(order_id)
        except LunoError as exc:
            logger.warning("bot: reconcile fetch failed: %s", exc)
        status = str(last.get("status") or last.get("state") or "")
        if status == "COMPLETE":
            break
        time.sleep(1.0)
    base = Decimal(str(last.get("base", "0") or "0"))
    counter = Decimal(str(last.get("counter", "0") or "0"))
    fee = Decimal(str(last.get("fee_counter", "0") or "0"))
    return base, counter, fee, str(last.get("status") or last.get("state") or "?")


# ------------------------------------------------------------------- state -----
def get_state(db: Session) -> BotState | None:
    return db.get(BotState, 1)


def ensure_state(db: Session) -> BotState:
    st = db.get(BotState, 1)
    if st is None:
        settings = settings_service.get_effective_settings(db)
        cash = Decimal(settings.account_size)
        st = BotState(id=1, enabled=False, tick_seconds=60, mode="paper", dry_run=True,
                      max_order_usd=Decimal("20"), daily_cap_usd=Decimal("100"),
                      daily_spent_usd=Decimal("0"),
                      initial_cash=cash, cash=cash, realized_pnl=Decimal(0))
        db.add(st)
        db.commit()
    return st


def _log(db: Session, kind: str, detail: str, *, ticker: str | None = None, equity: Decimal | None = None) -> None:
    db.add(BotEvent(kind=kind, ticker=ticker, detail=detail, equity=equity))


def start(db: Session) -> BotState:
    st = ensure_state(db)
    st.enabled = True
    if st.started_at is None:
        st.started_at = datetime.utcnow()
    _log(db, "start", f"Bot enabled ({'LIVE' if st.mode == 'live' else 'paper'}"
                      f"{' · dry-run' if st.mode == 'live' and st.dry_run else ''}).")
    db.commit()
    return st


def stop(db: Session) -> BotState:
    st = ensure_state(db)
    st.enabled = False
    _log(db, "stop", "Bot disabled.")
    db.commit()
    return st


def reset(db: Session) -> BotState:
    """Flatten the PAPER portfolio only. Live (Luno) positions are never deleted
    here — that would make the bot forget real holdings it still needs to sell."""
    st = ensure_state(db)
    db.execute(delete(BotPosition).where(BotPosition.venue == "paper"))
    db.execute(delete(BotEquity))
    st.cash = st.initial_cash
    st.realized_pnl = Decimal(0)
    st.last_equity = None
    _log(db, "info", f"Paper portfolio reset to ${st.initial_cash:.0f}. (Live positions untouched.)")
    db.commit()
    return st


# ------------------------------------------------------- mode / guardrails -----
def set_mode(db: Session, mode: str) -> BotState:
    if mode not in ("paper", "live"):
        raise ValueError("mode must be 'paper' or 'live'")
    st = ensure_state(db)
    if mode == "live" and get_broker() is None:
        raise ValueError("No Luno API keys on the server. Set LUNO_API_KEY_ID and "
                         "LUNO_API_KEY_SECRET in backend/.env, then restart.")
    st.mode = mode
    note = "PAPER (simulated)" if mode == "paper" else ("LIVE · DRY-RUN" if st.dry_run else "LIVE · REAL MONEY")
    _log(db, "info", f"Mode -> {note}")
    db.commit()
    return st


def set_dry_run(db: Session, dry: bool) -> BotState:
    st = ensure_state(db)
    st.dry_run = bool(dry)
    _log(db, "info", "Dry-run ON (logging only)." if dry else "Dry-run OFF — REAL ORDERS WILL BE PLACED.")
    db.commit()
    return st


def set_caps(db: Session, *, max_order_usd: Decimal | None = None, daily_cap_usd: Decimal | None = None) -> BotState:
    st = ensure_state(db)
    if max_order_usd is not None:
        st.max_order_usd = Decimal(str(max_order_usd))
    if daily_cap_usd is not None:
        st.daily_cap_usd = Decimal(str(daily_cap_usd))
    _log(db, "info", f"Caps: max ${st.max_order_usd}/order, ${st.daily_cap_usd}/day.")
    db.commit()
    return st


def luno_status() -> dict:
    """Read-only connection check + balances (no orders)."""
    b = get_broker()
    if b is None:
        return {"configured": False, "error": "No Luno keys in server .env.", "balances": []}
    try:
        bals = b.balances()
        rows = [
            {"asset": a, "balance": float(v["balance"]), "available": float(v["available"]), "reserved": float(v["reserved"])}
            for a, v in sorted(bals.items()) if v["balance"] > 0
        ]
        return {"configured": True, "error": None, "balances": rows}
    except Exception as exc:  # noqa: BLE001
        return {"configured": True, "error": str(exc)[:200], "balances": []}
    finally:
        b.close()


# -------------------------------------------------------------------- tick -----
def tick(db: Session) -> dict:
    st = get_state(db)
    if st is None or not st.enabled:
        return {"skipped": "disabled"}

    live = st.mode == "live"
    broker = get_broker() if live else None
    if live and broker is None:
        _log(db, "error", "Live mode but no Luno keys — no trades. Set keys or switch to paper.")
        db.commit()
        return {"error": "no_keys"}

    settings = settings_service.get_effective_settings(db)
    now = datetime.utcnow()
    venue = "luno" if live else "paper"

    # Paper cost model (live uses Luno's real fees via reconciliation).
    entry_frac = float(settings.brokerage_pct + settings.slippage_pct + settings.stt_pct) / 100.0
    exit_frac = float(settings.brokerage_pct + settings.slippage_pct) / 100.0
    gross_in = Decimal(str(1 + entry_frac))
    gross_out = Decimal(str(1 - exit_frac))

    # Daily spend cap bookkeeping (live).
    today = now.date()
    if st.daily_spent_date != today:
        st.daily_spent_usd = Decimal(0)
        st.daily_spent_date = today

    open_pos = list(db.scalars(
        select(BotPosition).where(BotPosition.status == "OPEN", BotPosition.venue == venue)
    ).all())
    acted = {sid for sid in db.scalars(
        select(BotPosition.signal_id).where(BotPosition.signal_id.is_not(None), BotPosition.venue == venue)
    ).all()}
    since = now - timedelta(days=_SIGNAL_MAX_AGE_DAYS)
    sigs = list(db.scalars(
        select(Signal).where(
            Signal.direction == SignalDirection.BUY,
            Signal.status == SignalStatus.OPEN,
            Signal.generated_at >= since,
        ).order_by(Signal.generated_at.desc())
    ).all())

    sec_ids = {p.security_id for p in open_pos} | {s.security_id for s in sigs}
    id_to_ticker = {
        s.id: s.ticker for s in db.scalars(select(Security).where(Security.id.in_(sec_ids))).all()
    } if sec_ids else {}
    prices = fetch_live_prices(list(id_to_ticker.values()), get_settings().binance_base_url)

    summary = {"closed": 0, "opened": 0, "skipped": 0, "mode": st.mode, "dry_run": bool(st.dry_run)}

    def mark(p: BotPosition) -> Decimal:
        m = prices.get(id_to_ticker.get(p.security_id))
        return p.quantity * (m if m is not None else p.entry_price)

    # 1. Manage open positions against live prices; exit on stop/horizon.
    survivors: list[BotPosition] = []
    held: set[int] = set()
    for p in open_pos:
        tk = id_to_ticker.get(p.security_id)
        px = prices.get(tk) if tk else None
        if px is None:
            survivors.append(p); held.add(p.security_id); continue
        reason = None
        if p.stop_price is not None and px <= p.stop_price:
            reason = "stop"
        elif (now - p.entry_datetime).days >= p.horizon_days:
            reason = "horizon"
        if not reason:
            survivors.append(p); held.add(p.security_id); continue

        if live and not st.dry_run:
            pair = to_luno_pair(tk)
            try:
                coid = f"trader-x-{p.id}-{int(now.timestamp())}"
                oid = broker.market_sell(pair, p.quantity, coid)
                base, counter, fee, status = _reconcile(broker, oid)
                proceeds = counter - fee
                pnl = proceeds - p.cost_basis
                p.exit_price = (counter / base) if base > 0 else px
                p.luno_order_id = oid
                _log(db, "close", f"LIVE {reason} SELL {p.quantity:.6f} {pair} -> ${proceeds:.2f} (fee ${fee:.2f}), P&L ${pnl:.2f} [{status}]", ticker=tk)
            except LunoError as exc:
                _log(db, "error", f"LIVE sell failed for {tk}: {exc}", ticker=tk)
                survivors.append(p); held.add(p.security_id); continue
        else:
            proceeds = px * p.quantity * gross_out
            pnl = proceeds - p.cost_basis
            p.exit_price = px
            tag = "DRY-RUN " if (live and st.dry_run) else ""
            _log(db, "close", f"{tag}{reason} exit {p.quantity:.6f} @ {px:.4f}, P&L ${pnl:.2f}", ticker=tk)

        p.status, p.exit_datetime, p.pnl, p.exit_reason = "CLOSED", now, pnl, reason
        st.realized_pnl += pnl
        if not live:
            st.cash += proceeds
        summary["closed"] += 1

    # 2. Open fresh actionable BUYs.
    if live:
        try:
            usdt_avail = broker.available(_QUOTE)
        except Exception as exc:  # noqa: BLE001
            _log(db, "error", f"Could not read Luno balance: {exc}")
            usdt_avail = Decimal(0)
        st.cash = usdt_avail  # display: real USDT
        equity_est = usdt_avail + sum((mark(p) for p in survivors), Decimal(0))
    else:
        equity_est = st.cash + sum((mark(p) for p in survivors), Decimal(0))

    max_open = max(1, settings.max_open_positions)
    n_open = len(held)
    for s in sigs:
        if s.id in acted or s.security_id in held or n_open >= max_open:
            if n_open >= max_open:
                break
            continue
        tk = id_to_ticker.get(s.security_id)
        px = prices.get(tk) if tk else None
        if px is None or px <= 0:
            continue

        if live:
            pair = to_luno_pair(tk)
            if pair is None:
                continue  # coin not tradeable on Luno — silently skip
            daily_left = st.daily_cap_usd - st.daily_spent_usd
            spend = min(st.max_order_usd, daily_left, st.cash * Decimal("0.99"))
            if spend < _MIN_POSITION_USD:
                summary["skipped"] += 1
                continue
            rule = broker.rule(pair) or {}
            min_vol = Decimal(str(rule.get("min_volume", "0") or "0"))
            if min_vol > 0 and (spend / px) < min_vol:
                summary["skipped"] += 1
                continue
            coid = f"trader-{s.id}-{int(now.timestamp())}"
            if st.dry_run:
                qty = (spend / px).quantize(Decimal("0.00000001"))
                cost = spend
                _log(db, "open", f"DRY-RUN LIVE BUY ${spend:.2f} of {pair} (~{qty:.6f} @ {px:.4f})", ticker=tk)
            else:
                try:
                    oid = broker.market_buy(pair, spend, coid)
                    base, counter, fee, status = _reconcile(broker, oid)
                    if base <= 0:
                        _log(db, "error", f"LIVE buy for {tk} not filled [{status}] — skipping.", ticker=tk)
                        continue
                    qty = base
                    cost = counter + fee
                    px = cost / qty  # effective fill price
                    _log(db, "open", f"LIVE BUY {qty:.6f} {pair} for ${cost:.2f} (fee ${fee:.2f}) [{status}]", ticker=tk)
                except LunoError as exc:
                    _log(db, "error", f"LIVE buy failed for {tk}: {exc}", ticker=tk)
                    continue
            db.add(BotPosition(
                security_id=s.security_id, signal_id=s.id, entry_datetime=now,
                entry_price=px, quantity=qty, stop_price=s.suggested_stop,
                horizon_days=s.horizon_days, cost_basis=cost, status="OPEN",
                venue="luno", luno_order_id=(None if st.dry_run else coid),
            ))
            st.daily_spent_usd += spend
        else:
            target = min(equity_est / Decimal(max_open), st.cash * Decimal("0.99"))
            if target < _MIN_POSITION_USD:
                summary["skipped"] += 1
                continue
            qty = (target / (px * gross_in)).quantize(Decimal("0.00000001"))
            cost = px * qty * gross_in
            if qty <= 0 or cost > st.cash:
                summary["skipped"] += 1
                continue
            db.add(BotPosition(
                security_id=s.security_id, signal_id=s.id, entry_datetime=now,
                entry_price=px, quantity=qty, stop_price=s.suggested_stop,
                horizon_days=s.horizon_days, cost_basis=cost, status="OPEN", venue="paper",
            ))
            st.cash -= cost
            stop_txt = f", stop {s.suggested_stop:.4f}" if s.suggested_stop is not None else ""
            _log(db, "open", f"BUY {qty:.6f} @ {px:.4f} (${cost:.0f}){stop_txt}", ticker=tk)

        held.add(s.security_id); acted.add(s.id); n_open += 1
        summary["opened"] += 1

    # 3. Mark-to-market equity.
    db.flush()
    equity = st.cash
    for p in db.scalars(select(BotPosition).where(BotPosition.status == "OPEN", BotPosition.venue == venue)).all():
        m = prices.get(id_to_ticker.get(p.security_id))
        equity += p.quantity * (m if m is not None else p.entry_price)
    st.last_equity = equity
    st.last_tick_at = now
    db.add(BotEquity(ts=now, equity=equity, cash=st.cash))

    if now.minute % 15 == 0:
        _log(db, "info", f"Heartbeat — {st.mode} equity ${equity:.2f}, {n_open} open, cash ${st.cash:.2f}", equity=equity)
    if now.minute == 0:
        db.execute(delete(BotEquity).where(BotEquity.ts < now - timedelta(days=_EQUITY_RETENTION_DAYS)))
        db.execute(delete(BotEvent).where(BotEvent.created_at < now - timedelta(days=_EVENT_RETENTION_DAYS)))

    db.commit()
    summary["equity"] = float(equity)
    return summary


def safe_tick() -> None:
    """Scheduler entry point — one tick, never raises."""
    db = SessionLocal()
    try:
        result = tick(db)
        if result.get("opened") or result.get("closed"):
            logger.info("bot tick: %s", result)
    except Exception:  # noqa: BLE001 — a bot failure must never kill the scheduler
        db.rollback()
        logger.exception("bot tick crashed")
        try:
            _log(db, "error", "Tick failed — see server logs.")
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    finally:
        db.close()
