"""
memory_brain.py – Persistent Memory Brain
──────────────────────────────────────────
Saves task summaries per task_type and retrieves relevant past context
to enrich the step prompt at task start.

Storage: data/memory/{task_type}.json (up to 50 entries per type)

Phase 9.5: per-file FileLock around every read-modify-write to prevent
JSON corruption under concurrent task execution.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

try:
    from filelock import FileLock, Timeout as FileLockTimeout
    _HAS_FILELOCK = True
except ImportError:
    _HAS_FILELOCK = False
    FileLockTimeout = Exception  # type: ignore

if TYPE_CHECKING:
    from .orchestrator_task import OrchestratorTask

logger = logging.getLogger("swarm.memory_brain")

_MEMORY_DIR    = Path(__file__).parent.parent.parent / "data" / "memory"
_MAX_ENTRIES   = 50
_CONTEXT_ENTRIES = 5
_LOCK_TIMEOUT  = 10    # seconds
_LOCK_SUFFIX   = ".lock"


class MemoryBrain:
    """
    Persists task summaries and provides past-context retrieval.
    Backed by per-task-type JSON files with FileLock concurrency control.
    """

    def __init__(self, mongo_db=None):
        self._db = mongo_db
        _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        if not _HAS_FILELOCK:
            logger.warning(
                "[MemoryBrain] filelock not installed — concurrent writes may corrupt data. "
                "Run: pip install filelock"
            )

    # ── Read API ───────────────────────────────────────────────────────────────

    def load_context(self, task_type: str, goal: str) -> list[dict]:
        summaries = self._load_json(task_type)
        return list(reversed(summaries[-_CONTEXT_ENTRIES:]))

    def build_context_block(self, task_type: str, goal: str) -> str:
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
        entry = {
            "task_id":         task.task_id,
            "task_type":       task.task_type,
            "goal":            task.goal[:300],
            "outcome":         str(task.current_state),
            "retries":         task.retry_count,
            "checkpoints":     [c.name for c in task.checkpoints],
            "failure_summary": task.failure_summary or "",
            "assigned_agents": task.assigned_agents,
            "saved_at":        datetime.now(timezone.utc).isoformat(),
        }
        self._atomic_append(task.task_type, entry)
        logger.info("[MemoryBrain] Saved: task=%s type=%s outcome=%s",
                    task.task_id[:8], task.task_type, entry["outcome"])

    def record_checkpoint(self, task: "OrchestratorTask", checkpoint_name: str) -> None:
        logger.debug("[MemoryBrain] Checkpoint '%s': task=%s state=%s",
                     checkpoint_name, task.task_id[:8], task.current_state)

    # ── Concurrency-safe helpers ───────────────────────────────────────────────

    def _atomic_append(self, task_type: str, entry: dict) -> None:
        """Atomic read-modify-write under FileLock."""
        path      = _MEMORY_DIR / f"{task_type}.json"
        lock_path = _MEMORY_DIR / f"{task_type}{_LOCK_SUFFIX}"

        if _HAS_FILELOCK:
            try:
                with FileLock(str(lock_path), timeout=_LOCK_TIMEOUT):
                    data = _read_json(path)
                    data.append(entry)
                    _write_json(path, data[-_MAX_ENTRIES:])
            except FileLockTimeout:
                logger.error("[MemoryBrain] Lock timeout saving type=%s — entry NOT saved. "
                             "Another process may be holding the lock.", task_type)
        else:
            data = _read_json(path)
            data.append(entry)
            _write_json(path, data[-_MAX_ENTRIES:])

    def _load_json(self, task_type: str) -> list:
        path      = _MEMORY_DIR / f"{task_type}.json"
        lock_path = _MEMORY_DIR / f"{task_type}{_LOCK_SUFFIX}"
        if not path.exists():
            return []
        if _HAS_FILELOCK:
            try:
                with FileLock(str(lock_path), timeout=_LOCK_TIMEOUT):
                    return _read_json(path)
            except FileLockTimeout:
                logger.warning("[MemoryBrain] Lock timeout reading type=%s — returning []", task_type)
                return []
        return _read_json(path)


# ── Module-level JSON helpers (no instance needed) ────────────────────────────

def _read_json(path: Path) -> list:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[MemoryBrain] Read error %s: %s", path.name, exc)
        return []


def _write_json(path: Path, data: list) -> None:
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning("[MemoryBrain] Write error %s: %s", path.name, exc)
