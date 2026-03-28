"""
Credit Tracker — Phase 3

Tracks credit reservations and actual charges per task step.
Ensures users are only charged for delivered value:
  - Reserve credits before a step
  - Commit on success
  - Refund on failure (full refund if no usable output)
  - Partial refund on partial success

Credit events are persisted to memory_store/credits.json.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_CREDIT_FILE = Path(__file__).parent.parent.parent / "memory_store" / "credit_events.json"


@dataclass
class CreditEvent:
    event_id:        str
    task_id:         str
    step_id:         str
    reserved_amount: int
    final_amount:    int
    refunded_amount: int
    reason:          str
    status:          str   # "reserved" | "committed" | "refunded" | "partial"
    timestamp:       str


def _load_events() -> List[Dict]:
    if not _CREDIT_FILE.exists():
        return []
    try:
        return json.loads(_CREDIT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_events(events: List[Dict]) -> None:
    _CREDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        _CREDIT_FILE.write_text(
            json.dumps(events, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("[CreditTracker] could not persist events: %s", exc)


class CreditTracker:
    """
    Per-task credit tracker. Create one per task.
    """

    def __init__(self, task_id: str):
        self.task_id    = task_id
        self._reserved: Dict[str, int] = {}   # step_id → reserved amount
        self._events:   List[CreditEvent] = []

    def reserve(self, step_id: str, amount: int, reason: str = "") -> None:
        """Reserve credits for a step before it runs."""
        self._reserved[step_id] = amount
        evt = CreditEvent(
            event_id=str(uuid.uuid4())[:8],
            task_id=self.task_id,
            step_id=step_id,
            reserved_amount=amount,
            final_amount=0,
            refunded_amount=0,
            reason=reason,
            status="reserved",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._events.append(evt)
        logger.debug("[CreditTracker] reserved %d credits for step %s", amount, step_id)

    def commit(self, step_id: str, actual_amount: Optional[int] = None, reason: str = "") -> int:
        """
        Commit credits on successful step completion.
        If actual_amount < reserved, the difference is automatically refunded.
        Returns the charged amount.
        """
        reserved = self._reserved.get(step_id, 0)
        charged  = actual_amount if actual_amount is not None else reserved
        charged  = min(charged, reserved)  # never charge more than reserved
        refunded = reserved - charged

        evt = CreditEvent(
            event_id=str(uuid.uuid4())[:8],
            task_id=self.task_id,
            step_id=step_id,
            reserved_amount=reserved,
            final_amount=charged,
            refunded_amount=refunded,
            reason=reason,
            status="committed" if refunded == 0 else "partial",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._events.append(evt)
        self._persist()
        logger.debug("[CreditTracker] committed %d, refunded %d for step %s", charged, refunded, step_id)
        return charged

    def refund(self, step_id: str, reason: str = "Step failed — no usable output") -> int:
        """Full refund for a failed step. Returns the refunded amount."""
        reserved = self._reserved.get(step_id, 0)
        evt = CreditEvent(
            event_id=str(uuid.uuid4())[:8],
            task_id=self.task_id,
            step_id=step_id,
            reserved_amount=reserved,
            final_amount=0,
            refunded_amount=reserved,
            reason=reason,
            status="refunded",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._events.append(evt)
        self._persist()
        logger.debug("[CreditTracker] refunded %d for step %s (%s)", reserved, step_id, reason)
        return reserved

    def total_charged(self) -> int:
        return sum(e.final_amount for e in self._events if e.status in ("committed", "partial"))

    def total_reserved(self) -> int:
        return sum(e.reserved_amount for e in self._events if e.status == "reserved")

    def total_refunded(self) -> int:
        return sum(e.refunded_amount for e in self._events)

    def summary(self) -> Dict:
        return {
            "task_id":       self.task_id,
            "total_charged": self.total_charged(),
            "total_refunded":self.total_refunded(),
            "events":        [asdict(e) for e in self._events],
        }

    def _persist(self) -> None:
        events = _load_events()
        events.extend(asdict(e) for e in self._events if asdict(e) not in events)
        _save_events(events[-5000:])  # cap at 5000 events
