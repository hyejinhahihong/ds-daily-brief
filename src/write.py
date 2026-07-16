"""Sonnet writing — SPEC §2.4 / §4.1.

Fills summary / why_it_matters / whats_different for the selected items, one
Sonnet call per item, grounded STRICTLY in the collected abstract. No web
fetch (Phase 3), no fabrication: if the abstract is thin (< GROUNDING_MIN_CHARS)
the item is marked grounding-weak and the model is told to stay inside the given
text and drop whats_different. whats_different is null unless the abstract gives
an explicit comparison basis (SPEC 원칙 6) — the renderer omits the slot then.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .config import (
    GROUNDING_MIN_CHARS, RETRY_LIMIT, SONNET_MODEL,
    SONNET_PRICE_IN_PER_M, SONNET_PRICE_OUT_PER_M,
)
from .models import Item

_SYSTEM = """You write items for a personal Korean-language DS/AI daily brief.
For ONE item, given its original abstract, produce four fields.

Absolute rule — GROUND STRICTLY IN THE PROVIDED ABSTRACT.
- Never invent facts, numbers, methods, or results not present in the abstract.
- Do not restate the title as the summary. Do not pad with generic filler.
- If the abstract is thin, write less — never fabricate to fill space.

Fields:
1. title_ko — ONE Korean line (40~60 chars) that REWRITES the title with information,
   NOT a literal translation. Pack in numbers, the key result/conclusion, and proper
   nouns. Keep proper nouns in their original spelling (TabFM, XGBoost, NeurIPS).
   Example: "Google, TabFM 공개 — 학습 없이 표 데이터 분류·회귀, TabArena 51개 데이터셋 검증".
   For a paper this becomes a one-line Korean summary (shown as a subtitle); for
   news/blog/release it becomes the main Korean headline. Write it the same way either
   way: informative, concrete, single line. Ground it in the abstract.
2. summary — 3~5 Korean sentences faithfully conveying what the abstract says
   (what it does, key method/result). Plain, concrete, no marketing tone.
3. why_it_matters — 1~2 Korean sentences on context/implication. NOT a restatement
   of the summary's facts. Why a DS/AI reader should care.
4. whats_different — 1~2 Korean sentences on how this differs from prior methods,
   and you MUST name the concrete comparison target (e.g. "기존 DoWhy의 백도어 조정 대비").
   If the abstract gives NO basis to name a comparison target, return null. Never
   invent a comparison. (SPEC 원칙 6)

Emphasis (bold) — inside summary / why_it_matters / whats_different ONLY:
- Wrap the single most important phrase in **double asterisks** (markdown bold).
- MAX 2 per field, and 0 is fine — do not force it. Emphasize numbers
  ("**SWE-bench 59.0%**"), a conclusion ("**XGBoost를 능가**"), or a key proper noun.
- Never bold whole sentences. Do NOT put emphasis in title_ko.

Tone reference: concise and structured like a curated tech newsletter.
Output only the four fields as JSON."""

_SYSTEM_WEAK = """\n\n[GROUNDING WEAK] The abstract is very short or missing. Do NOT go
beyond the given text under any circumstance. Write summary as 1~2 Korean sentences
restating only what little is given. Keep title_ko modest (do not invent specifics not
in the text). Set whats_different to null. Use little or no bold. Better to be brief
than to invent."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "title_ko": {"type": "string"},
        "summary": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "whats_different": {"type": ["string", "null"]},
    },
    "required": ["title_ko", "summary", "why_it_matters", "whats_different"],
    "additionalProperties": False,
}


@dataclass
class WriteTracker:
    calls: int = 0
    in_tok: int = 0
    out_tok: int = 0
    weak: int = 0            # grounding-weak items written under strict limit
    cost_usd: float = 0.0

    def add(self, usage) -> None:
        self.calls += 1
        self.in_tok += usage.input_tokens
        self.out_tok += usage.output_tokens
        self.cost_usd = (
            self.in_tok / 1_000_000 * SONNET_PRICE_IN_PER_M
            + self.out_tok / 1_000_000 * SONNET_PRICE_OUT_PER_M
        )


def is_grounding_weak(it: Item) -> bool:
    return len(it.abstract or "") < GROUNDING_MIN_CHARS


def _user(it: Item) -> str:
    meta = [f"제목: {it.title}", f"출처: {it.source_domain}"]
    if it.venue:
        meta.append(f"학회: {it.venue}")
    meta.append(f"카테고리: {it.category}")
    if it.tags:
        meta.append(f"키워드: {', '.join(it.tags)}")
    meta.append(f"유형: {it.content_type}")
    abstract = (it.abstract or "").strip() or "(원문 초록 없음)"
    return "\n".join(meta) + f"\n\n원문 초록/요약:\n{abstract}"


def write_items(items: list[Item], budget_remaining: float | None = None) -> WriteTracker:
    """Fill summary/why_it_matters/whats_different in place via Sonnet.

    budget_remaining (USD): if set, stop before a call once spend reaches it
    (SPEC §7.3 폭주 방지). None = no writing-side cap (Phase 2 samplers).
    """
    import anthropic

    client = anthropic.Anthropic(max_retries=RETRY_LIMIT)
    tracker = WriteTracker()

    for it in items:
        if budget_remaining is not None and tracker.cost_usd >= budget_remaining:
            print(f"[write] 예산 상한 도달(${tracker.cost_usd:.4f} ≥ ${budget_remaining:.4f}) → 집필 중단")
            break
        weak = is_grounding_weak(it)
        system = _SYSTEM + (_SYSTEM_WEAK if weak else "")
        try:
            resp = client.messages.create(
                model=SONNET_MODEL,
                max_tokens=1024,
                thinking={"type": "disabled"},
                system=system,
                messages=[{"role": "user", "content": _user(it)}],
                output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            )
        except Exception as exc:  # noqa: BLE001 — skip a bad item, keep going
            print(f"[write] 집필 실패 ({type(exc).__name__}) → 건너뜀: {it.title[:50]}")
            continue
        tracker.add(resp.usage)
        if weak:
            tracker.weak += 1
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            print(f"[write] JSON 파싱 실패 → 건너뜀: {it.title[:50]}")
            continue
        it.title_ko = (data.get("title_ko") or "").strip() or None
        it.summary = (data.get("summary") or "").strip() or None
        it.why_it_matters = (data.get("why_it_matters") or "").strip() or None
        wd = data.get("whats_different")
        it.whats_different = wd.strip() if isinstance(wd, str) and wd.strip() else None

    return tracker
