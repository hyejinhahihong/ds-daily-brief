"""Lane 7 — GitHub Releases (SPEC §3.8).

Major/minor releases only (patch x.y.Z excluded), no pre-releases.
Sparse by design — an empty day is normal. Uses GITHUB_TOKEN from env if
present (higher rate limit); works unauthenticated too (60 req/hr).
"""

from __future__ import annotations

import os
import re
from typing import Optional

from ..models import TIER_MULTIPLIER, Item
from .base import (
    FeedStatus, clean_text, domain, http_get, now_iso, struct_to_dt, url_hash, within_window,
)

_SEMVER = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
_PRERELEASE_TOKENS = re.compile(r"(rc|alpha|beta|dev|preview|nightly|a\d|b\d)", re.IGNORECASE)


def _is_major_or_minor(tag: str) -> bool:
    """True for x.y.0 / x.y; False for patch releases x.y.Z (Z>0)."""
    m = _SEMVER.search(tag or "")
    if not m:
        return True  # non-semver tag → keep (rare; let measurement show it)
    patch = m.group(3)
    return patch is None or patch == "0"


def _parse_iso(s: Optional[str]):
    if not s:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def collect_github(lane_conf: dict, repos: list[str]) -> tuple[list[Item], list[FeedStatus]]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    collected = now_iso()
    items: list[Item] = []
    diags: list[FeedStatus] = []

    for repo in repos:
        api = f"https://api.github.com/repos/{repo}/releases?per_page=10"
        try:
            resp = http_get(api, headers=headers)
            releases = resp.json()
        except Exception as exc:  # noqa: BLE001
            diags.append(FeedStatus(lane_conf["lane"], repo, api, "error", note=type(exc).__name__))
            continue

        kept = 0
        for rel in releases if isinstance(releases, list) else []:
            if rel.get("prerelease") or rel.get("draft"):
                continue
            tag = rel.get("tag_name") or rel.get("name") or ""
            if _PRERELEASE_TOKENS.search(tag) or not _is_major_or_minor(tag):
                continue
            published = _parse_iso(rel.get("published_at"))
            if not within_window(published):
                continue
            link = rel.get("html_url")
            if not link:
                continue
            title = f"{repo} {tag}".strip()
            # Release notes are Markdown; keep as-is (strip only stray HTML/whitespace).
            body = clean_text(rel.get("body") or "")
            items.append(
                Item(
                    url=link,
                    url_hash=url_hash(link),
                    title=title,
                    source_domain=domain(link),
                    lane=lane_conf["lane"],
                    lane_weight=lane_conf["lane_weight"],
                    source_tier=lane_conf["source_tier"],
                    tier_multiplier=TIER_MULTIPLIER[lane_conf["source_tier"]],
                    content_type="release",
                    published_at=published.isoformat() if published else None,
                    collected_at=collected,
                    abstract=body or None,
                )
            )
            kept += 1
        diags.append(FeedStatus(lane_conf["lane"], repo, api,
                                "ok" if kept else "empty", kept=kept,
                                seen=len(releases) if isinstance(releases, list) else 0))
    return items, diags
