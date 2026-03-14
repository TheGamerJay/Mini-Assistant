"""
mission_manager.py — Phase 4 Mission Manager
──────────────────────────────────────────────
Sits at the END of the pipeline (after Reflection) and manages
multi-turn mission state.

Responsibilities:
  1. Detect if the current request continues an existing mission
  2. Create a new mission if a long-horizon intent is detected
  3. Update the active mission with the turn outcome
  4. Provide mission context for injection into Manager/Supervisor

Long-horizon intents (mission-worthy):
  app_builder, planning, debugging (multi-step),
  3d_character_generation, 3d_asset_generation

Continuation detection:
  - Same session has an active mission
  - Current intent is compatible with that mission's intent
  - Message contains continuation keywords ("add", "also", "now", "next",
    "and", "with", "it", "that", "the app", "the project")

Phase 4 rules:
  - Does NOT auto-close missions (user must say "done" / "finished" etc.)
  - Does NOT merge missions
  - One active mission per session at a time
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from ..phase1.intent_planner import PlannerOutput
from ..phase1.critic import CriticResult
from .mission_store import Mission, MissionStore

logger = logging.getLogger(__name__)


# ── Intents that merit a mission ──────────────────────────────────────────────

_MISSION_WORTHY = {
    "app_builder",
    "planning",
    "debugging",
    "3d_character_generation",
    "3d_asset_generation",
    "code_runner",
}

# Keywords that suggest the user is continuing an existing objective
_CONTINUATION = re.compile(
    r"\b(add|also|now|next|and|with|also add|the app|the project|the code|"
    r"it|that|those|these|the site|the tool|the game|what about|one more|"
    r"also need|can you also|can u also|make it|update|change|modify|"
    r"refactor|improve|extend|expand|continue|same)\b",
    re.IGNORECASE,
)

# Keywords that signal mission closure
_CLOSE_SIGNAL = re.compile(
    r"\b(done|finished|complete|completed|that.?s it|that.?s all|"
    r"stop|cancel|abandon|close|no more|wrap up|ship it|deploy)\b",
    re.IGNORECASE,
)

# Compatible intent pairs: (active_mission_intent, current_intent)
_COMPATIBLE = {
    ("app_builder",   "app_builder"),
    ("app_builder",   "code_runner"),
    ("app_builder",   "debugging"),
    ("app_builder",   "file_analysis"),
    ("planning",      "planning"),
    ("planning",      "app_builder"),
    ("planning",      "code_runner"),
    ("debugging",     "debugging"),
    ("debugging",     "code_runner"),
    ("code_runner",   "code_runner"),
    ("code_runner",   "debugging"),
    ("3d_character_generation", "3d_character_generation"),
    ("3d_character_generation", "3d_asset_generation"),
    ("3d_asset_generation",     "3d_asset_generation"),
}


# ── Output type ───────────────────────────────────────────────────────────────

@dataclass
class MissionResult:
    action:          str            # "created" | "updated" | "closed" | "none"
    mission:         Optional[Mission]
    is_continuation: bool
    context_injected: bool
    mission_summary: str

    def to_dict(self) -> dict:
        return {
            "action":           self.action,
            "mission_id":       self.mission.id if self.mission else None,
            "mission_title":    self.mission.title if self.mission else None,
            "mission_status":   self.mission.status if self.mission else None,
            "is_continuation":  self.is_continuation,
            "context_injected": self.context_injected,
        }


# ── Manager ───────────────────────────────────────────────────────────────────

class MissionManager:
    """
    Manages multi-turn mission lifecycle.

    Usage:
        mgr = MissionManager()
        result = mgr.process(
            message="Add user login to it",
            plan=planner_output,
            critic=critic_result,
            session_id="abc123",
        )
        if result.mission and result.is_continuation:
            # inject result.mission.summary_for_prompt() into next LLM call
    """

    def __init__(self, store: Optional[MissionStore] = None):
        self._store = store or _get_shared_store()

    # ── Public API ────────────────────────────────────────────────────────────

    def process(
        self,
        message:    str,
        plan:       PlannerOutput,
        critic:     CriticResult,
        session_id: str,
    ) -> MissionResult:
        """
        Evaluate the current turn against the active mission (if any)
        and update state accordingly.

        Returns MissionResult describing what happened.
        """
        intent  = plan.intent
        outcome = "success" if critic.passed else "partial"

        # 1. Check if user is signalling mission close
        active = self._store.active_for_session(session_id)
        if active and _CLOSE_SIGNAL.search(message):
            self._store.update_status(active.id, "completed")
            active = self._store.get(active.id)
            logger.info("Mission closed: [%s] %s", active.id[:8], active.title)
            return MissionResult(
                action="closed",
                mission=active,
                is_continuation=True,
                context_injected=False,
                mission_summary=f"Mission '{active.title}' marked complete.",
            )

        # 2. Continue existing mission?
        if active:
            pair = (active.intent, intent)
            is_compat  = pair in _COMPATIBLE
            has_cont   = bool(_CONTINUATION.search(message))

            if is_compat or has_cont:
                self._store.add_turn(
                    mission_id=active.id,
                    session_id=session_id,
                    intent=intent,
                    message=message,
                    outcome=outcome,
                )
                updated = self._store.get(active.id)
                logger.info(
                    "Mission updated: [%s] turn %d (%s)",
                    active.id[:8], updated.turn_count, intent,
                )
                return MissionResult(
                    action="updated",
                    mission=updated,
                    is_continuation=True,
                    context_injected=True,
                    mission_summary=updated.summary_for_prompt(),
                )

        # 3. Create a new mission for mission-worthy intents
        if intent in _MISSION_WORTHY and len(message.strip()) > 15:
            mission = self._store.create(
                goal=message,
                intent=intent,
                session_id=session_id,
                context={"response_mode": plan.response_mode},
            )
            self._store.add_turn(
                mission_id=mission.id,
                session_id=session_id,
                intent=intent,
                message=message,
                outcome=outcome,
            )
            logger.info(
                "Mission created: [%s] %s (intent=%s)",
                mission.id[:8], mission.title, intent,
            )
            return MissionResult(
                action="created",
                mission=self._store.get(mission.id),
                is_continuation=False,
                context_injected=False,
                mission_summary="",
            )

        # 4. No mission action
        return MissionResult(
            action="none",
            mission=None,
            is_continuation=False,
            context_injected=False,
            mission_summary="",
        )

    def get_active_mission(self, session_id: str) -> Optional[Mission]:
        """Return the active mission for a session, if any."""
        return self._store.active_for_session(session_id)

    def get_mission_context(self, session_id: str) -> str:
        """Return mission context string for LLM prompt injection."""
        mission = self._store.active_for_session(session_id)
        if not mission:
            return ""
        return mission.summary_for_prompt()

    def list_missions(
        self,
        status:     Optional[str] = None,
        session_id: Optional[str] = None,
        limit:      int           = 20,
    ) -> list[Mission]:
        return self._store.list_missions(status=status, session_id=session_id, limit=limit)

    def close_mission(self, mission_id: str, status: str = "completed") -> bool:
        if status not in ("completed", "abandoned", "paused"):
            status = "completed"
        return self._store.update_status(mission_id, status)


# ── Shared store + singleton ──────────────────────────────────────────────────

_shared_store:   Optional[MissionStore]   = None
_shared_manager: Optional[MissionManager] = None


def _get_shared_store() -> MissionStore:
    global _shared_store
    if _shared_store is None:
        _shared_store = MissionStore()
    return _shared_store


def get_mission_manager() -> MissionManager:
    global _shared_manager
    if _shared_manager is None:
        _shared_manager = MissionManager()
    return _shared_manager
