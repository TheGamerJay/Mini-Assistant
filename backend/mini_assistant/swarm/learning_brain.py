"""
learning_brain.py – Learning Brain (cross-task pattern tracking)
────────────────────────────────────────────────────────────────
Records task outcomes as lessons and aggregates patterns across
all tasks (success rate, failure trends, avg retries, fix-loop frequency).

Storage: data/learning.json (single consolidated file)
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .orchestrator_task import OrchestratorTask

logger = logging.getLogger("swarm.learning_brain")

_LEARNING_FILE = Path(__file__).parent.parent.parent / "data" / "learning.json"
_MAX_LESSONS   = 200


class LearningBrain:
    """
    Tracks task outcomes as lessons and derives aggregate patterns.
    Called only at task completion (success or failure).
    """

    def __init__(self):
        _LEARNING_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ── Write API ──────────────────────────────────────────────────────────────

    def record_outcome(self, task: "OrchestratorTask") -> dict:
        """
        Record a lesson from a completed/failed task.
        Returns the lesson dict that was saved (for debug_log).
        """
        fix_loop_count = sum(1 for s in task.steps if "Fix" in s.name and "loop" in s.name)
        lesson = {
            "task_id":         task.task_id,
            "task_type":       task.task_type,
            "goal_summary":    task.goal[:200],
            "outcome":         str(task.current_state),
            "retries":         task.retry_count,
            "fix_loops":       fix_loop_count,
            "checkpoints_hit": [c.name for c in task.checkpoints],
            "failure_summary": task.failure_summary or "",
            "assigned_agents": task.assigned_agents,
            "step_count":      len(task.steps),
            "timestamp":       datetime.now(timezone.utc).isoformat(),
        }

        data = self._load()
        lessons = data.get("lessons", [])
        lessons.append(lesson)
        lessons = lessons[-_MAX_LESSONS:]   # rolling cap
        data["lessons"]  = lessons
        data["patterns"] = self._compute_patterns(lessons)
        self._save(data)

        logger.info(
            "[LearningBrain] Lesson recorded: type=%s outcome=%s retries=%d fix_loops=%d",
            lesson["task_type"], lesson["outcome"], lesson["retries"], lesson["fix_loops"],
        )
        return lesson

    # ── Read API ───────────────────────────────────────────────────────────────

    def get_patterns(self) -> dict:
        """Return the most recently computed pattern aggregates."""
        return self._load().get("patterns", {})

    def get_recent_lessons(self, task_type: str | None = None, limit: int = 10) -> list[dict]:
        """Return recent lessons, optionally filtered by task_type."""
        lessons = self._load().get("lessons", [])
        if task_type:
            lessons = [l for l in lessons if l.get("task_type") == task_type]
        return list(reversed(lessons[-limit:]))

    # ── Pattern computation ────────────────────────────────────────────────────

    def _compute_patterns(self, lessons: list) -> dict:
        if not lessons:
            return {}
        total      = len(lessons)
        successes  = sum(1 for l in lessons if l["outcome"] == "completed")
        failures   = sum(1 for l in lessons if l["outcome"] == "failed")
        fix_loops  = sum(l.get("fix_loops", 0) for l in lessons)
        avg_retries = round(sum(l.get("retries", 0) for l in lessons) / total, 2)

        # Count agent frequency
        agent_counter: Counter = Counter()
        for l in lessons:
            for a in l.get("assigned_agents", []):
                agent_counter[a] += 1

        # Most frequent failure summaries (deduplicated)
        failure_summaries = [
            l["failure_summary"] for l in lessons
            if l.get("failure_summary") and l["outcome"] == "failed"
        ]
        unique_failures = list(dict.fromkeys(failure_summaries))[-5:]

        # Per-type breakdown
        by_type: dict[str, dict] = {}
        for l in lessons:
            tt = l.get("task_type", "unknown")
            bucket = by_type.setdefault(tt, {"total": 0, "completed": 0, "failed": 0})
            bucket["total"] += 1
            if l["outcome"] == "completed":
                bucket["completed"] += 1
            elif l["outcome"] == "failed":
                bucket["failed"] += 1

        return {
            "total_tasks":      total,
            "success_rate":     round(successes / total, 2),
            "failure_rate":     round(failures  / total, 2),
            "avg_retries":      avg_retries,
            "total_fix_loops":  fix_loops,
            "top_agents":       agent_counter.most_common(5),
            "common_failures":  unique_failures,
            "by_type":          by_type,
            "computed_at":      datetime.now(timezone.utc).isoformat(),
        }

    # ── JSON helpers ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if not _LEARNING_FILE.exists():
            return {}
        try:
            return json.loads(_LEARNING_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[LearningBrain] Load failed: %s", exc)
            return {}

    def _save(self, data: dict) -> None:
        try:
            _LEARNING_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("[LearningBrain] Save failed: %s", exc)
