"""Phase 5: deterministic tests for the technical / macro / sentiment layers
and fusion (§14)."""

from datetime import datetime

import numpy as np
import pandas as pd

from app.config import Settings
from app.db.models import SignalDirection
from app.signals import macro_regime
from app.signals.engine import build_signal
from app.signals.scoring import LayerScore
from app.signals.sentiment import sentiment_score
from app.signals.technical import technical_score


def _uptrend_df(n=80):
    close = np.linspace(100, 200, n)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.full(n, 1000.0),
        }
    )


def _downtrend_df(n=80):
    close = np.linspace(200, 100, n)
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": np.full(n, 1000.0)}
    )


# --- Technical ---

def test_technical_uptrend_is_positive():
    r = technical_score(_uptrend_df())
    assert r.score > 0
    assert any(s.name == "sma_cross" and s.contribution > 0 for s in r.subsignals)
    assert r.extra["atr"] is not None


def test_technical_downtrend_is_negative():
    assert technical_score(_downtrend_df()).score < 0


def test_technical_insufficient_history():
    r = technical_score(_uptrend_df(n=10))
    assert r.score == 0.0
    assert "insufficient" in r.extra.get("note", "")


# --- Macro regime ---

def test_macro_btc_uptrend_is_risk_on():
    series = {"BTC": list(np.linspace(30000, 40000, 25))}  # BTC trending up
    layer = macro_regime.macro_regime_score(series)
    assert layer.score > 0
    assert "risk-on" in layer.extra["regime"]


def test_macro_btc_downtrend_is_risk_off():
    series = {"BTC": list(np.linspace(40000, 30000, 25))}
    layer = macro_regime.macro_regime_score(series)
    assert layer.score < 0


def test_macro_empty_is_neutral():
    layer = macro_regime.macro_regime_score({})
    assert layer.score == 0.0
    assert macro_regime.sector_tilt(layer, "Layer 1") == 0.0


# --- Sentiment ---

def test_sentiment_positive_and_volume_dampening():
    strong = sentiment_score([(0.8, 1.0)] * 6)
    weak = sentiment_score([(0.8, 1.0)])
    assert strong.score > weak.score > 0  # more coverage -> higher conviction


def test_sentiment_no_news_is_zero():
    r = sentiment_score([])
    assert r.score == 0.0 and r.extra["article_count"] == 0


# --- Fusion ---

def test_fusion_buy_on_strong_bull_inputs():
    s = Settings(_env_file=None)
    macro = LayerScore(score=0.5, extra={"regime": "risk-on", "sector_tilts": {"Basic Materials": 0.2}})
    draft = build_signal(
        security_id=1, sector="Basic Materials", price_df=_uptrend_df(),
        macro_layer=macro, sentiment_pairs=[(0.7, 1.0)] * 6,
        settings=s, generated_at=datetime(2026, 7, 20),
    )
    assert draft.direction == SignalDirection.BUY
    assert draft.suggested_entry is not None
    assert draft.suggested_stop is not None and draft.suggested_stop < draft.suggested_entry
    assert draft.suggested_size and draft.suggested_size > 0
    assert draft.rationale["technical"]["signals"]  # transparent reasons present
    assert draft.confidence is None  # no measured hit rate yet (Phase 6)


def test_fusion_hold_when_mixed():
    s = Settings(_env_file=None)
    macro = LayerScore(score=0.0, extra={"regime": "neutral", "sector_tilts": {}})
    # Flat price -> weak technical; no news -> neutral sentiment.
    flat = pd.DataFrame(
        {"open": [100.0] * 80, "high": [101.0] * 80, "low": [99.0] * 80,
         "close": [100.0] * 80, "volume": [1000.0] * 80}
    )
    draft = build_signal(
        security_id=1, sector=None, price_df=flat, macro_layer=macro,
        sentiment_pairs=[], settings=s, generated_at=datetime(2026, 7, 20),
    )
    assert draft.direction == SignalDirection.HOLD
    assert draft.suggested_stop is None  # no stop for HOLD
