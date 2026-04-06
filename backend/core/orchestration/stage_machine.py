"""
orchestration/stage_machine.py — Strict execution stage machine.

Enforces legal stage transitions for every CEO task execution.
CEO calls transition() BEFORE routing to a brain.

VIOLATION POLICY:
  HARD_FAIL — pipeline must stop, task marked failed, audit record emitted
    - Any transition from a terminal stage (done/failed → anything)
    - Any QA-bypass (building → done, planning → qa_hands, etc.)
    - Any brain called from the wrong stage (GatewayViolationError)
    - Any risky action attempted without approval
  SOFT_WARN — log warning, continue execution
    - Re-entry to a stage already visited (e.g. already in planning)
    - Unknown future stages (forward compatibility)
    - Telemetry/audit write failures

Stage diagram:

  input
    │
    ├──► context_ingestion  (github scan, file scan, web prefetch)
    │         │
    │         ▼
    └──────► planning ──► building ──► qa_hands ──► qa_vision
                              ▲            │               │
                              │            ▼               ▼
                           repair ◄─── (fail)          finalize
                              │                            │
                              ▼                            ▼
                           failed (terminal)             done (terminal)

Rules:
  - CEO transitions BEFORE routing to a brain
  - context_ingestion is the ONLY valid stage for github_brain / file scanners
  - finalize is where response is assembled — no brain can be called there
  - "done" and "failed" are terminal: no further transitions
  - "repair" always returns to "building" — QA is never skipped after repair
  - All hard-fail violations emit a structured AuditRecord before raising
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from .task_model import Task, task_registry

log = logging.getLogger("ceo_router.stage_machine")

# ---------------------------------------------------------------------------
# Audit store path
# ---------------------------------------------------------------------------

_AUDIT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "memory_store", "audit.json")
)

_AUDIT_LOG: list["AuditRecord"] = []


# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

STAGES: list[str] = [
    "input",
    "context_ingestion",   # github scan, file scan, web prefetch — before planning
    "planning",
    "building",
    "qa_hands",
    "qa_vision",
    "finalize",            # assemble response, generate summary — no brain active
    "repair",
    "done",                # terminal
    "failed",              # terminal
]

# Which brains are legal in which stages.
# Brains not listed here are UNKNOWN → allowed (future extension point).
# Brains listed here are ENFORCED — calling them from any other stage is a hard-fail.
BRAIN_STAGE_MAP: dict[str, set[str]] = {
    "planner":      {"planning"},
    "builder":      {"building", "repair"},
    "hands":        {"qa_hands"},
    "vision":       {"qa_vision"},
    "doctor":       {"repair"},
    "github_brain": {"context_ingestion"},   # ONLY valid in context_ingestion stage
    "file_scanner": {"context_ingestion"},
    "web_prefetch": {"context_ingestion"},
}

# Stage → task status
_STAGE_STATUS_MAP: dict[str, str] = {
    "input":             "in_progress",
    "context_ingestion": "in_progress",
    "planning":          "in_progress",
    "building":          "in_progress",
    "qa_hands":          "in_progress",
    "qa_vision":         "in_progress",
    "finalize":          "in_progress",
    "repair":            "needs_approval",
    "done":              "complete",
    "failed":            "failed",
}

# from_stage → allowed to_stages
VALID_TRANSITIONS: dict[str, set[str]] = {
    "input":             {"context_ingestion", "planning", "failed"},
    "context_ingestion": {"planning", "failed"},
    "planning":          {"building", "input", "failed"},    # "input" = needs clarification
    "building":          {"qa_hands", "repair", "failed"},
    "qa_hands":          {"qa_vision", "building", "repair", "failed"},
    "qa_vision":         {"finalize", "repair", "failed"},
    "finalize":          {"done", "failed"},
    "repair":            {"building", "failed"},
    "done":              set(),   # terminal
    "failed":            set(),   # terminal
}

# Max retries per stage
MAX_RETRIES: dict[str, int] = {
    "building":  3,
    "qa_hands":  2,
    "qa_vision": 2,
    "repair":    1,
}

# ---------------------------------------------------------------------------
# Violation severity policy
# ---------------------------------------------------------------------------

class ViolationSeverity(Enum):
    HARD_FAIL = "HARD_FAIL"   # pipeline must stop
    SOFT_WARN = "SOFT_WARN"   # log and continue

# (from_stage, to_stage) pairs that are ALWAYS hard-fail regardless of context.
# Anything not in VALID_TRANSITIONS that isn't in the soft whitelist is also hard-fail.
_HARD_FAIL_PAIRS: frozenset[tuple[str, str]] = frozenset({
    # Terminal → anything: absolutely forbidden
    ("done",   "input"),
    ("done",   "context_ingestion"),
    ("done",   "planning"),
    ("done",   "building"),
    ("done",   "qa_hands"),
    ("done",   "qa_vision"),
    ("done",   "finalize"),
    ("done",   "repair"),
    ("failed", "input"),
    ("failed", "context_ingestion"),
    ("failed", "planning"),
    ("failed", "building"),
    ("failed", "qa_hands"),
    ("failed", "qa_vision"),
    ("failed", "finalize"),
    ("failed", "repair"),
    # QA bypass — these skip required verification stages
    ("building",   "done"),
    ("building",   "qa_vision"),
    ("building",   "finalize"),
    ("planning",   "qa_hands"),
    ("planning",   "qa_vision"),
    ("planning",   "finalize"),
    ("planning",   "done"),
    ("input",      "qa_hands"),
    ("input",      "qa_vision"),
    ("input",      "done"),
    ("input",      "finalize"),
    # Context injection must come before planning
    ("qa_hands",   "context_ingestion"),
    ("qa_vision",  "context_ingestion"),
    ("building",   "context_ingestion"),
    ("repair",     "context_ingestion"),
    ("finalize",   "context_ingestion"),
})

# Transitions that are NOT in VALID_TRANSITIONS but are soft (re-entry, compat)
_SOFT_WARN_PAIRS: frozenset[tuple[str, str]] = frozenset({
    # Same-stage re-entry (e.g. planning → planning on re-entry)
    ("planning",   "planning"),
    ("building",   "building"),
    ("qa_hands",   "qa_hands"),
    ("qa_vision",  "qa_vision"),
    ("finalize",   "finalize"),
})


def get_violation_severity(from_stage: str, to_stage: str) -> ViolationSeverity:
    """
    Return HARD_FAIL or SOFT_WARN for an invalid transition.

    HARD_FAIL: terminal violations, QA-bypass, context injection out of order.
    SOFT_WARN: same-stage re-entry, unknown stage names.
    """
    pair = (from_stage, to_stage)
    if pair in _HARD_FAIL_PAIRS:
        return ViolationSeverity.HARD_FAIL
    if pair in _SOFT_WARN_PAIRS:
        return ViolationSeverity.SOFT_WARN
    # Unknown transition not in either list: hard-fail by default
    return ViolationSeverity.HARD_FAIL


def is_hard_violation(from_stage: str, to_stage: str) -> bool:
    """Return True if this invalid transition is a hard-fail."""
    return get_violation_severity(from_stage, to_stage) == ViolationSeverity.HARD_FAIL


# ---------------------------------------------------------------------------
# Audit record
# ---------------------------------------------------------------------------

@dataclass
class AuditRecord:
    """
    Structured record of every hard-fail or soft-warn violation.
    Emitted before raising — gives CEO full context for structured error responses.
    """
    task_id:         str
    session_id:      str
    current_stage:   str              # stage the task was in when violation occurred
    attempted_stage: str              # stage/brain that was blocked
    violating_brain: str              # "ceo" or brain name
    violation_type:  str              # "HARD_FAIL" | "SOFT_WARN"
    violation_class: str              # "invalid_transition" | "gateway_violation" | "retry_exceeded"
    reason:          str
    timestamp:       str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id":         self.task_id,
            "session_id":      self.session_id,
            "current_stage":   self.current_stage,
            "attempted_stage": self.attempted_stage,
            "violating_brain": self.violating_brain,
            "violation_type":  self.violation_type,
            "violation_class": self.violation_class,
            "reason":          self.reason,
            "timestamp":       self.timestamp,
        }


def emit_audit(
    task:            Task,
    attempted_stage: str,
    violating_brain: str,
    violation_type:  ViolationSeverity,
    violation_class: str,
    reason:          str,
) -> AuditRecord:
    """
    Create, store, and persist an AuditRecord.
    Always returns the record — never raises (audit failures are non-fatal).
    """
    rec = AuditRecord(
        task_id         = task.id,
        session_id      = task.session_id,
        current_stage   = task.current_stage,
        attempted_stage = attempted_stage,
        violating_brain = violating_brain,
        violation_type  = violation_type.value,
        violation_class = violation_class,
        reason          = reason,
    )
    _AUDIT_LOG.append(rec)
    _persist_audit()

    if violation_type == ViolationSeverity.HARD_FAIL:
        log.error(
            "AUDIT HARD_FAIL: task=%s stage=%s → %s brain=%s | %s",
            task.id, task.current_stage, attempted_stage, violating_brain, reason[:120],
        )
    else:
        log.warning(
            "AUDIT SOFT_WARN: task=%s stage=%s → %s brain=%s | %s",
            task.id, task.current_stage, attempted_stage, violating_brain, reason[:120],
        )

    return rec


def get_audit_log(task_id: Optional[str] = None) -> list[dict]:
    """Return all audit records, optionally filtered by task_id."""
    records = _AUDIT_LOG if task_id is None else [r for r in _AUDIT_LOG if r.task_id == task_id]
    return [r.to_dict() for r in records]


def _persist_audit() -> None:
    """Write audit log to disk atomically. Non-fatal on error."""
    try:
        os.makedirs(os.path.dirname(_AUDIT_PATH), exist_ok=True)
        payload = [r.to_dict() for r in _AUDIT_LOG[-500:]]  # keep last 500
        tmp = _AUDIT_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, _AUDIT_PATH)
    except Exception:
        pass  # audit persistence never crashes CEO


def _load_audit() -> None:
    """Load persisted audit log on import."""
    try:
        if not os.path.exists(_AUDIT_PATH):
            return
        with open(_AUDIT_PATH, encoding="utf-8") as fh:
            raw: list[dict] = json.load(fh)
        for d in raw:
            _AUDIT_LOG.append(AuditRecord(
                task_id         = d.get("task_id", ""),
                session_id      = d.get("session_id", ""),
                current_stage   = d.get("current_stage", ""),
                attempted_stage = d.get("attempted_stage", ""),
                violating_brain = d.get("violating_brain", ""),
                violation_type  = d.get("violation_type", "HARD_FAIL"),
                violation_class = d.get("violation_class", "unknown"),
                reason          = d.get("reason", ""),
                timestamp       = d.get("timestamp", ""),
            ))
    except Exception:
        pass


_load_audit()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class InvalidTransitionError(Exception):
    """
    Raised when CEO attempts a stage transition not in VALID_TRANSITIONS.
    Always carries severity. CEO must check severity before deciding to
    abort or continue.
    """
    def __init__(self, msg: str, severity: ViolationSeverity, audit: Optional[AuditRecord] = None):
        super().__init__(msg)
        self.severity = severity
        self.audit    = audit


class GatewayViolationError(Exception):
    """
    Raised when CEO attempts to call a brain from the wrong stage.
    Always hard-fail — pipeline must stop.
    """
    def __init__(self, msg: str, audit: Optional[AuditRecord] = None):
        super().__init__(msg)
        self.severity = ViolationSeverity.HARD_FAIL
        self.audit    = audit


class RetryLimitExceededError(Exception):
    """
    Raised when a stage hits MAX_RETRIES.
    Hard-fail — CEO must escalate to doctor or mark task failed.
    """
    def __init__(self, msg: str, audit: Optional[AuditRecord] = None):
        super().__init__(msg)
        self.severity = ViolationSeverity.HARD_FAIL
        self.audit    = audit


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

    If the transition is invalid:
      - Emits an AuditRecord (always)
      - Raises InvalidTransitionError with .severity = HARD_FAIL or SOFT_WARN

    CEO must check exc.severity:
      HARD_FAIL → mark task failed, return error response (do NOT continue)
      SOFT_WARN → log, continue (transition is skipped, task stays at current stage)

    On success: updates task, syncs status, persists to disk.
    """
    current = task.current_stage
    allowed = VALID_TRANSITIONS.get(current, set())

    if new_stage not in allowed:
        severity = get_violation_severity(current, new_stage)
        audit    = emit_audit(
            task            = task,
            attempted_stage = new_stage,
            violating_brain = brain,
            violation_type  = severity,
            violation_class = "invalid_transition",
            reason          = (
                f"Stage machine blocked: {current!r} → {new_stage!r}. "
                f"Legal from {current!r}: {sorted(allowed) or '(terminal)'}"
            ),
        )
        raise InvalidTransitionError(str(audit.reason), severity=severity, audit=audit)

    # Transition is valid — apply it
    task.record_transition(
        to_stage   = new_stage,
        reason     = reason,
        brain      = brain,
        elapsed_ms = elapsed_ms,
    )

    # Sync task status to new stage
    if new_stage == "done":
        task.set_status("complete", outcome="All QA passed — delivered.")
    elif new_stage == "failed":
        task.set_status("failed", outcome=reason)
    elif new_stage == "repair":
        task.set_status("needs_approval", outcome="")
    elif task.status == "pending":
        task.set_status("in_progress")

    task_registry.update(task)

    log.info(
        "stage_machine: %s → %s | task=%s brain=%s",
        current, new_stage, task.id, brain,
    )


