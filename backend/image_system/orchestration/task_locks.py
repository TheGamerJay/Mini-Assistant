"""
Task Locks — Phase 4

Single-writer lock system to prevent parallel overlapping mutations.

Rules:
  - Only ONE active writer per (project_id, scope)
  - Read-only operations (analyze, review, QA, research) always run in parallel
  - Writers must acquire a lock before mutating; released on step completion or failure
  - Conflicting writes are queued, not rejected

Scopes:
  - "global"         — entire project
  - "file:{path}"    — specific file
  - "ui"             — frontend/UI layer
  - "api"            — backend API
  - "schema"         — database schema
  - "config"         — configuration files
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

_LOCK_TIMEOUT = 120.0  # seconds — auto-release stale locks

# Read-only operation types that NEVER need a lock
READ_ONLY_OPS: Set[str] = {
    "analyze", "analyze_code", "review", "qa_review",
    "research", "fetch_memory", "risk_estimate",
    "visual_inspect", "screenshot", "log_check",
    "plan", "cost_estimate",
}


@dataclass
class LockEntry:
    lock_id:    str
    task_id:    str
    step_id:    str
    scope:      str
    acquired_at: float
    owner:      str   # "task_id:step_id"


class TaskLockManager:
    """
    Async-safe lock manager with timeout-based auto-release.
    One global instance shared across all request handlers.
    """

    def __init__(self):
        self._locks:  Dict[str, LockEntry]  = {}   # scope → LockEntry
        self._asyncio_locks: Dict[str, asyncio.Lock] = {}
        self._mutex = asyncio.Lock()

    def _get_asyncio_lock(self, scope: str) -> asyncio.Lock:
        if scope not in self._asyncio_locks:
            self._asyncio_locks[scope] = asyncio.Lock()
        return self._asyncio_locks[scope]

    async def acquire(
        self,
        scope:    str,
        task_id:  str,
        step_id:  str,
        timeout:  float = 30.0,
    ) -> Optional[str]:
        """
        Acquire a write lock for a scope.

        Returns:
            lock_id string on success, None on timeout.
        """
        # Evict stale locks first
        await self._evict_stale()

        lock = self._get_asyncio_lock(scope)
        try:
            await asyncio.wait_for(lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("[TaskLocks] timeout acquiring lock for scope=%s task=%s", scope, task_id)
            return None

        lock_id = str(uuid.uuid4())[:8]
        entry = LockEntry(
            lock_id=lock_id,
            task_id=task_id,
            step_id=step_id,
            scope=scope,
            acquired_at=time.monotonic(),
            owner=f"{task_id}:{step_id}",
        )
        async with self._mutex:
            self._locks[scope] = entry

        logger.debug("[TaskLocks] acquired scope=%s by %s", scope, entry.owner)
        return lock_id

    async def release(self, scope: str, lock_id: str) -> bool:
        """
        Release a write lock.
        Returns True if released, False if lock_id doesn't match (already released by timeout).
        """
        async with self._mutex:
            entry = self._locks.get(scope)
            if not entry or entry.lock_id != lock_id:
                logger.debug("[TaskLocks] release mismatch: scope=%s lock_id=%s", scope, lock_id)
                return False
            del self._locks[scope]

        lock = self._asyncio_locks.get(scope)
        if lock and lock.locked():
            lock.release()

        logger.debug("[TaskLocks] released scope=%s", scope)
        return True

    def is_locked(self, scope: str) -> bool:
        """Check if a scope is currently write-locked."""
        entry = self._locks.get(scope)
        if not entry:
            return False
        # Auto-expire in sync context
        if time.monotonic() - entry.acquired_at > _LOCK_TIMEOUT:
            return False
        return True

    def can_proceed(self, operation: str, scope: str) -> tuple[bool, str]:
        """
        Check if an operation can proceed given current locks.

        Args:
            operation: Tool category name.
            scope:     Target scope.

        Returns:
            (can_proceed: bool, reason: str)
        """
        # Read-only ops always proceed
        if operation in READ_ONLY_OPS:
            return True, "Read-only operation — no lock required."

        if self.is_locked(scope):
            entry = self._locks.get(scope)
            owner = entry.owner if entry else "unknown"
            return False, f"Scope '{scope}' is locked by {owner}. Queuing write."

        return True, "Scope is free."

    async def _evict_stale(self) -> None:
        """Remove locks held longer than _LOCK_TIMEOUT."""
        now = time.monotonic()
        async with self._mutex:
            stale = [s for s, e in self._locks.items() if now - e.acquired_at > _LOCK_TIMEOUT]
            for scope in stale:
                entry = self._locks.pop(scope)
                lock = self._asyncio_locks.get(scope)
                if lock and lock.locked():
                    lock.release()
                logger.warning("[TaskLocks] evicted stale lock: scope=%s owner=%s", scope, entry.owner)


# Singleton
_lock_manager: Optional[TaskLockManager] = None


def get_lock_manager() -> TaskLockManager:
    global _lock_manager
    if _lock_manager is None:
        _lock_manager = TaskLockManager()
    return _lock_manager
