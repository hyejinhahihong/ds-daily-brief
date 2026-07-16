"""Lanes 2 & 4 — arXiv (SPEC §3.3 / §3.5).

Role separation (작업 2):
  - HF Daily Papers → the DL / LLM·FM stream. Kept as-is (already curated).
  - arXiv raw → only the niche HF ignores (tabular / causal / time series /
    anomaly / clustering / XAI / imbalanced), via keyword_groups. This is
    what tames the 111/day firehose.
  - Venue-in-comments papers → lane 2 (학회), kept regardless of keyword.

Paging: the API is capped per request, so we page by submittedDate until the
oldest entry falls before the collection-window cutoff. Without this, even a
3-day window was silently truncated at one page.
"""

from __future__ import annotations

import re
import time
from typing import Optional

import feedparser

from ..models import TIER_MULTIPLIER, Item
from .base import (
    FeedStatus, clean_text, domain, http_get, now_iso, struct_to_dt, url_hash,
    window_cutoff, within_window,
)
from .keywords import compile_groups, match_groups

ARXIV_API = "http://export.arxiv.org/api/query"
ARXIV_PAGE_SIZE = 200
ARXIV_MAX_PAGES = 30
HF_DAILY_API = "https://huggingface.co/api/daily_papers"

# SPEC §3.3 — 추적 학회
_VENUES = [
    "NeurIPS", "ICML", "ICLR", "AISTATS", "AAAI", "UAI",
    "KDD", "CIKM", "WWW", "WSDM", "RecSys",
    "CLeaR", "ACIC",
]
_VENUE_RE = re.compile(r"\b(" + "|".join(_VENUES) + r")\b", re.IGNORECASE)
_ACCEPT_RE = re.compile(
    r"accepted\s+(?:at|to|by|in)|camera[- ]ready|to\s+appear|proceedings\s+of",
    re.IGNORECASE,
)


def detect_venue(comment: Optional[str]) -> Optional[str]:
    """Return 'NeurIPS 2026'-style string if the comment claims acceptance."""
    if not comment:
        return None
    m = _VENUE_RE.search(comment)
    if not m:
        return None
    # A bare venue token isn't enough (could be "unlike ICML-style methods");
    # require an acceptance cue OR a year next to the venue.
    year_near = re.search(r"20\d\d", comment[max(0, m.start() - 20): m.end() + 20])
    if not (_ACCEPT_RE.search(comment) or year_near):
        return None
    canon = {v.upper(): v for v in _VENUES}
    venue = canon.get(m.group(1).upper(), m.group(1))
    return f"{venue} {year_near.group(0)}" if year_near else venue


def _fetch_arxiv_entries(categories: list[str], max_total: int) -> tuple[list, Optional[str]]:
    """Page by submittedDate desc until the oldest entry predates the cutoff."""
    cutoff = window_cutoff()
    query = "+OR+".join(f"cat:{c}" for c in categories)
    entries: list = []
    err: Optional[str] = None

    for page in range(ARXIV_MAX_PAGES):
        start = page * ARXIV_PAGE_SIZE
        url = (
            f"{ARXIV_API}?search_query={query}"
            f"&sortBy=submittedDate&sortOrder=descending"
            f"&start={start}&max_results={ARXIV_PAGE_SIZE}"
        )
        try:
            resp = http_get(url, timeout=60.0, retries=2)  # arXiv API 는 느리고 flaky
        except Exception as exc:  # noqa: BLE001
            err = type(exc).__name__
            break
        page_entries = feedparser.parse(resp.content).entries or []
        if not page_entries:
            break
        entries.extend(page_entries)

        oldest = min(
            (struct_to_dt(e.get("published_parsed")) for e in page_entries
             if e.get("published_parsed")),
            default=None,
        )
        time.sleep(1.5)  # arXiv API 예의 (rate limit)
        if len(page_entries) < ARXIV_PAGE_SIZE or len(entries) >= max_total:
            break
        if oldest is not None and oldest < cutoff:
            break
    return entries, err


class ArxivResult:
    """Structured result so the report can show the role split + group counts."""

    def __init__(self) -> None:
        self.lane2: list[Item] = []          # 학회 (venue in comments)
        self.lane4_raw: list[Item] = []      # arXiv niche (keyword-filtered)
        self.lane4_hf: list[Item] = []       # HF Daily (DL/LLM stream)
        self.dropped_raw: int = 0            # arXiv papers dropped (no keyword hit)
        self.diags: list[FeedStatus] = []

    @property
    def lane4(self) -> list[Item]:
        return self.lane4_raw + self.lane4_hf


