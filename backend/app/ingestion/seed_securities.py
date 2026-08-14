"""Seed the tradable universe with crypto assets (Binance USDT pairs).

The ``securities`` table is repurposed as the crypto asset registry: ``ticker``
is the Binance symbol (e.g. BTCUSDT), ``sector`` is a category, ``currency`` is
the quote currency (USDT). Running this WIPES the old (JSE) domain data so the
app starts clean on crypto.

Run:  python -m app.ingestion.seed_securities
"""

from __future__ import annotations

import logging

from sqlalchemy import delete

from app.db import models as m
from app.db.session import SessionLocal
from app.repositories import securities as securities_repo

logger = logging.getLogger("app.seed")

# Major, liquid Binance USDT pairs. symbol / name / category (all public facts).
CRYPTO_ASSETS: list[dict[str, str]] = [
    {"ticker": "BTCUSDT", "name": "Bitcoin", "sector": "Layer 1"},
    {"ticker": "ETHUSDT", "name": "Ethereum", "sector": "Layer 1"},
    {"ticker": "BNBUSDT", "name": "BNB", "sector": "Exchange"},
    {"ticker": "SOLUSDT", "name": "Solana", "sector": "Layer 1"},
    {"ticker": "XRPUSDT", "name": "XRP", "sector": "Payments"},
    {"ticker": "ADAUSDT", "name": "Cardano", "sector": "Layer 1"},
    {"ticker": "DOGEUSDT", "name": "Dogecoin", "sector": "Meme"},
    {"ticker": "AVAXUSDT", "name": "Avalanche", "sector": "Layer 1"},
    {"ticker": "LINKUSDT", "name": "Chainlink", "sector": "Oracle"},
    {"ticker": "DOTUSDT", "name": "Polkadot", "sector": "Layer 0"},
    {"ticker": "LTCUSDT", "name": "Litecoin", "sector": "Payments"},
    {"ticker": "TRXUSDT", "name": "TRON", "sector": "Layer 1"},
    {"ticker": "ATOMUSDT", "name": "Cosmos", "sector": "Layer 0"},
    {"ticker": "UNIUSDT", "name": "Uniswap", "sector": "DeFi"},
    {"ticker": "XLMUSDT", "name": "Stellar", "sector": "Payments"},
    {"ticker": "BCHUSDT", "name": "Bitcoin Cash", "sector": "Payments"},
    {"ticker": "ETCUSDT", "name": "Ethereum Classic", "sector": "Layer 1"},
    {"ticker": "FILUSDT", "name": "Filecoin", "sector": "Storage"},
    {"ticker": "NEARUSDT", "name": "NEAR Protocol", "sector": "Layer 1"},
    {"ticker": "APTUSDT", "name": "Aptos", "sector": "Layer 1"},
    {"ticker": "ARBUSDT", "name": "Arbitrum", "sector": "Layer 2"},
    {"ticker": "OPUSDT", "name": "Optimism", "sector": "Layer 2"},
]

# Domain tables to clear, children first (FK-safe).
_WIPE_ORDER = [
    m.PaperTrade, m.Trade, m.Signal, m.IndicatorValue, m.PriceBar,
    m.NewsSentiment, m.NewsArticle, m.SensAnnouncement, m.MacroSeries,
    m.Watchlist, m.ProviderCall, m.Security,
]


def wipe_domain_data(db) -> None:
    for model in _WIPE_ORDER:
        db.execute(delete(model))
    db.commit()


def seed(db) -> int:
    for row in CRYPTO_ASSETS:
        securities_repo.upsert(
            db,
            ticker=row["ticker"],
            name=row["name"],
            sector=row["sector"],
            isin=None,
            currency="USDT",
        )
    db.commit()
    return len(CRYPTO_ASSETS)


def run(*, wipe: bool = True) -> None:
    db = SessionLocal()
    try:
        if wipe:
            logger.warning("Wiping old (JSE) domain data before seeding crypto assets...")
            wipe_domain_data(db)
        count = seed(db)
        logger.info("Seeded %d crypto assets.", count)
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run()