# ---------------------------------------------------------------------------
# Gateway: brain call validation
# ---------------------------------------------------------------------------

def validate_brain_call(brain_name: str, task: Task) -> None:
    """
    Validate that brain_name is legal for task.current_stage.

    Raises GatewayViolationError (always HARD_FAIL) if the call is illegal.
    Emits AuditRecord before raising.

    Brains not in BRAIN_STAGE_MAP are unknown → allowed (forward compat).
    """
    allowed_stages = BRAIN_STAGE_MAP.get(brain_name)
    if allowed_stages is None:
        return  # unknown brain — pass through (future extension point)

    if task.current_stage not in allowed_stages:
        audit = emit_audit(
            task            = task,
            attempted_stage = f"brain:{brain_name}",
            violating_brain = brain_name,
            violation_type  = ViolationSeverity.HARD_FAIL,
            violation_class = "gateway_violation",
            reason          = (
                f"Gateway blocked: brain={brain_name!r} called from "
                f"stage={task.current_stage!r}. "
                f"Valid stages for {brain_name!r}: {sorted(allowed_stages)}"
            ),
        )
        raise GatewayViolationError(str(audit.reason), audit=audit)


# ---------------------------------------------------------------------------
# Retry limit check
# ---------------------------------------------------------------------------

def check_retry_limit(task: Task, stage: str) -> None:
    """
    Raise RetryLimitExceededError if this stage has hit MAX_RETRIES.
    Emits AuditRecord before raising.
    """
    limit   = MAX_RETRIES.get(stage)
    current = task.get_retry(stage)
    if limit is not None and current >= limit:
        audit = emit_audit(
            task            = task,
            attempted_stage = stage,
            violating_brain = "ceo",
            violation_type  = ViolationSeverity.HARD_FAIL,
            violation_class = "retry_exceeded",
            reason          = (
                f"Stage {stage!r} hit max retries ({limit}). "
                f"CEO must escalate to doctor or mark task failed."
            ),
        )
        raise RetryLimitExceededError(str(audit.reason), audit=audit)


# ---------------------------------------------------------------------------
# Read-only helpers (no side effects)
# ---------------------------------------------------------------------------

def can_transition(task: Task, new_stage: str) -> bool:
    """Return True if the transition is valid — no side effects, no exceptions."""
    return new_stage in VALID_TRANSITIONS.get(task.current_stage, set())


def is_terminal(task: Task) -> bool:
    """Return True if the task is in a terminal stage."""
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
