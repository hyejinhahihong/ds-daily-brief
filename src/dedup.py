"""seen.json dedup index — SPEC §3.11 / §3.10.

Filters out items surfaced on a prior run (so the same article doesn't appear
two days running — Phase 1 completion criterion, SPEC §9), and doubles as the
source for "연결된 이전 기사" later (Phase 4). URL normalization/hashing is
reused from collectors.base for consistency.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .config import ROOT, now_kst
from .models import Item

SEEN_PATH = ROOT / "data" / "seen.json"
RETENTION_DAYS = 180  # SPEC §3.11


def load_seen(path: Path = SEEN_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def filter_unseen(items: list[Item], seen: dict[str, dict]) -> list[Item]:
    """Drop items whose url_hash was recorded on a previous run."""
    return [it for it in items if it.url_hash not in seen]


def update_seen(seen: dict[str, dict], ranked: list[Item], run_date: str) -> dict[str, dict]:
    """Record newly-ranked items (SPEC §3.11 schema). first_seen = today."""
    for it in ranked:
        if it.url_hash in seen:
            continue
        seen[it.url_hash] = {
            "url": it.url,
            "title": it.title,
            "category": it.category,
            "source_tier": it.source_tier,
            "first_seen": run_date,
            "tags": it.tags,
        }
    return seen


def prune(seen: dict[str, dict], days: int = RETENTION_DAYS) -> dict[str, dict]:
    cutoff = now_kst().date() - timedelta(days=days)
    kept: dict[str, dict] = {}
    for h, rec in seen.items():
        fs = rec.get("first_seen")
        try:
            if fs and datetime.fromisoformat(fs).date() < cutoff:
                continue
        except ValueError:
            pass  # unparseable date → keep (safer than dropping)
        kept[h] = rec
    return kept


def save_seen(seen: dict[str, dict], path: Path = SEEN_PATH) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
