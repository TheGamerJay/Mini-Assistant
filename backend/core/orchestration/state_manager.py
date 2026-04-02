"""
orchestration/state_manager.py — CEO orchestration state tracker.

Tracks the full state of a multi-brain execution session.
State is per session_id, in-memory only (not persisted to disk).

CEO uses this to:
  - know what has been done
  - prevent infinite loops (retry_count limits)
  - track evidence from each brain
  - know when approval is pending
  - build the X-Ray report

State fields:
  user_goal         — original user request
  current_step      — what is currently running
  completed_steps   — list of completed steps with results
  failed_steps      — list of failed steps with reasons
  active_brain      — which brain is currently tasked
  retry_count       — per-brain retry attempts (resets per brain)
  approval_status   — "none" | "pending" | "approved" | "rejected"
  waiting_for_input — bool: is CEO waiting for user input
  evidence_history  — all brain results in order (for X-Ray)
  repair_memory_used — whether repair memory was consulted
  start_time        — when orchestration started
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class StepRecord:
    """Record of a single brain execution step."""
    step_num:    int
    brain:       str
    action:      str
    status:      str            # success | fail | needs_approval | needs_input
    summary:     str
    confidence:  float
    evidence:    list[Any]
    elapsed_ms:  float
    reason:      str = ""       # why CEO routed here
    proposed_fix: str = ""


@dataclass
class OrchestrationState:
    """Full state for one multi-brain CEO orchestration session."""
    session_id:       str
    user_goal:        str
    complexity:       str       # simple | multi_step | full_system

    # Step tracking
    current_step:     str                   = "init"
    completed_steps:  list[StepRecord]      = field(default_factory=list)
    failed_steps:     list[StepRecord]      = field(default_factory=list)

    # Brain tracking
    active_brain:     Optional[str]         = None
    retry_counts:     dict[str, int]        = field(default_factory=dict)  # brain → retries

    # Approval tracking
    approval_status:  str                   = "none"   # none | pending | approved | rejected
    pending_approval: Optional[dict]        = None
    approval_history: list[dict]            = field(default_factory=list)

    # User input
    waiting_for_input: bool                 = False
    clarification_needed: Optional[str]    = None

    # Evidence archive (for X-Ray)
    evidence_history:  list[StepRecord]    = field(default_factory=list)

    # Repair memory
    repair_memory_used:      bool          = False
    repair_memory_matches:   list[dict]    = field(default_factory=list)
    repair_memory_guidance:  Optional[str] = None

    # Final result
    final_status:     str                   = "in_progress"   # in_progress | complete | failed | needs_approval
    final_result:     Optional[dict]        = None

    # Timing
    start_time:       float                 = field(default_factory=time.perf_counter)
    end_time:         Optional[float]       = None

    # Step counter
    _step_counter:    int                   = 0

    def next_step_num(self) -> int:
        self._step_counter += 1
        return self._step_counter

    def record_step(self, record: StepRecord) -> None:
        """Record any brain result to both history and appropriate list."""
        self.evidence_history.append(record)
        if record.status in ("success", "needs_approval", "needs_input"):
            self.completed_steps.append(record)
        else:
            self.failed_steps.append(record)

    def increment_retry(self, brain: str) -> int:
        """Increment and return the retry count for a brain."""
        self.retry_counts[brain] = self.retry_counts.get(brain, 0) + 1
        return self.retry_counts[brain]

    def get_retry(self, brain: str) -> int:
        return self.retry_counts.get(brain, 0)

    def set_approval_pending(self, proposal: dict) -> None:
        self.approval_status   = "pending"
        self.pending_approval  = proposal
        self.waiting_for_input = True
        self.approval_history.append({"status": "requested", **proposal})

    def resolve_approval(self, approved: bool, feedback: str = "") -> None:
        if self.pending_approval:
            self.approval_history[-1]["resolved"] = "approved" if approved else "rejected"
            self.approval_history[-1]["feedback"] = feedback
        self.approval_status   = "approved" if approved else "rejected"
        self.pending_approval  = None
        self.waiting_for_input = False

    def elapsed_ms(self) -> float:
        t = self.end_time or time.perf_counter()
        return round((t - self.start_time) * 1000, 1)

    def brains_used(self) -> list[str]:
        seen: list[str] = []
        for r in self.evidence_history:
            if r.brain not in seen:
                seen.append(r.brain)
        return seen

    def to_dict(self) -> dict:
        return {
            "session_id":          self.session_id,
            "user_goal":           self.user_goal,
            "complexity":          self.complexity,
            "current_step":        self.current_step,
            "active_brain":        self.active_brain,
            "retry_counts":        self.retry_counts,
            "approval_status":     self.approval_status,
            "waiting_for_input":   self.waiting_for_input,
            "final_status":        self.final_status,
            "elapsed_ms":          self.elapsed_ms(),
            "brains_used":         self.brains_used(),
            "steps_completed":     len(self.completed_steps),
            "steps_failed":        len(self.failed_steps),
            "repair_memory_used":  self.repair_memory_used,
        }


# ---------------------------------------------------------------------------
# Session store
# ---------------------------------------------------------------------------

_STATES: dict[str, OrchestrationState] = {}


def create(session_id: str, user_goal: str, complexity: str) -> OrchestrationState:
    """Create and store a new orchestration state for a session."""
    state = OrchestrationState(
        session_id = session_id,
        user_goal  = user_goal,
        complexity = complexity,
    )
    _STATES[session_id] = state
    return state


def get(session_id: str) -> Optional[OrchestrationState]:
    return _STATES.get(session_id)


def get_or_create(session_id: str, user_goal: str, complexity: str) -> OrchestrationState:
    if session_id in _STATES:
        return _STATES[session_id]
    return create(session_id, user_goal, complexity)


def clear(session_id: str) -> None:
    _STATES.pop(session_id, None)


def list_sessions() -> list[str]:
    """Return all active session IDs."""
    return list(_STATES.keys())
