"""
mission_store.py — Phase 4 Mission Persistence
────────────────────────────────────────────────
A "mission" is a multi-turn, high-level objective that persists across
conversation turns and sessions until explicitly closed.

Examples:
  "Build a todo app" → mission created, open
  "Add user auth to it" → mission found, updated with new turn
  "Deploy it" → mission updated with deployment turn
  "Done" → mission closed (status=completed)

Mission lifecycle:
  created → active → (paused) → completed | abandoned

Storage: JSON file at ./memory_store/missions.json
Max stored: 200 missions (oldest pruned on save)
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_PATH  = os.getenv("MISSION_STORE_PATH", "./memory_store/missions.json")
MAX_MISSIONS   = 200
MISSION_STATUSES = ("active", "paused", "completed", "abandoned")


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class MissionTurn:
    """A single conversation turn that advanced this mission."""
    turn:         int
    session_id:   str
    intent:       str
    message:      str   # truncated to 200 chars
    outcome:      str   # "success" | "partial" | "failed"
    timestamp:    str   = field(default_factory=lambda: _now())


@dataclass
class Mission:
    """
    A persistent multi-turn objective.

    Fields:
        id            Unique mission UUID.
        title         Short human-readable title (first 60 chars of goal).
        goal          Full original goal text.
        status        "active" | "paused" | "completed" | "abandoned"
        intent        Primary intent that created this mission.
        session_id    Session that created this mission.
        turns         List of MissionTurn records.
        created_at    ISO timestamp.
        updated_at    ISO timestamp.
        context       Freeform dict of mission-level metadata (e.g. tech stack).
    """
    id:          str
    title:       str
    goal:        str
    status:      str
    intent:      str
    session_id:  str
    turns:       list[MissionTurn]  = field(default_factory=list)
    created_at:  str                = field(default_factory=lambda: _now())
    updated_at:  str                = field(default_factory=lambda: _now())
    context:     dict               = field(default_factory=dict)

    # ── Convenience ──────────────────────────────────────────────────────────

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def add_turn(
        self,
        session_id: str,
        intent:     str,
        message:    str,
        outcome:    str = "success",
    ) -> None:
        turn = MissionTurn(
            turn=len(self.turns) + 1,
            session_id=session_id,
            intent=intent,
            message=message[:200],
            outcome=outcome,
        )
        self.turns.append(turn)
        self.updated_at = _now()

    def summary_for_prompt(self) -> str:
        """Short context string to inject into LLM prompts."""
        recent = self.turns[-3:] if self.turns else []
        lines = [f"Active mission: {self.title} (goal: {self.goal[:120]})"]
        if recent:
            lines.append("Recent turns:")
            for t in recent:
                lines.append(f"  [{t.outcome}] {t.intent}: {t.message[:80]}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["turn_count"] = self.turn_count
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Mission":
        turns_raw = d.pop("turns", [])
        d.pop("turn_count", None)
        turns = [MissionTurn(**t) for t in turns_raw]
        return cls(**d, turns=turns)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Store ─────────────────────────────────────────────────────────────────────

class MissionStore:
    """Persistent JSON store for Mission records."""

    def __init__(self, store_path: Optional[str] = None):
        self._path = Path(store_path or _DEFAULT_PATH)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._missions: dict[str, Mission] = {}
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if self._path.exists():
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                for d in raw:
                    m = Mission.from_dict(d)
                    self._missions[m.id] = m
                logger.debug("Loaded %d missions from %s", len(self._missions), self._path)
        except Exception as exc:
            logger.warning("Could not load missions: %s", exc)
            self._missions = {}

    def _save(self) -> None:
        missions_list = [m.to_dict() for m in self._missions.values()]
        if len(missions_list) > MAX_MISSIONS:
            # Keep newest MAX_MISSIONS by updated_at
            missions_list.sort(key=lambda d: d.get("updated_at", ""), reverse=True)
            missions_list = missions_list[:MAX_MISSIONS]
            self._missions = {}
            for d in missions_list:
                m = Mission.from_dict(d.copy())
                self._missions[m.id] = m
        try:
            self._path.write_text(
                json.dumps(missions_list, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Could not save missions: %s", exc)

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def create(
        self,
        goal:       str,
        intent:     str,
        session_id: str,
        context:    Optional[dict] = None,
    ) -> Mission:
        """Create and persist a new active mission."""
        m = Mission(
            id=str(uuid.uuid4()),
            title=goal[:60],
            goal=goal,
            status="active",
            intent=intent,
            session_id=session_id,
            context=context or {},
        )
        self._missions[m.id] = m
        self._save()
        logger.info("Mission created: [%s] %s", m.id[:8], m.title)
        return m

    def get(self, mission_id: str) -> Optional[Mission]:
        return self._missions.get(mission_id)

    def update_status(self, mission_id: str, status: str) -> bool:
        m = self._missions.get(mission_id)
        if not m:
            return False
        m.status     = status
        m.updated_at = _now()
        self._save()
        return True

    def add_turn(
        self,
        mission_id: str,
        session_id: str,
        intent:     str,
        message:    str,
        outcome:    str = "success",
    ) -> bool:
        m = self._missions.get(mission_id)
        if not m:
            return False
        m.add_turn(session_id, intent, message, outcome)
        self._save()
        return True

    def active_for_session(self, session_id: str) -> Optional[Mission]:
        """Return the most recently updated active mission for a session."""
        candidates = [
            m for m in self._missions.values()
            if m.is_active and m.session_id == session_id
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda m: m.updated_at)

    def list_missions(
        self,
        status:     Optional[str] = None,
        session_id: Optional[str] = None,
        limit:      int           = 20,
    ) -> list[Mission]:
        missions = list(self._missions.values())
        if status:
            missions = [m for m in missions if m.status == status]
        if session_id:
            missions = [m for m in missions if m.session_id == session_id]
        missions.sort(key=lambda m: m.updated_at, reverse=True)
        return missions[:limit]

    def __len__(self) -> int:
        return len(self._missions)
