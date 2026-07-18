"""Per-stage pipeline snapshots — data/raw/{stage}/YYYY-MM-DD.json (Phase 4 작업 1).

현재 파이프라인은 최종 채택분만 남겨, 어느 단계에서 사건이 탈락했는지 사후 추적이
불가능하다 (Kimi K3 회귀 진단이 오래 걸린 이유). 각 단계의 아이템 스냅샷을 날짜별로
저장해 scripts/replay.py 가 collect / dedup / rank / select 어디서 떨어졌는지 짚게 한다.

저장은 best-effort — 스냅샷 쓰기 실패가 프로덕션 파이프라인을 죽이지 않는다 (SPEC §6.4 원칙).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .config import ROOT
from .models import Item

# 파이프라인 순서 그대로. replay 의 탈락-단계 추적이 이 순서로 스냅샷을 훑는다.
STAGES: tuple[str, ...] = ("collect", "dedup", "rank", "select")

_SNAP_ROOT = ROOT / "data" / "raw"


def stage_path(stage: str, run_date: str) -> Path:
    return _SNAP_ROOT / stage / f"{run_date}.json"


def save_stage(stage: str, items: list[Item], run_date: str) -> None:
    """Persist a stage's items. Best-effort: never raises into the pipeline."""
    try:
        path = stage_path(stage, run_date)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [it.model_dump() for it in items]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — diagnostics must not break production
        print(f"[snapshot] {stage}/{run_date} 저장 실패 ({type(exc).__name__}) — 무시하고 계속")


def load_stage(stage: str, run_date: str) -> Optional[list[dict]]:
    """Return the raw dicts for a stage/date, or None if not snapshotted."""
    path = stage_path(stage, run_date)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
