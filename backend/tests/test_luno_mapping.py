"""Luno symbol mapping: which app coins are tradeable on Luno in USDT."""

from app.brokers.mapping import app_base, is_tradeable, to_luno_pair

TRADEABLE = {
    "BTCUSDT": "XBTUSDT",  # Bitcoin is XBT on Luno
    "ETHUSDT": "ETHUSDT",
    "BNBUSDT": "BNBUSDT",
    "SOLUSDT": "SOLUSDT",
    "XRPUSDT": "XRPUSDT",
    "ADAUSDT": "ADAUSDT",
    "DOGEUSDT": "DOGEUSDT",
    "LINKUSDT": "LINKUSDT",
    "TRXUSDT": "TRXUSDT",
    "XLMUSDT": "XLMUSDT",
    "BCHUSDT": "BCHUSDT",
}
NOT_TRADEABLE = ["AVAXUSDT", "DOTUSDT", "LTCUSDT", "ATOMUSDT", "UNIUSDT",
                 "ETCUSDT", "FILUSDT", "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT"]


def test_app_base():
    assert app_base("BTCUSDT") == "BTC"
    assert app_base("ETHUSDT") == "ETH"


def test_tradeable_pairs_map_correctly():
    for ticker, pair in TRADEABLE.items():
        assert to_luno_pair(ticker) == pair
        assert is_tradeable(ticker) is True


def test_untradeable_coins_return_none():
    for ticker in NOT_TRADEABLE:
        assert to_luno_pair(ticker) is None
        assert is_tradeable(ticker) is False


def test_bitcoin_uses_xbt():
    # The one gotcha: BTC must become XBT on Luno.
    assert to_luno_pair("BTCUSDT") == "XBTUSDT"
