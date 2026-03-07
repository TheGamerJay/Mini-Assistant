"""
task_queue.py – Thread-Safe Task Queue with Dependency Resolution
──────────────────────────────────────────────────────────────────
Manages the lifecycle of SwarmTasks across a single swarm run.

Key capabilities
  • Dependency tracking – a task is only "ready" when all its depends_on
    tasks have status == COMPLETE.
  • Thread safety – all mutations are protected by a RLock so the manager
    can submit tasks from multiple threads without races.
  • Retry support – failed tasks are automatically re-queued up to
    task.max_retries times before being permanently marked FAILED.
  • Progress introspection – easy checks for completion and stalled state.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from .task_models import SwarmTask, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class TaskQueue:
    """
    Thread-safe task queue for a single swarm execution.

    Usage
    -----
        queue = TaskQueue(tasks)

        # Execution loop
        while not queue.all_done():
            for task in queue.get_ready_tasks():
                queue.mark_running(task.id)
                # ... execute in thread ...
                queue.mark_complete(task.id, result)
                # or:
                queue.mark_failed(task.id, error_str)
    """

    def __init__(self, tasks: list[SwarmTask]):
        self._tasks: dict[str, SwarmTask] = {t.id: t for t in tasks}
        self._lock  = threading.RLock()
        logger.info("TaskQueue initialised with %d tasks.", len(tasks))

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get(self, task_id: str) -> Optional[SwarmTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def all_tasks(self) -> list[SwarmTask]:
        with self._lock:
            return list(self._tasks.values())

    def pending_tasks(self) -> list[SwarmTask]:
        with self._lock:
            return [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]

    def running_tasks(self) -> list[SwarmTask]:
        with self._lock:
            return [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]

    def failed_tasks(self) -> list[SwarmTask]:
        with self._lock:
            return [t for t in self._tasks.values() if t.status == TaskStatus.FAILED]

    def complete_tasks(self) -> list[SwarmTask]:
        with self._lock:
            return [t for t in self._tasks.values() if t.status == TaskStatus.COMPLETE]

    # ── Dependency resolution ─────────────────────────────────────────────────

    def _deps_satisfied(self, task: SwarmTask) -> bool:
        """Return True if every dependency task has status == COMPLETE."""
        for dep_id in task.depends_on:
            dep = self._tasks.get(dep_id)
            if dep is None:
                logger.warning(
                    "Task %s depends on unknown task %s – treating as satisfied.",
                    task.id, dep_id,
                )
                continue
            if dep.status != TaskStatus.COMPLETE:
                return False
        return True

    def get_ready_tasks(self) -> list[SwarmTask]:
        """
        Return all PENDING tasks whose dependencies are all COMPLETE,
        sorted by priority (lowest number first = highest priority).
        """
        with self._lock:
            ready = [
                t for t in self._tasks.values()
                if t.status == TaskStatus.PENDING and self._deps_satisfied(t)
            ]
            ready.sort(key=lambda t: t.priority)
            return ready

    # ── State transitions ─────────────────────────────────────────────────────

    def mark_running(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.mark_started()
                logger.debug("[%s] → RUNNING  (%s)", task_id, task.assigned_agent)

    def mark_complete(self, task_id: str, result: TaskResult) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.mark_complete(result)
                logger.info("[%s] → COMPLETE (%s): %s",
                            task_id, task.assigned_agent,
                            result.output[:80].replace("\n", " "))

    def mark_failed(self, task_id: str, error: str) -> None:
        """
        Mark a task as failed. If retries remain, reset to PENDING so
        the queue will re-schedule it. Otherwise, mark permanently FAILED.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            if task.can_retry():
                task.retries += 1
                task.status   = TaskStatus.PENDING
                task.error    = error
                logger.warning(
                    "[%s] → RETRY %d/%d (%s)",
                    task_id, task.retries, task.max_retries, error[:100],
                )
            else:
                task.mark_failed(error)
                logger.error("[%s] → FAILED (%s): %s",
                             task_id, task.assigned_agent, error[:100])

    # ── Progress checks ───────────────────────────────────────────────────────

    def all_done(self) -> bool:
        """True when every task is either COMPLETE or FAILED."""
        with self._lock:
            return all(
                t.status in (TaskStatus.COMPLETE, TaskStatus.FAILED)
                for t in self._tasks.values()
            )

    def is_stalled(self) -> bool:
        """
        True when there are still pending tasks but none are ready
        (e.g. circular dependencies or all dependencies failed).
        """
        with self._lock:
            if self.all_done():
                return False
            return len(self.get_ready_tasks()) == 0 and len(self.running_tasks()) == 0

    def completed_ids(self) -> set[str]:
        with self._lock:
            return {t.id for t in self._tasks.values() if t.status == TaskStatus.COMPLETE}

    def summary(self) -> dict:
        with self._lock:
            counts = {s: 0 for s in TaskStatus}
            for t in self._tasks.values():
                counts[t.status] += 1
            return {
                "total":    len(self._tasks),
                "complete": counts[TaskStatus.COMPLETE],
                "failed":   counts[TaskStatus.FAILED],
                "running":  counts[TaskStatus.RUNNING],
                "pending":  counts[TaskStatus.PENDING],
            }

    def __len__(self) -> int:
        return len(self._tasks)

    def __repr__(self) -> str:
        s = self.summary()
        return (
            f"TaskQueue(total={s['total']} complete={s['complete']} "
            f"failed={s['failed']} running={s['running']} pending={s['pending']})"
        )
