"""
api/xray_endpoint.py — X-Ray mode endpoint for admin/dev transparency.

X-Ray exposes the full CEO decision pipeline — every event, every decision,
every validation result — in one structured response.

Visibility:
  - User UI: event "summary" fields only (simplified)
  - X-Ray (admin/dev): full "detail" fields included

Endpoints:
  GET /api/ceo/xray/{session_id}   — full X-Ray dump for a session
  GET /api/ceo/events/{session_id} — events timeline (summary only, for UI)

X-Ray response:
  {
      "session_id":   str,
      "decision":     RouterDecision.to_dict(),
      "execution_plan": [...],
      "events":       [ full event dict with detail ],
      "checkpoints":  [...],
      "retrieval":    { retrieval_used, sources, selected_context },
      "validation":   { ok, issues, validation_type },
      "session_state": { current_plan, current_step, user_decisions },
      "elapsed_ms":   float,
  }

Rules:
  - X-Ray endpoint requires admin auth (checked via header)
  - UI events endpoint returns summary-only (no detail payloads)
  - X-Ray data is never shown to end users by default
"""

from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("ceo_router.xray")

_XRAY_SESSIONS: dict[str, dict] = {}  # session_id → last full result


def store_xray_data(session_id: str, data: dict) -> None:
    """Called by chat_endpoint after each execution to persist X-Ray data."""
    _XRAY_SESSIONS[session_id] = data
    log.debug("xray: stored session=%s keys=%s", session_id, list(data.keys()))


def get_xray_data(session_id: str) -> Optional[dict]:
    return _XRAY_SESSIONS.get(session_id)


try:
    from fastapi import APIRouter, HTTPException, Header
    from typing import Optional as Opt

    router = APIRouter(prefix="/api/ceo", tags=["ceo-xray"])

    def _require_admin(x_admin_key: str = Header(default="")) -> None:
        """Basic admin key check. Replace with real auth in production."""
        import os
        expected = os.getenv("ADMIN_XRAY_KEY", "")
        if expected and x_admin_key != expected:
            raise HTTPException(status_code=403, detail="X-Ray requires admin key")

    @router.get("/xray/{session_id}")
    async def xray_session(
        session_id:  str,
        x_admin_key: str = Header(default=""),
    ):
        """
        Full X-Ray dump for a session — admin only.
        Returns all CEO decisions, events (with detail), checkpoints, and validation.
        """
        _require_admin(x_admin_key)

        data = get_xray_data(session_id)
        if data is None:
            raise HTTPException(status_code=404, detail=f"No X-Ray data for session '{session_id}'")

        # Include full event detail in X-Ray response
        return {
            "session_id":    session_id,
            "xray_mode":     True,
            **data,
        }

    @router.get("/events/{session_id}")
    async def events_timeline(session_id: str):
        """
        Events timeline for a session — user-safe (summary only, no detail).
        Used by the UI to show progress without exposing internal data.
        """
        data = get_xray_data(session_id)
        if data is None:
            raise HTTPException(status_code=404, detail=f"No events for session '{session_id}'")

        # Strip detail from events — return summary only
        events = data.get("events", [])
        user_events = [
            {
                "event_type": e.get("event_type"),
                "module":     e.get("module"),
                "status":     e.get("status"),
                "summary":    e.get("summary"),
                "timestamp":  e.get("timestamp"),
                "session_id": e.get("session_id"),
                # "detail" intentionally omitted
            }
            for e in events
        ]

        return {
            "session_id": session_id,
            "xray_mode":  False,
            "events":     user_events,
        }

    @router.get("/checkpoints/{session_id}")
    async def session_checkpoints(session_id: str):
        """Return checkpoints for a session — used by UI for progress display."""
        from ..execution.checkpoint_manager import get_checkpoints
        checkpoints = get_checkpoints(session_id)
        if not checkpoints:
            raise HTTPException(status_code=404, detail=f"No checkpoints for session '{session_id}'")
        return {"session_id": session_id, "checkpoints": checkpoints}

    @router.post("/controls/{session_id}/pause")
    async def pause_session(session_id: str):
        """Pause execution for a session."""
        from ..execution.user_controls import pause_execution
        import core.events.event_emitter as _ev
        result = pause_execution(session_id)
        _ev.user_control(session_id, "pause")
        return result

    @router.post("/controls/{session_id}/resume")
    async def resume_session(session_id: str, checkpoint_id: Opt[str] = None):
        """Resume execution for a session, optionally from a specific checkpoint."""
        from ..execution.user_controls import resume_execution
        import core.events.event_emitter as _ev
        result = resume_execution(session_id, checkpoint_id)
        _ev.user_control(session_id, "resume", {"checkpoint_id": checkpoint_id})
        return result

    @router.post("/controls/{session_id}/approve/{checkpoint_id}")
    async def approve_checkpoint(session_id: str, checkpoint_id: str):
        """Approve a paused checkpoint step."""
        from ..execution.user_controls import approve_step
        import core.events.event_emitter as _ev
        result = approve_step(session_id, checkpoint_id)
        _ev.user_control(session_id, "approve_step", {"checkpoint_id": checkpoint_id})
        return result

    @router.post("/controls/{session_id}/reject/{checkpoint_id}")
    async def reject_checkpoint(session_id: str, checkpoint_id: str, reason: str = ""):
        """Reject a paused checkpoint step."""
        from ..execution.user_controls import reject_step
        import core.events.event_emitter as _ev
        result = reject_step(session_id, checkpoint_id, reason)
        _ev.user_control(session_id, "reject_step", {"checkpoint_id": checkpoint_id, "reason": reason})
        return result

except ImportError:
    router = None
    log.warning("api/xray_endpoint: FastAPI not available — endpoint not registered")
