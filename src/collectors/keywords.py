"""Deterministic keyword-group matching for arXiv raw filtering (SPEC §3.5).

This is a *measurement/inclusion* filter, not Haiku category assignment
(Phase 1) — it decides which niche arXiv papers HF Daily Papers won't cover.
Matched group names are stored on Item.tags; they map to the SPEC §2.2
subtags but carry no tier judgment.
"""

from __future__ import annotations

import re
from functools import lru_cache


def compile_groups(keyword_groups: dict[str, list[str]]) -> dict[str, list[re.Pattern]]:
    """Word-boundary regexes so acronyms (ATE/CATE/HTE/GBDT) don't match
    inside longer words (e.g. 'ATE' must not fire on 'state').

    Case policy: a keyword containing any uppercase letter is matched
    case-SENSITIVELY. This is essential — 'DiD' (difference-in-differences)
    matched case-insensitively would fire on the ordinary word 'did' and
    blow up the causal group. All-lowercase keywords stay case-insensitive.
    """
    compiled: dict[str, list[re.Pattern]] = {}
    for group, words in keyword_groups.items():
        pats: list[re.Pattern] = []
        for raw in words:
            w = raw.strip()
            flags = 0 if any(c.isupper() for c in w) else re.IGNORECASE
            pats.append(re.compile(r"\b" + re.escape(w) + r"\b", flags))
        compiled[group] = pats
    return compiled


def match_groups(text: str, compiled: dict[str, list[re.Pattern]]) -> list[str]:
    """Return the sorted group names with at least one keyword hit in text."""
    if not text:
        return []
    hits = [g for g, pats in compiled.items() if any(p.search(text) for p in pats)]
    return sorted(hits)
