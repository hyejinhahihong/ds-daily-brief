"""Replay the pipeline for a given date and check coverage regression cases.

Phase 4 작업 1. 특정 날짜로 collect → dedup → (rank → select) 를 재실행하고,
tests/coverage_cases.yaml 의 각 케이스가 어느 단계에서 탈락했는지
(collect / dedup / rank / select) 를 짚어 PASS / FAIL 을 출력한다.

기본은 무비용(collect + dedup 만; Haiku 랭킹 없음). collect 단계에서 이미 부재한
사건(리콜 실패)은 랭킹 없이도 확정 판정된다. 랭킹/선별까지 추적하려면 --rank.

Usage:
  # 07-16 raw 스냅샷으로 재현 (무비용). Kimi K3 리콜 실패 확인.
  uv run python scripts/replay.py 2026-07-16 --from-json data/raw_2026-07-16.json

  # 라이브 수집 + Haiku 랭킹/선별까지 (비용 발생)
  uv run python scripts/replay.py 2026-07-18 --rank
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import yaml  # noqa: E402

from src.collectors.base import WINDOW_DAYS  # noqa: E402
from src.config import load_dotenv  # noqa: E402
from src.dedup import filter_unseen, load_seen  # noqa: E402
from src.models import Item  # noqa: E402
from src.run_phase1 import load_items_from_json  # noqa: E402
from src.snapshot import save_stage  # noqa: E402

CASES_PATH = ROOT / "tests" / "coverage_cases.yaml"
CATEGORIES_PATH = ROOT / "config" / "categories.yaml"
SOURCES_PATH = ROOT / "config" / "sources.yaml"


def _haystack(it: Item) -> str:
    """모든 매칭 대상 텍스트를 소문자로 이어붙임 (제목·초록·URL·venue·태그)."""
    parts = [it.title or "", it.abstract or "", it.url or "", it.venue or "", " ".join(it.tags)]
    return " ".join(parts).lower()


def _matches(it: Item, needles: list[str]) -> bool:
    hay = _haystack(it)
    return any(n.lower() in hay for n in needles)


def _as_date(v) -> date:
    """YAML 은 `2026-07-16` 을 date 객체로 자동 파싱한다. str/date 모두 허용."""
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def _in_window(case_date, run_date) -> bool:
    """사건일이 run_date 의 3일 수집 창(§3.10) 안인가. 0 ≤ (run - case) ≤ WINDOW_DAYS."""
    delta = (_as_date(run_date) - _as_date(case_date)).days
    return 0 <= delta <= WINDOW_DAYS


def replay(run_date: str, from_json: Path | None, do_rank: bool, apply_seen: bool) -> int:
    cfg_src = yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8"))

    # 1) collect
    if from_json:
        collect = load_items_from_json(from_json)
        print(f"[replay] collect: {from_json} 에서 {len(collect)}건 로드")
    else:
        from src.run_collect import collect_all, dedup as run_dedup
        raw, _diags, _res = collect_all(cfg_src)
        collect = run_dedup(raw)
        print(f"[replay] collect: 라이브 수집 {len(collect)}건 (run-dedup 후)")
    save_stage("collect", collect, run_date)

    # 2) dedup (seen.json). 과거 날짜 replay 시 현재 seen 은 오염돼 있을 수 있어 기본은 미적용.
    if apply_seen:
        seen = load_seen()
        dedup_items = filter_unseen(collect, seen)
        print(f"[replay] dedup: seen 적용 → {len(dedup_items)}건 (⚠ 현재 seen 상태 기준)")
    else:
        dedup_items = list(collect)
        print(f"[replay] dedup: seen 미적용(--seen 로 켜기) → {len(dedup_items)}건")
    save_stage("dedup", dedup_items, run_date)

    stages: dict[str, list[Item]] = {"collect": collect, "dedup": dedup_items}
    computed = ["collect", "dedup"]

    # 3) rank + select (선택 — 비용 발생)
    if do_rank:
        load_dotenv()
        from src.rank import rank_items
        from src.select import compute_final_scores, select
        from src.run_phase1 import PREFERENCES
        prefs = PREFERENCES.read_text(encoding="utf-8") if PREFERENCES.exists() else ""
        tk = rank_items(dedup_items, preferences=prefs)
        save_stage("rank", dedup_items, run_date)
        compute_final_scores(dedup_items)
        cats = yaml.safe_load(CATEGORIES_PATH.read_text(encoding="utf-8"))
        chosen = select(dedup_items, cats["categories"], cats.get("total_max", 16))
        save_stage("select", chosen, run_date)
        stages["rank"] = dedup_items
        stages["select"] = chosen
        computed += ["rank", "select"]
        print(f"[replay] rank ${tk.cost_usd:.4f} → select {len(chosen)}건")

    # 4) trace cases
    cases = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    deepest = computed[-1]
    rows: list[tuple] = []
    fails = 0
    for c in cases:
        cid = c["id"]
        if not _in_window(c["date"], run_date):
            rows.append((cid, "SKIP", f"창 밖 (사건 {c['date']}, 창 {WINDOW_DAYS}일)", ""))
            continue

        survived_to = None
        for st in computed:
            if any(_matches(it, c["must_contain_any"]) for it in stages[st]):
                survived_to = st
        drop_stage = "collect" if survived_to is None else (
            computed[computed.index(survived_to) + 1] if computed.index(survived_to) + 1 < len(computed) else None
        )

        if survived_to == "select":
            status, note = "PASS", "출력에 존재"
        elif survived_to == deepest and deepest != "select":
            status = "SURVIVES"
            note = f"{deepest}까지 생존 — rank/select 미평가(--rank 로 확인)"
        else:
            status = "FAIL"
            note = f"탈락 단계 = {drop_stage}"
            fails += 1

        # 카테고리 진단(rank 이후에만 의미) — 참고용, 판정엔 미반영
        cat_note = ""
        if do_rank and survived_to:
            hit = next((it for it in stages.get("select", []) if _matches(it, c["must_contain_any"])), None)
            if hit and hit.category and hit.category != c["expect_category"]:
                cat_note = f"카테고리 {hit.category}≠기대 {c['expect_category']}"
        rows.append((cid, status, note, cat_note))

    # 5) 출력
    print(f"\n{'='*72}\n  커버리지 회귀 리플레이 — {run_date}  (평가 단계: {' → '.join(computed)})\n{'='*72}")
    print(f"  {'id':<20}{'결과':<10}{'설명'}")
    print(f"  {'-'*66}")
    for cid, status, note, cat_note in rows:
        line = f"  {cid:<20}{status:<10}{note}"
        if cat_note:
            line += f"  · {cat_note}"
        print(line)
    print(f"  {'-'*66}")
    print(f"  FAIL {fails}건 / 전체 {len(cases)}건 (창 안 케이스만 판정, SKIP 제외)\n")
    return 1 if fails else 0


def main() -> None:
    ap = argparse.ArgumentParser(description="커버리지 회귀 리플레이 (Phase 4 작업 1)")
    ap.add_argument("date", help="재실행 날짜 YYYY-MM-DD")
    ap.add_argument("--from-json", type=Path, help="라이브 수집 대신 raw 스냅샷 로드")
    ap.add_argument("--rank", action="store_true", help="Haiku 랭킹+선별까지 실행 (비용 발생)")
    ap.add_argument("--seen", action="store_true", help="seen.json dedup 적용 (기본 미적용)")
    args = ap.parse_args()
    code = replay(args.date, args.from_json, args.rank, args.seen)
    sys.exit(code)


if __name__ == "__main__":
    main()
