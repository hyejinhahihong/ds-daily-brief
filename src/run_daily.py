"""Phase 3 production runner — the daily job GitHub Actions calls.

  collect → dedup(seen) → Haiku rank → select → Sonnet write → render →
  publish(json) → index → persist seen → Telegram send.

Differences from run_phase2 (the Phase-2 sampler):
  - Persists seen.json (production dedup — the same article won't run twice).
  - Saves data/published/YYYY-MM-DD.json (durable, schema-versioned source).
  - Writes /index.html (copy of today).
  - Sends Telegram TOP 3 (fail-safe).
  - Enforces the SPEC §7.3 daily USD budget across rank + write, and alerts on breach.

Usage:
  uv run python -m src.run_daily                         # live collect + send (cron/dispatch)
  uv run python -m src.run_daily --from-json data/raw_2026-07-16.json --dry-run
  uv run python -m src.run_daily --no-send               # produce + publish, skip Telegram
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import yaml

from .build_site import build as build_site
from .config import DAILY_BUDGET_USD, ROOT, load_dotenv, today_kst_iso
from .dedup import filter_unseen, load_seen, prune, save_seen, update_seen
from .deliver import telegram
from .publish import save_published
from .rank import rank_items
from .run_phase1 import CATEGORIES, PREFERENCES, load_items_from_json
from .select import compute_final_scores, select
from .write import write_items

SOURCES = ROOT / "config" / "sources.yaml"


def _collect_fresh() -> list:
    from .run_collect import collect_all, dedup
    cfg = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))
    raw, _diags, _res = collect_all(cfg)
    return dedup(raw)


def _page_url(run_date: str) -> str:
    base = os.environ.get("SITE_BASE_URL", "").rstrip("/")
    if not base:
        return ""
    return f"{base}/news/{run_date[:4]}/{run_date[5:7]}/{run_date[8:10]}.html"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json", help="raw JSON 로드 (라이브 수집 대신 — 수동 테스트용)")
    ap.add_argument("--no-send", action="store_true", help="텔레그램 발송 생략 (발행까지만)")
    ap.add_argument("--dry-run", action="store_true",
                    help="발송 안 함 + seen.json 미영속 + 발송 메시지 미리보기 (로컬 테스트)")
    args = ap.parse_args()

    load_dotenv()
    cfg = yaml.safe_load(CATEGORIES.read_text(encoding="utf-8"))
    categories = cfg["categories"]
    total_max = cfg.get("total_max", 16)
    run_date = today_kst_iso()  # KST 기준 (SPEC §7.2) — Actions UTC 러너 날짜 밀림 방지

    # 1) collect
    if args.from_json:
        raw = load_items_from_json(Path(args.from_json))
        print(f"[daily] {args.from_json} 에서 {len(raw)}건 로드")
    else:
        print("[daily] 수집 중...")
        raw = _collect_fresh()
        print(f"[daily] 수집 {len(raw)}건")

    # 2) dedup (seen.json)
    seen = load_seen()
    new = filter_unseen(raw, seen)
    print(f"[daily] seen 필터: {len(raw)}건 → 신규 {len(new)}건")

    # 3) rank (budget-guarded internally, SPEC §7.3)
    prefs = PREFERENCES.read_text(encoding="utf-8") if PREFERENCES.exists() else ""
    rank_tk = rank_items(new, preferences=prefs)
    print(f"[daily] 랭킹 완료 ${rank_tk.cost_usd:.4f} (호출 {rank_tk.calls})")

    # 4) select
    compute_final_scores(new)
    chosen = select(new, categories, total_max)
    print(f"[daily] 선별 {len(chosen)}건")

    # 5) write (budget = 남은 예산; SPEC §7.3 폭주 방지)
    remaining = max(0.0, DAILY_BUDGET_USD - rank_tk.cost_usd)
    write_tk = write_items(chosen, budget_remaining=remaining)
    total_cost = rank_tk.cost_usd + write_tk.cost_usd
    print(f"[daily] 집필 완료 ${write_tk.cost_usd:.4f} · 합계 ${total_cost:.4f}")

    # 6) publish durable JSON (schema-versioned) — build_site 의 소스
    pub = save_published(chosen, run_date)
    # 7) 전체 사이트 재생성 (일별 + index + archive + category, published 소스, $0)
    build_site(verbose=False)
    out = ROOT / "news" / run_date[:4] / run_date[5:7] / f"{run_date[8:10]}.html"
    print(f"[daily] 발행 저장: {pub}  ·  사이트 재생성(일별/index/archive/category)")

    # 9) persist seen.json (production dedup) — dry-run 은 건너뜀
    if args.dry_run:
        print("[daily] --dry-run → seen.json 미영속")
    else:
        ranked_new = [it for it in new if it.category]
        seen = prune(update_seen(seen, ranked_new, run_date))
        save_seen(seen)
        print(f"[daily] seen.json 갱신: +{len(ranked_new)} → 총 {len(seen)}건")

    # 예산 초과 경고 (SPEC §7.3). write 는 budget_remaining 으로 이미 중단됨 → 여기선 알림만.
    over_budget = total_cost >= DAILY_BUDGET_USD
    if over_budget:
        print(f"[daily] ⚠ 일일 예산 초과 (${total_cost:.4f} ≥ ${DAILY_BUDGET_USD}) — 집필은 상한에서 중단됨")

    # 10) Telegram send (예산 초과 시 본문 앞에 경고 한 줄)
    page_url = _page_url(run_date)
    alert = (f"⚠ 일일 예산 초과 (${total_cost:.2f}) — 일부 항목 미집필 가능\n\n" if over_budget else "")
    if args.dry_run:
        print("\n[daily] --dry-run 발송 미리보기 ↓\n" + "-" * 60)
        print(alert + telegram.build_message(chosen, run_date, page_url))
        print("-" * 60)
    elif args.no_send:
        print("[daily] --no-send → 텔레그램 생략")
    else:
        telegram.send_daily(chosen, run_date, page_url, prefix=alert)

    print(f"\n[daily] 완료. 합계 ${total_cost:.4f}")


if __name__ == "__main__":
    main()
