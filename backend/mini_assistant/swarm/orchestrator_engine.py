"""
orchestrator_engine.py – Stateful Orchestrator Engine
───────────────────────────────────────────────────────
Wraps SwarmManager with state-machine-enforced workflow governance.

Each user request becomes an OrchestratorTask that progresses through
defined WorkflowStates. The engine enforces:

  • Valid state transitions         (via OrchestratorTask.transition())
  • Agent / state rules             (agents only run in their allowed states)
  • Named checkpoints at milestones (post_plan, post_codegen, post_test, …)
  • Partial output preservation     (last good outputs always kept on failure)
  • Retry and fix-loop limits       (configurable max_fix_loops)
  • Persistent checkpoints          (TaskStore.save_sync() after each step)
  • Resume from last safe state     (OrchestratorEngine.resume())
  • Rollback to named checkpoint    (OrchestratorEngine.rollback())
  • Agent lifecycle hooks           (Memory Brain, Learning Brain stubs)
  • Full audit trail                (OrchestratorTask.state_history + steps)

Architecture
────────────
  OrchestratorEngine
    └─ creates / drives OrchestratorTask (macro, persisted)
         └─ calls SwarmManager.run() for agent execution (micro, existing)
              └─ TaskQueue → per-agent SwarmTask objects
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

from .orchestrator_task import (
    OrchestratorTask,
    WorkflowState,
    WorkflowStep,
    StepStatus,
    OrchTaskType,
    AGENT_ALLOWED_STATES,
    CHECKPOINT_NAMES,
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


# ─── Agent lifecycle hooks (stubs – replace with real agents in Phase 8) ───────

def _hook_memory_brain(task: OrchestratorTask, event: str, data: Optional[dict] = None) -> None:
    """
    Memory Brain hook – called at key task lifecycle events.
    Stub: logs the event and stores a summary in task.metadata.
    Replace with real Memory Brain call in Phase 8.
    Events: task_start, checkpoint_saved, task_complete, task_failed
    """
    entry = {"event": event, "state": str(task.current_state), **(data or {})}
    task.metadata.setdefault("memory_log", []).append(entry)
    logger.debug("[%s] Memory Brain hook: %s", task.task_id[:8], event)


def _hook_learning_brain(task: OrchestratorTask, event: str) -> None:
    """
    Learning Brain hook – called only on task_complete or task_failed.
    Stub: records a lesson summary in task.metadata.
    Replace with real Learning Brain call in Phase 9.
    """
    if event not in ("task_complete", "task_failed"):
        return
    lesson = {
        "event":        event,
        "task_type":    task.task_type,
        "retries":      task.retry_count,
        "checkpoints":  [c.name for c in task.checkpoints],
        "outcome":      str(task.current_state),
        "failure":      task.failure_summary or task.failure_reason or "",
    }
    task.metadata.setdefault("learning_log", []).append(lesson)
    logger.debug("[%s] Learning Brain hook: %s", task.task_id[:8], event)


def _hook_doc_brain(task: OrchestratorTask) -> None:
    """
    Documentation Brain hook – called when DOCUMENTING state completes.
    Stub: records a doc entry in metadata.
    Replace with real Documentation Brain call in Phase 8.
    """
    task.metadata["doc_generated"] = {
        "task_id":    task.task_id,
        "task_type":  task.task_type,
        "goal":       task.goal[:200],
        "result":     (task.result or "")[:500],
    }
    logger.debug("[%s] Doc Brain hook fired.", task.task_id[:8])


# ─── Orchestrator Engine ───────────────────────────────────────────────────────

class OrchestratorEngine:
    """
    Drives an OrchestratorTask through the workflow state machine,
    using SwarmManager for agent execution at each step.
    """

    def __init__(
        self,
        assistant:  Optional["MiniAssistant"] = None,
        task_store: Optional[TaskStore]       = None,
    ):
        self._swarm         = SwarmManager(assistant)
        self._store         = task_store or TaskStore()
        self._max_fix_loops = 3

    # ── Agent enforcement ──────────────────────────────────────────────────────

    def _check_agent_allowed(self, agent_name: str, state: WorkflowState) -> None:
        allowed = AGENT_ALLOWED_STATES.get(agent_name)
        if allowed is None:
            logger.warning("No state restriction for agent '%s' – allowing.", agent_name)
            return
        if state not in allowed:
            raise PermissionError(
                f"Agent '{agent_name}' NOT permitted in state '{state.value}'. "
                f"Permitted: {[s.value for s in allowed]}"
            )

    # ── Output preservation (called on EVERY successful step) ─────────────────

    def _preserve_outputs(
        self,
        task:       OrchestratorTask,
        step:       WorkflowStep,
        output:     str,
        extra:      Optional[dict] = None,
    ) -> None:
        """
        Update task.preserved_outputs with the latest good output.
        Called after every successful step so failure never wipes useful work.
        """
        task.preserved_outputs.update({
            "last_output":    output[:3000],
            "last_step":      step.name,
            "last_state":     step.state,
            "last_agent":     step.agent_name,
            **(extra or {}),
        })

    # ── Sync execution ─────────────────────────────────────────────────────────

    def _run_step_sync(
        self,
        task:       OrchestratorTask,
        step:       WorkflowStep,
        agent_name: str,
        state:      WorkflowState,
    ) -> tuple[bool, str, list[str]]:
        """
        Execute one workflow step synchronously via SwarmManager.
        Returns (success, output_text, swarm_task_ids).
        """
        self._check_agent_allowed(agent_name, state)

        logger.info(
            "[%s] Step '%s' | state=%s | agent=%s",
            task.task_id[:8], step.name, state.value, agent_name,
        )

        swarm_result = self._swarm.run(task.goal)
        task_ids = [t.id for t in swarm_result.tasks]
        output   = swarm_result.final_output or ""

        return swarm_result.success, output, task_ids

    def _execute_workflow_sync(self, task: OrchestratorTask) -> None:
        """Drive the task through its blueprint. Called in a thread executor."""
        blueprint = _BLUEPRINTS.get(task.task_type, _BLUEPRINTS[OrchTaskType.GENERIC])
        fix_loops = 0
        step_idx  = 0

        # Memory Brain: task started
        _hook_memory_brain(task, "task_start", {"goal": task.goal[:200]})
        self._store.save_sync(task)

        # Resume: set of already-DONE states to skip
        done_states = {
            WorkflowState(s.state)
            for s in task.steps
            if s.status == StepStatus.DONE and s.state
        }

        while step_idx < len(blueprint):
            if task.current_state in TERMINAL_STATES:
                break

            step_name, target_state, agent_name = blueprint[step_idx]

            # Skip already-done states (resume path)
            if target_state in done_states:
                logger.info("[%s] Skip already-done: %s", task.task_id[:8], target_state)
                step_idx += 1
                continue

            # State transition
            try:
                task.transition(target_state, reason=f"Starting '{step_name}'")
            except ValueError as exc:
                logger.warning("[%s] Skip invalid transition to %s: %s",
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
                if agent_name not in task.assigned_agents:
                    task.assigned_agents.append(agent_name)

                if success:
                    step.complete(output=output[:2000])

                    # Always preserve outputs on success
                    self._preserve_outputs(task, step, output)

                    # Save named checkpoint if this state has one
                    cp_name = CHECKPOINT_NAMES.get(target_state)
                    if cp_name:
                        task.save_checkpoint(
                            cp_name,
                            preserved_outputs={"last_output": output[:3000]},
                        )
                        _hook_memory_brain(task, "checkpoint_saved", {"checkpoint": cp_name})

                    # Doc Brain hook after DOCUMENTING
                    if target_state == WorkflowState.DOCUMENTING:
                        _hook_doc_brain(task)

                    self._store.save_sync(task)
                    step_idx += 1

                else:
                    # ── Failure handling ───────────────────────────────────────
                    # Always preserve whatever output we got (partial work)
                    if output:
                        self._preserve_outputs(task, step, output,
                                               extra={"partial": True})

                    # Test failure → fix loop
                    if target_state == WorkflowState.TESTING and fix_loops < self._max_fix_loops:
                        fix_loops += 1
                        step.fail(error=f"Tests failed (loop {fix_loops}/{self._max_fix_loops})")
                        task.failure_summary = (
                            f"Tests failed in loop {fix_loops}. "
                            f"Last partial output preserved. Attempting fix."
                        )
                        task.increment_retry()
                        logger.info("[%s] Fix loop %d/%d", task.task_id[:8],
                                    fix_loops, self._max_fix_loops)

                        task.transition(WorkflowState.FIXING, reason=f"Fix loop {fix_loops}")
                        fix_step = task.add_step(
                            f"Fix (loop {fix_loops})",
                            str(WorkflowState.FIXING), "debug_agent",
                        )
                        fix_step.start()
                        self._store.save_sync(task)

                        fix_ok, fix_out, fix_ids = self._run_step_sync(
                            task, fix_step, "debug_agent", WorkflowState.FIXING
                        )
                        fix_step.swarm_task_ids = fix_ids
                        if fix_ok:
                            fix_step.complete(output=fix_out[:2000])
                            self._preserve_outputs(task, fix_step, fix_out)
                            cp_name = CHECKPOINT_NAMES.get(WorkflowState.FIXING)
                            if cp_name:
                                task.save_checkpoint(cp_name)
                        else:
                            fix_step.fail(error=fix_out[:500])
                            # Still preserve whatever came back
                            if fix_out:
                                self._preserve_outputs(task, fix_step, fix_out,
                                                       extra={"partial": True})

                        task.transition(WorkflowState.TESTING,
                                        reason=f"Re-test after fix loop {fix_loops}")
                        # step_idx unchanged → re-runs testing step

                    elif task.can_retry():
                        # General retry from PLANNING
                        task.increment_retry()
                        step.fail(error=f"Failed – retry {task.retry_count}/{task.max_retries}")
                        task.failure_summary = (
                            f"Step '{step_name}' failed. Partial outputs preserved. "
                            f"Retry {task.retry_count}/{task.max_retries}."
                        )
                        try:
                            task.transition(WorkflowState.PLANNING, reason="General retry")
                            step_idx   = 0
                            done_states.clear()
                        except ValueError:
                            task.failure_reason  = output[:500] or "Step failed"
                            task.failure_summary = (
                                f"Step '{step_name}' failed and cannot retry from here. "
                                f"Last checkpoint: {task.last_checkpoint_name() or 'none'}."
                            )
                            task.transition(WorkflowState.FAILED,
                                            reason="Cannot retry from here")
                            break

                    else:
                        # Out of retries – fail and preserve everything we have
                        step.fail(error=output[:500] or "Retries exhausted")
                        task.failure_reason  = output[:500] or "Step failed after max retries"
                        task.failure_summary = (
                            f"Step '{step_name}' failed after {task.max_retries} retries. "
                            f"Last checkpoint: {task.last_checkpoint_name() or 'none'}. "
                            f"Partial outputs preserved in preserved_outputs."
                        )
                        task.transition(WorkflowState.FAILED, reason="Max retries exceeded")
                        break

            except PermissionError as exc:
                step.fail(error=str(exc))
                task.failure_reason  = str(exc)
                task.failure_summary = f"Agent state violation in step '{step_name}': {exc}"
                task.transition(WorkflowState.FAILED, reason="Agent state violation")
                break

            except Exception as exc:
                step.fail(error=str(exc))
                logger.exception("[%s] Unhandled exception in step '%s'.",
                                 task.task_id[:8], step_name)
                if task.can_retry():
                    task.increment_retry()
                    task.failure_summary = (
                        f"Exception in '{step_name}': {exc!s:.200}. "
                        f"Retrying ({task.retry_count}/{task.max_retries})."
                    )
                    try:
                        task.transition(WorkflowState.PLANNING,
                                        reason=f"Retry after: {exc!s:.100}")
                        step_idx   = 0
                        done_states.clear()
                    except ValueError:
                        task.failure_reason  = str(exc)
                        task.failure_summary = (
                            f"Fatal exception in '{step_name}': {exc!s:.300}. "
                            f"Last checkpoint: {task.last_checkpoint_name() or 'none'}."
                        )
                        task.transition(WorkflowState.FAILED, reason=str(exc))
                        break
                else:
                    task.failure_reason  = str(exc)
                    task.failure_summary = (
                        f"Fatal exception in '{step_name}' after all retries: {exc!s:.300}. "
                        f"Last checkpoint: {task.last_checkpoint_name() or 'none'}. "
                        f"Preserved outputs available."
                    )
                    task.transition(WorkflowState.FAILED, reason=str(exc))
                    break

            self._store.save_sync(task)

        # ── Mark completed ─────────────────────────────────────────────────────
        if task.current_state not in TERMINAL_STATES:
            done_steps = [s for s in task.steps if s.status == StepStatus.DONE]
            task.result = done_steps[-1].output if done_steps else "Completed successfully."
            task.transition(WorkflowState.COMPLETED, reason="All steps completed")

        # ── Post-task hooks ────────────────────────────────────────────────────
        hook_event = (
            "task_complete" if task.current_state == WorkflowState.COMPLETED
            else "task_failed"
        )
        _hook_memory_brain(task, hook_event, {
            "result":      (task.result or "")[:300],
            "checkpoints": [c.name for c in task.checkpoints],
        })
        _hook_learning_brain(task, hook_event)

        self._store.save_sync(task)

    # ── Public async API ───────────────────────────────────────────────────────

    async def run(
        self,
        goal:     str,
        metadata: Optional[dict] = None,
    ) -> OrchestratorTask:
        """Create and execute a new OrchestratorTask."""
        task_type = _classify(goal)
        task      = OrchestratorTask(goal=goal, task_type=task_type, metadata=metadata or {})

        logger.info("[%s] New %s task: %s", task.task_id[:8], task_type, goal[:80])
        self._store.save_sync(task)

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._execute_workflow_sync, task)
        except Exception as exc:
            logger.exception("[%s] Fatal executor error.", task.task_id[:8])
            if task.current_state not in TERMINAL_STATES:
                task.failure_reason  = str(exc)
                task.failure_summary = (
                    f"Fatal error: {exc!s:.300}. "
                    f"Last checkpoint: {task.last_checkpoint_name() or 'none'}. "
                    f"Preserved outputs available."
                )
                task.force_state(WorkflowState.FAILED, reason=f"Fatal: {exc}")

        await self._store.save(task)
        logger.info("[%s] Done: state=%s retries=%d checkpoints=%d",
                    task.task_id[:8], task.current_state,
                    task.retry_count, len(task.checkpoints))
        return task

    async def resume(self, task_id: str) -> Optional[OrchestratorTask]:
        """Resume an interrupted/failed task from its last safe state."""
        task = await self._store.load(task_id)
        if not task:
            return None

        if task.current_state in {WorkflowState.COMPLETED, WorkflowState.CANCELLED}:
            return task

        safe_state = task.last_completed_state() or WorkflowState.CREATED
        logger.info("[%s] Resuming from state=%s (was %s)",
                    task.task_id[:8], safe_state, task.current_state)

        for step in task.steps:
            if step.status in (StepStatus.IN_PROGRESS, StepStatus.FAILED):
                step.status       = StepStatus.PENDING
                step.error        = ""
                step.started_at   = None
                step.completed_at = None

        task.force_state(safe_state, reason=f"Resumed – was {task.current_state}")
        task.failure_reason  = None
        task.failure_summary = None

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._execute_workflow_sync, task)
        except Exception as exc:
            if task.current_state not in TERMINAL_STATES:
                task.failure_reason  = str(exc)
                task.failure_summary = f"Resume failed: {exc!s:.300}"
                task.force_state(WorkflowState.FAILED, reason=f"Resume failed: {exc}")

        await self._store.save(task)
        return task

    async def rollback(self, task_id: str, checkpoint_name: str) -> Optional[OrchestratorTask]:
        """
        Reset a task to a named checkpoint WITHOUT re-running it.
        Caller should follow up with resume() to re-execute from that point.
        """
        task = await self._store.load(task_id)
        if not task:
            return None

        cp = task.rollback_to_checkpoint(checkpoint_name)
        if not cp:
            logger.warning("[%s] Checkpoint '%s' not found.", task.task_id[:8], checkpoint_name)
            return task   # return unchanged

        logger.info("[%s] Rolled back to checkpoint '%s' (state=%s)",
                    task.task_id[:8], checkpoint_name, cp.state)
        await self._store.save(task)
        return task

    async def cancel(self, task_id: str) -> Optional[OrchestratorTask]:
        """Mark a task as CANCELLED."""
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
