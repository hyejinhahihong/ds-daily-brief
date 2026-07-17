"""Phase 0 runner — collect 7 lanes locally and measure per-lane volume.

Usage:
  uv run python -m src.run_collect                        # 3-day rolling
  uv run python -m src.run_collect --since 2026-06-28     # 창 확장
  uv run python -m src.run_collect --since 2026-06-28 --coverage   # 커버리지 검증

Deliberately excluded (SPEC-driven): Haiku ranking / seen.json / sending /
HTML — those are Phase 1+. See docs/TASK.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows 콘솔(cp949)에서도 한국어/em-dash 출력이 깨지지 않도록.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import yaml

from .collectors.anthropic_news import collect_anthropic
from .collectors.arxiv import ArxivResult, collect_arxiv
from .collectors.base import FeedStatus, collect_rss_feed, set_window_since, window_cutoff
from .collectors.github import collect_github
from .config import now_kst, today_kst_iso
from .models import Item

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "sources.yaml"
DATA_DIR = ROOT / "data"


def _lane_conf(lanes: dict, n: int) -> dict:
    c = dict(lanes[n])
    c["lane"] = n
    return c


def collect_all(cfg: dict) -> tuple[list[Item], list[FeedStatus], ArxivResult]:
    lanes = cfg["lanes"]
    items: list[Item] = []
    diags: list[FeedStatus] = []

    # RSS lanes: 1, 3, 5, 6, 8
    for lane_no, feed_key in [(1, "lane1_feeds"), (3, "lane3_feeds"),
                              (5, "lane5_feeds"), (6, "lane6_feeds"),
                              (8, "lane8_feeds")]:
        conf = _lane_conf(lanes, lane_no)
        for feed in cfg.get(feed_key, []):
            feed_items, status = collect_rss_feed(feed, conf)
            items.extend(feed_items)
            diags.append(status)

    # Lane 1 보조: Anthropic (RSS 없음 → HTML 스크래퍼, 작업 2)
    anth_items, anth_status = collect_anthropic(_lane_conf(lanes, 1))
    items.extend(anth_items)
    diags.append(anth_status)

    # Lanes 2 & 4: arXiv (paged, keyword-filtered, HF split) — 작업 2
    ax = cfg["arxiv"]
    res = collect_arxiv(
        _lane_conf(lanes, 2), _lane_conf(lanes, 4),
        ax["categories"], ax["keyword_groups"], ax.get("max_total", 3000),
    )
    items.extend(res.lane2)
    items.extend(res.lane4)
    diags.extend(res.diags)

    # Lane 7: GitHub Releases
    gh_items, gh_diags = collect_github(_lane_conf(lanes, 7), cfg.get("lane7_repos", []))
    items.extend(gh_items)
    diags.extend(gh_diags)

    return items, diags, res


def dedup(items: list[Item]) -> list[Item]:
    """Within-run dedup by url_hash (seen.json persistence is Phase 1)."""
    seen: dict[str, Item] = {}
    for it in items:
        prev = seen.get(it.url_hash)
        if prev is None or it.lane_weight > prev.lane_weight:
            seen[it.url_hash] = it
    return list(seen.values())


def write_json(items: list[Item], run_date: str) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / f"raw_{run_date}.json"
    out.write_text(
        json.dumps([it.model_dump() for it in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def _window_label(days: float) -> str:
    cutoff = window_cutoff()
    return f"{cutoff.date()} ~ {now_kst().date()}  ({days:.0f}일)"


# --------------------------------------------------------------------------
# Report — 작업 3
# --------------------------------------------------------------------------
def print_report(items: list[Item], diags: list[FeedStatus], cfg: dict,
                 res: ArxivResult, window_days: float) -> None:
    lanes = cfg["lanes"]
    by_lane: dict[int, list[Item]] = {}
    for it in items:
        by_lane.setdefault(it.lane, []).append(it)

    print("\n" + "=" * 82)
    print(f"  Phase 0 — 레인별 물량 실측  (수집 창: {_window_label(window_days)}, SPEC §3.10)")
    print("=" * 82)
    print(f"{'레인':<24}{'weight':>8}{'합계':>7}{'일평균':>8}{'Tier1':>8}{'venue':>7}")
    print("-" * 82)

    total = 0
    for n in sorted(lanes.keys()):
        li = by_lane.get(n, [])
        cnt = len(li)
        total += cnt
        t1 = sum(1 for it in li if it.source_tier == 1)
        t1_ratio = f"{(t1 / cnt * 100):.0f}%" if cnt else "-"
        venue_n = sum(1 for it in li if it.venue)
        w = lanes[n]["lane_weight"]
        print(f"{n}. {lanes[n]['name']:<21}{w:>8.2f}{cnt:>7}{cnt / window_days:>8.1f}"
              f"{t1_ratio:>8}{venue_n:>7}")
    print("-" * 82)
    print(f"{'합계 (dedup 후)':<24}{'':>8}{total:>7}{total / window_days:>8.1f}")
    print("=" * 82)

    # arXiv 역할 분리 + 키워드 그룹별 건수 (작업 2/3)
    print("\n  ── 레인 4 arXiv 역할 분리 ──")
    raw_total = len(res.lane4_raw) + res.dropped_raw
    print(f"    HF Daily (DL/LLM 담당) : {len(res.lane4_hf):>4}건")
    print(f"    arXiv raw niche 유지    : {len(res.lane4_raw):>4}건  "
          f"(원시 {raw_total}건 중 {res.dropped_raw}건 드롭 = HF 담당영역)")
    print(f"    → 일평균 {(len(res.lane4_raw)) / window_days:.1f}건/일  "
          f"(억제 전 원시 {raw_total / window_days:.1f}건/일)")
    print("\n  ── arXiv 키워드 그룹별 건수 (raw niche, 논문당 복수 그룹 가능) ──")
    for g in cfg["arxiv"]["keyword_groups"].keys():
        c = sum(1 for it in res.lane4_raw if g in it.tags)
        c2 = sum(1 for it in res.lane2 if g in it.tags)
        star = "  ← 필수" if g == "causal" else ""
        print(f"    {g:<12}: raw {c:>3}   (학회 레인2 매칭 {c2}){star}")

    # 레인 1 최종 살아있는 피드 목록 (작업 3)
    print("\n  ── 레인 1 피드 상태 (최종) ──")
    for d in [d for d in diags if d.lane == 1]:
        mark = {"ok": "✅", "empty": "·", "error": "❌"}.get(d.status, "?")
        extra = f"  ({d.note})" if d.note else ""
        print(f"    {mark} {d.name:<26} {d.status:<6} kept={d.kept}{extra}")

    # content_type
    ctypes: dict[str, int] = {}
    for it in items:
        ctypes[it.content_type] = ctypes.get(it.content_type, 0) + 1
    print("\n  content_type:", "  ".join(f"{k}={v}" for k, v in sorted(ctypes.items())))

    # 피드 진단 (작업 1: UA 폴백 결과 포함)
    errors = [d for d in diags if d.status == "error"]
    empties = [d for d in diags if d.status == "empty"]
    browser = [d for d in diags if d.note == "browser-UA"]
    print(f"\n  피드 진단:  ok={sum(1 for d in diags if d.status == 'ok')}  "
          f"empty={len(empties)}  error={len(errors)}")
    if browser:
        print("  ── 브라우저 UA 폴백으로 복구됨 ──")
        for d in browser:
            print(f"    [L{d.lane}] {d.name}  (+{d.kept}건)")
    if errors:
        print("  ── error (UA 폴백에도 실패 → URL 교체 필요) ──")
        for d in errors:
            print(f"    [L{d.lane}] {d.name}: {d.note}  ({d.url})")
    if empties:
        print("  ── empty (0건 — 죽었거나 창 내 신규 없음) ──")
        for d in empties:
            print(f"    [L{d.lane}] {d.name}  ({d.url})")

    print("\n  ※ '상위 스코어 진입률'은 Haiku 랭킹(Phase 1, SPEC §4.1) 필요 → 이번 산출 제외.")


# --------------------------------------------------------------------------
# Coverage — 작업 4
# --------------------------------------------------------------------------
def _fmt(it: Item) -> str:
    d = (it.published_at or "")[:10] or "──────────"
    return f"    {d} · {it.title}\n              {it.url}"


def _sorted_desc(items: list[Item]) -> list[Item]:
    return sorted(items, key=lambda it: it.published_at or "0000", reverse=True)


def print_coverage(items: list[Item], diags: list[FeedStatus], window_days: float) -> None:
    by_lane: dict[int, list[Item]] = {}
    for it in items:
        by_lane.setdefault(it.lane, []).append(it)

    print("\n" + "#" * 82)
    print(f"  커버리지 검증  (창: {_window_label(window_days)})")
    print("#" * 82)

    l1 = _sorted_desc(by_lane.get(1, []))
    print(f"\n[레인 1] 빅테크 리서치 블로그 — 전체 {len(l1)}건 (날짜 역순)")
    for it in l1:
        print(_fmt(it))

    key_groups = {"causal", "tabular", "timeseries"}
    l2 = _sorted_desc([it for it in by_lane.get(2, []) if key_groups & set(it.tags)])
    print(f"\n[레인 2] 학회 중 causal/tabular/timeseries 매칭 — {len(l2)}건")
    for it in l2:
        print(f"{_fmt(it)}   [{','.join(it.tags)}]  venue={it.venue}")

    l3 = _sorted_desc(by_lane.get(3, []))
    print(f"\n[레인 3] 큐레이션 뉴스레터 — 전체 {len(l3)}건")
    for it in l3:
        print(_fmt(it))

    # 알려진 검증 케이스: Google TabFM (2026-06-30, research.google/blog)
    print("\n[검증 케이스] Google TabFM (2026-06-30, research.google/blog)")
    hits = [it for it in by_lane.get(1, [])
            if ("tabfm" in it.title.lower() or "tabular foundation" in it.title.lower()
                or ("research.google" in it.url and (it.published_at or "").startswith("2026-06-30")))]
    if hits:
        for it in hits:
            print(f"    ✅ FOUND: {(it.published_at or '')[:10]} · {it.title}\n              {it.url}")
    else:
        gd = next((d for d in diags if "google research" in d.name.lower()), None)
        print("    ❌ NOT FOUND — 진단:")
        if gd:
            print(f"       Google Research Blog 피드: status={gd.status}, "
                  f"수집 {gd.kept}건 / 피드제공 {gd.seen}건, note='{gd.note}'")
            print("       → 피드가 최근 N건만 노출하면 06-30 항목이 이미 밀려났을 수 있음")
            print("       → 또는 제목에 'TabFM'/'tabular foundation' 문자열이 없어 매칭 실패")
        else:
            print("       Google Research Blog 진단 항목을 찾지 못함 (config 확인)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", help="절대 수집 시작일 YYYY-MM-DD (기본: 최근 3일 롤링)")
    parser.add_argument("--coverage", action="store_true", help="레인 1/2/3 전체 목록 출력")
    args = parser.parse_args()

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

    if args.since:
        since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        set_window_since(since)
        window_days = max((datetime.now(timezone.utc) - since).days, 1)
    else:
        window_days = 3.0

    run_date = today_kst_iso()
    print(f"[collect] 시작 — {run_date}  창={_window_label(window_days)}")

    raw, diags, res = collect_all(cfg)
    print(f"[collect] 원시 {len(raw)}건 → dedup 중...")
    items = dedup(raw)
    out = write_json(items, run_date)

    print_report(items, diags, cfg, res, window_days)
    if args.coverage:
        print_coverage(items, diags, window_days)

    print(f"\n[collect] 저장: {out}  ({len(items)}건)")


if __name__ == "__main__":
    main()
