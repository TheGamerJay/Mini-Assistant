"""
manager.py — Manager Layer
───────────────────────────
Operational coordination between the CEO and the Planner.

Responsibilities:
  1. Receive incoming request (message, history, session_id)
  2. Maintain lightweight in-memory session state per session_id
  3. Inject relevant context (recent intent trail, active topic, project summary)
  4. Normalize the request (trim, resolve common abbreviations)
  5. Produce a structured ManagerPacket for the Supervisor

The Manager does NOT do deep reasoning.
The Manager does NOT execute tasks.
The Manager ensures continuity and context richness across turns.

Session state is in-memory for Phase 2 (full persistence in Phase 7).
Each session holds:
  - recent_intents:  last 5 detected intents (deque)
  - active_topic:    best-guess topic from recent messages
  - turn_count:      number of turns in this session
  - last_seen:       timestamp of last activity
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..phase1.intent_planner import PlannerOutput
from .ceo import CEOPosture


# ── Session state (in-memory) ─────────────────────────────────────────────────

@dataclass
class SessionState:
    session_id:     str
    recent_intents: deque = field(default_factory=lambda: deque(maxlen=5))
    active_topic:   str   = ""
    turn_count:     int   = 0
    last_seen:      float = field(default_factory=time.time)

    def record_turn(self, intent: str, message: str) -> None:
        self.recent_intents.append(intent)
        self.turn_count += 1
        self.last_seen = time.time()
        # Update active topic heuristic — use first 6 words of message
        words = message.strip().split()[:6]
        self.active_topic = " ".join(words)

    def intent_trail(self) -> list[str]:
        return list(self.recent_intents)

    def is_continuation(self, current_intent: str) -> bool:
        """True if the last 2 intents match — likely a follow-up."""
        trail = self.intent_trail()
        if len(trail) >= 2:
            return trail[-1] == current_intent and trail[-2] == current_intent
        return False


# Global session store (Phase 2: in-memory)
_SESSIONS: dict[str, SessionState] = {}
_SESSION_TTL = 3600   # 1 hour — prune stale sessions


def _get_or_create_session(session_id: str) -> SessionState:
    now = time.time()
    # Prune stale sessions periodically (every ~100 gets)
    if len(_SESSIONS) > 200:
        stale = [sid for sid, s in _SESSIONS.items() if now - s.last_seen > _SESSION_TTL]
        for sid in stale:
            del _SESSIONS[sid]

    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = SessionState(session_id=session_id)
    return _SESSIONS[session_id]


# ── Output type ───────────────────────────────────────────────────────────────

@dataclass
class ManagerPacket:
    """Structured request packet passed from Manager → Supervisor."""
    session_id:             str
    normalized_message:     str             # cleaned message for brain consumption
    original_message:       str             # raw effective message (for logging)
    intent:                 str             # from Planner
    response_mode:          str             # from Planner
    ceo_mode:               str             # from CEO
    risk_posture:           str             # from CEO
    priority:               str             # from CEO
    session_context:        dict            # session state snapshot
    project_context_summary: dict           # lightweight project context (if available)
    recent_files:           list[str]       # recently touched files (empty for Phase 2)
    history:                list            # conversation history
    is_continuation:        bool            # is this a follow-up on the same topic?
    ceo_notes:              list[str]       # CEO policy notes
    manager_ms:             float = 0.0

    def to_dict(self) -> dict:
        return {
            "session_id":              self.session_id,
            "normalized_message":      self.normalized_message,
            "intent":                  self.intent,
            "response_mode":           self.response_mode,
            "ceo_mode":                self.ceo_mode,
            "risk_posture":            self.risk_posture,
            "priority":                self.priority,
            "session_context":         self.session_context,
            "project_context_summary": self.project_context_summary,
            "is_continuation":         self.is_continuation,
            "ceo_notes":               self.ceo_notes,
            "manager_ms":              self.manager_ms,
        }


# ── Normalizer ────────────────────────────────────────────────────────────────

def _normalize(message: str) -> str:
    """Light normalization — strip, collapse whitespace."""
    return " ".join(message.strip().split())


# ── Project context injection ─────────────────────────────────────────────────

def _get_project_summary(intent: str) -> dict:
    """
    Pull a lightweight project context summary when intent warrants it.
    Only file_analysis, debugging, code_runner, planning, and app_builder
    need this context — skip for normal_chat and image_generate to save time.
    """
    if intent not in ("file_analysis", "debugging", "code_runner", "planning", "app_builder"):
        return {}

    try:
        from ..scanner import get_context
        ctx = get_context().to_dict()
        # Return a compact summary — not the full context
        return {
            "stack":       ctx.get("stack", {}),
            "entrypoints": ctx.get("entrypoints", [])[:5],
            "warnings":    ctx.get("warnings", [])[:3],
            "feature_count": len(ctx.get("feature_map", [])),
            "duplicate_risk_count": len(ctx.get("duplicate_risks", [])),
        }
    except Exception:
        return {}


# ── Public API ────────────────────────────────────────────────────────────────

def prepare(
    message: str,
    session_id: str,
    plan: PlannerOutput,
    posture: CEOPosture,
    history: Optional[list] = None,
) -> ManagerPacket:
    """
    Manager preparation pass.

    Takes raw message + Planner output + CEO posture and produces a
    normalized, context-enriched ManagerPacket for the Supervisor.

    Args:
        message:    Effective user message (slash args resolved, safety-cleaned).
        session_id: Session identifier.
        plan:       PlannerOutput from Phase 1 Planner.
        posture:    CEOPosture from CEO assessment.
        history:    Conversation history (list of {role, content}).

    Returns:
        ManagerPacket — always succeeds.
    """
    t0 = time.perf_counter()

    # Session state
    session = _get_or_create_session(session_id)
    is_continuation = session.is_continuation(plan.intent)
    session.record_turn(plan.intent, message)

    session_context = {
        "turn_count":     session.turn_count,
        "recent_intents": session.intent_trail(),
        "active_topic":   session.active_topic,
        "is_continuation":is_continuation,
        "last_seen_ts":   datetime.fromtimestamp(session.last_seen, tz=timezone.utc).isoformat(),
    }

    # Normalize message
    normalized = _normalize(message)

    # Project context (only when relevant)
    project_summary = _get_project_summary(plan.intent)

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    return ManagerPacket(
        session_id              = session_id,
        normalized_message      = normalized,
        original_message        = message,
        intent                  = plan.intent,
        response_mode           = plan.response_mode,
        ceo_mode                = posture.mode,
        risk_posture            = posture.risk_posture,
        priority                = posture.priority,
        session_context         = session_context,
        project_context_summary = project_summary,
        recent_files            = [],   # Phase 7: populated from file tracking
        history                 = history or [],
        is_continuation         = is_continuation,
        ceo_notes               = posture.notes,
        manager_ms              = elapsed_ms,
    )


def get_session_summary(session_id: str) -> dict:
    """Return a summary of the session state (for diagnostics / API)."""
    s = _SESSIONS.get(session_id)
    if not s:
        return {"session_id": session_id, "exists": False}
    return {
        "session_id":     s.session_id,
        "exists":         True,
        "turn_count":     s.turn_count,
        "recent_intents": s.intent_trail(),
        "active_topic":   s.active_topic,
        "last_seen_ts":   datetime.fromtimestamp(s.last_seen, tz=timezone.utc).isoformat(),
    }
