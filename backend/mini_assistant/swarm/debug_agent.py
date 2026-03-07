"""
debug_agent.py – Debug Agent
──────────────────────────────
Analyses failures, stack traces, and broken outputs, then proposes fixes.

The debug agent is called by the manager when:
  • A coding task fails outright (exception during execution)
  • Tests produced by the tester agent fail after the coding agent's repair loop
  • The manager decides a result is unacceptable

The agent returns a fixed response that can be substituted for the failed one.
"""

from __future__ import annotations

from .base_agent  import BaseAgent
from .task_models import SwarmTask, TaskResult


_DEBUG_SYSTEM = """\
You are an expert software debugger and failure analyst.

Your job is to:
1. Identify the root cause of the failure precisely.
2. Explain what went wrong in plain language (1–2 sentences).
3. Provide the COMPLETE fixed code or fixed response.

Rules:
- Always wrap fixed code in a fenced code block with language tag.
- Do not just describe the fix – implement it.
- If the error is environmental (missing package, wrong path), say so clearly.
- If multiple issues exist, fix all of them.
- Ensure the fix doesn't introduce new bugs.
"""


class DebugAgent(BaseAgent):
    """
    Debug agent: root-cause analysis + fix generation.

    Input (via task.args or dependency context):
      error      – the error message or stack trace
      code       – the broken code (optional)
      context    – prior task results for the full picture
    """

    agent_name = "debug_agent"
    agent_type = "debug"

    def run(self, task: SwarmTask, context: dict[str, TaskResult]) -> TaskResult:
        self._logger.info("Debugging: %s", task.description[:80])

        # Gather all available context
        dep_context = self._inject_context(task, context)

        # Pull error and code from args or description
        error = task.args.get("error", "")
        code  = task.args.get("code",  "")

        # Build a rich debug prompt
        parts = [f"Task that failed: {task.description}"]

        if error:
            parts.append(f"\nError / stack trace:\n```\n{error[:3000]}\n```")

        if code:
            lang = task.args.get("language", "python")
            parts.append(f"\nBroken code:\n```{lang}\n{code[:3000]}\n```")

        if dep_context != task.description:
            parts.append(f"\nAdditional context from dependencies:\n{dep_context[:2000]}")

        prompt = "\n".join(parts)

        response = self._call_llm(
            user_prompt   = prompt,
            system_prompt = _DEBUG_SYSTEM,
            temperature   = 0.05,   # very low – we want precise fixes
        )

        self._logger.info("Debug complete (%d chars).", len(response))
        return self._make_result(task=task, output=response)
