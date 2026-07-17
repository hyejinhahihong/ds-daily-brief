"""Phase 2 runner — load → dedup → Haiku rank → select → Sonnet write → HTML.

Produces the daily full-text sample page and measures Sonnet writing cost.
Does NOT persist seen.json (keeps the sample re-runnable) and does NOT send or
build index/category pages — those are Phase 1 / next-step / Phase 3.

  uv run python -m src.run_phase2 --from-json data/raw_2026-07-16.json
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

from .config import GROUNDING_MIN_CHARS, ROOT, load_dotenv, today_kst_iso
from .dedup import filter_unseen, load_seen
from .models import Item
from .rank import rank_items
from .render import render_daily
from .run_phase1 import CATEGORIES, load_items_from_json
from .select import compute_final_scores, select
from .write import is_grounding_weak, write_items

DATA = ROOT / "data"


def _render_and_save(chosen, categories, run_date: str) -> Path:
    html = render_daily(chosen, categories, run_date)
    out = ROOT / "news" / run_date[:4] / run_date[5:7] / f"{run_date[8:10]}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def report_cost(rank_tk, write_tk) -> None:
    print("\n" + "=" * 84)
    print("  Sonnet 집필 비용 실측")
    print("=" * 84)
    print(f"  Haiku 랭킹 : 호출 {rank_tk.calls}, in {rank_tk.in_tok:,}/out {rank_tk.out_tok:,}, "
          f"${rank_tk.cost_usd:.4f}")
    print(f"  Sonnet 집필: 호출 {write_tk.calls}, in {write_tk.in_tok:,}/out {write_tk.out_tok:,}, "
          f"${write_tk.cost_usd:.4f}  (표준가 $3/$15, 2026-08-31까지 인트로 $2/$10)")
    combined = rank_tk.cost_usd + write_tk.cost_usd
    print(f"  이번 1회 합계: ${combined:.4f}")
    print(f"\n  월 환산 (평일 22회):")
    print(f"    Sonnet 집필 : ${write_tk.cost_usd:.4f} × 22 = ${write_tk.cost_usd*22:.2f}  "
          f"(집필은 매일 ~16건 고정이라 이 환산이 현실적)")
    print(f"    Haiku 랭킹  : 첫실행 기준 ${rank_tk.cost_usd*22:.2f} (상한). 정상운영 일일신규분만 → 더 낮음")
    print(f"    합계(상한)  : ${combined*22:.2f}")
    print(f"  SPEC §7.3 추정 $10~15 대조 → 실측 ${combined*22:.2f} 수준.")


_LANE_NAMES = {1: "빅테크리서치", 2: "학회논문", 3: "큐레이션", 4: "arXiv일반",
               5: "실무블로그", 6: "AI미디어", 7: "GitHub", 8: "국문보조"}


def report_routing(chosen, ranked, routing: dict, categories) -> None:
    """과제 4 — 배정 검증 (SPEC §2.3 v5 사다리): (a) 16건 상세, (b) practice 유입, (c) rung 분포."""
    cat_name = {c["id"]: c["name"] for c in categories}

    # (a) 16건 전체 — 제목 / 레인 / 카테고리 / rung / base / final
    print("\n" + "=" * 104)
    print("  (a) 배정 검증 — 재랭킹 후 선별 16건")
    print("=" * 104)
    print(f"  {'제목':<44}{'레인':<12}{'카테고리':<16}{'rung':>5}{'base':>7}{'final':>8}")
    print("-" * 104)
    for it in sorted(chosen, key=lambda x: (x.final_score or 0), reverse=True):
        r = routing.get(it.url_hash, {})
        title = (it.title[:42] + "…") if len(it.title) > 43 else it.title
        lane = f"{it.lane}.{_LANE_NAMES.get(it.lane, '')}"
        print(f"  {title:<44}{lane:<12}{cat_name.get(it.category, it.category or '')[:14]:<16}"
              f"{str(r.get('rung')):>5}{it.base_score:>7}{it.final_score:>8}")

    # (b) '실무 사례 · 노하우'(practice) 유입 — 몇 건, 어느 레인에서
    prac = [it for it in chosen if it.category == "practice"]
    lane5_collected = sum(1 for it in ranked if it.lane == 5)
    print("\n" + "=" * 104)
    print("  (b) '실무 사례 · 노하우'(practice) 유입 — 이전 FDE 0건 대비")
    print("=" * 104)
    print(f"  선별 {len(prac)}건. (레인 5 실무블로그 수집 {lane5_collected}건 → practice 선별 "
          f"{sum(1 for it in prac if it.lane == 5)}건)")
    for it in prac:
        r = routing.get(it.url_hash, {})
        print(f"    · L{it.lane}({_LANE_NAMES.get(it.lane, '')}) rung{r.get('rung')} "
              f"base {it.base_score} — {it.title[:60]}")
    if not prac:
        print("    (0건 — 후보 없어 비움. 억지로 안 채움, SPEC 원칙 3)")

    # (c) rung 분포 + 8번(practice) 자석 경고 + 기본값(7번 fallback) 의존
    print("\n" + "=" * 104)
    print("  (c) rung 분포")
    print("=" * 104)
    dist: dict = {}
    default_cnt = 0
    for it in chosen:
        r = routing.get(it.url_hash, {})
        dist[r.get("rung")] = dist.get(r.get("rung"), 0) + 1
        if r.get("default"):
            default_cnt += 1
    for rung in sorted(k for k in dist if k is not None):
        print(f"    rung {rung}: {dist[rung]}건")
    rung8 = dist.get(8, 0)
    print(f"\n  8번(practice) 배정: {rung8}건", end="")
    if rung8 > 3:
        print("  ⚠ 3건 초과 — 형식 축이 자석이 됐다. §2.3 사다리 재검토 필요.")
    else:
        print("  (3건 이하 — 형식 축 격리 정상)")
    print(f"  기본값(7번 예측모델링 fallback) 의존: {default_cnt}건", end="")
    print("  ⚠ 과다 — 사다리 공백 검토." if default_cnt > 3 else "  (양호)")


def report_weak(chosen) -> None:
    weak = [it for it in chosen if is_grounding_weak(it)]
    print("\n" + "=" * 84)
    print(f"  '원문 근거 부족' 아이템 렌더 실측 (abstract < {GROUNDING_MIN_CHARS}자)")
    print("=" * 84)
    print(f"  선별 {len(chosen)}건 중 근거 부족 {len(weak)}건. Phase 3 fetch 보강 범위 판단용.")
    for it in weak:
        alen = len(it.abstract or "")
        print(f"\n  ── [{it.category}] {it.source_domain} · abstract {alen}자")
        print(f"     제목: {it.title[:70]}")
        print(f"     원문: {(it.abstract or '(없음)')[:120]}")
        print(f"     요약: {(it.summary or '(집필 실패)')}")
        print(f"     WHY : {(it.why_it_matters or '-')}")
        print(f"     DIFF: {it.whats_different if it.whats_different else '(생략 — 비교 대상 없음)'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json", help="raw JSON (abstract 포함) — 전체 파이프라인")
    ap.add_argument("--render-only", help="집필 완료 JSON에서 HTML만 재생성 (API 호출 없음)")
    ap.add_argument("--rewrite", help="선별 완료 JSON의 같은 아이템을 Sonnet 재집필만 (랭킹/선별 그대로). "
                                      "새 필드(title_ko/bold) 추가 시 사용")
    args = ap.parse_args()

    cfg = yaml.safe_load(CATEGORIES.read_text(encoding="utf-8"))
    categories = cfg["categories"]
    total_max = cfg.get("total_max", 16)
    run_date = today_kst_iso()

    # 렌더 전용: 저장된 집필 결과로 HTML만 다시 만든다 (레이아웃 반복용, 무비용).
    if args.render_only:
        chosen = [Item(**d) for d in json.loads(Path(args.render_only).read_text(encoding="utf-8"))]
        out = _render_and_save(chosen, categories, run_date)
        report_weak(chosen)
        print(f"\n  재생성: {out}")
        return

    # 재집필 전용: 선별된 같은 아이템을 Sonnet 으로만 다시 쓴다 (랭킹/선별 불변).
    if args.rewrite:
        load_dotenv()
        chosen = [Item(**d) for d in json.loads(Path(args.rewrite).read_text(encoding="utf-8"))]
        print(f"[phase2] 재집필 {len(chosen)}건 (Haiku 랭킹 생략, 같은 선별 유지)...")
        write_tk = write_items(chosen)
        print(f"[phase2] 재집필 완료 ${write_tk.cost_usd:.4f} (근거부족 엄격제한 {write_tk.weak}건)")
        dump = DATA / f"written_{run_date}.json"
        dump.write_text(json.dumps([it.model_dump() for it in chosen], ensure_ascii=False, indent=2),
                        encoding="utf-8")
        out = _render_and_save(chosen, categories, run_date)
        print("\n" + "=" * 84)
        print("  Sonnet 재집필 비용 실측 (title_ko + bold 신규 필드)")
        print("=" * 84)
        print(f"  Sonnet 집필: 호출 {write_tk.calls}, in {write_tk.in_tok:,}/out {write_tk.out_tok:,}, "
              f"${write_tk.cost_usd:.4f}  (표준가 $3/$15, 2026-08-31까지 인트로 $2/$10)")
        print(f"    월 환산(평일 22회): ${write_tk.cost_usd*22:.2f}")
        report_weak(chosen)
        print("\n" + "=" * 84)
        print(f"  생성: {out}")
        print(f"  로컬에서 열기: file:///{str(out).replace(chr(92), '/')}")
        print("=" * 84)
        return

    if not args.from_json:
        ap.error("--from-json / --render-only / --rewrite 중 하나가 필요합니다")

    load_dotenv()
    raw = load_items_from_json(Path(args.from_json))
    new = filter_unseen(raw, load_seen())
    print(f"[phase2] {len(raw)}건 로드 → seen 필터 후 신규 {len(new)}건")

    print("[phase2] Haiku 랭킹...")
    rank_tk = rank_items(new)
    print(f"[phase2] 랭킹 완료 ${rank_tk.cost_usd:.4f}")
    compute_final_scores(new)
    chosen = select(new, categories, total_max)
    print(f"[phase2] 선별 {len(chosen)}건")

    print(f"[phase2] Sonnet 집필 ({len(chosen)}건, 건별 호출)...")
    write_tk = write_items(chosen)
    print(f"[phase2] 집필 완료 ${write_tk.cost_usd:.4f} (근거부족 엄격제한 {write_tk.weak}건)")

    # 집필 결과 덤프 → 이후 --render-only 로 무비용 재렌더
    dump = DATA / f"written_{run_date}.json"
    dump.write_text(json.dumps([it.model_dump() for it in chosen], ensure_ascii=False, indent=2),
                    encoding="utf-8")
    out = _render_and_save(chosen, categories, run_date)

    report_cost(rank_tk, write_tk)
    report_routing(chosen, new, rank_tk.routing, categories)
    report_weak(chosen)
    print("\n" + "=" * 84)
    print(f"  생성: {out}")
    print(f"  로컬에서 열기: file:///{str(out).replace(chr(92), '/')}")
    print("=" * 84)


if __name__ == "__main__":
    main()
