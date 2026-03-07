"""
manager.py – Swarm Manager
────────────────────────────
The brain of the swarm. Coordinates all agents from planning to final output.

Full execution pipeline
  1. PlannerAgent decomposes the user request into SwarmTask objects.
  2. Tasks are loaded into a TaskQueue with dependency tracking.
  3. Ready tasks are dispatched to specialist agents – in parallel where possible.
  4. Failed tasks are routed to the DebugAgent for repair (up to 2 attempts).
  5. After all tasks complete, TesterAgent validates coding outputs.
  6. Manager LLM synthesises a final combined response from all task outputs.
  7. Reflection is logged; successful solutions are stored in memory.

Parallel execution uses a ThreadPoolExecutor with a configurable worker
count (default: 4). Tasks that share no dependencies run concurrently;
tasks with dependencies wait until their prerequisites are done.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, wait, FIRST_COMPLETED
from typing import Any, Optional, TYPE_CHECKING

from .task_models     import SwarmTask, TaskResult, SwarmResult, TaskStatus, TaskType
from .task_queue      import TaskQueue
from .planner_agent   import PlannerAgent
from .research_agent  import ResearchAgent
from .coding_agent    import CodingAgent
from .debug_agent     import DebugAgent
from .tester_agent    import TesterAgent
from .file_analyst_agent import FileAnalystAgent
from .vision_agent    import VisionAgent
from .base_agent      import BaseAgent

from ..config import AGENT_MODELS, MODELS, OLLAMA_HOST

if TYPE_CHECKING:
    from ..main import MiniAssistant

logger = logging.getLogger("swarm.manager")

MAX_PARALLEL_WORKERS = 4
MAX_DEBUG_RETRIES    = 2


# ─── Manager LLM prompt ───────────────────────────────────────────────────────

_SYNTHESIS_SYSTEM = """\
You are the manager of a multi-agent AI assistant called Mini Assistant.

You have received the results from several specialist agents who worked
on different parts of a user request.

Your job:
1. Synthesise all results into a single, coherent final answer.
2. Present the information logically (use headings if the response is long).
3. If code was generated, include the relevant parts clearly.
4. If research was done, summarise key findings.
5. Highlight any remaining issues or partial failures.
6. Be direct and professional.