def collect_arxiv(
    lane2_conf: dict,
    lane4_conf: dict,
    categories: list[str],
    keyword_groups: dict[str, list[str]],
    max_total: int,
) -> ArxivResult:
    compiled = compile_groups(keyword_groups)
    entries, err = _fetch_arxiv_entries(categories, max_total)
    collected = now_iso()
    res = ArxivResult()

    for e in entries:
        link = e.get("link")
        title = (e.get("title") or "").replace("\n", " ").strip()
        if not link or not title:
            continue
        published = struct_to_dt(e.get("published_parsed") or e.get("updated_parsed"))
        if not within_window(published):
            continue
        abstract = (e.get("summary") or "").replace("\n", " ")
        groups = match_groups(f"{title} {abstract}", compiled)
        venue = detect_venue(e.get("arxiv_comment") or e.get("comment"))

        if venue:
            conf = lane2_conf                       # 학회 → 키워드 무관 전량 유지
        elif groups:
            conf = lane4_conf                       # 니치 → arXiv raw 유지
        else:
            res.dropped_raw += 1                    # HF 담당 영역 → arXiv raw 에서 제외
            continue

        item = Item(
            url=link, url_hash=url_hash(link), title=title,
            source_domain=domain(link),
            lane=conf["lane"], lane_weight=conf["lane_weight"],
            source_tier=conf["source_tier"],
            tier_multiplier=TIER_MULTIPLIER[conf["source_tier"]],
            venue=venue, content_type="paper",
            tags=groups,                            # 결정적 키워드 태그 (Haiku 아님)
            published_at=published.isoformat() if published else None,
            collected_at=collected,
            abstract=clean_text(abstract) or None,
        )
        (res.lane2 if venue else res.lane4_raw).append(item)

    res.diags.append(FeedStatus(
        lane2_conf["lane"], "arXiv API — venue in comments (학회)", ARXIV_API,
        "error" if err else ("ok" if res.lane2 else "empty"),
        kept=len(res.lane2), seen=len(entries), note=err or "",
    ))
    res.diags.append(FeedStatus(
        lane4_conf["lane"], "arXiv API — raw niche (keyword-filtered)", ARXIV_API,
        "error" if err else ("ok" if res.lane4_raw else "empty"),
        kept=len(res.lane4_raw), seen=len(entries),
        note=(err or f"dropped {res.dropped_raw} non-niche"),
    ))

    hf_items, hf_diag = _collect_hf_daily(lane4_conf, compiled, collected)
    res.lane4_hf = hf_items
    res.diags.append(hf_diag)
    return res


def _collect_hf_daily(lane4_conf: dict, compiled, collected: str) -> tuple[list[Item], FeedStatus]:
    try:
        resp = http_get(HF_DAILY_API, retries=1)
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return [], FeedStatus(lane4_conf["lane"], "HF Daily Papers (DL/LLM stream)",
                              HF_DAILY_API, "error", note=type(exc).__name__)

    items: list[Item] = []
    rows = data if isinstance(data, list) else []
    for row in rows:
        paper = row.get("paper", {}) if isinstance(row, dict) else {}
        arxiv_id = paper.get("id") or (row.get("id") if isinstance(row, dict) else None)
        title = (paper.get("title") or (row.get("title") if isinstance(row, dict) else "") or "").strip()
        if not arxiv_id or not title:
            continue
        link = f"https://arxiv.org/abs/{arxiv_id}"
        abstract = paper.get("summary") or ""
        items.append(
            Item(
                url=link, url_hash=url_hash(link), title=title,
                source_domain="arxiv.org",
                lane=lane4_conf["lane"], lane_weight=lane4_conf["lane_weight"],
                source_tier=lane4_conf["source_tier"],
                tier_multiplier=TIER_MULTIPLIER[lane4_conf["source_tier"]],
                content_type="paper",
                tags=match_groups(f"{title} {abstract}", compiled),
                published_at=row.get("publishedAt") if isinstance(row, dict) else None,
                collected_at=collected,
                abstract=clean_text(abstract) or None,
            )
        )
    return items, FeedStatus(lane4_conf["lane"], "HF Daily Papers (DL/LLM stream)",
                            HF_DAILY_API, "ok" if items else "empty",
                            kept=len(items), seen=len(rows))
