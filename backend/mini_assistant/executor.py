"""
executor.py – Step Executor
────────────────────────────
Runs the steps produced by the planner sequentially.

Each step either:
  - Calls a tool  (search, python, file_read, image_gen, screenshot, computer)
  - Calls a brain (coding, vision, research, fast)

Outputs from earlier steps are injected as context into later steps
that list them in `depends_on`.

Usage:
    plan   = planner.plan(message)
    result = executor.execute(plan, assistant)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from .planner import Plan, Step

if TYPE_CHECKING:
    from .main import MiniAssistant

logger = logging.getLogger(__name__)


# ─── Result types ─────────────────────────────────────────────────────────────

@dataclass
class StepResult:
    step_id: str
    task: str
    output: Any           # str, dict, list – whatever the tool/brain returned
    success: bool = True
    error: Optional[str] = None


@dataclass
class ExecutionResult:
    goal: str
    steps: list[StepResult]
    final_output: str = ""   # The last successful text output
    success: bool = True

    @property
    def all_outputs(self) -> dict[str, Any]:
        """Map step_id → output for dependency injection."""
        return {r.step_id: r.output for r in self.steps}

    @property
    def errors(self) -> list[str]:
        return [r.error for r in self.steps if r.error]


# ─── Executor ─────────────────────────────────────────────────────────────────

class Executor:
    """
    Execute a Plan step by step.

    Requires a MiniAssistant instance to access brains and tools.
    """

    def __init__(self, assistant: "MiniAssistant"):
        self._assistant = assistant

    # ── Tool dispatchers ──────────────────────────────────────────────────────

    def _run_search(self, step: Step, context: dict) -> str:
        from .tools.search import web_search
        query = step.args.get("query") or step.task
        results = web_search(query)
        if not results:
            return "No results found."
        lines = []
        for r in results[:5]:
            lines.append(f"[{r.get('title','')}]({r.get('url','')})\n{r.get('body','')}")
        return "\n\n".join(lines)

    def _run_python(self, step: Step, context: dict) -> dict:
        from .tools.code_exec import execute_python
        code = step.args.get("code", "")
        if not code:
            # Extract code from prior step output if available
            for dep in step.depends_on:
                dep_out = context.get(dep, "")
                if isinstance(dep_out, str) and "```python" in dep_out:
                    import re
                    m = re.search(r"```python\n(.*?)```", dep_out, re.DOTALL)
                    if m:
                        code = m.group(1)
                        break
        if not code:
            return {"success": False, "error": "No code to execute"}
        return execute_python(code)

    def _run_file_read(self, step: Step, context: dict) -> str:
        from .tools.file_reader import read_path
        path = step.args.get("path", ".")
        return read_path(path)

    def _run_image_gen(self, step: Step, context: dict) -> dict:
        from .tools.image_gen import generate_image
        prompt = step.args.get("prompt") or step.task
        return generate_image(prompt)

    def _run_screenshot(self, step: Step, context: dict) -> dict:
        from .tools.computer import take_screenshot
        return take_screenshot()

    def _run_computer(self, step: Step, context: dict) -> dict:
        from .tools.computer import click, type_text, press_key, open_app
        action = step.args.get("action", "")
        if action == "click":
            return click(step.args.get("x", 0), step.args.get("y", 0))
        elif action == "type":
            return type_text(step.args.get("text", ""))
        elif action == "press":
            return press_key(step.args.get("key", ""))
        elif action == "open":
            return open_app(step.args.get("app", ""))
        return {"success": False, "error": f"Unknown computer action: {action}"}

    # ── Brain dispatcher ──────────────────────────────────────────────────────

    def _run_brain(self, step: Step, context: dict) -> str:
        brain_name = step.brain or "fast"
        brain = self._assistant._get_brain(brain_name)

        # Build prompt with dependent step outputs injected
        prompt_parts = [step.task]
        if step.depends_on:
            for dep_id in step.depends_on:
                dep_output = context.get(dep_id)
                if dep_output:
                    if isinstance(dep_output, dict):
                        import json
                        dep_output = json.dumps(dep_output, indent=2)
                    prompt_parts.append(f"\n\nContext from step {dep_id}:\n{dep_output}")

        full_prompt = "\n".join(prompt_parts)
        return brain.respond(full_prompt)

    # ── Step runner ───────────────────────────────────────────────────────────

    def _execute_step(self, step: Step, context: dict) -> StepResult:
        """Execute a single step. Returns a StepResult."""
        try:
            logger.info("Executing step [%s]: %s (tool=%s brain=%s)",
                        step.id, step.task[:60], step.tool, step.brain)

            tool_dispatchers = {
                "search":     self._run_search,
                "python":     self._run_python,
                "file_read":  self._run_file_read,
                "image_gen":  self._run_image_gen,
                "screenshot": self._run_screenshot,
                "computer":   self._run_computer,
            }

            if step.tool and step.tool in tool_dispatchers:
                output = tool_dispatchers[step.tool](step, context)
            elif step.brain:
                output = self._run_brain(step, context)
            else:
                # Default: treat as a brain call with fast brain
                step.brain = "fast"
                output = self._run_brain(step, context)

            return StepResult(step_id=step.id, task=step.task, output=output)

        except Exception as exc:
            logger.error("Step [%s] failed: %s", step.id, exc)
            return StepResult(
                step_id=step.id,
                task=step.task,
                output=None,
                success=False,
                error=str(exc),
            )

    # ── Public API ────────────────────────────────────────────────────────────

    def execute(self, plan: Plan) -> ExecutionResult:
        """
        Execute all steps in the plan sequentially.

        Returns:
            ExecutionResult with per-step outputs and a final combined output.
        """
        context: dict[str, Any] = {}
        step_results: list[StepResult] = []
        final_text = ""

        for step in plan.steps:
            result = self._execute_step(step, context)
            step_results.append(result)
            context[step.id] = result.output

            # Track last successful text output
            if result.success and isinstance(result.output, str):
                final_text = result.output
            elif result.success and isinstance(result.output, dict):
                # For dicts (tool results), extract text if available
                if "stdout" in result.output:
                    final_text = result.output["stdout"] or result.output.get("stderr", "")
                elif "error" in result.output and not result.output.get("success"):
                    final_text = f"Error: {result.output['error']}"

        overall_success = all(r.success for r in step_results)
        if not final_text:
            errors = [r.error for r in step_results if r.error]
            final_text = f"Execution failed: {'; '.join(errors)}" if errors else "No output produced."

        logger.info(
            "Plan executed: %d/%d steps succeeded, final output length=%d",
            sum(1 for r in step_results if r.success),
            len(step_results),
            len(final_text),
        )

        return ExecutionResult(
            goal=plan.goal,
            steps=step_results,
            final_output=final_text,
            success=overall_success,
        )
