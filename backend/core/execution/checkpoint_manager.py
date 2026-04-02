"""
execution/checkpoint_manager.py — Checkpoint system for pausable execution.

Checkpoints are real markers that reflect actual execution steps.
They allow the UI to show progress, allow users to pause/review, and allow
the system to resume from a known good state.

Checkpoint types (in execution order):
  pre_execution    — before any step runs (plan review)
  post_plan        — after execution plan is built, before any step runs
  post_module      — after module_call completes, before validation
  pre_validation   — before validation step runs
  post_validation  — after validation completes (final checkpoint)

Checkpoint structure:
  {
      "checkpoint_id":       str,     # unique: "{session_id}_{type}_{step}"
      "type":                str,     # checkpoint type (see above)
      "step":                str,     # human-readable step name
      "status":              str,     # "pending" | "completed" | "skipped"
      "summary":             str,     # what happened at this checkpoint
      "requires_user_input": bool,    # if True, execution pauses here
      "data":                dict,    # payload (plan, module output, validation, etc.)
      "timestamp":           str,     # ISO 8601 UTC
  }

Rules:
- checkpoints must reflect real execution steps — never invented
- a checkpoint with requires_user_input=True pauses execution
- paused checkpoints can be resumed or revised
- each session has its own checkpoint stack — no cross-session leakage
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Optional

log = logging.getLogger("ceo_router.checkpoint_manager")

# In-memory checkpoint store — keyed by session_id
# Format: { session_id: [ checkpoint_dict, ... ] }
_CHECKPOINTS: dict[str, list[dict[str, Any]]] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_checkpoint(
    session_id:          str,
    checkpoint_type:     str,
    step:                str,
    summary:             str,
    data:                Optional[dict[str, Any]] = None,
    requires_user_input: bool = False,
) -> dict[str, Any]:
    """
    Create and store a checkpoint for the given session.
    Returns the checkpoint dict.
    """
    checkpoint_id = f"{session_id}_{checkpoint_type}_{uuid.uuid4().hex[:8]}"
    checkpoint = {
        "checkpoint_id":       checkpoint_id,
        "type":                checkpoint_type,
        "step":                step,
        "status":              "pending",
        "summary":             summary,
        "requires_user_input": requires_user_input,
        "data":                data or {},
        "timestamp":           _now_iso(),
    }
    if session_id not in _CHECKPOINTS:
        _CHECKPOINTS[session_id] = []
    _CHECKPOINTS[session_id].append(checkpoint)
    log.debug(
        "checkpoint: created type=%s step=%s requires_input=%s id=%s",
        checkpoint_type, step, requires_user_input, checkpoint_id,
    )
    return checkpoint


def complete_checkpoint(checkpoint_id: str, session_id: str) -> bool:
    """Mark a checkpoint as completed. Returns True if found."""
    for cp in _CHECKPOINTS.get(session_id, []):
        if cp["checkpoint_id"] == checkpoint_id:
            cp["status"] = "completed"
            log.debug("checkpoint: completed id=%s", checkpoint_id)
            return True
    return False


def get_checkpoints(session_id: str) -> list[dict[str, Any]]:
    """Return all checkpoints for a session in order."""
    return list(_CHECKPOINTS.get(session_id, []))


def get_pending_checkpoint(session_id: str) -> Optional[dict[str, Any]]:
    """
    Return the first pending checkpoint that requires user input, if any.
    This is the gate — if one exists, execution must pause.
    """
    for cp in _CHECKPOINTS.get(session_id, []):
        if cp["status"] == "pending" and cp["requires_user_input"]:
            return cp
    return None


def clear_checkpoints(session_id: str) -> None:
    """Clear all checkpoints for a session (e.g. on mode change)."""
    _CHECKPOINTS.pop(session_id, None)
    log.debug("checkpoint: cleared session=%s", session_id)


def resume_from_checkpoint(
    checkpoint_id: str,
    session_id:    str,
    revision:      Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """
    Resume from a paused checkpoint.
    If revision is provided, it replaces the checkpoint's data before completing.
    Returns the checkpoint dict, or None if not found.
    """
    for cp in _CHECKPOINTS.get(session_id, []):
        if cp["checkpoint_id"] == checkpoint_id:
            if revision:
                cp["data"].update(revision)
                log.debug("checkpoint: revised id=%s keys=%s", checkpoint_id, list(revision.keys()))
            cp["status"] = "completed"
            log.debug("checkpoint: resumed id=%s", checkpoint_id)
            return cp
    log.warning("checkpoint: resume failed — id=%s not found in session=%s", checkpoint_id, session_id)
    return None


# ---------------------------------------------------------------------------
# Checkpoint builders for standard execution phases
# ---------------------------------------------------------------------------

def checkpoint_pre_execution(session_id: str, plan_steps: list[dict]) -> dict[str, Any]:
    return create_checkpoint(
        session_id      = session_id,
        checkpoint_type = "pre_execution",
        step            = "before_execution",
        summary         = f"Ready to execute {len(plan_steps)} step(s). Review the plan.",
        data            = {"plan": plan_steps},
        requires_user_input = False,
    )


def checkpoint_post_plan(
    session_id: str,
    module:     str,
    plan_steps: list[dict],
    complexity: str,
) -> dict[str, Any]:
    """
    Requires user input for full_system complexity — user reviews plan before build starts.
    """
    requires = complexity == "full_system"
    return create_checkpoint(
        session_id      = session_id,
        checkpoint_type = "post_plan",
        step            = "plan_review",
        summary         = (
            f"Execution plan built for {module} ({len(plan_steps)} step(s)). "
            + ("Review and confirm before execution begins." if requires else "Proceeding automatically.")
        ),
        data            = {"module": module, "plan": plan_steps, "complexity": complexity},
        requires_user_input = requires,
    )


def checkpoint_post_module(
    session_id: str,
    module:     str,
    result:     dict[str, Any],
) -> dict[str, Any]:
    # Summarize without dumping full output
    summary_keys = [k for k in result if not k.startswith("_")]
    return create_checkpoint(
        session_id      = session_id,
        checkpoint_type = "post_module",
        step            = f"after_{module}",
        summary         = f"{module} completed. Keys: {', '.join(summary_keys[:5])}",
        data            = {"module": module, "output_keys": summary_keys},
        requires_user_input = False,
    )


def checkpoint_pre_validation(
    session_id:      str,
    module:          str,
    validation_type: str,
) -> dict[str, Any]:
    return create_checkpoint(
        session_id      = session_id,
        checkpoint_type = "pre_validation",
        step            = "before_validation",
        summary         = f"Validating {module} output using {validation_type} rules.",
        data            = {"module": module, "validation_type": validation_type},
        requires_user_input = False,
    )


def checkpoint_post_validation(
    session_id:  str,
    module:      str,
    val_result:  dict[str, Any],
) -> dict[str, Any]:
    ok     = val_result.get("ok", True)
    issues = val_result.get("issues", [])
    return create_checkpoint(
        session_id      = session_id,
        checkpoint_type = "post_validation",
        step            = "after_validation",
        summary         = (
            f"Validation {'passed' if ok else 'failed'} for {module}."
            + (f" Issues: {'; '.join(issues[:2])}" if issues else "")
        ),
        data            = {"module": module, "validation": val_result},
        requires_user_input = not ok,  # pause on validation failure for user review
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
