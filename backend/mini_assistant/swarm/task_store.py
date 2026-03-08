"""
task_store.py – OrchestratorTask Persistence
──────────────────────────────────────────────
Persists OrchestratorTask objects across server restarts.

Storage backends (priority order)
──────────────────────────────────
1. MongoDB  – async, used for production (MONGO_URL env var must be set)
2. JSON file – sync, local dev fallback (./data/orchestrator_tasks.json)

The store provides both async (for FastAPI endpoints) and sync (for use
inside the synchronous SwarmManager execution loop) save methods.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from .orchestrator_task import OrchestratorTask

logger = logging.getLogger("swarm.task_store")

_DATA_DIR  = Path(__file__).parent.parent.parent / "data"
_TASK_FILE = _DATA_DIR / "orchestrator_tasks.json"


# ─── JSON file helpers (sync) ──────────────────────────────────────────────────

def _ensure_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_json_store() -> dict[str, dict]:
    _ensure_data_dir()
    if not _TASK_FILE.exists():
        return {}
    try:
        return json.loads(_TASK_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read task store file: %s", exc)
        return {}


def _save_json_store(store: dict[str, dict]) -> None:
    _ensure_data_dir()
    try:
        _TASK_FILE.write_text(
            json.dumps(store, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Could not write task store file: %s", exc)


# ─── TaskStore ─────────────────────────────────────────────────────────────────

class TaskStore:
    """
    Persists OrchestratorTask objects to MongoDB (if available) or a
    local JSON file.

    Usage
    -----
        store = TaskStore(mongo_db=db)          # from server.py
        await store.save(task)                  # async (MongoDB or JSON)
        store.save_sync(task)                   # sync (JSON only – for use inside threads)
        task = await store.load(task_id)
        tasks = await store.list_recent(50)
    """

    COLLECTION = "orchestrator_tasks"

    def __init__(self, mongo_db=None):
        self._db = mongo_db

    # ── MongoDB (async) ────────────────────────────────────────────────────────

    async def _mongo_save(self, task: OrchestratorTask) -> None:
        col = self._db[self.COLLECTION]
        doc = task.to_dict()
        doc["_id"] = task.task_id
        await col.replace_one({"_id": task.task_id}, doc, upsert=True)

    async def _mongo_load(self, task_id: str) -> Optional[OrchestratorTask]:
        col = self._db[self.COLLECTION]
        doc = await col.find_one({"_id": task_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return OrchestratorTask.from_dict(doc)

    async def _mongo_list(self, limit: int = 50) -> list[dict]:
        col    = self._db[self.COLLECTION]
        fields = {"goal": 1, "task_id": 1, "task_type": 1, "current_state": 1,
                  "created_at": 1, "completed_at": 1, "retry_count": 1,
                  "failure_reason": 1}
        cursor = col.find({}, fields).sort("created_at", -1).limit(limit)
        result = []
        async for doc in cursor:
            doc.pop("_id", None)
            result.append(doc)
        return result

    async def _mongo_delete(self, task_id: str) -> bool:
        col = self._db[self.COLLECTION]
        res = await col.delete_one({"_id": task_id})
        return res.deleted_count > 0

    # ── JSON file (sync) ───────────────────────────────────────────────────────

    def _json_save(self, task: OrchestratorTask) -> None:
        store = _load_json_store()
        store[task.task_id] = task.to_dict()
        _save_json_store(store)

    def _json_load(self, task_id: str) -> Optional[OrchestratorTask]:
        store = _load_json_store()
        d     = store.get(task_id)
        return OrchestratorTask.from_dict(d) if d else None

    def _json_list(self, limit: int = 50) -> list[dict]:
        store = _load_json_store()
        _SUMMARY_KEYS = ("task_id", "task_type", "goal", "current_state",
                         "created_at", "completed_at", "retry_count", "failure_reason")
        tasks = sorted(store.values(), key=lambda t: t.get("created_at", ""), reverse=True)
        return [
            {k: t[k] for k in _SUMMARY_KEYS if k in t}
            for t in tasks[:limit]
        ]

    def _json_delete(self, task_id: str) -> bool:
        store = _load_json_store()
        if task_id not in store:
            return False
        del store[task_id]
        _save_json_store(store)
        return True

    # ── Public async API ───────────────────────────────────────────────────────

    async def save(self, task: OrchestratorTask) -> None:
        """Persist the task. Uses MongoDB if available, JSON file as fallback."""
        try:
            if self._db is not None:
                await self._mongo_save(task)
                return
        except Exception as exc:
            logger.warning("MongoDB save failed (%s) – using JSON fallback.", exc)
        self._json_save(task)

    async def load(self, task_id: str) -> Optional[OrchestratorTask]:
        """Load a task by ID. Returns None if not found."""
        try:
            if self._db is not None:
                return await self._mongo_load(task_id)
        except Exception as exc:
            logger.warning("MongoDB load failed (%s) – trying JSON fallback.", exc)
        return self._json_load(task_id)

    async def list_recent(self, limit: int = 50) -> list[dict]:
        """Return summary dicts for the most recent tasks (newest first)."""
        try:
            if self._db is not None:
                return await self._mongo_list(limit)
        except Exception as exc:
            logger.warning("MongoDB list failed (%s) – using JSON fallback.", exc)
        return self._json_list(limit)

    async def delete(self, task_id: str) -> bool:
        """Delete a task. Returns True if deleted."""
        try:
            if self._db is not None:
                return await self._mongo_delete(task_id)
        except Exception as exc:
            logger.warning("MongoDB delete failed (%s) – using JSON fallback.", exc)
        return self._json_delete(task_id)

    # ── Sync API (for use inside SwarmManager thread) ─────────────────────────

    def save_sync(self, task: OrchestratorTask) -> None:
        """
        Synchronous checkpoint save – always writes to the JSON file.
        Call this from inside the SwarmManager execution thread to persist
        state transitions without blocking on async I/O.
        The async `save()` method will then sync to MongoDB at the end of the run.
        """
        self._json_save(task)
