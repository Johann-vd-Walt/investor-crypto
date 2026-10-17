"""Dip-buying controls: two-speed regime, pullback entry, contrarian sentiment,
dip trade plan, point-in-time backtest context, settings coercion, and the
bot's accumulation sleeve. All opt-in; defaults must keep original behaviour."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.config import Settings
from app.services import settings as settings_service
from app.signals import backtest as bt
from app.signals import macro_regime, paper
from app.signals.engine import build_signal, trade_plan
from app.signals.scoring import LayerScore
from app.signals.sentiment import fear_greed_sentiment
from app.signals.technical import technical_score


def _settings(**kw) -> Settings:
    return Settings(_env_file=None).model_copy(update=kw)


def _uptrend_then_pullback(n_up=240, n_down=12, start=100.0, top=200.0, drop=0.08):
    """Long uptrend, then a short pullback of ``drop`` — still above the SMA200."""
    up = np.linspace(start, top, n_up)
    down = np.linspace(top, top * (1 - drop), n_down + 1)[1:]
    return np.concatenate([up, down])


def _choppy_pullback():
    """Uptrend, then a choppy ~6% pullback that leaves RSI in the 30-40 band."""
    closes = list(np.linspace(100, 200, 240))
    c = closes[-1]
    for i in range(14):
        c *= 0.985 if i % 2 == 0 else 1.006
        closes.append(c)
    return closes


def _df(close):
    close = np.asarray(close, dtype=float)
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": np.full(len(close), 1000.0)})


# --- Two-speed regime -------------------------------------------------------

def test_classic_regime_unchanged_by_default():
    btc = list(_uptrend_then_pullback())
    assert macro_regime.macro_regime_score({"BTC": btc}).score == -0.5  # pullback = risk-off


def test_two_speed_pullback_in_uptrend_is_positive():
    btc = list(_uptrend_then_pullback())
    layer = macro_regime.macro_regime_score({"BTC": btc}, mode="two_speed")
    assert layer.score > 0
    assert layer.extra["pullback"] is True
    assert "pullback" in layer.extra["regime"]


def test_two_speed_downtrend_below_long_sma_is_risk_off():
    btc = list(np.linspace(200, 100, 260))
    assert macro_regime.macro_regime_score({"BTC": btc}, mode="two_speed").score == -0.5


def test_two_speed_falls_back_to_classic_without_history():
    btc = list(np.linspace(40000, 30000, 25))
    layer = macro_regime.macro_regime_score({"BTC": btc}, mode="two_speed")
    assert layer.extra["mode"] == "classic" and layer.score == -0.5


# --- Pullback entry ---------------------------------------------------------

def test_pullback_off_by_default_and_on_when_enabled():
    df = _df(_choppy_pullback())
    off = technical_score(df)
    on = technical_score(df, pullback_rsi=40.0)
    assert off.extra["dip_entry"] is False
    assert on.extra["dip_entry"] is True
    assert 30 <= on.extra["rsi_14"] < 40
    assert on.score > off.score
    assert any("pullback" in s.detail for s in on.subsignals)


def test_pullback_never_fires_below_long_term_trend():
    df = _df(np.linspace(200, 100, 260))
    r = technical_score(df, pullback_rsi=40.0)
    assert r.extra["dip_entry"] is False


def test_dip_trade_plan_longer_horizon_wider_stop_smaller_size():
    s = _settings(pullback_entry=True)
    assert trade_plan(True, s) == (25, Decimal("3.0"))
    assert trade_plan(False, s) == (10, Decimal("2.0"))

    macro = LayerScore(score=0.5, extra={"regime": "x", "sector_tilts": {}})
    df = _df(_uptrend_then_pullback())
    kw = dict(security_id=1, sector=None, price_df=df, macro_layer=macro,
              sentiment_pairs=[(0.9, 1.0)] * 6, generated_at=datetime(2026, 10, 17))
    dip = build_signal(settings=_settings(pullback_entry=True, buy_threshold=0.0), **kw)
    base = build_signal(settings=_settings(buy_threshold=0.0), **kw)
    assert dip.horizon_days == 25 and base.horizon_days == 10
    assert dip.rationale["sizing"]["dip_entry"] is True
    assert dip.suggested_stop < base.suggested_stop  # wider stop


# --- Contrarian sentiment ---------------------------------------------------

def test_fear_greed_trend_mode_is_original_mapping():
    assert fear_greed_sentiment(75) == 0.5
    assert fear_greed_sentiment(25) == -0.5


def test_fear_greed_contrarian_mode():
    assert fear_greed_sentiment(10, mode="contrarian") == pytest.approx(0.6)
    assert fear_greed_sentiment(0, mode="contrarian") == 1.0
    assert fear_greed_sentiment(55, mode="contrarian") == 0.0
    assert fear_greed_sentiment(90, mode="contrarian") == pytest.approx(-0.6)


# --- Settings coercion ------------------------------------------------------

def test_settings_coercion_bools_and_choices():
    out = settings_service.coerce_overrides({
        "pullback_entry": "false", "dca_enabled": True, "regime_mode": "two_speed",
        "dca_ticker": "ethusdt",
    })
    assert out["pullback_entry"] is False and out["dca_enabled"] is True
    assert out["regime_mode"] == "two_speed" and out["dca_ticker"] == "ETHUSDT"
    with pytest.raises(ValueError):
        settings_service.coerce_overrides({"regime_mode": "yolo"})
    with pytest.raises(ValueError):
        settings_service.coerce_overrides({"luno_only_universe": "maybe"})


# --- Backtest context -------------------------------------------------------

def test_context_by_date_is_point_in_time():
    d0 = date(2025, 1, 1)
    closes = list(_uptrend_then_pullback())
    btc = [(d0 + timedelta(days=i), c) for i, c in enumerate(closes)]
    fng = [(d0 + timedelta(days=10), 10.0)]
    ctx = bt.context_by_date(btc, fng, _settings(sentiment_mode="contrarian"))
    assert ctx[d0][1] == 0.0                       # before any F&G reading
    assert ctx[d0 + timedelta(days=10)][1] > 0     # extreme fear -> buy-side
    # Truncating the future must not change past values (no lookahead).
    ctx_short = bt.context_by_date(btc[:100], fng, _settings(sentiment_mode="contrarian"))
    for d, v in ctx_short.items():
        assert ctx[d] == v


class _Bar:
    def __init__(self, dt, c):
        self.bar_datetime = dt
        self.open = self.close = Decimal(str(c))
        self.high = Decimal(str(c * 1.01))
        self.low = Decimal(str(c * 0.99))
        self.volume = Decimal("1000")


def test_walk_forward_with_context_runs_and_skips_missing_dates():
    closes = list(_uptrend_then_pullback()) + list(np.linspace(185, 220, 40))
    t0 = datetime(2025, 1, 1)
    bars = [_Bar(t0 + timedelta(days=i), c) for i, c in enumerate(closes)]
    costs = paper.Costs(brokerage_pct=Decimal("0.1"), slippage_pct=Decimal("0.1"), stt_pct=Decimal(0))
    s = _settings(buy_threshold=0.0)
    assert bt.walk_forward(ticker="X", bars=bars, settings=s, costs=costs, context={}) == []
    btc = [(b.bar_datetime.date(), float(b.close)) for b in bars]
    ctx = bt.context_by_date(btc, [], s)
    assert bt.walk_forward(ticker="X", bars=bars, settings=s, costs=costs, context=ctx)


# --- Accumulation sleeve (DB-backed, rolled back) ---------------------------

def _db_ok() -> bool:
    try:
        from app.db.session import check_db_connection
        return check_db_connection()[0]
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _db_ok(), reason="DB not reachable.")
def test_dca_step_paper_buys_then_waits_for_interval():
    from sqlalchemy import select

    from app.bot import engine
    from app.db.models import BotPosition, BotState, Security
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        sec = db.scalar(select(Security).where(Security.ticker == "BTCUSDT"))
        if sec is None:
            pytest.skip("BTCUSDT not seeded")
        # Isolate from any existing paper accumulation rows.
        db.query(BotPosition).filter(BotPosition.kind == "dca", BotPosition.venue == "paper").delete()
        st = BotState(id=99, cash=Decimal("1000"), daily_cap_usd=Decimal("100"),
                      daily_spent_usd=Decimal(0), max_order_usd=Decimal("20"), dry_run=True)
        s = _settings(dca_enabled=True, dca_amount_usd=Decimal("50"), dca_min_drawdown_pct=Decimal(0))
        now = datetime(2030, 1, 1, 12, 0)
        res = engine._dca_step(db, st, s, None, sec=sec, venue="paper", live=False, now=now,
                               px=Decimal("50000"), gross_in=Decimal("1.002"))
        assert res == "bought"
        assert st.cash < Decimal("951")
        db.flush()
        again = engine._dca_step(db, st, s, None, sec=sec, venue="paper", live=False,
                                 now=now + timedelta(days=1), px=Decimal("50000"), gross_in=Decimal("1.002"))
        assert again == "not_due"
        # Drawdown gate: an absurd 99% requirement blocks the buy.
        gated = engine._dca_step(db, st, s.model_copy(update={"dca_min_drawdown_pct": Decimal(99)}), None,
                                 sec=sec, venue="paper", live=False, now=now + timedelta(days=30),
                                 px=Decimal("50000"), gross_in=Decimal("1.002"))
        assert gated in ("above_gate", "no_history")
    finally:
        db.rollback()
        db.close()
