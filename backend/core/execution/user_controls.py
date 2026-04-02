"""
execution/user_controls.py — User control actions during execution.

Users can influence execution without bypassing CEO.
Every control action routes back through CEO for re-evaluation.

Supported controls:
  pause             — halt execution at next checkpoint
  resume            — continue from current checkpoint
  modify_plan       — submit a plan revision (CEO re-evaluates)
  approve_step      — approve a step that requires user input
  reject_step       — reject a step; triggers replanning or escalation
  request_regen     — request module output regeneration

Rules:
- CEO must re-evaluate after any user modification
- System must not continue blindly after plan change
- All changes go through CEO (no direct module bypass)
- Pause state is stored per session — not global
- Control actions emit user_control events for UI tracking

Control result:
  {
      "control":     str,       # the action taken
      "session_id":  str,
      "status":      str,       # "accepted" | "rejected" | "pending"
      "message":     str,       # human-readable confirmation
      "next_action": str,       # what will happen next
  }
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger("ceo_router.user_controls")

# Per-session pause state: { session_id: bool }
_PAUSED: dict[str, bool] = {}

# Per-session pending modifications: { session_id: dict }
_PENDING_MODS: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Control handlers
# ---------------------------------------------------------------------------

def pause_execution(session_id: str) -> dict[str, Any]:
    """Signal that execution should pause at the next checkpoint."""
    _PAUSED[session_id] = True
    log.info("user_controls: pause requested session=%s", session_id)
    return _result(
        control    = "pause",
        session_id = session_id,
        status     = "accepted",
        message    = "Execution will pause at the next checkpoint.",
        next_action = "Wait for the checkpoint_reached event, then resume or modify.",
    )


def resume_execution(
    session_id:    str,
    checkpoint_id: Optional[str] = None,
    revision:      Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Resume from a paused checkpoint, optionally with a revision."""
    _PAUSED.pop(session_id, None)
    log.info("user_controls: resume requested session=%s checkpoint=%s", session_id, checkpoint_id)

    if checkpoint_id:
        from .checkpoint_manager import resume_from_checkpoint
        cp = resume_from_checkpoint(checkpoint_id, session_id, revision)
        if not cp:
            return _result(
                control     = "resume",
                session_id  = session_id,
                status      = "rejected",
                message     = f"Checkpoint {checkpoint_id} not found.",
                next_action = "Check the checkpoint_id and retry.",
            )

    return _result(
        control     = "resume",
        session_id  = session_id,
        status      = "accepted",
        message     = "Execution resumed." + (" Revision applied." if revision else ""),
        next_action = "Execution continues from the current checkpoint.",
    )


def modify_plan(
    session_id:   str,
    modification: dict[str, Any],
) -> dict[str, Any]:
    """
    Submit a plan modification.
    CEO will re-evaluate before the next step runs.

    modification keys (all optional):
      - message:    str   — revised user message (CEO re-routes)
      - skip_steps: list  — step numbers to skip
      - add_context: dict — extra context to inject
    """
    _PENDING_MODS[session_id] = modification
    log.info("user_controls: plan modified session=%s keys=%s", session_id, list(modification.keys()))
    return _result(
        control     = "modify_plan",
        session_id  = session_id,
        status      = "pending",
        message     = "Plan modification queued. CEO will re-evaluate before next step.",
        next_action = "The system will re-route based on your modification.",
    )


def approve_step(session_id: str, checkpoint_id: str) -> dict[str, Any]:
    """Approve a step that was paused waiting for user input."""
    from .checkpoint_manager import complete_checkpoint, get_pending_checkpoint

    completed = complete_checkpoint(checkpoint_id, session_id)
    if not completed:
        return _result(
            control     = "approve_step",
            session_id  = session_id,
            status      = "rejected",
            message     = f"Checkpoint {checkpoint_id} not found or already completed.",
            next_action = "Check the checkpoint_id and retry.",
        )

    log.info("user_controls: step approved session=%s checkpoint=%s", session_id, checkpoint_id)
    return _result(
        control     = "approve_step",
        session_id  = session_id,
        status      = "accepted",
        message     = "Step approved. Execution continues.",
        next_action = "The next step in the plan will run now.",
    )


def reject_step(session_id: str, checkpoint_id: str, reason: str = "") -> dict[str, Any]:
    """
    Reject a step. Marks checkpoint as skipped; caller handles replanning.
    CEO must re-evaluate — execution does not continue automatically.
    """
    from .checkpoint_manager import get_checkpoints

    for cp in get_checkpoints(session_id):
        if cp["checkpoint_id"] == checkpoint_id:
            cp["status"] = "skipped"
            cp["reject_reason"] = reason
            break

    log.info("user_controls: step rejected session=%s checkpoint=%s reason=%s",
             session_id, checkpoint_id, reason)
    return _result(
        control     = "reject_step",
        session_id  = session_id,
        status      = "accepted",
        message     = f"Step rejected. CEO will replan.{(' Reason: ' + reason) if reason else ''}",
        next_action = "Submit a revised request or wait for CEO to offer alternatives.",
    )


def request_regen(
    session_id: str,
    module:     str,
    feedback:   str = "",
) -> dict[str, Any]:
    """Request that the module regenerates its output."""
    _PENDING_MODS[session_id] = {
        "regen_module": module,
        "regen_feedback": feedback,
    }
    log.info("user_controls: regen requested session=%s module=%s", session_id, module)
    return _result(
        control     = "request_regen",
        session_id  = session_id,
        status      = "pending",
        message     = f"Regeneration queued for {module}." + (f" Feedback: {feedback}" if feedback else ""),
        next_action = "The module will regenerate its output on next execution.",
    )


# ---------------------------------------------------------------------------
# State queries
# ---------------------------------------------------------------------------

def is_paused(session_id: str) -> bool:
    return _PAUSED.get(session_id, False)


def get_pending_modification(session_id: str) -> Optional[dict[str, Any]]:
    return _PENDING_MODS.pop(session_id, None)


def clear_session_controls(session_id: str) -> None:
    """Clear all control state for a session (e.g. on mode change)."""
    _PAUSED.pop(session_id, None)
    _PENDING_MODS.pop(session_id, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(
    control:     str,
    session_id:  str,
    status:      str,
    message:     str,
    next_action: str,
) -> dict[str, Any]:
    return {
        "control":     control,
        "session_id":  session_id,
        "status":      status,
        "message":     message,
        "next_action": next_action,
    }
