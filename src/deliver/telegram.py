"""Telegram delivery — SPEC §6.3 / §6.4.

Sends TODAY'S TOP 3 (title_ko) + a link to the full HTML page. Fail-safe by
design (SPEC §6.4): any error — missing token, network, API — is logged and
swallowed, returning False. The pipeline never dies because a channel is down.
No dependency beyond httpx (already used by collectors).
"""

from __future__ import annotations

import os

from ..models import Item

_API = "https://api.telegram.org/bot{token}/sendMessage"
_MAX = 4096  # Telegram message limit (SPEC §6.3 — 여유 있음)


def _top3_title(it: Item) -> str:
    # 발송은 한글이 낫다 → title_ko 우선 (paper 도 한글 한 줄 요약이 옴).
    return it.title_ko or it.title


def build_message(items: list[Item], run_date: str, page_url: str) -> str:
    md = run_date[5:].replace("-", "/")
    top3 = sorted([it for it in items if it.is_top3],
                  key=lambda it: (it.final_score or 0), reverse=True)
    lines = [f"📰 AI & ML News Letter · {md}", "", "오늘의 TOP 3"]
    for i, it in enumerate(top3, 1):
        lines.append(f"{i}. {_top3_title(it)}")
    if page_url:
        lines += ["", f"전체 보기 → {page_url}"]
    msg = "\n".join(lines)
    return msg[: _MAX - 1] if len(msg) > _MAX else msg


def send_daily(items: list[Item], run_date: str, page_url: str = "", prefix: str = "") -> bool:
    """POST TOP 3 + link to Telegram. Returns True on success, False (logged) on any failure.

    prefix: optional text prepended (e.g. a budget-breach warning line).
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[telegram] TELEGRAM_BOT_TOKEN/CHAT_ID 없음 → 발송 건너뜀 (파이프라인 계속).")
        return False
    text = (prefix + build_message(items, run_date, page_url))[: _MAX - 1]
    try:
        import httpx

        resp = httpx.post(
            _API.format(token=token),
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": False},
            timeout=30,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            print("[telegram] 발송 성공.")
            return True
        print(f"[telegram] 발송 실패 status={resp.status_code} body={resp.text[:200]} → 로그만, 계속.")
        return False
    except Exception as exc:  # noqa: BLE001 — 발송 실패가 파이프라인을 죽이지 않는다 (SPEC §6.4)
        print(f"[telegram] 발송 예외 ({type(exc).__name__}: {exc}) → 로그만, 계속.")
        return False
