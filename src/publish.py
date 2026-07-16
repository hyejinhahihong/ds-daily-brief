"""Publish artifacts — Phase 3-a / 3-b.

Two jobs, both cheap and lossless:

1. save_published() — dump the day's FINAL items to data/published/YYYY-MM-DD.json
   in the SPEC §8 schema, wrapped with a schema_version. This is the durable
   source of truth for later category/archive/RSS pages (Phase 4). seen.json is
   dedup-only (no summary/title_ko), so it can't play this role — hence a separate
   store. Bumping SCHEMA_VERSION on a field change lets a future migration find
   and upgrade old files instead of silently losing them (the failure mode the
   reference site hit: pre-schema items became "요약 정보 없음").

2. build_index() — write /index.html = a copy of today's daily page (DESIGN §6:
   index = 오늘자 그대로). Copy, not redirect — one fewer hop from a KakaoTalk link.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT, SCHEMA_VERSION
from .models import Item

PUBLISHED_DIR = ROOT / "data" / "published"


def save_published(items: list[Item], run_date: str) -> Path:
    """Dump final items to data/published/YYYY-MM-DD.json (schema-versioned)."""
    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "items": [it.model_dump() for it in items],
    }
    out = PUBLISHED_DIR / f"{run_date}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_published(run_date: str) -> list[Item]:
    """Read back a published day (schema-aware). Used by later pages / migration."""
    path = PUBLISHED_DIR / f"{run_date}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    # Forward-compatible: accept either the wrapped form or a bare list.
    rows = data["items"] if isinstance(data, dict) else data
    return [Item(**d) for d in rows]


def build_index(daily_html: str, root: Path = ROOT) -> Path:
    """Write /index.html as a copy of today's daily page (DESIGN §6)."""
    out = root / "index.html"
    out.write_text(daily_html, encoding="utf-8")
    return out
