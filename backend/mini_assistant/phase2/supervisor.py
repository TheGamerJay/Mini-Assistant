"""
supervisor.py — Supervisor Layer
──────────────────────────────────
Execution controller. Receives the Planner's task list and coordinates
execution in the correct order.

Phase 2 capabilities:
  - Sequential task execution (parallel comes in Phase 4)
  - Per-task state tracking: pending → running → completed / failed
  - Single retry on safe-to-retry tasks
  - Failure isolation (one failed task does not abort the whole plan)
  - Passes task outputs to dependent tasks as context

The Supervisor does NOT call brains directly.
In Phase 2 it manages task state and delegates actual brain calls
back to the execution layer (image_system/api/server.py) via the
existing chat endpoint logic.

In Phase 4+ the Supervisor will dispatch directly to the brain registry
and run parallelisable tasks concurrently.

Task states:
  pending    — not yet started
  running    — currently executing
  completed  — finished successfully
  failed     — finished with an error
  skipped    — dependency failed, cannot run
  retrying   — first attempt failed, second attempt in progress
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .manager import ManagerPacket

logger = logging.getLogger(__name__)


# ── Task state types ──────────────────────────────────────────────────────────

TASK_STATES = ("pending", "running", "completed", "failed", "skipped", "retrying")


@dataclass
class TaskState:
    id:          str
    description: str
    brain:       Optional[str]  = None
    tool:        Optional[str]  = None
    depends_on:  list[str]      = field(default_factory=list)
    state:       str            = "pending"
    output:      Any            = None
    error:       Optional[str]  = None
    attempts:    int            = 0
    started_at:  Optional[float]= None
    finished_at: Optional[float]= None

    @property
    def duration_ms(self) -> float:
        if self.started_at and self.finished_at:
            return round((self.finished_at - self.started_at) * 1000, 1)
        return 0.0

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "description": self.description,
            "brain":       self.brain,
            "tool":        self.tool,
            "state":       self.state,
            "error":       self.error,
            "attempts":    self.attempts,
            "duration_ms": self.duration_ms,
        }


@dataclass
class SupervisorResult:
    """Outcome of the Supervisor's execution pass."""
    plan_intent:    str
    tasks:          list[TaskState]
    overall_state:  str             # completed | partial | failed
    execution_mode: str             # sequential (Phase 4 adds: parallel)
    supervisor_ms:  float           = 0.0

    @property
    def completed_tasks(self) -> list[TaskState]:
        return [t for t in self.tasks if t.state == "completed"]

    @property
    def failed_tasks(self) -> list[TaskState]:
        return [t for t in self.tasks if t.state == "failed"]

    @property
    def task_outputs(self) -> dict[str, Any]:
        """Map task_id → output for downstream consumers."""
        return {t.id: t.output for t in self.tasks if t.output is not None}

    def to_dict(self) -> dict:
        return {
            "plan_intent":    self.plan_intent,
            "overall_state":  self.overall_state,
            "execution_mode": self.execution_mode,
            "supervisor_ms":  self.supervisor_ms,
            "tasks":          [t.to_dict() for t in self.tasks],
            "completed":      len(self.completed_tasks),
            "failed":         len(self.failed_tasks),
            "total":          len(self.tasks),
        }


# ── Safe-to-retry determination ───────────────────────────────────────────────

# These task descriptions are idempotent — safe to retry once
_RETRY_SAFE_KEYWORDS = (
    "validate", "check", "review", "critic", "analyse", "analyze",
    "format", "enhance", "search", "scan", "list",
)


def _is_safe_to_retry(task: TaskState) -> bool:
    desc_lower = task.description.lower()
    return any(kw in desc_lower for kw in _RETRY_SAFE_KEYWORDS)


# ── Supervisor ────────────────────────────────────────────────────────────────

