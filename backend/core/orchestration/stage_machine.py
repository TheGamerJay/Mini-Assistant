"""
orchestration/stage_machine.py — Strict execution stage machine.

Enforces legal stage transitions for every CEO task execution.
CEO calls transition() BEFORE routing to a brain. Invalid transitions raise
InvalidTransitionError — CEO must catch and surface these as fatal errors.

Stage diagram:

  input ──► planning ──► building ──► qa_hands ──► qa_vision ──► done
                             ▲             │              │
                             │             ▼              ▼
                           repair ◄────── (fail)      (fail)
                             │
                             ▼
                           failed  (terminal)

Rules enforced here:
  - CEO must transition through stages in order
  - Skipping from "planning" directly to "qa_hands" is blocked
  - "repair" always returns to "building" (QA is never bypassed after repair)
  - "done" and "failed" are terminal — no further transitions allowed
  - "planning" may return to "input" if clarification is needed
  - Gateway validates which brains are allowed in which stages
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from .task_model import Task, task_registry

log = logging.getLogger("ceo_router.stage_machine")

# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

STAGES: list[str] = [
    "input",
    "planning",
    "building",
    "qa_hands",
    "qa_vision",
    "repair",
    "done",
    "failed",
]

# from_stage → set of valid to_stages
VALID_TRANSITIONS: dict[str, set[str]] = {
    "input":     {"planning", "failed"},
    "planning":  {"building", "input", "failed"},     # "input" = back to clarify
    "building":  {"qa_hands", "repair", "failed"},
    "qa_hands":  {"qa_vision", "building", "repair", "failed"},  # "building" = rebuild with QA hint
    "qa_vision": {"done", "repair", "failed"},
    "repair":    {"building", "failed"},              # always back through QA
    "done":      set(),                               # terminal
    "failed":    set(),                               # terminal
}

# Stage → task status mapping
_STAGE_STATUS_MAP: dict[str, str] = {
    "input":     "in_progress",
    "planning":  "in_progress",
    "building":  "in_progress",
    "qa_hands":  "in_progress",
    "qa_vision": "in_progress",
    "repair":    "needs_approval",
    "done":      "complete",
    "failed":    "failed",
}

# Which brains are legal in which stages
# CEO calling a brain outside its valid stages triggers GatewayViolationError
BRAIN_STAGE_MAP: dict[str, set[str]] = {
    "planner":      {"planning"},
    "builder":      {"building", "repair"},
    "hands":        {"qa_hands"},
    "vision":       {"qa_vision"},
    "doctor":       {"repair"},
    "github_brain": {"input", "planning"},   # pre-planning context injection
}

# Max retries per stage before CEO must escalate or fail
MAX_RETRIES: dict[str, int] = {
    "building":  3,
    "qa_hands":  2,
    "qa_vision": 2,
    "repair":    1,
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class InvalidTransitionError(Exception):
    """
    Raised when CEO attempts a stage transition that is not in VALID_TRANSITIONS.
    CEO must catch this and either resolve or mark the task as failed.
    """
    pass


class GatewayViolationError(Exception):
    """
    Raised when CEO attempts to call a brain from an invalid stage.
    Prevents brain calls that don't make sense for the current task position.
    """
    pass


class RetryLimitExceededError(Exception):
    """
    Raised when a stage has been retried more times than MAX_RETRIES allows.
    CEO should escalate to doctor or mark failed.
    """
    pass


# ---------------------------------------------------------------------------
# Core transition function
# ---------------------------------------------------------------------------

def transition(
    task:       Task,
    new_stage:  str,
    reason:     str,
    brain:      str   = "ceo",
    elapsed_ms: float = 0.0,
) -> None:
    """
    Advance a Task to new_stage.

    Raises InvalidTransitionError if the move is not legal.
    On success: updates task in-place, syncs task.status, persists to disk.

    CEO must call this BEFORE routing to the corresponding brain.
    """
    current = task.current_stage
    allowed = VALID_TRANSITIONS.get(current, set())

    if new_stage not in allowed:
        raise InvalidTransitionError(
            f"Stage machine blocked: {current!r} → {new_stage!r} is not allowed. "
            f"Legal transitions from {current!r}: {sorted(allowed) or '(terminal stage)'}"
        )

    task.record_transition(
        to_stage   = new_stage,
        reason     = reason,
        brain      = brain,
        elapsed_ms = elapsed_ms,
    )

    # Sync task status to match new stage
    new_status = _STAGE_STATUS_MAP.get(new_stage, "in_progress")
    if new_stage == "done":
        task.set_status("complete", outcome="All QA passed — delivered.")
    elif new_stage == "failed":
        task.set_status("failed", outcome=reason)
    elif new_stage == "repair":
        task.set_status("needs_approval", outcome="")
    else:
        if task.status == "pending":
            task.set_status("in_progress")
        # Otherwise preserve existing status (don't downgrade complete → in_progress etc.)

    task_registry.update(task)

    log.info(
        "stage_machine: %s → %s | task=%s brain=%s reason=%.60s",
        current, new_stage, task.id, brain, reason,
    )


# ---------------------------------------------------------------------------
# Gateway: brain call validation
# ---------------------------------------------------------------------------

def validate_brain_call(brain_name: str, task: Task) -> None:
    """
    Validate that brain_name is legal to call from task.current_stage.

    Raises GatewayViolationError if not.
    Called by brain_router.gateway_dispatch() before every brain invocation.

    Unknown brains (not in BRAIN_STAGE_MAP) are allowed — future extension point.
    """
    allowed_stages = BRAIN_STAGE_MAP.get(brain_name)
    if allowed_stages is None:
        return  # unknown brain — pass through

    if task.current_stage not in allowed_stages:
        raise GatewayViolationError(
            f"Gateway blocked: brain={brain_name!r} cannot be called from "
            f"stage={task.current_stage!r}. "
            f"Valid stages for {brain_name!r}: {sorted(allowed_stages)}"
        )


def check_retry_limit(task: Task, stage: str) -> None:
    """
    Raise RetryLimitExceededError if this stage has hit its max retry count.
    CEO calls this before incrementing retry and re-entering the same stage.
    """
    limit   = MAX_RETRIES.get(stage)
    current = task.get_retry(stage)
    if limit is not None and current >= limit:
        raise RetryLimitExceededError(
            f"Stage {stage!r} has reached max retries ({limit}). "
            f"CEO must escalate to doctor or mark task failed."
        )


# ---------------------------------------------------------------------------
# Read-only helpers (no side effects)
# ---------------------------------------------------------------------------

def can_transition(task: Task, new_stage: str) -> bool:
    """Return True if the transition is valid — no side effects."""
    return new_stage in VALID_TRANSITIONS.get(task.current_stage, set())


def is_terminal(task: Task) -> bool:
    """Return True if the task is in a terminal stage (done or failed)."""
    return task.current_stage in {"done", "failed"}


def stage_info(task: Task) -> dict:
    """Return a loggable dict of the task's current stage position."""
    return {
        "task_id":       task.id,
        "current_stage": task.current_stage,
        "status":        task.status,
        "retries":       task.retries,
        "history_len":   len(task.history),
        "valid_next":    sorted(VALID_TRANSITIONS.get(task.current_stage, set())),
    }
