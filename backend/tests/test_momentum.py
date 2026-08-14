"""Phase B: momentum + liquidity unit tests (deterministic, §14)."""

from decimal import Decimal

from app.signals import momentum


def test_average_daily_value_zar():
    # Native crypto: value = close * volume. 100 units/day @ $10,000 -> $1,000,000/day.
    adv = momentum.average_daily_value_zar([10000.0] * 20, [100.0] * 20, lookback=20)
    assert adv == Decimal("1000000.0")


def test_is_liquid_threshold():
    closes = [10000.0] * 20
    vols = [100.0] * 20  # $1,000,000/day traded value
    assert momentum.is_liquid(closes, vols, min_zar=Decimal("500000"), lookback=20)
    assert not momentum.is_liquid(closes, vols, min_zar=Decimal("5000000"), lookback=20)


def test_momentum_value_positive_uptrend():
    closes = [100.0 + i for i in range(200)]  # steadily rising
    m = momentum.momentum_value(closes, lookback=90, skip=5)
    assert m is not None and m > 0


def test_momentum_value_none_when_too_short():
    assert momentum.momentum_value([1.0, 2.0, 3.0], lookback=90, skip=5) is None


def test_cross_sectional_scores_rank_to_minus1_plus1():
    scores = momentum.cross_sectional_scores({"a": 0.1, "b": 0.5, "c": -0.2})
    assert scores["b"] == 1.0    # best momentum -> +1
    assert scores["c"] == -1.0   # worst -> -1
    assert -1.0 < scores["a"] < 1.0
    # Nones are neutral, not ranked.
    scores2 = momentum.cross_sectional_scores({"a": None, "b": 0.5})
    assert scores2["a"] == 0.0
