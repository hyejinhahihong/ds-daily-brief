"""Data models — SPEC §8.

Phase 0 populates only the collection-time fields. Ranking fields
(base_score / final_score / category / tags) are assigned by Haiku in
Phase 1 (SPEC §4.1); writing fields (summary / why_it_matters / ...) by
Sonnet in Phase 2. They carry SPEC-accurate defaults here so the schema
is documented in one place, but Phase 0 code never fills them.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# SPEC §3.1.1 — 원본성(source_tier) → 배수. Tier 5 는 페널티.
TIER_MULTIPLIER: dict[int, float] = {1: 1.0, 2: 0.95, 3: 0.85, 4: 0.8, 5: 0.5}


class Item(BaseModel):
    # --- collection-time (Phase 0) ---
    url: str
    url_hash: str
    title: str                      # 원문 제목
    source_domain: str
    lane: int                       # 1~7 (+8 국문 보조, +9 모델 릴리스), SPEC §3.1
    lane_weight: float              # 0.4~1.0, SPEC §3.1
    source_tier: int                # 1~5 원본성, SPEC §3.1.1
    tier_multiplier: float          # 1.0~0.5
    venue: Optional[str] = None     # "NeurIPS 2026" 등, 레인 2일 때
    content_type: Literal["news", "paper", "release", "blog"]
    published_at: Optional[str] = None
    collected_at: str
    abstract: Optional[str] = None   # 원문 초록/요약 (수집 시점 저장, SPEC §8). Sonnet 집필 근거.

    # --- assigned in Phase 1 (Haiku ranking, SPEC §4) ---
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    base_score: Optional[float] = None
    final_score: Optional[float] = None

    # --- written in Phase 2 (Sonnet, SPEC §2.4) ---
    # 한글 재작성 제목/요약 (SPEC §8). paper → 부제(한글 한 줄 요약),
    # news/blog/release → 주 제목(한글 재작성). 렌더 분기는 render.py.
    title_ko: Optional[str] = None
    summary: Optional[str] = None
    why_it_matters: Optional[str] = None
    whats_different: Optional[str] = None
    related_prev: Optional[str] = None
    is_top3: bool = False
