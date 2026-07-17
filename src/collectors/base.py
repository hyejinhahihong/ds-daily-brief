"""Shared collector utilities: HTTP, URL normalization, date windowing, RSS.

No LLM, no ranking, no sending — Phase 0 is pure deterministic collection.
"""

from __future__ import annotations

import calendar
import hashlib
import html as _html
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import httpx

from ..config import now_kst
from ..models import TIER_MULTIPLIER, Item

# Honest feed-reader UA. Measured better than a spoofed browser UA: the
# hard-blocked publisher feeds (Meta, Anthropic) 403 either way, while
# Medium-hosted feeds (TDS, ...) yield MORE to a plain UA than to a
# browser string (Cloudflare treats datacenter "browsers" as suspicious).
USER_AGENT = "ds-daily-brief/0.1 (+personal daily brief; feed reader)"
WINDOW_DAYS = 3  # SPEC §3.10 — 최근 3일 롤링 (기본값)
HTTP_TIMEOUT = 20.0

# UA 폴백: 정직한 UA 로 먼저 시도하고, 403/에러일 때만 브라우저 UA 로 재시도.
# (브라우저 UA 를 기본값으로 쓰면 Medium 계열 피드가 오히려 Cloudflare 에 막힌다 —
#  실측으로 확인됨. 그래서 '기본 정직 → 실패 시 브라우저'의 사다리로 간다.)
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Tracking query params dropped during normalization so the same article
# from different referrers hashes to one key (feeds the dedup, SPEC §3.11).
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "ref", "ref_src", "source", "fbclid", "gclid", "mc_cid",
    "mc_eid", "_hsenc", "_hsmi",
}


# --------------------------------------------------------------------------
# URL / hashing
# --------------------------------------------------------------------------
def normalize_url(url: str) -> str:
    """Lowercase host, strip fragment + tracking params, drop trailing slash."""
    p = urlparse(url.strip())
    scheme = p.scheme.lower() or "https"
    netloc = p.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    query = urlencode(
        [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in _TRACKING_PARAMS]
    )
    path = p.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()


def domain(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def now_iso() -> str:
    return now_kst().isoformat()  # collected_at — KST (SPEC §7.2)


# --------------------------------------------------------------------------
# Date windowing (SPEC §3.10)
# --------------------------------------------------------------------------
def struct_to_dt(struct_time: Any) -> Optional[datetime]:
    if not struct_time:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(struct_time), tz=timezone.utc)
    except (ValueError, OverflowError, TypeError, OSError):
        # Bogus feed dates (pre-epoch / far-future) — Windows rejects these.
        return None


# Collection window (SPEC §3.10). Default = 3-day rolling; an absolute
# `since` can be set (커버리지 검증용 창 확장) via set_window_since().
_WINDOW_SINCE: Optional[datetime] = None


def set_window_since(dt: Optional[datetime]) -> None:
    global _WINDOW_SINCE
    _WINDOW_SINCE = dt


def window_cutoff(days: int = WINDOW_DAYS) -> datetime:
    # 롤링 창 = "지금 - N일". 순간(instant)이라 UTC/KST 표현이 같은 시점이지만,
    # KST-aware 로 통일(피드 published_at 은 UTC-aware 파싱 → aware 비교 정상, SPEC §7.2).
    if _WINDOW_SINCE is not None:
        return _WINDOW_SINCE
    return now_kst() - timedelta(days=days)


def within_window(dt: Optional[datetime], days: int = WINDOW_DAYS) -> bool:
    """Undated items pass (can't be filtered) — counted separately upstream."""
    if dt is None:
        return True
    return dt >= window_cutoff(days)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def http_get(
    url: str,
    headers: Optional[dict[str, str]] = None,
    timeout: float = HTTP_TIMEOUT,
    retries: int = 1,
) -> httpx.Response:
    h = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        h.update(headers)
    import time

    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.get(url, headers=h, timeout=timeout, follow_redirects=True)
            # 5xx/429 are transient (arXiv API is flaky) → retried below; a
            # 4xx like 403/404 is a hard block — surfaced, not retried.
            resp.raise_for_status()
            return resp
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            code = exc.response.status_code
            if not (code == 429 or 500 <= code < 600):
                raise  # hard client error — no point retrying
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))  # linear backoff
    raise last_exc  # type: ignore[misc]


# --------------------------------------------------------------------------
# Diagnostics — per-feed status is a Phase 0 deliverable (reveals dead RSS)
# --------------------------------------------------------------------------
@dataclass
class FeedStatus:
    lane: int
    name: str
    url: str
    status: str          # ok | empty | error
    kept: int = 0        # items inside the window, after date filter
    seen: int = 0        # entries returned by the feed
    note: str = ""


# --------------------------------------------------------------------------
# Text cleaning (abstract capture — SPEC §8, Sonnet 집필 근거)
# --------------------------------------------------------------------------
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(s: Optional[str], limit: int = 4000) -> str:
    """Strip HTML tags, unescape entities, collapse whitespace, truncate.

    RSS <description>/<content> and arXiv <summary> arrive with markup and
    entities; this normalizes them to plain prose for ranking + writing.
    """
    if not s:
        return ""
    s = _HTML_TAG_RE.sub(" ", s)
    s = _html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def _rss_abstract(entry) -> str:
    """Best abstract from an RSS entry: full content if present, else summary."""
    raw = ""
    content = entry.get("content")
    if content and isinstance(content, list):
        raw = content[0].get("value", "") if content[0] else ""
    if not raw:
        raw = entry.get("summary") or entry.get("description") or ""
    return clean_text(raw)


# --------------------------------------------------------------------------
# RSS collection (lanes 1, 3, 5, 6, 8)
# --------------------------------------------------------------------------
def collect_rss_feed(feed: dict, lane_conf: dict) -> tuple[list[Item], FeedStatus]:
    lane = lane_conf["lane"]
    name = feed.get("name", feed["url"])
    url = feed["url"]
    tier = feed.get("source_tier", lane_conf["source_tier"])
    ctype = feed.get("content_type", lane_conf["content_type"])
    collected = now_iso()

    # UA 폴백 사다리: 정직한 UA → (실패 시) 브라우저 UA.
    ua_note = ""
    try:
        resp = http_get(url)
    except Exception as first_exc:  # noqa: BLE001
        try:
            resp = http_get(url, headers=BROWSER_HEADERS)
            ua_note = "browser-UA"  # 브라우저 UA 로 뚫림
        except Exception as exc:  # noqa: BLE001 — diagnostics want the message
            note = f"{type(first_exc).__name__}→{type(exc).__name__} (UA both)"
            return [], FeedStatus(lane, name, url, "error", note=note)

    parsed = feedparser.parse(resp.content)
    entries = parsed.entries or []
    items: list[Item] = []

    for e in entries:
        link = e.get("link")
        title = (e.get("title") or "").strip()
        if not link or not title:
            continue
        published = struct_to_dt(e.get("published_parsed") or e.get("updated_parsed"))
        if not within_window(published):
            continue
        items.append(
            Item(
                url=link,
                url_hash=url_hash(link),
                title=title,
                source_domain=domain(link),
                lane=lane,
                lane_weight=lane_conf["lane_weight"],
                source_tier=tier,
                tier_multiplier=TIER_MULTIPLIER[tier],
                content_type=ctype,
                published_at=published.isoformat() if published else None,
                collected_at=collected,
                abstract=_rss_abstract(e) or None,
            )
        )

    status = "ok" if items else "empty"
    return items, FeedStatus(lane, name, url, status, kept=len(items),
                             seen=len(entries), note=ua_note)