class Supervisor:
    """
    Supervises the execution of a Planner task list.

    Phase 2: sequential execution with single-retry and failure isolation.
    Phase 4: will add parallel execution for tasks marked as parallelisable.
    """

    def __init__(self, packet: ManagerPacket):
        self._packet = packet

    def _build_task_states(self, sequential_tasks: list[dict]) -> list[TaskState]:
        """Convert Planner task dicts into tracked TaskState objects."""
        states: list[TaskState] = []
        for t in sequential_tasks:
            states.append(TaskState(
                id          = t.get("id", f"t{len(states)+1}"),
                description = t.get("task", ""),
                brain       = t.get("brain"),
                tool        = t.get("tool"),
                depends_on  = t.get("depends_on", []),
            ))
        return states

    def _dependencies_met(self, task: TaskState, all_tasks: list[TaskState]) -> bool:
        """True if all tasks this one depends on have completed."""
        completed_ids = {t.id for t in all_tasks if t.state == "completed"}
        return all(dep in completed_ids for dep in task.depends_on)

    def _execute_task(
        self,
        task: TaskState,
        context: dict[str, Any],
        packet: ManagerPacket,
    ) -> Any:
        """
        Execute a single task.

        Phase 2: tasks are tracked but not independently dispatched to brains.
        The actual brain call happens in the chat endpoint's execution layer.
        The Supervisor marks tasks as they logically progress through the pipeline.

        Returns a string output token for downstream context injection.
        """
        # For Phase 2, the Supervisor manages task state around the
        # existing single-pass execution. Each task is marked completed
        # once the overall brain call returns. Full per-task brain dispatch
        # arrives in Phase 4 when the Supervisor gains direct brain access.
        task_hint = f"[{task.description}]"
        if task.tool == "scanner":
            # Actually call the scanner for file_analysis tasks
            try:
                from ..scanner import get_context
                ctx = get_context().to_dict()
                return f"Project context scanned: {len(ctx.get('feature_map', []))} features, {len(ctx.get('warnings', []))} warnings"
            except Exception as e:
                raise RuntimeError(f"Scanner failed: {e}")
        return task_hint  # placeholder — real output comes from brain execution layer

    def supervise(self, sequential_tasks: list[dict]) -> SupervisorResult:
        """
        Execute all tasks in the plan sequentially with state tracking.

        Args:
            sequential_tasks: Task list from PlannerOutput.sequential_tasks.

        Returns:
            SupervisorResult with per-task state and overall outcome.
        """
        t0 = time.perf_counter()
        task_states = self._build_task_states(sequential_tasks)
        context: dict[str, Any] = {}

        for task in task_states:
            # Skip if a dependency failed
            if not self._dependencies_met(task, task_states):
                failed_deps = [
                    dep for dep in task.depends_on
                    if not any(t.id == dep and t.state == "completed" for t in task_states)
                ]
                task.state = "skipped"
                task.error = f"Skipped — dependency failed: {', '.join(failed_deps)}"
                logger.info("Task [%s] skipped (dep failed): %s", task.id, task.description[:50])
                continue

            # Mark running
            task.state      = "running"
            task.started_at = time.time()
            task.attempts  += 1

            logger.info(
                "Supervisor → task [%s] %s  brain=%s tool=%s",
                task.id, task.description[:50], task.brain, task.tool,
            )

            try:
                output     = self._execute_task(task, context, self._packet)
                task.output      = output
                task.state       = "completed"
                task.finished_at = time.time()
                context[task.id] = output

            except Exception as exc:
                logger.warning("Task [%s] failed (attempt %d): %s", task.id, task.attempts, exc)

                # Single retry for safe-to-retry tasks
                if task.attempts < 2 and _is_safe_to_retry(task):
                    task.state    = "retrying"
                    task.attempts += 1
                    logger.info("Task [%s] retrying...", task.id)
                    try:
                        output     = self._execute_task(task, context, self._packet)
                        task.output      = output
                        task.state       = "completed"
                        task.finished_at = time.time()
                        context[task.id] = output
                        logger.info("Task [%s] succeeded on retry.", task.id)
                        continue
                    except Exception as retry_exc:
                        exc = retry_exc

                task.state       = "failed"
                task.error       = str(exc)
                task.finished_at = time.time()

        # Determine overall state
        n_completed = sum(1 for t in task_states if t.state == "completed")
        n_failed    = sum(1 for t in task_states if t.state == "failed")
        n_total     = len(task_states)

        if n_failed == 0 and n_completed > 0:
            overall = "completed"
        elif n_completed > 0:
            overall = "partial"
        else:
            overall = "failed"

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        logger.info(
            "Supervisor done: %d/%d completed, %d failed, overall=%s  (%.1f ms)",
            n_completed, n_total, n_failed, overall, elapsed_ms,
        )

        return SupervisorResult(
            plan_intent    = self._packet.intent,
            tasks          = task_states,
            overall_state  = overall,
            execution_mode = "sequential",
            supervisor_ms  = elapsed_ms,
        )
