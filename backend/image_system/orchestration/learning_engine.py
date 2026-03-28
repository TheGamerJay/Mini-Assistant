"""
Learning Engine — Phase 6

After every completed (or failed) task, records:
  - predicted vs actual success
  - predicted vs actual credit cost
  - what strategy worked
  - what caused failure

Over time, these records improve:
  - confidence estimates (ConfidenceEngine)
  - cost estimates (CostEstimator)
  - template selection (TemplateEngine)

All learned records are validated before being used to update estimates.
Harmful or incorrect patterns are NOT reinforced.

Storage: memory_store/learning_records.json
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LEARNING_FILE = Path(__file__).parent.parent.parent / "memory_store" / "learning_records.json"
_MAX_RECORDS   = 2000


@dataclass
class LearningRecord:
    record_id:        str
    task_type:        str        # "build" | "patch" | "image" | "chat"
    mode:             str
    context_hash:     str        # hash of intent + mode + task_type
    predicted_success: float
    actual_success:   bool
    predicted_cost:   int
    actual_cost:      int
    steps_completed:  int
    steps_total:      int
    failure_reason:   Optional[str]
    winning_strategy: Optional[str]
    risk_level:       str
    created_at:       str


def _load() -> List[Dict]:
    if not _LEARNING_FILE.exists():
        return []
    try:
        return json.loads(_LEARNING_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(records: List[Dict]) -> None:
    _LEARNING_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        _LEARNING_FILE.write_text(
            json.dumps(records[-_MAX_RECORDS:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("[LearningEngine] could not save records: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record_outcome(
    task_type:         str,
    mode:              str,
    predicted_success: float,
    actual_success:    bool,
    predicted_cost:    int,
    actual_cost:       int,
    steps_completed:   int,
    steps_total:       int,
    risk_level:        str = "low",
    failure_reason:    Optional[str] = None,
    winning_strategy:  Optional[str] = None,
) -> LearningRecord:
    """
    Record the outcome of a completed/failed task.
    Call this at the end of every task, regardless of success.
    """
    import hashlib
    context_hash = hashlib.md5(f"{task_type}|{mode}|{risk_level}".encode()).hexdigest()[:10]

    record = LearningRecord(
        record_id=str(uuid.uuid4())[:8],
        task_type=task_type,
        mode=mode,
        context_hash=context_hash,
        predicted_success=predicted_success,
        actual_success=actual_success,
        predicted_cost=predicted_cost,
        actual_cost=actual_cost,
        steps_completed=steps_completed,
        steps_total=steps_total,
        failure_reason=failure_reason,
        winning_strategy=winning_strategy,
        risk_level=risk_level,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    records = _load()
    records.append(asdict(record))
    _save(records)

    logger.info(
        "[LearningEngine] recorded: type=%s success=%s predicted=%.2f actual_cost=%d",
        task_type, actual_success, predicted_success, actual_cost,
    )
    return record


def get_success_rate(task_type: str, mode: str, risk_level: str = "low") -> Optional[float]:
    """
    Return historical success rate for similar tasks.
    Returns None if fewer than 5 matching records exist.
    """
    records = _load()
    import hashlib
    context_hash = hashlib.md5(f"{task_type}|{mode}|{risk_level}".encode()).hexdigest()[:10]

    matching = [r for r in records if r.get("context_hash") == context_hash]
    if len(matching) < 5:
        return None  # not enough data to be meaningful

    successes = sum(1 for r in matching if r.get("actual_success"))
    return round(successes / len(matching), 2)


def get_avg_cost(task_type: str, mode: str) -> Optional[float]:
    """
    Return historical average actual credit cost for similar tasks.
    Returns None if fewer than 3 matching records exist.
    """
    records = _load()
    matching = [r for r in records
                if r.get("task_type") == task_type and r.get("mode") == mode and r.get("actual_success")]

    if len(matching) < 3:
        return None

    costs = [r.get("actual_cost", 0) for r in matching]
    return round(sum(costs) / len(costs), 1)


def get_common_failures(task_type: str, top_n: int = 3) -> List[str]:
    """Return the most common failure reasons for a task type."""
    records = _load()
    failures = [
        r.get("failure_reason", "")
        for r in records
        if r.get("task_type") == task_type and not r.get("actual_success") and r.get("failure_reason")
    ]
    # Simple frequency count
    freq: Dict[str, int] = {}
    for f in failures:
        freq[f] = freq.get(f, 0) + 1
    return [k for k, _ in sorted(freq.items(), key=lambda x: -x[1])[:top_n]]