Do NOT say "the coding agent did X" or reference internal agents.
Write as a unified assistant response.
"""


# ─── Swarm Manager ────────────────────────────────────────────────────────────

class SwarmManager:
    """
    Orchestrates the full multi-agent swarm pipeline.

    Usage
    -----
        manager  = SwarmManager(assistant)
        result   = manager.run("Build a FastAPI login app and generate a logo")
        print(result.final_output)
    """

    def __init__(self, assistant: Optional["MiniAssistant"] = None):
        self._assistant = assistant
        self._agents    = self._build_agents()

    # ── Agent registry ────────────────────────────────────────────────────────

    def _build_agents(self) -> dict[str, BaseAgent]:
        """Initialise all agents, injecting shared components where available."""
        repair_loop      = self._assistant._get_repair_loop()      if self._assistant else None
        solution_memory  = self._assistant._solutions             if self._assistant else None
        tester           = self._assistant._tester                if self._assistant else None
        reviewer         = self._assistant._reviewer              if self._assistant else None

        agents = {
            "planner_agent":      PlannerAgent(),
            "research_agent":     ResearchAgent(),
            "coding_agent":       CodingAgent(repair_loop=repair_loop, solution_memory=solution_memory),
            "debug_agent":        DebugAgent(),
            "tester_agent":       TesterAgent(tester=tester, reviewer=reviewer),
            "file_analyst_agent": FileAnalystAgent(),
            "vision_agent":       VisionAgent(),
        }
        logger.info("Swarm agents initialised: %s", list(agents.keys()))
        return agents

    def _get_agent(self, agent_name: str) -> BaseAgent:
        """Return named agent, falling back to ResearchAgent for unknown names."""
        agent = self._agents.get(agent_name)
        if agent is None:
            logger.warning("Unknown agent '%s' – falling back to research_agent.", agent_name)
            return self._agents["research_agent"]
        return agent

    # ── Task execution ────────────────────────────────────────────────────────

    def _execute_task(
        self,
        task: SwarmTask,
        context: dict[str, TaskResult],
    ) -> TaskResult:
        """Execute one task via its assigned agent. Returns a TaskResult."""
        agent = self._get_agent(task.assigned_agent)
        logger.info(
            "[%s] → %s (%s): %s",
            task.id, task.assigned_agent, task.type, task.description[:60],
        )
        try:
            result = agent.run(task, context)
            return result
        except Exception as exc:
            logger.exception("[%s] Agent %s raised an unhandled exception.", task.id, task.assigned_agent)
            return TaskResult(
                task_id = task.id,
                agent   = task.assigned_agent,
                success = False,
                output  = "",
                error   = str(exc),
            )

    def _debug_failed_task(
        self,
        task: SwarmTask,
        context: dict[str, TaskResult],
        attempt: int = 1,
    ) -> Optional[TaskResult]:
        """Route a failed task to the DebugAgent and return its fix."""
        if attempt > MAX_DEBUG_RETRIES:
            return None

        logger.info("[%s] Routing to debug_agent (attempt %d).", task.id, attempt)
        debug_task = SwarmTask(
            id             = f"{task.id}_debug{attempt}",
            type           = TaskType.DEBUG,
            description    = f"Fix failure in task [{task.id}]: {task.description}",
            assigned_agent = "debug_agent",
            depends_on     = list(task.depends_on),
            args           = {
                "error":    task.error or "Unknown error",
                "code":     context.get(task.id, TaskResult("","",False)).output,
                "language": task.args.get("language", "python"),
            },
        )
        return self._execute_task(debug_task, context)

    # ── Parallel execution loop ───────────────────────────────────────────────

    def _run_queue(
        self,
        queue: TaskQueue,
        context: dict[str, TaskResult],
    ) -> None:
        """
        Execute all queued tasks, respecting dependencies.
        Tasks with no unmet dependencies run in parallel (up to MAX_PARALLEL_WORKERS).
        """
        active: dict[Future, SwarmTask] = {}

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS, thread_name_prefix="swarm") as pool:
            while not queue.all_done():

                # Submit all tasks that are ready and not already running
                for task in queue.get_ready_tasks():
                    queue.mark_running(task.id)
                    fut = pool.submit(self._execute_task, task, dict(context))
                    active[fut] = task

                if not active:
                    if queue.is_stalled():
                        logger.error("Queue is stalled – circular dependencies or all deps failed.")
                        break
                    # All done
                    break

                # Wait for at least one future to finish
                done, _ = wait(active, timeout=300, return_when=FIRST_COMPLETED)

                for fut in done:
                    task   = active.pop(fut)
                    try:
                        result = fut.result()
                    except Exception as exc:
                        result = TaskResult(
                            task_id=task.id, agent=task.assigned_agent,
                            success=False, error=str(exc),
                        )

                    if result.success:
                        context[task.id] = result
                        queue.mark_complete(task.id, result)
                    else:
                        # Attempt debug repair
                        fixed = self._debug_failed_task(task, context)
                        if fixed and fixed.success:
                            context[task.id] = fixed
                            queue.mark_complete(task.id, fixed)
                        else:
                            queue.mark_failed(task.id, result.error or "Agent returned failure")

    # ── Post-execution validation ─────────────────────────────────────────────

    def _validate_coding_outputs(
        self,
        queue: TaskQueue,
        context: dict[str, TaskResult],
    ) -> None:
        """
        After all tasks complete, run TesterAgent on coding outputs that
        weren't already validated inside the coding agent's repair loop.
        """
        coding_tasks = [
            t for t in queue.complete_tasks()
            if t.type == TaskType.CODING and not t.args.get("skip_validation")
        ]
        if not coding_tasks:
            return

        tester_agent = self._agents["tester_agent"]
        for c_task in coding_tasks:
            result = context.get(c_task.id)
            if not result:
                continue

            # Skip if already internally tested (CodingAgent + RepairLoop)
            if result.data.get("tests_passed") is not None:
                logger.info("[%s] Skipping external validation – already tested.", c_task.id)
                continue

            logger.info("[%s] Running external tester on coding output.", c_task.id)
            val_task = SwarmTask(
                id             = f"{c_task.id}_val",
                type           = TaskType.TESTING,
                description    = f"Validate output of task [{c_task.id}]",
                assigned_agent = "tester_agent",
                depends_on     = [c_task.id],
                args           = {"request": c_task.description, "output": result.output},
            )
            val_result = tester_agent.run(val_task, context)

            if not val_result.success:
                logger.warning("[%s] Validation failed – routing to debug.", c_task.id)
                fix = self._debug_failed_task(
                    task    = c_task,
                    context = context,
                )
                if fix and fix.success:
                    context[c_task.id] = fix
                    c_task.result = fix

    # ── Final synthesis ───────────────────────────────────────────────────────

    def _synthesise(
        self,
        request: str,
        tasks: list[SwarmTask],
        context: dict[str, TaskResult],
    ) -> str:
        """
        Ask the manager model to combine all task outputs into a final answer.
        """
        import ollama
        client = ollama.Client(host=OLLAMA_HOST)
        model  = AGENT_MODELS.get("manager", MODELS["fallback"])

        # Build a concise summary of all task outputs
        parts: list[str] = [f"User request: {request}\n\nAgent results:"]
        for task in tasks:
            result = context.get(task.id)
            if not result:
                continue
            label  = task.type.upper()
            output = result.output[:1500] if result.success else f"[FAILED] {result.error}"
            parts.append(f"\n### [{label}] {task.description[:60]}\n{output}")

        combined = "\n".join(parts)

        try:
            resp = client.chat(
                model    = model,
                messages = [
                    {"role": "system", "content": _SYNTHESIS_SYSTEM},
                    {"role": "user",   "content": combined},
                ],
                options  = {"temperature": 0.2},
            )
            return resp["message"]["content"].strip()
        except Exception as exc:
            logger.warning("Synthesis LLM failed (%s) – concatenating outputs.", exc)
            # Graceful fallback: concatenate task outputs directly
            return "\n\n---\n\n".join(
                f"**{t.description[:60]}**\n\n{context[t.id].output}"
                for t in tasks
                if t.id in context and context[t.id].success
            ) or "No successful outputs to combine."

    # ── Public API ────────────────────────────────────────────────────────────

    def run(
        self,
        request: str,
        extra_context: Optional[dict] = None,
    ) -> SwarmResult:
        """
        Run the full swarm pipeline for a user request.

        Args:
            request:       The user's raw request string.
            extra_context: Optional pre-populated context dict (task_id → TaskResult).

        Returns:
            SwarmResult with final_output and full task audit trail.
        """
        run_id  = str(uuid.uuid4())[:12]
        t_start = time.time()
        logger.info("=== Swarm run [%s] started ===", run_id)
        logger.info("Request: %s", request[:120])

        context: dict[str, TaskResult] = dict(extra_context or {})
        errors:  list[str]             = []

        # ── 1. Plan ───────────────────────────────────────────────────────────
        planner = self._agents["planner_agent"]
        assert isinstance(planner, PlannerAgent)
        tasks = planner.plan_direct(request)

        if not tasks:
            return SwarmResult(
                run_id=run_id, request=request, success=False,
                final_output="Planning failed – no tasks were generated.",
            )

        # ── 2. Execute ────────────────────────────────────────────────────────
        queue = TaskQueue(tasks)
        self._run_queue(queue, context)

        # ── 3. Post-execution validation ──────────────────────────────────────
        self._validate_coding_outputs(queue, context)

        # ── 4. Collect errors ─────────────────────────────────────────────────
        for failed in queue.failed_tasks():
            errors.append(f"[{failed.id}] {failed.description[:60]}: {failed.error}")

        # ── 5. Synthesise final response ──────────────────────────────────────
        final = self._synthesise(request, tasks, context)

        # ── 6. Log reflection ─────────────────────────────────────────────────
        if self._assistant:
            self._assistant._reflection.log(
                task          = request,
                result        = "success" if not errors else "partial",
                brain         = "swarm",
                errors_seen   = errors[:5],
                fixes_applied = [f"Swarm run {run_id}"],
            )

        duration = time.time() - t_start
        logger.info(
            "=== Swarm run [%s] complete in %.1fs | tasks=%d errors=%d ===",
            run_id, duration, len(tasks), len(errors),
        )

        task_results = {tid: res for tid, res in context.items()}

        return SwarmResult(
            run_id           = run_id,
            request          = request,
            success          = len(errors) == 0,
            final_output     = final,
            tasks            = tasks,
            task_results     = task_results,
            summary          = queue.summary().__str__(),
            errors           = errors,
            duration_seconds = duration,
        )
