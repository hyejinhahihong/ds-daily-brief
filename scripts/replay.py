"""Replay the pipeline / probe source reachability for coverage regression cases.

Phase 4 작업 1 + 1.5. tests/coverage_cases.yaml 의 케이스를 두 type 으로 나눠 검증한다.

  type: pipeline     — 특정 날짜로 collect → dedup → (rank → select) 재실행하고,
                       케이스가 어느 단계에서 탈락했는지(collect/dedup/rank/select) 짚어 PASS/FAIL.
                       스냅샷이 있는 날짜(07-16~)만 가능. 기본 무비용, --rank 로 랭킹·선별까지.
  type: reachability — "우리 소스 목록(config/sources.yaml)이 이 사건에 도달 가능한가"를 판정.
                       스냅샷·랭킹 불필요. REACH_OK / REACH_FAIL / NOT_CONFIGURED.

SKIP 은 "창 밖"이 아니라 "type 에 맞는 검증 수단 없음"(pipeline 인데 replay_date≠실행일)일 때만.

Usage:
  # baseline: reachability 전체 + 07-16 pipeline 재현
  uv run python scripts/replay.py 2026-07-16 --from-json data/raw_2026-07-16.json

  # 라이브 수집 + Haiku 랭킹/선별까지 (비용 발생)
  uv run python scripts/replay.py 2026-07-18 --rank
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import yaml  # noqa: E402

from src.collectors.base import set_window_since  # noqa: E402
from src.config import load_dotenv  # noqa: E402
from src.dedup import filter_unseen, load_seen  # noqa: E402
from src.models import Item  # noqa: E402
from src.run_phase1 import load_items_from_json  # noqa: E402
from src.snapshot import save_stage  # noqa: E402

CASES_PATH = ROOT / "tests" / "coverage_cases.yaml"
CATEGORIES_PATH = ROOT / "config" / "categories.yaml"
SOURCES_PATH = ROOT / "config" / "sources.yaml"


def _haystack(it: Item) -> str:
    """매칭 대상 텍스트를 소문자로 이어붙임 (제목·초록·URL·venue·태그)."""
    parts = [it.title or "", it.abstract or "", it.url or "", it.venue or "", " ".join(it.tags)]
    return " ".join(parts).lower()


def _matches(it: Item, needles: list[str]) -> bool:
    hay = _haystack(it)
    return any(n.lower() in hay for n in needles)


# ---------------------------------------------------------------------------
# pipeline: run stages for run_date, trace where each case dropped
# ---------------------------------------------------------------------------
def run_pipeline(run_date, from_json, do_rank, apply_seen, since=None):
    """Return ({stage: [Item]}, computed_stages) after running the pipeline."""
    cfg_src = yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8"))

    # 과거 사건 replay 시 수집 창을 사건일로 맞춘다(라이브 3일 창은 오늘 기준이라 과거를 못 담음).
    if since and not from_json:
        from datetime import datetime, timezone
        set_window_since(datetime.fromisoformat(since).replace(tzinfo=timezone.utc))
        print(f"[replay] 수집 창 since={since} 로 고정")

    if from_json:
        collect = load_items_from_json(from_json)
        print(f"[replay] collect: {from_json} 에서 {len(collect)}건 로드")
    else:
        from src.run_collect import collect_all, dedup as run_dedup
        raw, _diags, _res = collect_all(cfg_src)
        collect = run_dedup(raw)
        print(f"[replay] collect: 라이브 수집 {len(collect)}건 (run-dedup 후)")
    save_stage("collect", collect, run_date)

    if apply_seen:
        dedup_items = filter_unseen(collect, load_seen())
        print(f"[replay] dedup: seen 적용 → {len(dedup_items)}건 (⚠ 현재 seen 상태 기준)")
    else:
        dedup_items = list(collect)
        print(f"[replay] dedup: seen 미적용(--seen 로 켜기) → {len(dedup_items)}건")
    save_stage("dedup", dedup_items, run_date)

    stages = {"collect": collect, "dedup": dedup_items}
    computed = ["collect", "dedup"]

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

    return stages, computed


def check_pipeline(case, run_date, stages, computed, do_rank):
    """(status, note, extra) for a pipeline-type case."""
    if str(case["replay_date"]) != str(run_date):
        return "SKIP", f"replay_date {case['replay_date']} ≠ 실행일 {run_date} (그 날짜로 재실행 필요)", ""

    needles = case["must_contain_any"]
    survived_to = None
    for st in computed:
        if any(_matches(it, needles) for it in stages[st]):
            survived_to = st
    deepest = computed[-1]

    if survived_to == "select":
        status, note = "PASS", "출력에 존재"
    elif survived_to == deepest and deepest != "select":
        status = "SURVIVES"
        note = f"{deepest}까지 생존 — rank/select 미평가(--rank 로 확인)"
    else:
        if survived_to is None:
            drop = "collect"
        else:
            i = computed.index(survived_to)
            drop = computed[i + 1] if i + 1 < len(computed) else deepest
        status, note = "FAIL", f"탈락 단계 = {drop}"

    extra = ""
    if do_rank and survived_to:
        hit = next((it for it in stages.get("select", []) if _matches(it, needles)), None)
        if hit and hit.category and hit.category != case.get("expect_category"):
            extra = f"카테고리 {hit.category}≠기대 {case['expect_category']}"
    return status, note, extra


# ---------------------------------------------------------------------------
# reachability: is any expected source configured in sources.yaml?
# ---------------------------------------------------------------------------
def check_reachability(case, sources_text):
    """(status, note) for a reachability-type case — config 기준 판정.

    REACH_OK       expect_source_any 중 하나가 config 에 설정됨 (원리적으로 도달 가능).
    NOT_CONFIGURED 하나도 설정 안 됨 → 피드/소스로 구조적 미도달. 작업 2·3 의 baseline.
    REACH_FAIL     (예약) 설정돼 있으나 라이브 확인 시 해당일 아이템 미반환. 최근 사건에서만
                   검증 가능 → 작업 2·3 이후 최신 사건으로 확장. 과거 사건은 라이브 확인 불가.
    """
    srcs = case.get("expect_source_any", [])
    hit = [s for s in srcs if s.lower() in sources_text.lower()]
    if not hit:
        return "NOT_CONFIGURED", f"소스 미설정: {srcs}"
    return "REACH_OK", f"설정됨: {hit}"


def main() -> None:
    ap = argparse.ArgumentParser(description="커버리지 회귀 리플레이 (Phase 4 작업 1/1.5)")
    ap.add_argument("date", help="pipeline 케이스 재실행 날짜 YYYY-MM-DD")
    ap.add_argument("--from-json", type=Path, help="라이브 수집 대신 raw 스냅샷 로드 (pipeline)")
    ap.add_argument("--rank", action="store_true", help="Haiku 랭킹+선별까지 실행 (비용 발생)")
    ap.add_argument("--seen", action="store_true", help="seen.json dedup 적용 (기본 미적용)")
    ap.add_argument("--since", help="수집 창 시작일 고정 YYYY-MM-DD (과거 사건 pipeline replay용)")
    args = ap.parse_args()
    run_date = args.date

    cases = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    sources_text = SOURCES_PATH.read_text(encoding="utf-8")
    pipeline_cases = [c for c in cases if c.get("type") == "pipeline"]
    reach_cases = [c for c in cases if c.get("type") == "reachability"]

    # pipeline 을 실제로 돌릴 필요가 있을 때만 수집/랭킹 실행.
    need_pipeline = bool(args.from_json) or any(
        str(c["replay_date"]) == str(run_date) for c in pipeline_cases
    )
    stages, computed = ({}, [])
    if need_pipeline:
        stages, computed = run_pipeline(run_date, args.from_json, args.rank, args.seen, args.since)

    rows = []  # (id, type, status, note, extra)
    fails = 0
    for c in cases:
        if c.get("type") == "pipeline":
            if not need_pipeline:
                status, note, extra = "SKIP", "pipeline 미실행 (해당일 아님)", ""
            else:
                status, note, extra = check_pipeline(c, run_date, stages, computed, args.rank)
            if status == "FAIL":
                fails += 1
        else:  # reachability
            status, note = check_reachability(c, sources_text)
            extra = ""
        rows.append((c["id"], c.get("type", "?"), status, note, extra))

    # 출력
    stage_label = (" → ".join(computed)) if computed else "(pipeline 미실행)"
    print(f"\n{'='*78}\n  커버리지 리플레이 — 실행일 {run_date}  ·  pipeline 단계: {stage_label}\n{'='*78}")
    print(f"  {'id':<20}{'type':<14}{'결과':<16}{'설명'}")
    print(f"  {'-'*72}")
    for cid, ctype, status, note, extra in rows:
        line = f"  {cid:<20}{ctype:<14}{status:<16}{note}"
        if extra:
            line += f"  · {extra}"
        print(line)
    print(f"  {'-'*72}")
    print(f"  pipeline FAIL {fails}건  ·  reachability: "
          f"{sum(1 for r in rows if r[2]=='REACH_OK')} OK / "
          f"{sum(1 for r in rows if r[2]=='NOT_CONFIGURED')} NOT_CONFIGURED\n")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
