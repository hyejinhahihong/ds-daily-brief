"""final_score + category-quota selection — SPEC §4.2 / §2.1.

    final_score = base_score × lane_weight × tier_multiplier

lane_weight is used AS-IS from SPEC (never changed here). Fills each category's
floor first, distributes remaining slots by final_score up to per-category max
and the global cap (16). Floors that have no candidates stay empty — quotas are
never force-filled (SPEC 원칙 3).
"""

from __future__ import annotations

from .models import Item


def compute_final_scores(items: list[Item]) -> None:
    """Compute normal quality score, preserving verified major-event significance."""
    for it in items:
        if it.base_score is None:
            it.final_score = None
            continue
        quality_score = it.base_score * it.lane_weight * it.tier_multiplier
        # A major launch's importance is assessed independently from a discovery
        # source's lane weight. Normal articles retain the existing formula.
        if it.coverage_priority and it.event_score is not None:
            quality_score = max(quality_score, it.event_score)
        it.final_score = round(quality_score, 3)


def select(items: list[Item], categories: list[dict], total_max: int = 16) -> list[Item]:
    """Return the chosen 12~16 items with is_top3 marked."""
    ranked = [it for it in items if it.is_relevant and it.final_score is not None and it.category]
    by_cat: dict[str, list[Item]] = {c["id"]: [] for c in categories}
    for it in ranked:
        if it.category in by_cat:
            by_cat[it.category].append(it)
    for lst in by_cat.values():
        # A verified major model launch retains one category slot even when a
        # lower source-lane multiplier would otherwise displace it.
        lst.sort(key=lambda it: (it.coverage_priority, it.final_score), reverse=True)

    chosen: list[Item] = []
    taken: dict[str, int] = {c["id"]: 0 for c in categories}

    # 1) fill each category's floor (only if candidates exist).
    for c in categories:
        cid = c["id"]
        for it in by_cat[cid][: c["min"]]:
            chosen.append(it)
            taken[cid] += 1

    # 2) distribute remaining global slots by final_score, respecting per-cat max.
    pool: list[Item] = []
    for c in categories:
        cid = c["id"]
        pool.extend(by_cat[cid][taken[cid]: c["max"]])
    pool.sort(key=lambda it: (it.coverage_priority, it.final_score), reverse=True)

    cap = {c["id"]: c["max"] for c in categories}
    for it in pool:
        if len(chosen) >= total_max:
            break
        if taken[it.category] < cap[it.category]:
            chosen.append(it)
            taken[it.category] += 1

    # 3) global cap: if over (shouldn't be, but guard), cut lowest final_score.
    chosen.sort(key=lambda it: it.final_score, reverse=True)
    chosen = chosen[:total_max]

    # 4) TODAY'S TOP 3 (SPEC §2.5) — top by final_score overall.
    for rank, it in enumerate(chosen):
        it.is_top3 = rank < 3

    return chosen
