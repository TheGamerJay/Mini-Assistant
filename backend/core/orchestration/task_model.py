"""
orchestration/task_model.py — Formal Task lifecycle model (Kanban-style).

Every CEO execution creates a Task that tracks the full lifecycle.
Persists to memory_store/tasks.json so tasks survive restarts and are
visible to the admin dashboard / X-Ray panel.

Task status (Kanban columns):
  pending        → created, CEO not yet active
  in_progress    → CEO executing right now
  needs_approval → Doctor proposed a fix; waiting for user
  blocked        → waiting for user clarification input
  complete       → all QA passed, response delivered
  failed         → exhausted retries or unrecoverable error

Task stage (maps 1:1 to stage_machine.STAGES):
  input → planning → building → qa_hands → qa_vision → done
                                    ↕
                                  repair ← (when QA fails)
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("ceo_router.task_model")

# Persist to memory_store/tasks.json (two levels up from this file)
_STORE_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "memory_store", "tasks.json")
)

# In-memory registry: task_id → Task
_TASKS: dict[str, "Task"] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# TransitionRecord — one logged stage hop
# ---------------------------------------------------------------------------

@dataclass
class TransitionRecord:
    """
    Immutable record of a single stage transition.
    Appended to Task.history on every CEO stage change.
    """
    from_stage:  str
    to_stage:    str
    reason:      str
    brain:       str
    timestamp:   str   = field(default_factory=_now_iso)
    elapsed_ms:  float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_stage":  self.from_stage,
            "to_stage":    self.to_stage,
            "reason":      self.reason,
            "brain":       self.brain,
            "timestamp":   self.timestamp,
            "elapsed_ms":  self.elapsed_ms,
        }


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

@dataclass
class Task:
    """
    Formal task object — one per CEO execution.

    CEO creates this at the start of every execute_builder_task() /
    stream_builder_task() call. stage_machine transitions it through stages.
    brain_router gateway validates each brain call against current_stage.
    """
    id:            str
    title:         str                    # truncated user goal (≤80 chars)
    session_id:    str
    status:        str = "pending"        # pending|in_progress|needs_approval|blocked|complete|failed
    current_stage: str = "input"          # maps to stage_machine STAGES
    history:       list[TransitionRecord] = field(default_factory=list)
    retries:       dict[str, int]         = field(default_factory=dict)
    created_at:    str                    = field(default_factory=_now_iso)
    updated_at:    str                    = field(default_factory=_now_iso)
    final_outcome: Optional[str]          = None

    # ── Mutators ───────────────────────────────────────────────────────────────

    def touch(self) -> None:
        self.updated_at = _now_iso()

    def increment_retry(self, stage: str) -> int:
        self.retries[stage] = self.retries.get(stage, 0) + 1
        self.touch()
        return self.retries[stage]

    def get_retry(self, stage: str) -> int:
        return self.retries.get(stage, 0)

    def record_transition(
        self,
        to_stage:    str,
        reason:      str,
        brain:       str   = "ceo",
        elapsed_ms:  float = 0.0,
    ) -> None:
        """Append a TransitionRecord and advance current_stage."""
        rec = TransitionRecord(
            from_stage = self.current_stage,
            to_stage   = to_stage,
            reason     = reason,
            brain      = brain,
            elapsed_ms = elapsed_ms,
        )
        self.history.append(rec)
        self.current_stage = to_stage
        self.touch()

    def set_status(self, status: str, outcome: str = "") -> None:
        self.status = status
        if outcome:
            self.final_outcome = outcome
        self.touch()

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":            self.id,
            "title":         self.title,
            "session_id":    self.session_id,
            "status":        self.status,
            "current_stage": self.current_stage,
            "retries":       self.retries,
            "created_at":    self.created_at,
            "updated_at":    self.updated_at,
            "final_outcome": self.final_outcome,
            "history":       [r.to_dict() for r in self.history],
        }

    def summary_dict(self) -> dict[str, Any]:
        """Lightweight dict for API responses / logging."""
        return {
            "task_id":       self.id,
            "title":         self.title,
            "status":        self.status,
            "current_stage": self.current_stage,
            "retries":       self.retries,
            "created_at":    self.created_at,
            "updated_at":    self.updated_at,
            "steps":         len(self.history),
        }


# ---------------------------------------------------------------------------
# TaskRegistry
# ---------------------------------------------------------------------------

class TaskRegistry:
    """
    In-memory + on-disk registry of all Tasks.
    All mutations persist to disk atomically (tmp-file swap).

    CEO uses this via the module-level `task_registry` singleton.
    """

    def create(self, session_id: str, goal: str) -> Task:
        """Create a new Task for a session and persist it."""
        task = Task(
            id         = uuid.uuid4().hex,
            title      = goal[:80],
            session_id = session_id,
            status     = "pending",
        )
        _TASKS[task.id] = task
        _persist()
        log.info("task_model: created task_id=%s session=%s", task.id, session_id)
        return task

    def get(self, task_id: str) -> Optional[Task]:
        return _TASKS.get(task_id)

    def get_by_session(self, session_id: str) -> Optional[Task]:
        """Return the most recently created task for a session."""
        matches = [t for t in _TASKS.values() if t.session_id == session_id]
        if not matches:
            return None
        return max(matches, key=lambda t: t.created_at)

    def update(self, task: Task) -> None:
        """Persist an updated task to disk."""
        _TASKS[task.id] = task
        _persist()

    def list_active(self) -> list[Task]:
        active_statuses = {"pending", "in_progress", "needs_approval", "blocked"}
        return [t for t in _TASKS.values() if t.status in active_statuses]

    def list_all(self) -> list[Task]:
        return list(_TASKS.values())

    def list_by_session(self, session_id: str) -> list[Task]:
        return [t for t in _TASKS.values() if t.session_id == session_id]


# Module-level singleton — import this everywhere
task_registry = TaskRegistry()


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _persist() -> None:
    """
    Write all tasks to disk atomically via tmp-file swap.
    Never raises — persistence failures are non-fatal to CEO execution.
    """
    try:
        os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
        payload = {tid: t.to_dict() for tid, t in _TASKS.items()}
        tmp = _STORE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, _STORE_PATH)
    except Exception as exc:
        log.warning("task_model: persist failed (non-fatal) — %s", exc)


def _load_from_disk() -> None:
    """
    Load persisted tasks on module import.
    Corrupt or missing file is silently ignored.
    """
    try:
        if not os.path.exists(_STORE_PATH):
            return
        with open(_STORE_PATH, encoding="utf-8") as fh:
            raw: dict[str, dict] = json.load(fh)
        for tid, d in raw.items():
            history = [
                TransitionRecord(
                    from_stage = r["from_stage"],
                    to_stage   = r["to_stage"],
                    reason     = r["reason"],
                    brain      = r.get("brain", "ceo"),
                    timestamp  = r.get("timestamp", ""),
                    elapsed_ms = r.get("elapsed_ms", 0.0),
                )
                for r in d.get("history", [])
            ]
            _TASKS[tid] = Task(
                id            = d["id"],
                title         = d["title"],
                session_id    = d["session_id"],
                status        = d.get("status", "unknown"),
                current_stage = d.get("current_stage", "input"),
                retries       = d.get("retries", {}),
                created_at    = d.get("created_at", ""),
                updated_at    = d.get("updated_at", ""),
                final_outcome = d.get("final_outcome"),
                history       = history,
            )
        log.info("task_model: loaded %d tasks from disk", len(_TASKS))
    except Exception as exc:
        log.warning("task_model: load from disk failed (non-fatal) — %s", exc)


# Load persisted tasks immediately at import time
_load_from_disk()
