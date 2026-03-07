"""
coding_agent.py – Coding Agent
────────────────────────────────
Writes, edits, scaffolds, and implements code.

Integrates with the existing RepairLoop so that every code response
goes through: generate → auto-test → fix → retry (up to MAX_RETRIES).

Successful solutions are stored in SolutionMemory for future reuse.
"""

from __future__ import annotations

import re
from typing import Optional, TYPE_CHECKING

from .base_agent  import BaseAgent
from .task_models import SwarmTask, TaskResult

if TYPE_CHECKING:
    from ..self_improvement.repair_loop import RepairLoop
    from ..memory.solution_memory       import SolutionMemory


_CODING_SYSTEM = """\
You are an expert software engineer and coding assistant.

Capabilities:
- Write clean, production-ready code in any language
- Scaffold complete project structures with all necessary files
- Implement features based on specifications or prior research
- Follow best practices: type hints, error handling, docstrings, tests

Rules:
- Always wrap code in fenced code blocks with the language tag (e.g. ```python)
- Include inline comments for non-obvious logic
- If multiple files are needed, show each with a clear filename header
- Prefer simple, readable solutions
- Point out security concerns in code you write
"""


class CodingAgent(BaseAgent):
    """
    Coding agent with integrated test-repair loop.

    If repair_loop is provided (from MiniAssistant), the generated code
    is automatically tested and repaired before being returned.
    If solution_memory is provided, successful patterns are stored.
    """

    agent_name = "coding_agent"
    agent_type = "coding"

    def __init__(
        self,
        repair_loop: Optional["RepairLoop"] = None,
        solution_memory: Optional["SolutionMemory"] = None,
    ):
        super().__init__()
        self._repair_loop     = repair_loop
        self._solution_memory = solution_memory

    def run(self, task: SwarmTask, context: dict[str, TaskResult]) -> TaskResult:
        self._logger.info("Coding: %s", task.description[:80])

        # Check solution memory for existing pattern
        if self._solution_memory:
            prior = self._solution_memory.find_solutions(task.description, top_k=1)
            if prior and prior[0].get("code"):
                self._logger.info("Found prior solution: %s", prior[0].get("title",""))

        language = task.args.get("language", "python")
        prompt   = self._inject_context(task, context)

        # Initial generation
        response = self._call_llm(
            user_prompt   = prompt,
            system_prompt = _CODING_SYSTEM,
            temperature   = 0.1,
        )

        # Run the repair loop (test → fix → retry)
        if self._repair_loop and language.lower() == "python":
            self._logger.info("Running repair loop on generated code.")
            repair_result = self._repair_loop.run(
                request  = task.description,
                response = response,
                run_tests = True,
                run_review = True,
            )
            response = repair_result.final_response

            # Store successful patterns
            if repair_result.success and self._solution_memory:
                code = _extract_code(response)
                if code:
                    self._solution_memory.store_solution(
                        title       = task.description[:80],
                        description = task.description,
                        code        = code,
                        fixes       = repair_result.fixes_applied,
                        tags        = ["python", task.type],
                    )

            extra = {
                "tests_passed":   repair_result.tests_passed,
                "repair_attempts": repair_result.attempt_count,
                "review_passed":  repair_result.review_passed,
            }
        else:
            extra = {}

        self._logger.info("Coding complete (%d chars).", len(response))
        return self._make_result(task=task, output=response, data=extra)


def _extract_code(text: str) -> str:
    """Pull the first Python fenced block from a response."""
    m = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else ""
