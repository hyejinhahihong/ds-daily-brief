"""Haiku filter + ranking — SPEC §4.1 / §4.2.

Assigns base_score (0~10), category (1 of 8), and subtags to each collected
item, in batches, under the SPEC §7.3 budget guards. `stub=True` runs a
deterministic offline scorer to validate the pipeline (seen.json, selection,
dedup, output format) without an API key — clearly NOT real Haiku judgment.

lane_weight / tier_multiplier are NOT touched here (final_score is computed in
select.py). Category assignment is Haiku's job (never heuristic in the real path).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from .config import (
    BATCH_SIZE, DAILY_BUDGET_USD, DAILY_CALL_LIMIT, HAIKU_MODEL,
    HAIKU_PRICE_IN_PER_M, HAIKU_PRICE_OUT_PER_M, MAX_TOKENS_PER_CALL, RETRY_LIMIT,
)
from .models import Item

# base_score 판정 기준 (SPEC §4.2) + 라우팅 사다리 (SPEC §2.3 v4).
_RANK_INSTRUCTIONS = """You are a filter/ranker for a personal DS/AI news brief.
For each item, output base_score (0-10 float), a category, subtags, plus the routing
rung you matched and whether you fell back to the default.

base_score criteria (SPEC §4.2), weigh in this order:
1. Novelty — new vs. existing methods.
2. Reproducibility — is code/model released.
3. Tabular-data applicability — the user's core filter axis (favor it).
4. Concreteness — numbers/experiments/cases (penalize marketing fluff).

Routing — a PRIORITY LADDER (SPEC §2.3). Evaluate top-down; the FIRST rung that
matches decides the category. Set routing_rung to that rung number (1-8).

Rungs 1-7 are TOPIC-based (what the piece is ABOUT). Rung 8 is FORMAT-based (how the
piece is WRITTEN) and sits LAST so it only catches practitioner how-to/retrospective
pieces that no topic rung fit — otherwise it would magnet every practical write-up.

1 causal-inference — causal inference / treatment effect / counterfactual / confounder /
  uplift / DiD / propensity / double ML / causal discovery / SCM. (deep-learning or tabular alike)
2 ai-agent — autonomy / tool use / function calling / multi-agent / orchestration / MCP / agentic workflow
3 llm-foundation-model — model release·training·benchmark / RAG / prompting / alignment /
  LLM evaluation·reliability / context
4 mlops — pipeline / serving / deployment / monitoring / drift / feature store / registry / experiment tracking
5 industry-application — a specific company/industry's real adoption / adoption-rate·ROI survey /
  recommendation·ads·search service application (when APPLICATION, not the research itself, is the topic)
6 deep-learning — the architecture / training method ITSELF is the topic
7 predictive-modeling — applying to a prediction TASK (tabular / timeseries / anomaly /
  imbalanced / clustering / XAI)
8 practice — a practitioner's way of working / workflow / trial-and-error / retrospective / tips /
  Forward Deployed Engineer case / on-site build. ONLY when "HOW they work" is the topic and NOTHING
  on rungs 1-7 fit.

JUDGMENT PRINCIPLE — decide by the TOPIC, not the surface keyword or the format.
- e.g. "Uncertainty Quantification for LLM Function-Calling": UQ is a surface signal, but the
  topic is LLM function calling → rung 2 (ai-agent) or 3 (llm-foundation-model). NOT predictive-modeling.
- If the TOPIC is clear, go to that topic rung even when the piece is a retrospective/how-we-did-it.
  e.g. "Airbnb: how we built a 4-layer LLM eval pipeline (retrospective)" → topic is MLOps → rung 4.
  Only go to rung 8 (practice) when NO topic rung fits, e.g. "How an Anthropic engineer works with
  Claude Code" → no topic rung → rung 8.
- The ultimate DEFAULT when neither a topic nor a practice-format applies is rung 7 (predictive-modeling).
  Set routed_by_default=true ONLY when you fall back to rung 7 with no clear topic. Otherwise false.

Subtags (only when the category matches; else []):
- predictive-modeling: tabular, XAI, anomaly, timeseries, imbalanced, clustering, feature-selection
- causal-inference: did, psm-ipw, uplift, double-ml, causal-forest, causal-discovery, causal-llm

