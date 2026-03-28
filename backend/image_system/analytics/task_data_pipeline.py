"""
Task Data Pipeline — centralized analytics persistence.

All structured analytics records flow through this single module so that
the privacy gate (data_minimizer) and anonymizer are applied consistently.

Record types
------------
  TaskAnalyticsRecord    (Tier A — always collected)
    session_id_hash, mode, turn_count, timestamp

  IntentSummaryRecord    (Tier B — improve_system only)
    intent_type, ambiguity_score, confidence_label, risk_level

  ExecutionSummaryRecord (Tier B)
    task_id, step_count, completed_steps, total_credits, duration_ms, success

  FailureSummaryRecord   (Tier B)
    task_id, failure_class, retry_count, rolled_back

  ResultSummaryRecord    (Tier B)
    task_id, verification_passed, quality_score

All records are stored in memory_store/task_analytics.json (shared file,
capped at 10 000 records).  The pipeline serialises concurrent writes with a
threading.Lock to avoid corruption.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.image_system.privacy.data_minimizer import DataTier, should_collect
from backend.image_system.privacy.anonymizer import hash_id, scrub

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_DEFAULT_STORE = Path(__file__).resolve().parent.parent.parent.parent / "memory_store" / "task_analytics.json"
_MAX_RECORDS = 10_000
_write_lock = threading.Lock()


def _store_path() -> Path:
    env = os.environ.get("TASK_ANALYTICS_PATH")
    return Path(env) if env else _DEFAULT_STORE


def _load(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(records: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


def _append(record: Dict[str, Any]) -> None:
    path = _store_path()
    with _write_lock:
        records = _load(path)
        records.append(record)
        if len(records) > _MAX_RECORDS:
            records = records[-_MAX_RECORDS:]
        _save(records, path)


# ---------------------------------------------------------------------------
# Record dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TaskAnalyticsRecord:
    """Tier A — always collected regardless of privacy mode."""
    session_id_hash: str          # 8-char hash, not the real ID
    mode:            str          # chat | builder | image
    turn_count:      int
    recorded_at:     str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tier:            str = "A"


@dataclass
class IntentSummaryRecord:
    """Tier B — improve_system mode only."""
    intent_type:      str          # build | patch | query | image | analysis | chat
    ambiguity_score:  float
    confidence_label: str          # high | medium | low
    risk_level:       str          # low | medium | high | critical
    recorded_at:      str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tier:             str = "B"


@dataclass
class ExecutionSummaryRecord:
    """Tier B — improve_system mode only."""
    task_id:         str
    step_count:      int
    completed_steps: int
    total_credits:   float
    duration_ms:     float
    success:         bool
    recorded_at:     str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tier:            str = "B"


@dataclass
class FailureSummaryRecord:
    """Tier B — improve_system mode only."""
    task_id:       str
    failure_class: str    # TRANSIENT | MODEL | SCOPE | STRUCTURAL | FATAL
    retry_count:   int
    rolled_back:   bool
    recorded_at:   str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tier:          str = "B"


@dataclass
class ResultSummaryRecord:
    """Tier B — improve_system mode only."""
    task_id:             str
    verification_passed: bool
    quality_score:       float   # 0.0–1.0 or -1 if not checked
    recorded_at:         str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tier:                str = "B"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record_task_analytics(
    session_id: str,
    mode: str,
    turn_count: int,
    user_mode: Optional[str] = None,
) -> bool:
    """
    Persist a Tier A TaskAnalyticsRecord.

    Always passes the privacy gate (Tier A is always allowed).
    The session_id is one-way hashed — the real ID is never stored.

    Returns True if persisted, False if skipped.
    """
    if not should_collect(DataTier.A, user_mode):
        return False
    rec = TaskAnalyticsRecord(
        session_id_hash=hash_id(session_id),
        mode=mode,
        turn_count=turn_count,
    )
    try:
        _append(asdict(rec))
        return True
    except Exception as exc:
        logger.warning("task_data_pipeline: failed to record Tier A — %s", exc)
        return False


def record_intent_summary(
    intent_type: str,
    ambiguity_score: float,
    confidence_label: str,
    risk_level: str,
    user_mode: Optional[str] = None,
) -> bool:
    """Persist a Tier B IntentSummaryRecord (improve_system only)."""
    if not should_collect(DataTier.B, user_mode):
        return False
    rec = IntentSummaryRecord(
        intent_type=intent_type,
        ambiguity_score=round(ambiguity_score, 3),
        confidence_label=confidence_label,
        risk_level=risk_level,
    )
    try:
        _append(asdict(rec))
        return True
    except Exception as exc:
        logger.warning("task_data_pipeline: failed to record IntentSummary — %s", exc)
        return False


def record_execution_summary(
    task_id: str,
    step_count: int,
    completed_steps: int,
    total_credits: float,
    duration_ms: float,
    success: bool,
    user_mode: Optional[str] = None,
) -> bool:
    """Persist a Tier B ExecutionSummaryRecord (improve_system only)."""
    if not should_collect(DataTier.B, user_mode):
        return False
    rec = ExecutionSummaryRecord(
        task_id=task_id,
        step_count=step_count,
        completed_steps=completed_steps,
        total_credits=round(total_credits, 4),
        duration_ms=round(duration_ms, 1),
        success=success,
    )
    try:
        _append(asdict(rec))
        return True
    except Exception as exc:
        logger.warning("task_data_pipeline: failed to record ExecutionSummary — %s", exc)
        return False


def record_failure_summary(
    task_id: str,
    failure_class: str,
    retry_count: int,
    rolled_back: bool,
    user_mode: Optional[str] = None,
) -> bool:
    """Persist a Tier B FailureSummaryRecord (improve_system only)."""
    if not should_collect(DataTier.B, user_mode):
        return False
    rec = FailureSummaryRecord(
        task_id=task_id,
        failure_class=failure_class,
        retry_count=retry_count,
        rolled_back=rolled_back,
    )
    try:
        _append(asdict(rec))
        return True
    except Exception as exc:
        logger.warning("task_data_pipeline: failed to record FailureSummary — %s", exc)
        return False


def record_result_summary(
    task_id: str,
    verification_passed: bool,
    quality_score: float,
    user_mode: Optional[str] = None,
) -> bool:
    """Persist a Tier B ResultSummaryRecord (improve_system only)."""
    if not should_collect(DataTier.B, user_mode):
        return False
    rec = ResultSummaryRecord(
        task_id=task_id,
        verification_passed=verification_passed,
        quality_score=round(quality_score, 3),
    )
    try:
        _append(asdict(rec))
        return True
    except Exception as exc:
        logger.warning("task_data_pipeline: failed to record ResultSummary — %s", exc)
        return False


def get_recent_analytics(limit: int = 100) -> List[Dict[str, Any]]:
    """Return the most recent `limit` analytics records (all tiers)."""
    records = _load(_store_path())
    return records[-limit:]
