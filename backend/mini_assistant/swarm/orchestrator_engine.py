"""
orchestrator_engine.py – Stateful Orchestrator Engine
───────────────────────────────────────────────────────
Wraps SwarmManager with state-machine-enforced workflow governance.

Each user request becomes an OrchestratorTask that progresses through
defined WorkflowStates. The engine enforces:

  • Valid state transitions         (via OrchestratorTask.transition())
  • Agent / state rules             (agents only run in their allowed states)
  • Retry and fix-loop limits       (configurable max_fix_loops)
  • Persistent checkpoints          (TaskStore.save_sync() after each step)
  • Resume from last safe state     (OrchestratorEngine.resume())
  • Full audit trail                (OrchestratorTask.state_history + WorkflowStep list)

Architecture
────────────
  OrchestratorEngine
    └─ creates / drives OrchestratorTask (macro, persisted)
         └─ calls SwarmManager.run() for agent execution (micro, existing)
              └─ TaskQueue → per-agent SwarmTask objects

SwarmManager is run in a thread executor to avoid blocking FastAPI's
async event loop, since SwarmManager.run() uses threading internally.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional, TYPE_CHECKING

from .orchestrator_task import (
    OrchestratorTask,
    WorkflowState,
    WorkflowStep,
    StepStatus,
    OrchTaskType,
    AGENT_ALLOWED_STATES,
    TERMINAL_STATES,
)
from .task_store import TaskStore
from .manager    import SwarmManager

if TYPE_CHECKING:
    from ..main import MiniAssistant

logger = logging.getLogger("swarm.orchestrator")


# ─── Intent classification ─────────────────────────────────────────────────────

_TYPE_PATTERNS: list[tuple[str, list[str]]] = [
    (OrchTaskType.FIX,    ["fix", "bug", "error", "broken", "crash", "exception",
                            "traceback", "debug", "patch", "not working"]),
    (OrchTaskType.TEST,   ["test", "validate", "verify", "assert", "coverage",
                            "spec", "unit test", "integration test"]),
    (OrchTaskType.REVIEW, ["review", "audit", "analyse", "analyze", "inspect",
                            "check quality", "code review"]),
    (OrchTaskType.DEPLOY, ["deploy", "ship", "release", "push to production",
                            "publish", "vercel", "railway", "go live"]),
    (OrchTaskType.BUILD,  ["build", "create", "generate", "make", "implement",
                            "write", "add feature", "scaffold", "new app"]),
]

def _classify(goal: str) -> str:
    lower = goal.lower()
    for task_type, keywords in _TYPE_PATTERNS:
        if any(kw in lower for kw in keywords):
            return task_type
    return OrchTaskType.GENERIC


# ─── Workflow blueprints ───────────────────────────────────────────────────────
# Each blueprint is an ordered list of (step_name, WorkflowState, agent_name).
# The engine drives through these sequentially.
# Future agents (tool_agent, doc_agent, etc.) are listed even though they are
# not yet in SwarmManager – the engine will fall back gracefully.

_BLUEPRINTS: dict[str, list[tuple[str, WorkflowState, str]]] = {
    OrchTaskType.BUILD: [
        ("Load Context", WorkflowState.LOADING_CONTEXT, "research_agent"),
        ("Plan",         WorkflowState.PLANNING,         "planner_agent"),
        ("Code",         WorkflowState.CODING,           "coding_agent"),
        ("Review",       WorkflowState.REVIEWING,        "tester_agent"),
        ("Test",         WorkflowState.TESTING,          "tester_agent"),
        ("Document",     WorkflowState.DOCUMENTING,      "doc_agent"),
    ],
    OrchTaskType.FIX: [
        ("Load Context", WorkflowState.LOADING_CONTEXT, "research_agent"),
        ("Plan",         WorkflowState.PLANNING,         "planner_agent"),
        ("Fix",          WorkflowState.FIXING,           "debug_agent"),
        ("Test",         WorkflowState.TESTING,          "tester_agent"),
    ],
    OrchTaskType.TEST: [
        ("Load Context", WorkflowState.LOADING_CONTEXT, "research_agent"),
        ("Test",         WorkflowState.TESTING,          "tester_agent"),
    ],
    OrchTaskType.REVIEW: [
        ("Load Context", WorkflowState.LOADING_CONTEXT,  "research_agent"),
        ("Review",       WorkflowState.REVIEWING,         "file_analyst_agent"),
    ],
    OrchTaskType.DEPLOY: [
        ("Load Context", WorkflowState.LOADING_CONTEXT, "research_agent"),
        ("Plan",         WorkflowState.PLANNING,         "planner_agent"),
        ("Deploy",       WorkflowState.DEPLOYING,        "tool_agent"),
    ],
    OrchTaskType.GENERIC: [
        ("Load Context", WorkflowState.LOADING_CONTEXT, "research_agent"),
        ("Plan",         WorkflowState.PLANNING,         "planner_agent"),
        ("Code",         WorkflowState.CODING,           "coding_agent"),
        ("Test",         WorkflowState.TESTING,          "tester_agent"),
    ],
}


# ─── Orchestrator Engine ───────────────────────────────────────────────────────

class OrchestratorEngine:
    """
    Drives an OrchestratorTask through the workflow state machine,
    using SwarmManager for agent execution at each step.

    Usage (from FastAPI endpoint)
    ─────────────────────────────
        engine = OrchestratorEngine(assistant, task_store)
        task   = await engine.run("Build a REST API in FastAPI")
        print(task.current_state, task.result)
    """

    def __init__(
        self,
        assistant:  Optional["MiniAssistant"] = None,
        task_store: Optional[TaskStore]       = None,
    ):
        self._swarm         = SwarmManager(assistant)
        self._store         = task_store or TaskStore()
        self._max_fix_loops = int(3)   # max testing ↔ fixing cycles per task

    # ── Agent enforcement ──────────────────────────────────────────────────────

    def _check_agent_allowed(self, agent_name: str, state: WorkflowState) -> None:
        """
        Log a warning (or raise PermissionError) if the agent is not allowed
        to run in the current state.

        Unknown agents are warned but not blocked – forward compatibility.
        """
        allowed = AGENT_ALLOWED_STATES.get(agent_name)
        if allowed is None:
            logger.warning(
                "No state restriction defined for agent '%s' – allowing.", agent_name
            )
            return
        if state not in allowed:
            raise PermissionError(
                f"Agent '{agent_name}' is NOT permitted in state '{state.value}'. "
                f"Permitted states: {[s.value for s in allowed]}"
            )

    # ── Sync execution (runs inside a thread via run_in_executor) ─────────────

    def _run_step_sync(
        self,
        task:       OrchestratorTask,
        step:       WorkflowStep,
        agent_name: str,
        state:      WorkflowState,
    ) -> tuple[bool, str, list[str]]:
        """
        Execute one workflow step synchronously.

        Returns (success, output_text, list_of_swarm_task_ids).
        Uses TaskStore.save_sync() for mid-execution checkpoints.
        """
        self._check_agent_allowed(agent_name, state)

        logger.info(
            "[%s] Step '%s' | state=%s | agent=%s",
            task.task_id[:8], step.name, state.value, agent_name,
        )

        # Run the swarm – this is synchronous (ThreadPoolExecutor inside)
        swarm_result = self._swarm.run(task.goal)

        task_ids = [t.id for t in swarm_result.tasks]
        output   = swarm_result.final_output or ""

        # Checkpoint
        self._store.save_sync(task)

        return swarm_result.success, output, task_ids

    def _execute_workflow_sync(self, task: OrchestratorTask) -> None:
        """
        Drive the task through its blueprint states.
        Called from an asyncio thread executor.
        """
        blueprint   = _BLUEPRINTS.get(task.task_type, _BLUEPRINTS[OrchTaskType.GENERIC])
        fix_loops   = 0
        step_idx    = 0

        # Resume: skip steps whose state was already DONE
        done_states = {
            WorkflowState(s.state)
            for s in task.steps
            if s.status == StepStatus.DONE and s.state
        }

        while step_idx < len(blueprint):
            if task.current_state in TERMINAL_STATES:
                break

            step_name, target_state, agent_name = blueprint[step_idx]

            # Skip states already completed (resume path)
            if target_state in done_states:
                logger.info("[%s] Skipping already-done state=%s", task.task_id[:8], target_state)
                step_idx += 1
                continue

            # Transition
            try:
                task.transition(target_state, reason=f"Starting '{step_name}'")
            except ValueError as exc:
                logger.warning("[%s] Cannot transition to %s: %s – skipping step.",
                               task.task_id[:8], target_state, exc)
                step_idx += 1
                continue

            step = task.add_step(step_name, str(target_state), agent_name)
            step.start()
            self._store.save_sync(task)

            try:
                success, output, task_ids = self._run_step_sync(
                    task, step, agent_name, target_state
                )
                step.swarm_task_ids = task_ids

                # Track assigned agents
                for t in task_ids:
                    if agent_name not in task.assigned_agents:
                        task.assigned_agents.append(agent_name)

                if success:
                    step.complete(output=output[:2000])
                    step_idx += 1

                else:
                    # Test failure → enter fix loop if allowed
                    if target_state == WorkflowState.TESTING and fix_loops < self._max_fix_loops:
                        fix_loops += 1
                        step.fail(error=f"Tests failed (fix loop {fix_loops}/{self._max_fix_loops})")
                        task.increment_retry()
                        logger.info(
                            "[%s] Test failure – fix loop %d/%d",
                            task.task_id[:8], fix_loops, self._max_fix_loops,
                        )

                        # Insert a FIXING step dynamically
                        task.transition(WorkflowState.FIXING, reason=f"Fix loop {fix_loops}")
                        fix_step = task.add_step(
                            f"Fix (loop {fix_loops})",
                            str(WorkflowState.FIXING),
                            "debug_agent",
                        )
                        fix_step.start()
                        self._store.save_sync(task)

                        fix_success, fix_output, fix_task_ids = self._run_step_sync(
                            task, fix_step, "debug_agent", WorkflowState.FIXING
                        )
                        fix_step.swarm_task_ids = fix_task_ids
                        if fix_success:
                            fix_step.complete(output=fix_output[:2000])
                        else:
                            fix_step.fail(error=fix_output[:500])

                        # Loop back to TESTING (don't advance step_idx)
                        task.transition(WorkflowState.TESTING,
                                        reason=f"Re-test after fix loop {fix_loops}")
                        # step_idx stays pointing at TESTING step → re-runs it

                    elif task.can_retry():
                        # General retry: reset to PLANNING
                        task.increment_retry()
                        step.fail(error=f"Failed – retry {task.retry_count}/{task.max_retries}")
                        logger.info("[%s] General retry %d/%d",
                                    task.task_id[:8], task.retry_count, task.max_retries)
                        try:
                            task.transition(WorkflowState.PLANNING, reason="General retry")
                            step_idx = 0   # restart from planning step
                            done_states.clear()
                        except ValueError:
                            # Cannot loop back – fail
                            task.failure_reason = output[:500] or "Step failed"
                            task.transition(WorkflowState.FAILED, reason="Cannot retry from here")
                            break

                    else:
                        # Out of retries
                        step.fail(error=output[:500] or "Step failed – retries exhausted")
                        task.failure_reason = output[:500] or "Step failed after max retries"
                        task.transition(WorkflowState.FAILED, reason="Max retries exceeded")
                        break

            except PermissionError as exc:
                step.fail(error=str(exc))
                logger.error("[%s] Agent state violation: %s", task.task_id[:8], exc)
                task.failure_reason = str(exc)
                task.transition(WorkflowState.FAILED, reason="Agent state violation")
                break

            except Exception as exc:
                step.fail(error=str(exc))
                logger.exception("[%s] Unhandled exception in step '%s'.", task.task_id[:8], step_name)
                if task.can_retry():
                    task.increment_retry()
                    logger.info("[%s] Retrying after exception (%d/%d).",
                                task.task_id[:8], task.retry_count, task.max_retries)
                    try:
                        task.transition(WorkflowState.PLANNING, reason=f"Retry after exception: {exc}")
                        step_idx = 0
                        done_states.clear()
                    except ValueError:
                        task.failure_reason = str(exc)
                        task.transition(WorkflowState.FAILED, reason=str(exc))
                        break
                else:
                    task.failure_reason = str(exc)
                    task.transition(WorkflowState.FAILED, reason=str(exc))
                    break

            self._store.save_sync(task)

        # Mark completed if we exited without failure
        if task.current_state not in TERMINAL_STATES:
            done_steps = [s for s in task.steps if s.status == StepStatus.DONE]
            task.result = done_steps[-1].output if done_steps else "Completed successfully."
            task.transition(WorkflowState.COMPLETED, reason="All steps completed")

        self._store.save_sync(task)

    # ── Public async API ───────────────────────────────────────────────────────

    async def run(
        self,
        goal:     str,
        metadata: Optional[dict] = None,
    ) -> OrchestratorTask:
        """
        Create and execute a new OrchestratorTask for the user's goal.

        Runs SwarmManager in a thread executor so the FastAPI event loop
        is not blocked. Persists to TaskStore before returning.

        Returns the fully populated OrchestratorTask.
        """
        task_type = _classify(goal)
        task      = OrchestratorTask(goal=goal, task_type=task_type, metadata=metadata or {})

        logger.info("[%s] New %s task: %s", task.task_id[:8], task_type, goal[:80])
        self._store.save_sync(task)   # persist immediately so it's queryable

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._execute_workflow_sync, task)
        except Exception as exc:
            logger.exception("[%s] Fatal error in workflow executor.", task.task_id[:8])
            if task.current_state not in TERMINAL_STATES:
                task.failure_reason = str(exc)
                task.force_state(WorkflowState.FAILED, reason=f"Fatal: {exc}")

        # Final async save (syncs JSON state to MongoDB if configured)
        await self._store.save(task)

        logger.info(
            "[%s] Finished: state=%s retries=%d",
            task.task_id[:8], task.current_state, task.retry_count,
        )
        return task

    async def resume(self, task_id: str) -> Optional[OrchestratorTask]:
        """
        Resume an interrupted task from its last successfully completed state.

        - If already COMPLETED or CANCELLED: returns as-is (nothing to do).
        - If FAILED: resets state to last DONE step's state and re-runs.
        - If stuck IN_PROGRESS: re-runs from where it left off.

        Returns None if task_id is not found in the store.
        """
        task = await self._store.load(task_id)
        if not task:
            logger.error("Cannot resume: task %s not found.", task_id)
            return None

        if task.current_state in {WorkflowState.COMPLETED, WorkflowState.CANCELLED}:
            logger.info("[%s] Already %s – nothing to resume.", task.task_id[:8], task.current_state)
            return task

        # Determine safe resume state
        safe_state = task.last_completed_state() or WorkflowState.CREATED

        logger.info(
            "[%s] Resuming from state=%s (was %s)",
            task.task_id[:8], safe_state, task.current_state,
        )

        # Reset any in-progress or failed steps to pending
        for step in task.steps:
            if step.status in (StepStatus.IN_PROGRESS, StepStatus.FAILED):
                step.status      = StepStatus.PENDING
                step.error       = ""
                step.started_at  = None
                step.completed_at = None

        # Force reset to safe state (bypass normal transition validation)
        task.force_state(safe_state, reason=f"Resumed – was {task.current_state}")
        task.failure_reason = None

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._execute_workflow_sync, task)
        except Exception as exc:
            logger.exception("[%s] Fatal error during resume.", task.task_id[:8])
            if task.current_state not in TERMINAL_STATES:
                task.failure_reason = str(exc)
                task.force_state(WorkflowState.FAILED, reason=f"Resume failed: {exc}")

        await self._store.save(task)
        return task

    async def cancel(self, task_id: str) -> Optional[OrchestratorTask]:
        """
        Mark a task as CANCELLED. Only works if the task is not already terminal.
        (Note: if the task is mid-execution in a thread, the thread will complete
        its current step before the state is overwritten – cancellation is
        cooperative, not preemptive.)
        """
        task = await self._store.load(task_id)
        if not task:
            return None
        if task.current_state in TERMINAL_STATES:
            return task
        try:
            task.transition(WorkflowState.CANCELLED, reason="Cancelled by user")
        except ValueError:
            task.force_state(WorkflowState.CANCELLED, reason="Cancelled by user")
        await self._store.save(task)
        return task
