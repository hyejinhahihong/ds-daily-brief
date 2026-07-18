"""Lane 9 — Model releases (HuggingFace Hub, SPEC §3.9.1).

모델 릴리스는 예외 없이 HF Hub 에 뜬다 → 레인 1("블로그를 썼는가")에 의존하지 않는
결정적 경로. 다만 HF 는 하루 수백 개(대부분 파인튜닝/양자화 파생)라 그대로 붙이면
firehose 가 된다. 2단 필터로 억제:
  (a) org 화이트리스트 — 프론티어 랩만 (config lane9_hf.orgs)
  (b) likes/downloads 임계치 + 파생 이름 패턴(GGUF/AWQ/-4bit…) 제외

GitHub Releases(레인 7)처럼 sparse by design — 빈 날이 정상. HF_TOKEN 있으면 사용
(레이트리밋↑), 없어도 public read 동작.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from ..models import TIER_MULTIPLIER, Item
from .base import FeedStatus, domain, http_get, now_iso, url_hash, within_window

_DEFAULT_ENDPOINT = "https://huggingface.co/api/models"


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_derivative(model_id: str, patterns: list[str]) -> bool:
    """파인튜닝/양자화 파생(GGUF, AWQ, -bnb-4bit …)은 이름으로 배제."""
    low = model_id.lower()
    return any(p.lower() in low for p in patterns)


def collect_hf(lane_conf: dict, cfg: dict) -> tuple[list[Item], list[FeedStatus]]:
    endpoint = cfg.get("endpoint", _DEFAULT_ENDPOINT)
    orgs = cfg.get("orgs", [])
    limit = cfg.get("per_org_limit", 50)
    min_likes = cfg.get("min_likes", 20)
    min_dl = cfg.get("min_downloads", 1000)
    excl = cfg.get("exclude_name_patterns", [])

    headers = {"Accept": "application/json"}
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    collected = now_iso()
    items: list[Item] = []
    diags: list[FeedStatus] = []

    for org in orgs:
        api = f"{endpoint}?author={org}&sort=createdAt&direction=-1&limit={limit}"
        try:
            resp = http_get(api, headers=headers)
            models = resp.json()
        except Exception as exc:  # noqa: BLE001 — one bad org shouldn't kill the lane
            diags.append(FeedStatus(lane_conf["lane"], org, api, "error", note=type(exc).__name__))
            continue

        kept = 0
        for m in models if isinstance(models, list) else []:
            mid = m.get("id") or m.get("modelId")
            if not mid:
                continue
            published = _parse_iso(m.get("createdAt"))
            if not within_window(published):   # 3일 롤링 창 (SPEC §3.10)
                continue
            if _is_derivative(mid, excl):
                continue
            likes = m.get("likes") or 0
            dl = m.get("downloads") or 0
            if likes < min_likes and dl < min_dl:  # 파생/무명 모델 컷
                continue
            link = f"https://huggingface.co/{mid}"
            pt = m.get("pipeline_tag") or "?"
            abstract = (f"HuggingFace 모델 릴리스: {mid}. "
                        f"pipeline={pt}, likes={likes}, downloads={dl}.")
            items.append(
                Item(
                    url=link,
                    url_hash=url_hash(link),
                    title=mid,
                    source_domain=domain(link),
                    lane=lane_conf["lane"],
                    lane_weight=lane_conf["lane_weight"],
                    source_tier=lane_conf["source_tier"],
                    tier_multiplier=TIER_MULTIPLIER[lane_conf["source_tier"]],
                    content_type="release",
                    published_at=published.isoformat() if published else None,
                    collected_at=collected,
                    abstract=abstract,
                )
            )
            kept += 1
        diags.append(FeedStatus(lane_conf["lane"], org, api,
                                "ok" if kept else "empty", kept=kept,
                                seen=len(models) if isinstance(models, list) else 0))
    return items, diags
