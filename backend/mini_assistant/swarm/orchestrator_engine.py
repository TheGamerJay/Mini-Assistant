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
  • Real Memory Brain               (task summaries persisted across sessions)
  • Real Learning Brain             (cross-task pattern tracking)
  • Real Tool Brain + Security      (safe shell execution with guardrails)
  • Consolidated debug_log          (full event stream in task.metadata)
  • Enriched step prompts           (memory context + previous outputs injected)

Architecture
────────────
  OrchestratorEngine
    └─ creates / drives OrchestratorTask (macro, persisted)
         ├─ calls SwarmManager.run() for agent execution (micro, existing)
         ├─ MemoryBrain  – context retrieval + outcome persistence
         ├─ LearningBrain – cross-task pattern accumulation
         ├─ ToolBrain     – safe shell/git execution (DEPLOYING state)
         └─ SecurityBrain – embedded inside ToolBrain (automatic)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
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
from .task_store     import TaskStore
from .manager        import SwarmManager
from .memory_brain   import MemoryBrain
from .learning_brain import LearningBrain
from .tool_brain     import ToolBrain

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


# ─── Debug log helper ──────────────────────────────────────────────────────────

def _debug_entry(event: str, brain: str, data: Optional[dict] = None) -> dict:
    """Build a structured event entry for task.metadata['debug_log']."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type":      "event",
        "brain":     brain,
        "event":     event,
        **(data or {}),
    }


# ─── Orchestrator Engine ───────────────────────────────────────────────────────

class OrchestratorEngine:
    """
    Drives an OrchestratorTask through the workflow state machine,
    using SwarmManager for agent execution at each step.
    Real brain hooks (Memory, Learning, Tool, Security) are wired in.
    """

    def __init__(
        self,
        assistant:  Optional["MiniAssistant"] = None,
        task_store: Optional[TaskStore]       = None,
        mongo_db=None,
    ):
        self._swarm         = SwarmManager(assistant)
        self._store         = task_store or TaskStore()
        self._memory        = MemoryBrain(mongo_db=mongo_db)
        self._learning      = LearningBrain()
        self._tool          = ToolBrain()
        self._max_fix_loops = 3

    # ── Debug log ──────────────────────────────────────────────────────────────

    def _log(self, task: OrchestratorTask, event: str, brain: str,
             data: Optional[dict] = None) -> None:
        """Append a structured entry to task.metadata['debug_log']."""
        entry = _debug_entry(event, brain, data)
        task.metadata.setdefault("debug_log", []).append(entry)
        logger.debug("[%s][%s] %s %s", task.task_id[:8], brain, event,
                     str(data or "")[:80])

    # ── Agent enforcement ──────────────────────────────────────────────────────

    def _check_agent_allowed(self, task: OrchestratorTask,
                             agent_name: str, state: WorkflowState) -> None:
        allowed = AGENT_ALLOWED_STATES.get(agent_name)
        if allowed is None:
            self._log(task, "agent_check_skipped", "engine",
                      {"agent": agent_name, "state": str(state), "reason": "no restriction defined"})
            logger.warning("No state restriction for agent '%s' – allowing.", agent_name)
            return
        if state not in allowed:
            reason = (
                f"Agent '{agent_name}' NOT permitted in state '{state.value}'. "
                f"Permitted: {[s.value for s in allowed]}"
            )
            self._log(task, "agent_check_rejected", "engine",
                      {"agent": agent_name, "state": str(state), "reason": reason})
            raise PermissionError(reason)
        self._log(task, "agent_check_approved", "engine",
                  {"agent": agent_name, "state": str(state)})

    # ── Output preservation ────────────────────────────────────────────────────

    def _preserve_outputs(
        self,
        task:  OrchestratorTask,
        step:  WorkflowStep,
        output: str,
        extra:  Optional[dict] = None,
    ) -> None:
        task.preserved_outputs.update({
            "last_output":  output[:3000],
            "last_step":    step.name,
            "last_state":   step.state,
            "last_agent":   step.agent_name,
            **(extra or {}),
        })

    # ── Step prompt enrichment ─────────────────────────────────────────────────

    def _build_step_prompt(
        self,
        task:       OrchestratorTask,
        step_name:  str,
        agent_name: str,
    ) -> str:
        """
        Build a richer prompt for the agent by injecting:
        - memory context from past similar tasks
        - previous step output (if any)
        """
        parts = [f"Goal: {task.goal}",
                 f"Current step: {step_name} (agent: {agent_name})"]

        mem_block = self._memory.build_context_block(task.task_type, task.goal)
        if mem_block:
            parts.append(mem_block)

        last_out = task.preserved_outputs.get("last_output", "")
        if last_out:
            parts.append(
                f"Previous step output (use as context):\n{last_out[:1500]}"
            )

        return "\n\n".join(parts)

    # ── Tool execution (DEPLOYING state) ──────────────────────────────────────

    def _run_tool_step_sync(
        self,
        task:  OrchestratorTask,
        step:  WorkflowStep,
    ) -> tuple[bool, str, list[str]]:
        """
        For DEPLOYING state: extract a shell command from SwarmManager output,
        then run it through ToolBrain (which calls SecurityBrain internally).
        Falls back to returning the plan output if no executable command is found.
        """
        # First: ask SwarmManager to produce a deployment plan
        prompt = self._build_step_prompt(task, step.name, step.agent_name)
        swarm_result = self._swarm.run(prompt)
        plan_output  = swarm_result.final_output or ""
        task_ids     = [t.id for t in swarm_result.tasks]

        # Try to extract a shell command from the plan (lines starting with $)
        commands = [
            line.lstrip("$ ").strip()
            for line in plan_output.splitlines()
            if line.strip().startswith("$")
        ]

        if commands:
            # Run the first extracted command through ToolBrain
            cmd = commands[0]
            self._log(task, "tool_command_extracted", "tool_brain",
                      {"command": cmd, "source": "planner_output"})
            ok, tool_out, audit = self._tool.run(cmd, task_id=task.task_id)
            task.metadata.setdefault("debug_log", []).append(audit)
            self._log(task, "tool_command_result", "tool_brain",
                      {"success": ok, "exit_code": audit.get("exit_code"), "level": audit.get("level")})

            # Security block → step fails with clear reason
            if not ok and audit.get("level") == "blocked":
                task.failure_summary = (
                    f"Security Brain blocked command in '{step.name}': {audit.get('reason', '')}"
                )

            combined = f"{plan_output}\n\n[Tool output]:\n{tool_out}"
            return ok, combined, task_ids
        else:
            # No command found – treat plan output as the step output
            self._log(task, "tool_no_command_extracted", "tool_brain",
                      {"note": "no '$' prefixed command found in plan output"})
            return swarm_result.success, plan_output, task_ids

    # ── Main step execution ────────────────────────────────────────────────────

    def _run_step_sync(
        self,
        task:       OrchestratorTask,
        step:       WorkflowStep,
        agent_name: str,
        state:      WorkflowState,
    ) -> tuple[bool, str, list[str]]:
        """
        Execute one workflow step synchronously.
        DEPLOYING state goes through ToolBrain; all others through SwarmManager.
        Returns (success, output_text, swarm_task_ids).
        """
        self._check_agent_allowed(task, agent_name, state)

        logger.info(
            "[%s] Step '%s' | state=%s | agent=%s",
            task.task_id[:8], step.name, state.value, agent_name,
        )
        self._log(task, "step_started", "engine",
                  {"step": step.name, "state": str(state), "agent": agent_name})

        if state == WorkflowState.DEPLOYING:
            return self._run_tool_step_sync(task, step)

        # All other states → SwarmManager with enriched prompt
        prompt       = self._build_step_prompt(task, step.name, agent_name)
        swarm_result = self._swarm.run(prompt)
        task_ids     = [t.id for t in swarm_result.tasks]
        output       = swarm_result.final_output or ""
        return swarm_result.success, output, task_ids

    # ── Workflow driver ────────────────────────────────────────────────────────

    def _execute_workflow_sync(self, task: OrchestratorTask) -> None:
        """Drive the task through its blueprint. Called in a thread executor."""
        blueprint = _BLUEPRINTS.get(task.task_type, _BLUEPRINTS[OrchTaskType.GENERIC])
        fix_loops = 0
        step_idx  = 0

        # ── Memory Brain: task started ─────────────────────────────────────────
        mem_ctx = self._memory.load_context(task.task_type, task.goal)
        self._log(task, "task_start", "memory_brain", {
            "goal":         task.goal[:200],
            "past_context": len(mem_ctx),
        })
        self._store.save_sync(task)

        # Resume: set of already-DONE states to skip
        done_states = {
            WorkflowState(s.state)
            for s in task.steps
            if s.status == StepStatus.DONE and s.state
        }
        if done_states:
            self._log(task, "resume_skip_states", "engine",
                      {"skipping": [s.value for s in done_states]})

        while step_idx < len(blueprint):
            if task.current_state in TERMINAL_STATES:
                break

            step_name, target_state, agent_name = blueprint[step_idx]

            # Skip already-done states (resume path)
            if target_state in done_states:
                logger.info("[%s] Skip already-done: %s", task.task_id[:8], target_state)
                self._log(task, "step_skipped_already_done", "engine",
                          {"step": step_name, "state": str(target_state)})
                step_idx += 1
                continue

            # State transition
            try:
                task.transition(target_state, reason=f"Starting '{step_name}'")
                self._log(task, "state_transition", "engine",
                          {"to": str(target_state), "step": step_name})
            except ValueError as exc:
                logger.warning("[%s] Skip invalid transition to %s: %s",
                               task.task_id[:8], target_state, exc)
                self._log(task, "transition_rejected", "engine",
                          {"target": str(target_state), "reason": str(exc)})
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
                    self._preserve_outputs(task, step, output)

                    # Named checkpoint
                    cp_name = CHECKPOINT_NAMES.get(target_state)
                    if cp_name:
                        task.save_checkpoint(
                            cp_name,
                            preserved_outputs={"last_output": output[:3000]},
                        )
                        self._log(task, "checkpoint_saved", "memory_brain",
                                  {"checkpoint": cp_name, "state": str(target_state)})
                        self._memory.record_checkpoint(task, cp_name)

                    # Doc Brain hook after DOCUMENTING
                    if target_state == WorkflowState.DOCUMENTING:
                        task.metadata["doc_generated"] = {
                            "task_id":   task.task_id,
                            "task_type": task.task_type,
                            "goal":      task.goal[:200],
                            "result":    (task.result or output)[:500],
                        }
                        self._log(task, "doc_generated", "doc_brain",
                                  {"task_type": task.task_type})

                    self._log(task, "step_completed", "engine",
                              {"step": step_name, "state": str(target_state)})
                    self._store.save_sync(task)
                    step_idx += 1

                else:
                    # Always preserve whatever output we got
                    if output:
                        self._preserve_outputs(task, step, output, extra={"partial": True})

                    # Test failure → fix loop
                    if target_state == WorkflowState.TESTING and fix_loops < self._max_fix_loops:
                        fix_loops += 1
                        step.fail(error=f"Tests failed (loop {fix_loops}/{self._max_fix_loops})")
                        task.failure_summary = (
                            f"Tests failed in loop {fix_loops}. "
                            f"Last partial output preserved. Attempting fix."
                        )
                        task.increment_retry()
                        self._log(task, "fix_loop_started", "engine",
                                  {"loop": fix_loops, "max": self._max_fix_loops})
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
                                self._log(task, "checkpoint_saved", "memory_brain",
                                          {"checkpoint": cp_name})
                        else:
                            fix_step.fail(error=fix_out[:500])
                            if fix_out:
                                self._preserve_outputs(task, fix_step, fix_out,
                                                       extra={"partial": True})

                        self._log(task, "fix_loop_done", "engine",
                                  {"loop": fix_loops, "fix_ok": fix_ok})
                        task.transition(WorkflowState.TESTING,
                                        reason=f"Re-test after fix loop {fix_loops}")
                        # step_idx unchanged → re-runs testing step

                    elif task.can_retry():
                        task.increment_retry()
                        step.fail(error=f"Failed – retry {task.retry_count}/{task.max_retries}")
                        task.failure_summary = (
                            f"Step '{step_name}' failed. Partial outputs preserved. "
                            f"Retry {task.retry_count}/{task.max_retries}."
                        )
                        self._log(task, "general_retry", "engine",
                                  {"step": step_name, "retry": task.retry_count})
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
                        step.fail(error=output[:500] or "Retries exhausted")
                        task.failure_reason  = output[:500] or "Step failed after max retries"
                        task.failure_summary = (
                            f"Step '{step_name}' failed after {task.max_retries} retries. "
                            f"Last checkpoint: {task.last_checkpoint_name() or 'none'}. "
                            f"Partial outputs preserved in preserved_outputs."
                        )
                        self._log(task, "retries_exhausted", "engine",
                                  {"step": step_name, "reason": task.failure_summary[:200]})
                        task.transition(WorkflowState.FAILED, reason="Max retries exceeded")
                        break

            except PermissionError as exc:
                step.fail(error=str(exc))
                task.failure_reason  = str(exc)
                task.failure_summary = f"Agent state violation in step '{step_name}': {exc}"
                self._log(task, "agent_permission_denied", "engine",
                          {"step": step_name, "error": str(exc)[:200]})
                task.transition(WorkflowState.FAILED, reason="Agent state violation")
                break

            except Exception as exc:
                step.fail(error=str(exc))
                logger.exception("[%s] Unhandled exception in step '%s'.",
                                 task.task_id[:8], step_name)
                self._log(task, "step_exception", "engine",
                          {"step": step_name, "error": str(exc)[:200]})
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

        # ── Post-task: Memory Brain ────────────────────────────────────────────
        self._memory.save_task_summary(task)
        hook_event = (
            "task_complete" if task.current_state == WorkflowState.COMPLETED
            else "task_failed"
        )
        self._log(task, hook_event, "memory_brain", {
            "result":      (task.result or "")[:200],
            "checkpoints": [c.name for c in task.checkpoints],
        })

        # ── Post-task: Learning Brain ──────────────────────────────────────────
        try:
            lesson = self._learning.record_outcome(task)
            self._log(task, "learning_recorded", "learning_brain", {
                "outcome":   lesson["outcome"],
                "fix_loops": lesson["fix_loops"],
                "retries":   lesson["retries"],
            })
            patterns = self._learning.get_patterns()
            task.metadata["learning_patterns"] = {
                "success_rate":    patterns.get("success_rate"),
                "total_tasks":     patterns.get("total_tasks"),
                "avg_retries":     patterns.get("avg_retries"),
            }
        except Exception as exc:
            logger.warning("[%s] LearningBrain failed: %s", task.task_id[:8], exc)
            self._log(task, "learning_error", "learning_brain", {"error": str(exc)})

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
                self._log(task, "fatal_executor_error", "engine", {"error": str(exc)[:200]})
                task.force_state(WorkflowState.FAILED, reason=f"Fatal: {exc}")

        await self._store.save(task)
        logger.info("[%s] Done: state=%s retries=%d checkpoints=%d",
                    task.task_id[:8], task.current_state,
                    task.retry_count, len(task.checkpoints))
        return task

    async def resume(self, task_id: str) -> Optional[OrchestratorTask]:
        """
        Resume an interrupted/failed task from its last safe state.
        After a rollback the task is already at the checkpoint state;
        this method rehydrates preserved_outputs + assigned_agents and
        re-executes from the correct next blueprint step.
        """
        task = await self._store.load(task_id)
        if not task:
            return None

        if task.current_state in {WorkflowState.COMPLETED, WorkflowState.CANCELLED}:
            return task

        safe_state = task.last_completed_state() or WorkflowState.CREATED
        logger.info("[%s] Resuming from state=%s (currently %s)",
                    task.task_id[:8], safe_state, task.current_state)
        self._log(task, "resume_initiated", "engine", {
            "from_state":  str(task.current_state),
            "safe_state":  str(safe_state),
        })

        # Reset any stuck IN_PROGRESS or FAILED steps to PENDING
        reset_count = 0
        for step in task.steps:
            if step.status in (StepStatus.IN_PROGRESS, StepStatus.FAILED):
                step.status       = StepStatus.PENDING
                step.error        = ""
                step.started_at   = None
                step.completed_at = None
                reset_count += 1

        if reset_count:
            self._log(task, "steps_reset_to_pending", "engine",
                      {"count": reset_count})

        # Only force_state if we're not already there (avoid duplicate history entries)
        if task.current_state != safe_state:
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
                self._log(task, "resume_failed", "engine", {"error": str(exc)[:200]})
                task.force_state(WorkflowState.FAILED, reason=f"Resume failed: {exc}")

        await self._store.save(task)
        return task

    async def rollback(self, task_id: str, checkpoint_name: str) -> Optional[OrchestratorTask]:
        """
        Reset a task to a named checkpoint WITHOUT re-running it.
        - Truncates steps after checkpoint step_index
        - Resets preserved_outputs + assigned_agents to checkpoint state
        - Resets retry_count
        Caller should follow up with resume() to re-execute from that point.
        """
        task = await self._store.load(task_id)
        if not task:
            return None

        cp = task.rollback_to_checkpoint(checkpoint_name)
        if not cp:
            logger.warning("[%s] Checkpoint '%s' not found.", task.task_id[:8], checkpoint_name)
            return task   # return unchanged

        self._log(task, "rollback_complete", "engine", {
            "checkpoint":  checkpoint_name,
            "state":       cp.state,
            "step_index":  cp.step_index,
            "steps_kept":  len(task.steps),
        })
        logger.info("[%s] Rolled back to checkpoint '%s' (state=%s steps_kept=%d)",
                    task.task_id[:8], checkpoint_name, cp.state, len(task.steps))
        await self._store.save(task)
        return task

    async def cancel(self, task_id: str) -> Optional[OrchestratorTask]:
        """Mark a task as CANCELLED."""
        task = await self._store.load(task_id)
        if not task:
            return None
        if task.current_state in TERMINAL_STATES:
            return task
        self._log(task, "cancel_requested", "engine", {})
        try:
            task.transition(WorkflowState.CANCELLED, reason="Cancelled by user")
        except ValueError:
            task.force_state(WorkflowState.CANCELLED, reason="Cancelled by user")
        await self._store.save(task)
        return task
