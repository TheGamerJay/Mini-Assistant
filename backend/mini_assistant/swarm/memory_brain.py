"""
memory_brain.py – Persistent Memory Brain
──────────────────────────────────────────
Saves task summaries per task_type and retrieves relevant past context
to enrich the step prompt at task start.

Storage: data/memory/{task_type}.json (up to 50 entries per type)
MongoDB: collection 'memory_summaries' if db is available (future)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .orchestrator_task import OrchestratorTask

logger = logging.getLogger("swarm.memory_brain")

_MEMORY_DIR = Path(__file__).parent.parent.parent / "data" / "memory"
_MAX_ENTRIES = 50
_CONTEXT_ENTRIES = 5   # how many past summaries to inject into step prompt


class MemoryBrain:
    """
    Persists task summaries and provides past-context retrieval.
    Backed by per-task-type JSON files; MongoDB support can be
    added later by overriding the _load / _save methods.
    """

    def __init__(self, mongo_db=None):
        self._db = mongo_db
        _MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    # ── Read API ───────────────────────────────────────────────────────────────

    def load_context(self, task_type: str, goal: str) -> list[dict]:
        """
        Return the N most recent task summaries for this task_type.
        Used to inject memory into the step prompt at task start.
        """
        summaries = self._load_json(task_type)
        # Return last N, newest first
        return list(reversed(summaries[-_CONTEXT_ENTRIES:]))

    def build_context_block(self, task_type: str, goal: str) -> str:
        """
        Produce a human-readable memory block to prepend to step prompts.
        Returns empty string if no past summaries exist.
        """
        entries = self.load_context(task_type, goal)
        if not entries:
            return ""
        lines = ["=== Memory Context (recent similar tasks) ==="]
        for e in entries:
            outcome = e.get("outcome", "unknown")
            ts      = e.get("saved_at", "")[:10]
            summary = e.get("failure_summary", "") or e.get("goal", "")[:120]
            lines.append(f"[{ts}] {outcome.upper()} | {summary}")
        lines.append("=== End Memory ===")
        return "\n".join(lines)

    # ── Write API ──────────────────────────────────────────────────────────────

    def save_task_summary(self, task: "OrchestratorTask") -> None:
        """Save a task outcome summary for future retrieval."""
        checkpoints = [c.name for c in task.checkpoints]
        entry = {
            "task_id":        task.task_id,
            "task_type":      task.task_type,
            "goal":           task.goal[:300],
            "outcome":        str(task.current_state),
            "retries":        task.retry_count,
            "checkpoints":    checkpoints,
            "failure_summary": task.failure_summary or "",
            "assigned_agents": task.assigned_agents,
            "saved_at":       datetime.now(timezone.utc).isoformat(),
        }
        summaries = self._load_json(task.task_type)
        summaries.append(entry)
        self._save_json(task.task_type, summaries[-_MAX_ENTRIES:])
        logger.info("[MemoryBrain] Saved summary: task=%s type=%s outcome=%s",
                    task.task_id[:8], task.task_type, entry["outcome"])

    def record_checkpoint(self, task: "OrchestratorTask", checkpoint_name: str) -> None:
        """Log a checkpoint event into memory (lightweight, no duplicate summaries)."""
        logger.debug("[MemoryBrain] Checkpoint '%s' reached: task=%s state=%s",
                     checkpoint_name, task.task_id[:8], task.current_state)

    # ── Internal JSON helpers ──────────────────────────────────────────────────

    def _load_json(self, task_type: str) -> list:
        path = _MEMORY_DIR / f"{task_type}.json"
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[MemoryBrain] Load failed for type=%s: %s", task_type, exc)
            return []

    def _save_json(self, task_type: str, data: list) -> None:
        path = _MEMORY_DIR / f"{task_type}.json"
        try:
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("[MemoryBrain] Save failed for type=%s: %s", task_type, exc)