Return JSON: {"results": [{"index", "base_score", "category", "tags", "routing_rung",
"routed_by_default"}...]} for every item."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "base_score": {"type": "number"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "ai-agent", "llm-foundation-model", "deep-learning",
                            "predictive-modeling", "causal-inference", "mlops",
                            "practice", "industry-application",
                        ],
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "routing_rung": {"type": "integer"},  # 1~8 (범위는 코드에서 검증)
                    "routed_by_default": {"type": "boolean"},
                },
                "required": ["index", "base_score", "category", "tags",
                             "routing_rung", "routed_by_default"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


@dataclass
class BudgetTracker:
    calls: int = 0
    in_tok: int = 0
    out_tok: int = 0
    cost_usd: float = 0.0
    # routing diagnostics (SPEC §2.3 v4): url_hash -> {"rung", "default", "category"}.
    # Attached here so callers keep the `tracker = rank_items(...)` contract unchanged.
    routing: dict = field(default_factory=dict)

    def add(self, usage) -> None:
        self.calls += 1
        self.in_tok += usage.input_tokens
        self.out_tok += usage.output_tokens
        self.cost_usd = (
            self.in_tok / 1_000_000 * HAIKU_PRICE_IN_PER_M
            + self.out_tok / 1_000_000 * HAIKU_PRICE_OUT_PER_M
        )

    def exceeded(self) -> bool:
        return self.calls >= DAILY_CALL_LIMIT or self.cost_usd >= DAILY_BUDGET_USD


def _chunks(items: list[Item], n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _clamp(x: float) -> float:
    return max(0.0, min(10.0, float(x)))


def _item_line(idx: int, it: Item) -> str:
    parts = [f"[{idx}] {it.title}", f"src={it.source_domain}", f"type={it.content_type}"]
    if it.venue:
        parts.append(f"venue={it.venue}")
    if it.tags:
        parts.append(f"kw={','.join(it.tags)}")
    return " | ".join(parts)


# --------------------------------------------------------------------------
# Real Haiku ranking
# --------------------------------------------------------------------------
def rank_items(items: list[Item], preferences: str = "") -> BudgetTracker:
    """Rank in place via Haiku. Returns the budget tracker for reporting."""
    import anthropic

    client = anthropic.Anthropic(max_retries=RETRY_LIMIT)
    tracker = BudgetTracker()
    system = _RANK_INSTRUCTIONS
    if preferences.strip():
        system += "\n\nUser feedback to honor (👍👎 accumulated, SPEC §4.3):\n" + preferences.strip()
    system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    for batch in _chunks(items, BATCH_SIZE):
        if tracker.exceeded():
            print(f"[rank] 예산/호출 상한 도달 → 중단 (calls={tracker.calls}, ${tracker.cost_usd:.3f})")
            break
        user = "Rank these items:\n" + "\n".join(_item_line(i, it) for i, it in enumerate(batch))
        try:
            resp = client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=MAX_TOKENS_PER_CALL,
                system=system_blocks,
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            )
        except Exception as exc:  # noqa: BLE001 — skip a bad batch, keep going
            print(f"[rank] 배치 실패 ({type(exc).__name__}) → 건너뜀")
            continue
        tracker.add(resp.usage)
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            results = json.loads(text).get("results", [])
        except json.JSONDecodeError:
            continue
        for r in results:
            i = r.get("index")
            if isinstance(i, int) and 0 <= i < len(batch):
                batch[i].base_score = _clamp(r.get("base_score", 0))
                batch[i].category = r.get("category")
                batch[i].tags = list(r.get("tags") or [])
                tracker.routing[batch[i].url_hash] = {
                    "rung": r.get("routing_rung"),
                    "default": bool(r.get("routed_by_default")),
                    "category": r.get("category"),
                }
    return tracker


# --------------------------------------------------------------------------
# Stub scorer (offline plumbing validation only — NOT real Haiku)
# --------------------------------------------------------------------------
_STUB_ORDER = [
    "ai-agent", "llm-foundation-model", "deep-learning", "predictive-modeling",
    "causal-inference", "mlops", "practice", "industry-application",
]
_PRED_KW = {"tabular", "imbalanced", "xai", "anomaly", "clustering", "timeseries"}


def _stub_category(it: Item, i: int) -> str:
    tags = set(it.tags)
    if "causal" in tags:
        return "causal-inference"
    if tags & _PRED_KW:
        return "predictive-modeling"
    if it.content_type == "paper":
        return "deep-learning"
    if it.content_type == "release":
        return "mlops"
    if it.lane in (1, 6):
        return "industry-application"
    return _STUB_ORDER[i % len(_STUB_ORDER)]


def stub_rank(items: list[Item]) -> BudgetTracker:
    """Deterministic pseudo-scorer. STUB — validates plumbing, not quality."""
    for i, it in enumerate(items):
        h = int(it.url_hash[:8], 16)
        it.base_score = round(3.0 + (h % 700) / 100.0, 1)  # 3.00–9.99, deterministic
        it.category = _stub_category(it, i)
        # keep keyword tags as-is (arXiv items already carry them)
    return BudgetTracker()
