"""
memory/session_memory.py — Short-term session state for the CEO pipeline.

Session memory tracks the CURRENT task's state within a single conversation.
It is NOT long-term TR memory — it is cleared on mode change and never persisted.

Contains:
  - current_plan:    the execution plan for the active request
  - current_step:    which step is currently executing
  - user_decisions:  choices made by the user during this session
  - intermediate_outputs: partial results from completed steps

Isolation rules:
  - session memory is keyed by session_id
  - each mode (chat, builder, image) has its own isolated namespace
  - cleared entirely when mode changes — no cross-mode leakage
  - NOT written to disk — in-memory only

Cleared when:
  - mode changes (chat → builder, builder → image, etc.)
  - session ends (explicit clear or TTL expiry)
  - new top-level request resets the session state
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

log = logging.getLogger("ceo_router.session_memory")

# In-memory store: { session_id: { mode: SessionState } }
_STORE: dict[str, dict[str, "SessionState"]] = {}

# Default TTL in seconds (30 minutes)
_DEFAULT_TTL_S = 1800


class SessionState:
    """Mutable short-term state for one (session, mode) pair."""

    def __init__(self, session_id: str, mode: str) -> None:
        self.session_id          = session_id
        self.mode                = mode
        self.current_plan:       list[dict]      = []
        self.current_step:       Optional[str]   = None
        self.user_decisions:     dict[str, Any]  = {}
        self.intermediate_outputs: dict[str, Any] = {}
        self._created_at         = time.time()
        self._updated_at         = time.time()

    def update_plan(self, plan: list[dict]) -> None:
        self.current_plan = plan
        self._touch()

    def set_step(self, step: str) -> None:
        self.current_step = step
        self._touch()

    def record_decision(self, key: str, value: Any) -> None:
        self.user_decisions[key] = value
        self._touch()

    def store_output(self, step: str, output: Any) -> None:
        self.intermediate_outputs[step] = output
        self._touch()

    def is_expired(self, ttl_s: int = _DEFAULT_TTL_S) -> bool:
        return (time.time() - self._updated_at) > ttl_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id":            self.session_id,
            "mode":                  self.mode,
            "current_plan":          self.current_plan,
            "current_step":          self.current_step,
            "user_decisions":        self.user_decisions,
            "intermediate_outputs":  {k: str(v)[:200] for k, v in self.intermediate_outputs.items()},
        }

    def _touch(self) -> None:
        self._updated_at = time.time()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_or_create(session_id: str, mode: str) -> SessionState:
    """Get the session state for (session_id, mode), creating if needed."""
    if session_id not in _STORE:
        _STORE[session_id] = {}
    if mode not in _STORE[session_id]:
        _STORE[session_id][mode] = SessionState(session_id, mode)
        log.debug("session_memory: created state session=%s mode=%s", session_id, mode)
    state = _STORE[session_id][mode]
    if state.is_expired():
        # Reset expired state
        _STORE[session_id][mode] = SessionState(session_id, mode)
        log.debug("session_memory: reset expired state session=%s mode=%s", session_id, mode)
        return _STORE[session_id][mode]
    return state


def get(session_id: str, mode: str) -> Optional[SessionState]:
    """Get session state if it exists, else None."""
    state = _STORE.get(session_id, {}).get(mode)
    if state and state.is_expired():
        clear_mode(session_id, mode)
        return None
    return state


def clear_mode(session_id: str, mode: str) -> None:
    """
    Clear session state for a specific mode.
    Called on mode change — prevents cross-mode contamination.
    """
    if session_id in _STORE and mode in _STORE[session_id]:
        del _STORE[session_id][mode]
        log.debug("session_memory: cleared session=%s mode=%s", session_id, mode)


def clear_session(session_id: str) -> None:
    """Clear all state for a session (session end)."""
    _STORE.pop(session_id, None)
    log.debug("session_memory: cleared all modes session=%s", session_id)


def on_mode_change(session_id: str, old_mode: str, new_mode: str) -> None:
    """
    Called when the user switches mode.
    Clears the old mode's state to prevent contamination.
    new_mode state is created fresh on first access.
    """
    clear_mode(session_id, old_mode)
    log.info("session_memory: mode change session=%s %s → %s", session_id, old_mode, new_mode)


def snapshot(session_id: str, mode: str) -> dict[str, Any]:
    """Return a safe read-only snapshot of the session state."""
    state = get(session_id, mode)
    if state is None:
        return {"session_id": session_id, "mode": mode, "status": "empty"}
    return state.to_dict()
