"""Tests for the Arch news feed reader."""

from __future__ import annotations

from datetime import datetime

from uptray.core.arch_news import (
    NewsItem,
    new_items,
    newest_marker,
    parse_feed,
)

_SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Arch Linux: Recent news updates</title>
  <item>
    <title>Older announcement</title>
    <link>https://archlinux.org/news/older-announcement/</link>
    <pubDate>Mon, 20 Oct 2026 00:00:00 +0000</pubDate>
  </item>
  <item>
    <title>newer announcement now required</title>
    <link>https://archlinux.org/news/newer-announcement/</link>
    <pubDate>Wed, 04 Nov 2026 00:00:00 +0000</pubDate>
  </item>
  <item>
    <title></title>
    <link></link>
  </item>
</channel></rss>
"""


def test_parse_feed_returns_newest_first_and_skips_empty_entries() -> None:
    items = parse_feed(_SAMPLE_FEED)

    assert len(items) == 2
    assert items[0].title == "newer announcement now required"
    assert items[1].title == "Older announcement"
    assert items[0].link == "https://archlinux.org/news/newer-announcement/"


def test_parse_feed_handles_invalid_xml() -> None:
    assert parse_feed("<not-rss") == []


def test_new_items_filters_against_last_seen_marker() -> None:
    items = [
        NewsItem("b", "https://example.com/b", datetime.fromisoformat("2026-11-04T00:00:00")),
        NewsItem("a", "https://example.com/a", datetime.fromisoformat("2026-10-20T00:00:00")),
    ]

    fresh = new_items(items, "2026-10-21T00:00:00")

    assert [item.title for item in fresh] == ["b"]


def test_new_items_without_marker_returns_nothing() -> None:
    items = [NewsItem("a", "https://example.com/a", datetime.fromisoformat("2026-11-04T00:00:00"))]

    assert new_items(items, None) == []
    assert new_items(items, "garbage") == []


def test_newest_marker_uses_newest_item() -> None:
    items = [
        NewsItem("b", "https://example.com/b", datetime.fromisoformat("2026-11-04T00:00:00")),
    ]

    assert newest_marker(items) == "2026-11-04T00:00:00"
    assert newest_marker([]) is None
