"""Anthropic News — HTML scraper (lane 1).

Anthropic publishes no RSS feed (every rss/feed path 404s), so this is the
one sanctioned scraper (작업 2). Best-effort, title + URL + date only; any
failure skips silently and logs, never raising into the pipeline.

Robustness: the /news listing renders cards in 3+ inconsistent React DOM
layouts (h2 / h4 / no-heading), so we do NOT scrape titles from the listing.
Instead:
  - dates come from the listing's <time> tags (stable), one per /news/ link;
  - titles come from each in-window article's og:title meta (stable).
Only articles inside the collection window are fetched (usually 0–3/run).
Items without a parseable date are skipped (avoids pulling stale posts).
"""

from __future__ import annotations

import html as _html
import re
from datetime import datetime, timezone
from typing import Optional

from ..models import TIER_MULTIPLIER, Item
from .base import (
    BROWSER_HEADERS, FeedStatus, clean_text, http_get, now_iso, url_hash, within_window,
)

NEWS_URL = "https://www.anthropic.com/news"
BASE = "https://www.anthropic.com"

_LINK_RE = re.compile(r'href="(/news/[^"?#]+)"')
_TIME_RE = re.compile(r"<time[^>]*>(.*?)</time>", re.DOTALL)
_OG_RE = re.compile(r'<meta property="og:title" content="([^"]+)"')
_OGDESC_RE = re.compile(r'<meta property="og:description" content="([^"]+)"')
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return _html.unescape(_TAG_RE.sub("", s)).strip()


def _parse_date(text: str) -> Optional[datetime]:
    text = _clean(text)
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _og_title(article_html: str) -> Optional[str]:
    m = _OG_RE.search(article_html)
    if m:
        return _clean(m.group(1))
    m = _TITLE_RE.search(article_html)
    if m:  # "<title>Foo \ Anthropic</title>" → "Foo"
        return _clean(m.group(1)).split(" \\ ")[0].strip() or None
    return None


def collect_anthropic(lane_conf: dict) -> tuple[list[Item], FeedStatus]:
    lane = lane_conf["lane"]
    name = "Anthropic News (scraper)"
    collected = now_iso()

    try:
        page = http_get(NEWS_URL, headers=BROWSER_HEADERS, retries=1).text
    except Exception as exc:  # noqa: BLE001 — scraper never breaks the pipeline
        return [], FeedStatus(lane, name, NEWS_URL, "error", note=type(exc).__name__)

    # slug → date, from the nearest <time> after each /news/ link.
    slug_date: dict[str, Optional[datetime]] = {}
    for m in _LINK_RE.finditer(page):
        slug = m.group(1)
        if slug in slug_date:
            continue
        tm = _TIME_RE.search(page, m.end(), m.end() + 900)
        slug_date[slug] = _parse_date(tm.group(1)) if tm else None

    items: list[Item] = []
    for slug, published in slug_date.items():
        # Require a real date in-window — skip undated (would pull stale posts).
        if published is None or not within_window(published):
            continue
        link = BASE + slug
        try:
            article_html = http_get(link, headers=BROWSER_HEADERS).text
        except Exception:  # noqa: BLE001 — per-article failure: skip, don't break
            continue
        title = _og_title(article_html)
        if not title:
            continue
        desc_m = _OGDESC_RE.search(article_html)
        abstract = clean_text(_clean(desc_m.group(1))) if desc_m else ""
        items.append(
            Item(
                url=link, url_hash=url_hash(link), title=title,
                source_domain="anthropic.com",
                lane=lane, lane_weight=lane_conf["lane_weight"],
                source_tier=lane_conf["source_tier"],
                tier_multiplier=TIER_MULTIPLIER[lane_conf["source_tier"]],
                content_type="blog",
                published_at=published.isoformat(),
                collected_at=collected,
                abstract=abstract or None,
            )
        )

    return items, FeedStatus(lane, name, NEWS_URL, "ok" if items else "empty",
                             kept=len(items), seen=len(slug_date))
