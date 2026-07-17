"""Environment + cost-guard constants (SPEC §7.3, §7.4).

Secrets come from .env (never hardcoded). Budget guards are mandatory per
SPEC §7.3 ("폭주 방지 필수 구현").
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent

# --- 타임존: 모든 날짜 라벨은 KST 기준 (SPEC §7.2) ---
# GitHub Actions 러너는 UTC다. naive date.today()/datetime.now()를 쓰면 KST 06:30 실행이
# UTC 전날로 찍혀 파일이 하루 밀린다(2026-07-17 06:30 실행이 07-16 으로 저장된 버그).
# → 날짜/파일명/마스트헤드/first_seen/발송본문/수집창은 전부 아래 헬퍼로 KST 계산.
KST = ZoneInfo("Asia/Seoul")


def now_kst() -> datetime:
    """현재 시각(Asia/Seoul, tz-aware)."""
    return datetime.now(KST)


def today_kst_iso() -> str:
    """오늘 날짜 YYYY-MM-DD (KST). 출력 경로·published 파일명·run_date 의 기준."""
    return datetime.now(KST).date().isoformat()


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader (no dependency). Existing env vars win."""
    path = path or (ROOT / ".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


# --- ranking model (SPEC §4.1: 필터·랭킹 = Haiku) ---
HAIKU_MODEL = "claude-haiku-4-5"
HAIKU_PRICE_IN_PER_M = 1.0   # $/1M input tokens
HAIKU_PRICE_OUT_PER_M = 5.0  # $/1M output tokens

# --- writing model (SPEC §4.1: 집필·해석 = Sonnet) ---
SONNET_MODEL = "claude-sonnet-5"
SONNET_PRICE_IN_PER_M = 3.0   # $/1M input (표준가. 2026-08-31까지 인트로 $2)
SONNET_PRICE_OUT_PER_M = 15.0  # $/1M output (표준가. 인트로 $10)
GROUNDING_MIN_CHARS = 100  # abstract 이 이보다 짧으면 "원문 근거 부족" → 집필 엄격 제한

# --- budget guards (SPEC §7.3) ---
MAX_TOKENS_PER_CALL = 2000
DAILY_CALL_LIMIT = 150
RETRY_LIMIT = 3
DAILY_BUDGET_USD = 1.0
TIMEOUT_PER_LANE_SEC = 120  # SPEC §7.3 (수집기 fetch 타임아웃 상한)
BATCH_SIZE = 15  # items per Haiku call — keeps output under MAX_TOKENS_PER_CALL

# --- published-data schema version (Phase 3-a) ---
# 발행 아이템(data/published/*.json)에 박아 두는 스키마 버전. 필드를 추가/변경할 때
# 올린다. 과거 발행분을 마이그레이션할 때 이 값으로 판별 → 데이터 유실 방지.
# v5: title_ko(§8) 추가 + practice 카테고리(§2.1/§2.3).
SCHEMA_VERSION = "5"


# --- delivery / hosting (Phase 3) ---
def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# 텔레그램 (SPEC §6.3). 없으면 발송 건너뜀(파이프라인은 죽지 않음, SPEC §6.4).
TELEGRAM_BOT_TOKEN = "TELEGRAM_BOT_TOKEN"  # env 키 이름 (값은 .env/Secrets에서 런타임 조회)
TELEGRAM_CHAT_ID = "TELEGRAM_CHAT_ID"
# GitHub Pages 베이스 URL (예: https://<user>.github.io/<repo>). 발송 링크 조립용.
SITE_BASE_URL = "SITE_BASE_URL"
