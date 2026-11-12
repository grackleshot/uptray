"""Arch Linux news feed reader with read-marker support."""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

NEWS_FEED_URL = "https://archlinux.org/feeds/news/"
_MAX_FEED_BYTES = 1_000_000


@dataclass(frozen=True)
class NewsItem:
    """One entry from the Arch Linux news feed."""

    title: str
    link: str
    published: datetime


def parse_feed(xml_text: str) -> list[NewsItem]:
    """Parse an RSS 2.0 feed document into news items, newest first.

    Entries missing a title or link are skipped; unparsable dates fall back
    to a minimal datetime so the item still renders.
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []

    items: list[NewsItem] = []
    for entry in root.iter("item"):
        title = (entry.findtext("title") or "").strip()
        link = (entry.findtext("link") or "").strip()
        if not title or not link:
            continue
        published = _parse_pubdate(entry.findtext("pubDate"))
        items.append(NewsItem(title=title, link=link, published=published))
    items.sort(key=lambda item: item.published, reverse=True)
    return items


def fetch_news(timeout: float = 10.0, url: str = NEWS_FEED_URL) -> list[NewsItem]:
    """Fetch and parse the Arch news feed. Raises on network errors."""
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = response.read(_MAX_FEED_BYTES)
    return parse_feed(payload.decode("utf-8", errors="replace"))


def new_items(items: list[NewsItem], last_seen: str | None) -> list[NewsItem]:
    """Return items published after the last-read marker.

    When ``last_seen`` is None (first run) nothing is flagged as new, so the
    feed history does not flood the tray with "new" items on installation.
    """
    if last_seen is None:
        return []
    try:
        cutoff = datetime.fromisoformat(last_seen)
    except ValueError:
        return []
    return [item for item in items if item.published > cutoff]


def newest_marker(items: list[NewsItem]) -> str | None:
    """ISO timestamp of the newest item, for persisting a read marker."""
    return items[0].published.isoformat() if items else None


def _parse_pubdate(raw: str | None) -> datetime:
    """Parse an RFC 822 pubDate, falling back to epoch for malformed values."""
    text = (raw or "").strip()
    if text:
        try:
            return parsedate_to_datetime(text)
        except (TypeError, ValueError):
            pass
    return datetime.fromtimestamp(0)
