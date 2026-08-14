"""SENS announcements via a configurable RSS feed (Phase D).

There is no free, authoritative SENS API — the JSE's feed is licensed, and the
usable free sources are RSS/HTML that may be empty or rate-limited. So this
reads a **configurable** RSS feed (``SENS_RSS_URL``) and parses standard RSS
items. It ingests whatever the feed provides; if the feed is empty, the job
honestly records zero rather than inventing announcements (Guardrail 2.7).

The parser is pure and fixture-tested (§14).
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger("app.providers.sens")

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


@dataclass
class SensItem:
    headline: str
    url: str
    summary: str | None
    published_at: datetime | None
    category: str | None
    raw: dict


def _text(el: ET.Element | None) -> str | None:
    return el.text.strip() if el is not None and el.text else None


def parse_sens_rss(xml_text: str) -> list[SensItem]:
    """Parse RSS 2.0 ``<item>`` entries into SensItems. Skips items without a
    title or link; never fabricates missing fields."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"SENS feed is not valid XML: {exc}") from exc

    items: list[SensItem] = []
    for it in root.findall(".//item"):
        title = _text(it.find("title"))
        link = _text(it.find("link"))
        if not title or not link:
            continue
        pub_raw = _text(it.find("pubDate"))
        published = None
        if pub_raw:
            try:
                published = parsedate_to_datetime(pub_raw)
                if published.tzinfo is not None:
                    published = published.replace(tzinfo=None)  # store naive
            except (TypeError, ValueError):
                published = None
        category = _text(it.find("category"))
        items.append(
            SensItem(
                headline=title,
                url=link,
                summary=_text(it.find("description")),
                published_at=published,
                category=category,
                raw={"title": title, "link": link, "pubDate": pub_raw, "category": category},
            )
        )
    return items


class SensRssProvider:
    def __init__(self, feed_url: str) -> None:
        self._url = feed_url

    @property
    def name(self) -> str:
        return "sens_rss"

    def get_recent(self) -> list[SensItem]:
        resp = httpx.get(self._url, headers={"User-Agent": _USER_AGENT}, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        return parse_sens_rss(resp.text)
