"""Phase 1 runner — collect → dedup(seen.json) → Haiku rank → quota select.

Usage:
  uv run python -m src.run_phase1                       # real Haiku (needs .env key)
  uv run python -m src.run_phase1 --stub                # offline plumbing check
  uv run python -m src.run_phase1 --from-json data/raw_2026-07-16.json --stub

Outputs (SPEC §9 / 산출물):
  (a) 카테고리별 선별 결과   (b) 레인별 진입률 표
The 3-day dedup check (c) = run this 3× and watch seen.json filter repeats.

Not in scope (Phase 2+): Sonnet 집필, HTML, 발송. lane_weight 변경 금지.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import yaml

from .config import ROOT, load_dotenv, today_kst_iso
from .dedup import filter_unseen, load_seen, prune, save_seen, update_seen
from .models import Item
from .rank import rank_items, stub_rank
from .select import compute_final_scores, select

CATEGORIES = ROOT / "config" / "categories.yaml"
PREFERENCES = ROOT / "data" / "preferences.md"
LANE_NAMES = {1: "빅테크리서치", 2: "학회논문", 3: "큐레이션", 4: "arXiv일반",
              5: "실무블로그", 6: "AI미디어", 7: "GitHub", 8: "국문보조"}


def load_items_from_json(path: Path) -> list[Item]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Item(**d) for d in data]


def collect_fresh() -> list[Item]:
    from .run_collect import collect_all, dedup
    raw, _diags, _res = collect_all(yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8")))
    return dedup(raw)


# --------------------------------------------------------------------------
# Deliverables
# --------------------------------------------------------------------------
def report_selection(chosen: list[Item], categories: list[dict]) -> None:
    print("\n" + "=" * 84)
    print("  (a) 오늘자 선별 결과 — 카테고리별")
    print("=" * 84)
    top3 = [it for it in chosen if it.is_top3]
    print("  TODAY'S TOP 3:")
    for it in top3:
        print(f"    ★ [{it.final_score}] {it.title[:66]}")
    print("-" * 84)
    by_cat: dict[str, list[Item]] = {}
    for it in chosen:
        by_cat.setdefault(it.category, []).append(it)
    for c in categories:
        cid = c["id"]
        lst = sorted(by_cat.get(cid, []), key=lambda it: it.final_score, reverse=True)
        flag = "" if lst else "  · (금일 신규 없음)"
        print(f"\n  {c['name']} (T{c['tier']}, {c['min']}~{c['max']}) — {len(lst)}건{flag}")
        for it in lst:
            tags = f" #{' #'.join(it.tags)}" if it.tags else ""
            print(f"    base {it.base_score:>4} × w{it.lane_weight} × t{it.tier_multiplier} "
                  f"= final {it.final_score:<6}  L{it.lane} tier{it.source_tier}")
            print(f"       {it.title[:72]}{tags}")
    print(f"\n  합계 선별: {len(chosen)}건")


def report_lane_rates(new: list[Item], chosen: list[Item], raw: list[Item]) -> None:
    print("\n" + "=" * 84)
    print("  (b) 레인별 진입률")
    print("=" * 84)
    chosen_ids = {id(it) for it in chosen}
    print(f"{'레인':<16}{'수집':>6}{'신규':>6}{'선별':>6}{'진입률':>9}{'평균base':>10}")
    print("-" * 84)
    for lane in sorted(LANE_NAMES):
        raw_n = sum(1 for it in raw if it.lane == lane)
        new_lane = [it for it in new if it.lane == lane]
        sel_n = sum(1 for it in chosen if it.lane == lane)
        scored = [it.base_score for it in new_lane if it.base_score is not None]
        rate = f"{sel_n / len(new_lane) * 100:.0f}%" if new_lane else "-"
        avg = f"{sum(scored) / len(scored):.1f}" if scored else "-"
        print(f"{lane}.{LANE_NAMES[lane]:<14}{raw_n:>6}{len(new_lane):>6}{sel_n:>6}{rate:>9}{avg:>10}")
    print("-" * 84)
    print(f"{'합계':<16}{len(raw):>6}{len(new):>6}{len(chosen):>6}")


def report_tier5(new: list[Item], raw: list[Item]) -> None:
    print("\n" + "=" * 84)
    print("  (c) Tier 5 판정 실측")
    print("=" * 84)
    print("  판정 방식: 도메인/피드 화이트리스트 (config/sources.yaml, 수집 시점 정적 부여).")
    print("            LLM 판정 아님 — source_tier 는 레인·피드 설정값 (base.py:170).")
    tier5 = [it for it in new if it.source_tier == 5]
    print(f"\n  Tier 5 건수: {len(tier5)}건")
    if tier5:
        for dom in sorted({it.source_domain for it in tier5}):
            print(f"    - {dom} ({sum(1 for it in tier5 if it.source_domain == dom)}건)")
    else:
        print("    (도메인 없음 — sources.yaml 레인 기본 tier 는 1~4, tier5 오버라이드 피드 없음)")
    print("\n  참고 — 이번 실행 tier 분포:")
    for t in (1, 2, 3, 4, 5):
        n = sum(1 for it in new if it.source_tier == t)
        print(f"    tier {t} (×{ {1:1.0,2:0.95,3:0.85,4:0.8,5:0.5}[t] }): {n}건")


def report_cost(tracker, n_ranked: int) -> None:
    print("\n" + "=" * 84)
    print("  (d) 비용 실측")
    print("=" * 84)
    print(f"  이번 1회 실행 ({n_ranked}건 랭킹, 호출 {tracker.calls}회):")
    print(f"    입력 토큰 : {tracker.in_tok:,}")
    print(f"    출력 토큰 : {tracker.out_tok:,}")
    print(f"    비용      : ${tracker.cost_usd:.4f}  "
          f"(in ${tracker.in_tok/1e6*1.0:.4f} + out ${tracker.out_tok/1e6*5.0:.4f})")
    monthly = tracker.cost_usd * 22
    print(f"\n  평일 22회 월 환산: ${tracker.cost_usd:.4f} × 22 = ${monthly:.2f}")
    print(f"  SPEC §7.3 추정치 $10~15 와 대조 → ", end="")
    if monthly < 10:
        print(f"추정치 하회 (${monthly:.2f}).")
    elif monthly <= 15:
        print(f"추정치 범위 내 (${monthly:.2f}).")
    else:
        print(f"추정치 상회 (${monthly:.2f}) — 검토 필요.")
    if n_ranked:
        print(f"\n  ※ 이번 실행은 seen.json 비어있어 {n_ranked}건 전부 신규 (첫 실행 = 최대 배치).")
        print(f"    정상 운영 시 일일 신규분만 랭킹 → 실제 일일 비용은 이보다 낮음.")
        print(f"    건당 ${tracker.cost_usd/n_ranked:.5f} × 일일 신규 N건 × 22 로 재환산 가능.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stub", action="store_true", help="API 없이 결정적 스코어 (플럼빙 검증)")
    parser.add_argument("--from-json", help="Phase 0 raw JSON 로드 (재수집 대신)")
    args = parser.parse_args()

    load_dotenv()
    cfg = yaml.safe_load(CATEGORIES.read_text(encoding="utf-8"))
    categories = cfg["categories"]
    total_max = cfg.get("total_max", 16)
    run_date = today_kst_iso()

    # collect (or load)
    if args.from_json:
        raw = load_items_from_json(Path(args.from_json))
        print(f"[phase1] {args.from_json} 에서 {len(raw)}건 로드")
    else:
        print("[phase1] 수집 중...")
        raw = collect_fresh()
        print(f"[phase1] 수집 {len(raw)}건")

    # dedup via seen.json
    seen = load_seen()
    new = filter_unseen(raw, seen)
    print(f"[phase1] seen.json 필터: {len(raw)}건 → 신규 {len(new)}건 (기존 {len(raw) - len(new)}건 제외)")
    if not new:
        print("[phase1] 신규 없음 — seen.json 이 전부 걸러냄 (중복 방지 정상 동작). 선별 0건.")

    # rank
    prefs = PREFERENCES.read_text(encoding="utf-8") if PREFERENCES.exists() else ""
    if args.stub:
        print("[phase1] ⚠ STUB 랭킹 (결정적 의사 스코어 — 실제 Haiku 판정 아님)")
        tracker = stub_rank(new)
    else:
        print(f"[phase1] Haiku 랭킹 (claude-haiku-4-5, 배치)...")
        tracker = rank_items(new, preferences=prefs)
        print(f"[phase1] 랭킹 완료: 호출 {tracker.calls}회, 토큰 in {tracker.in_tok}/out {tracker.out_tok}, ${tracker.cost_usd:.4f}")

    # final_score + quota select
    compute_final_scores(new)
    chosen = select(new, categories, total_max)

    # reports
    report_selection(chosen, categories)
    report_lane_rates(new, chosen, raw)
    report_tier5(new, raw)
    if not args.stub:
        report_cost(tracker, len([it for it in new if it.base_score is not None]))

    # update seen.json with ranked-new items (category assigned)
    ranked_new = [it for it in new if it.category]
    seen = update_seen(seen, ranked_new, run_date)
    seen = prune(seen)
    save_seen(seen)
    print(f"\n[phase1] seen.json 갱신: {len(ranked_new)}건 추가 → 총 {len(seen)}건 기록")
    if args.stub:
        print("[phase1] ※ STUB 모드. 실제 base_score/final_score 는 .env 에 ANTHROPIC_API_KEY 넣고 --stub 없이 실행.")


if __name__ == "__main__":
    main()
