"""
reflection.py – Task Reflection Logger
────────────────────────────────────────
After each task, save a reflection entry for long-term learning.

Reflection entries look like:
{
    "task":         "Build FastAPI login system",
    "result":       "success",
    "brain":        "coding",
    "attempts":     2,
    "errors_seen":  ["ModuleNotFoundError: fastapi"],
    "fixes_applied":["Added fastapi to requirements.txt"],
    "lesson":       "Always generate requirements.txt for Python apps",
    "timestamp":    "2024-01-15T10:30:00Z"
}

Usage:
    reflection = Reflection()
    reflection.log(
        task="Write a binary search",
        result="success",
        brain="coding",
        errors_seen=["IndexError on empty list"],
        fixes_applied=["Added guard for empty input"],
    )
    recent = reflection.recent(10)
    lessons = reflection.search_lessons("fastapi")
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..config import MODELS

logger = logging.getLogger(__name__)

_DEFAULT_PATH = os.getenv("REFLECTION_LOG_PATH", "./memory_store/reflections.json")
MAX_REFLECTIONS = 1000


# ─── Data class ───────────────────────────────────────────────────────────────

class ReflectionEntry(dict):
    """
    A reflection entry is just a typed dict for IDE clarity.
    Fields: id, task, result, brain, attempts, errors_seen,
            fixes_applied, lesson, timestamp
    """
    pass


# ─── Lesson generator ─────────────────────────────────────────────────────────

_LESSON_SYSTEM = """\
You are an AI assistant reflecting on a completed task.

Based on the task summary, write ONE concise lesson learned (1–2 sentences).
Focus on actionable insights: what to do differently, what worked well,
or what to remember for similar tasks in future.

Respond with ONLY the lesson text. No preamble.
"""


def _generate_lesson(task: str, errors: list[str], fixes: list[str]) -> str:
    """Ask Claude/OpenAI to synthesise a lesson from the task outcomes."""
    if not errors and not fixes:
        return "Task completed successfully without issues."

    prompt = (
        f"Task: {task}\n"
        f"Errors encountered: {', '.join(errors[:3]) or 'none'}\n"
        f"Fixes applied: {', '.join(fixes[:3]) or 'none'}\n\n"
        "What is the key lesson from this task?"
    )
    try:
        ant_key = os.getenv("ANTHROPIC_API_KEY")
        oai_key = os.getenv("OPENAI_API_KEY")
        if ant_key:
            import anthropic
            client = anthropic.Anthropic(api_key=ant_key)
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                system=_LESSON_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text.strip()
        if oai_key:
            import openai
            client = openai.OpenAI(api_key=oai_key)
            resp = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=512,
                messages=[
                    {"role": "system", "content": _LESSON_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            return (resp.choices[0].message.content or "").strip()
        raise RuntimeError("No AI key")
    except Exception as exc:
        logger.warning("Lesson generation failed: %s", exc)
        if fixes:
            return f"Applied fix: {fixes[0]}"
        return "Review error handling for similar tasks."


# ─── Reflection store ─────────────────────────────────────────────────────────

class Reflection:
    """Persistent JSON log of task reflections."""

    def __init__(self, store_path: Optional[str] = None):
        self._path = Path(store_path or _DEFAULT_PATH)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[dict] = []
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if self._path.exists():
                self._entries = json.loads(self._path.read_text(encoding="utf-8"))
                logger.debug("Loaded %d reflections from %s", len(self._entries), self._path)
        except Exception as exc:
            logger.warning("Could not load reflections: %s", exc)
            self._entries = []

    def _save(self) -> None:
        if len(self._entries) > MAX_REFLECTIONS:
            # Drop oldest entries
            self._entries = self._entries[-MAX_REFLECTIONS:]
        try:
            self._path.write_text(
                json.dumps(self._entries, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Could not save reflections: %s", exc)

    # ── Logging ───────────────────────────────────────────────────────────────

    def log(
        self,
        task: str,
        result: str,                          # "success" | "failure" | "partial"
        brain: str = "",
        attempts: int = 1,
        errors_seen: Optional[list[str]] = None,
        fixes_applied: Optional[list[str]] = None,
        lesson: Optional[str] = None,         # auto-generated if None
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Log a reflection entry.

        Returns the entry id.
        """
        errors  = errors_seen   or []
        fixes   = fixes_applied or []

        if lesson is None:
            lesson = _generate_lesson(task, errors, fixes)

        entry: dict = {
            "id":            str(uuid.uuid4()),
            "task":          task,
            "result":        result,
            "brain":         brain,
            "attempts":      attempts,
            "errors_seen":   errors,
            "fixes_applied": fixes,
            "lesson":        lesson,
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }
        self._entries.append(entry)
        self._save()
        logger.info("Reflection logged: [%s] %s → %s", result.upper(), task[:60], lesson[:80])
        return entry["id"]

    def log_from_repair(self, task: str, brain: str, repair_result: Any) -> str:
        """
        Convenience method – log from a RepairResult object.
        """
        return self.log(
            task          = task,
            result        = "success" if repair_result.success else "failure",
            brain         = brain,
            attempts      = repair_result.attempt_count,
            errors_seen   = repair_result.errors_seen,
            fixes_applied = repair_result.fixes_applied,
        )

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def recent(self, n: int = 10) -> list[dict]:
        """Return the n most recent reflection entries."""
        return list(reversed(self._entries[-n:]))

    def search_lessons(self, query: str) -> list[dict]:
        """Return entries whose task or lesson contains the query string."""
        q = query.lower()
        return [
            e for e in self._entries
            if q in e.get("task", "").lower() or q in e.get("lesson", "").lower()
        ]

    def lessons_for_brain(self, brain: str) -> list[str]:
        """Return all lesson strings for a specific brain."""
        return [
            e["lesson"]
            for e in self._entries
            if e.get("brain") == brain and e.get("lesson")
        ]

    def format_relevant_lessons(self, task: str, max_lessons: int = 3) -> str:
        """
        Find lessons relevant to a task and format them for LLM injection.
        """
        matching = self.search_lessons(task)
        lessons = [e["lesson"] for e in matching[:max_lessons] if e.get("lesson")]
        if not lessons:
            return ""
        return "Lessons from previous similar tasks:\n" + "\n".join(
            f"- {l}" for l in lessons
        )

    def success_rate(self, brain: Optional[str] = None) -> float:
        """Return the fraction of tasks that resulted in 'success'."""
        entries = [e for e in self._entries if not brain or e.get("brain") == brain]
        if not entries:
            return 0.0
        successes = sum(1 for e in entries if e.get("result") == "success")
        return successes / len(entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"Reflection(entries={len(self._entries)}, path={self._path})"
