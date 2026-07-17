"""Static site builder — Phase 4. Regenerates ALL pages from data/published/*.json.

  data/published/*.json  →  news/YYYY/MM/DD.html (일별, 재렌더)
                            index.html            (최신 일별 복사)
                            archive.html          (연>월>일 계층)
                            category/*.html × 8   (누적 리스트 + 태그 필터)

NO LLM, NO ranking, NO writing — pure deterministic render from the durable
published data (SPEC 원칙: 재집필 금지). Cost = $0. Idempotent: safe to re-run.
run_daily calls this at the end; it can also be run standalone to rebuild the
whole site after a schema/template change.

  uv run python -m src.build_site
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import yaml

from .config import ROOT
from .models import Item
from .publish import PUBLISHED_DIR, build_index
from .render import render_archive, render_category, render_daily

CATEGORIES = ROOT / "config" / "categories.yaml"


def load_all_published() -> list[tuple[str, list[Item]]]:
    """[(run_date, items), ...] for every data/published/*.json (schema-aware)."""
    days: list[tuple[str, list[Item]]] = []
    if not PUBLISHED_DIR.exists():
        return days
    for f in sorted(PUBLISHED_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        run_date = data.get("run_date", f.stem) if isinstance(data, dict) else f.stem
        rows = data["items"] if isinstance(data, dict) else data
        days.append((run_date, [Item(**d) for d in rows]))
    return days


def build(verbose: bool = True) -> dict:
    cfg = yaml.safe_load(CATEGORIES.read_text(encoding="utf-8"))
    categories = cfg["categories"]
    subtags_map = cfg.get("subtags", {})
    days = load_all_published()

    made: list[str] = []

    # 1) 일별 페이지 재렌더 (news/YYYY/MM/DD.html, prefix 깊이 3)
    for run_date, items in days:
        html = render_daily(items, categories, run_date, prefix="../../../")
        out = ROOT / "news" / run_date[:4] / run_date[5:7] / f"{run_date[8:10]}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        made.append(str(out.relative_to(ROOT)).replace("\\", "/"))

    # 2) index.html = 최신 일별 (루트, prefix="")
    if days:
        latest_rd, latest_items = max(days, key=lambda x: x[0])
        idx_html = render_daily(latest_items, categories, latest_rd, prefix="")
        build_index(idx_html)
        made.append("index.html")

    # 3) archive.html (루트)
    day_summaries = [{"run_date": rd, "count": len(items)} for rd, items in days]
    (ROOT / "archive.html").write_text(render_archive(day_summaries, prefix=""), encoding="utf-8")
    made.append("archive.html")

    # 4) category/*.html × 8 (누적 리스트, prefix="../")
    catdir = ROOT / "category"
    catdir.mkdir(exist_ok=True)
    cat_counts: dict[str, int] = {}
    for c in categories:
        cid = c["id"]
        entries = [(rd, it) for rd, items in days for it in items if it.category == cid]
        cat_counts[cid] = len(entries)
        html = render_category(cid, c["name"], entries, subtags_map.get(cid, []),
                               categories, prefix="../")
        (catdir / f"{cid}.html").write_text(html, encoding="utf-8")
        made.append(f"category/{cid}.html")

    result = {"days": [rd for rd, _ in days], "cat_counts": cat_counts, "files": made}
    if verbose:
        print(f"[build_site] published {len(days)}일: {', '.join(rd for rd, _ in days) or '(없음)'}")
        print(f"[build_site] 카테고리 누적 건수:")
        for c in categories:
            print(f"    {c['name']:<22} {cat_counts[c['id']]}건")
        print(f"[build_site] 생성 파일 {len(made)}개 (LLM 호출 0, $0)")
    return result


if __name__ == "__main__":
    build()
