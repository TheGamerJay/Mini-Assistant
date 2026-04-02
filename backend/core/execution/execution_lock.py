"""
execution/execution_lock.py — Per-resource execution locking.

Prevents overlapping builder/file executions on the same resource.

Lock scopes:
  project_id  — no two builder executions run on the same project simultaneously
  file_id     — no two file writes run on the same file simultaneously
  session_id  — session-level lock for sequential message processing

Design:
  - asyncio.Lock per resource ID (lightweight, per-process)
  - Lock is acquired before module_call, released after
  - Unrelated resources (different project_ids) run freely in parallel
  - Lock timeout: 30s (prevents indefinite blocking on orphaned locks)

CEO does NOT hold locks — this is executor-layer only.
Modules never acquire locks directly.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

log = logging.getLogger("ceo_router.execution_lock")

# ---------------------------------------------------------------------------
# Lock registry
# ---------------------------------------------------------------------------

_PROJECT_LOCKS:  dict[str, asyncio.Lock] = {}
_FILE_LOCKS:     dict[str, asyncio.Lock] = {}
_SESSION_LOCKS:  dict[str, asyncio.Lock] = {}
_LOCK_REGISTRY   = asyncio.Lock()   # protects the dicts above

_LOCK_TIMEOUT = 30.0   # seconds before giving up on acquiring a lock


async def _get_lock(registry: dict, key: str) -> asyncio.Lock:
    """Get or create a lock for the given key."""
    async with _LOCK_REGISTRY:
        if key not in registry:
            registry[key] = asyncio.Lock()
        return registry[key]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def acquire_project_lock(project_id: str) -> bool:
    """
    Acquire an exclusive lock for a project.

    Returns True if acquired, False if timed out (another execution is running).
    Caller must call release_project_lock() when done.
    """
    return await _acquire(_PROJECT_LOCKS, project_id, "project")


async def release_project_lock(project_id: str) -> None:
    """Release a project lock. Safe to call even if not held."""
    await _release(_PROJECT_LOCKS, project_id, "project")


async def acquire_file_lock(file_id: str) -> bool:
    """Acquire an exclusive lock for a file."""
    return await _acquire(_FILE_LOCKS, file_id, "file")


async def release_file_lock(file_id: str) -> None:
    """Release a file lock."""
    await _release(_FILE_LOCKS, file_id, "file")


async def acquire_session_lock(session_id: str) -> bool:
    """
    Acquire a session-level lock.
    Ensures messages in the same session are processed sequentially.
    """
    return await _acquire(_SESSION_LOCKS, session_id, "session")


async def release_session_lock(session_id: str) -> None:
    """Release a session lock."""
    await _release(_SESSION_LOCKS, session_id, "session")


async def with_project_lock(project_id: Optional[str], coro):
    """
    Context-manager-style helper: run coro under a project lock.

    If no project_id or lock acquisition fails, coro still runs
    (lock is best-effort for non-critical paths).
    """
    if not project_id:
        return await coro

    acquired = await acquire_project_lock(project_id)
    if not acquired:
        log.warning("execution_lock: project lock timeout project_id=%s — running without lock", project_id)

    try:
        return await coro
    finally:
        if acquired:
            await release_project_lock(project_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _acquire(registry: dict, key: str, scope: str) -> bool:
    """Try to acquire a lock within _LOCK_TIMEOUT seconds."""
    lock = await _get_lock(registry, key)
    t0 = time.monotonic()
    try:
        await asyncio.wait_for(lock.acquire(), timeout=_LOCK_TIMEOUT)
        elapsed = round((time.monotonic() - t0) * 1000, 1)
        log.debug("execution_lock: acquired scope=%s key=%s wait=%.1fms", scope, key, elapsed)
        return True
    except asyncio.TimeoutError:
        log.warning(
            "execution_lock: TIMEOUT scope=%s key=%s after %.1fs — another execution is running",
            scope, key, _LOCK_TIMEOUT,
        )
        return False


async def _release(registry: dict, key: str, scope: str) -> None:
    """Release a lock if it is held."""
    lock = registry.get(key)
    if lock and lock.locked():
        lock.release()
        log.debug("execution_lock: released scope=%s key=%s", scope, key)
