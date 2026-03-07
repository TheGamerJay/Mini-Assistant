"""
tester_agent.py – Tester Agent
────────────────────────────────
Runs tests, validates outputs, and checks whether a task was completed correctly.

For Python code: auto-generates pytest unit tests and executes them.
For non-code outputs: uses the Reviewer LLM to evaluate quality.

The agent returns a TaskResult indicating pass/fail with detailed feedback
so the manager can decide whether to invoke the DebugAgent.
"""

from __future__ import annotations

import re
from typing import Optional, TYPE_CHECKING

from .base_agent  import BaseAgent
from .task_models import SwarmTask, TaskResult

if TYPE_CHECKING:
    from ..self_improvement.tester   import Tester
    from ..self_improvement.reviewer import Reviewer


_VALIDATOR_SYSTEM = """\
You are a strict output validator for an AI assistant.

Given the ORIGINAL REQUEST and the RESPONSE produced, answer:
1. Was the request fully addressed? (yes/no)
2. Are there obvious errors, missing pieces, or quality issues?
3. Provide a 1-sentence verdict.

Respond in this exact format (no markdown):
VERDICT: pass | fail
REASON: <one sentence>
ISSUES: <comma-separated list, or "none">
"""


class TesterAgent(BaseAgent):
    """
    Tester agent: validates task outputs using automated tests + LLM review.

    Accepts optional pre-built Tester and Reviewer instances from MiniAssistant
    to avoid double-instantiation.
    """

    agent_name = "tester_agent"
    agent_type = "tester"

    def __init__(
        self,
        tester:   Optional["Tester"]   = None,
        reviewer: Optional["Reviewer"] = None,
    ):
        super().__init__()
        self._tester   = tester
        self._reviewer = reviewer

    def run(self, task: SwarmTask, context: dict[str, TaskResult]) -> TaskResult:
        self._logger.info("Testing: %s", task.description[:80])

        # The thing we are testing
        target_output = task.args.get("output", "")
        original_req  = task.args.get("request", task.description)

        # If no explicit output, pull from the first dependency result
        if not target_output and task.depends_on:
            dep = context.get(task.depends_on[0])
            if dep:
                target_output = dep.output
                original_req  = original_req or dep.task_id

        if not target_output:
            return self._make_result(
                task    = task,
                output  = "Nothing to test – no output from dependencies.",
                success = False,
                error   = "missing_output",
            )

        # ── 1. Try automated pytest (Python code) ─────────────────────────────
        has_python = bool(re.search(r"```python", target_output))
        test_passed = True
        test_detail = ""

        if has_python and self._tester:
            self._logger.info("Running automated pytest.")
            tr = self._tester.test_response(
                request  = original_req,
                response = target_output,
            )
            test_passed = tr.passed
            test_detail = (
                f"Tests: {tr.tests_passed}/{tr.tests_run} passed. "
                + (tr.failure_summary[:300] if not tr.passed else "All good.")
            )
            self._logger.info(test_detail)

        # ── 2. LLM review as quality gate ─────────────────────────────────────
        review_passed = True
        review_detail = ""

        if self._reviewer:
            rr = self._reviewer.evaluate(original_req, target_output)
            review_passed = rr.passed
            review_detail = f"Review score: {rr.score:.2f}. {rr.feedback}"
            if not rr.passed and rr.issues:
                review_detail += " Issues: " + "; ".join(rr.issues[:3])
            self._logger.info(review_detail)
        else:
            # Fallback: lightweight LLM check
            raw = self._call_llm(
                user_prompt   = f"ORIGINAL REQUEST:\n{original_req}\n\nRESPONSE:\n{target_output[:2000]}",
                system_prompt = _VALIDATOR_SYSTEM,
                temperature   = 0.0,
            )
            review_passed = "pass" in raw.lower().split("verdict:")[-1][:20]
            review_detail = raw[:200]

        overall = test_passed and review_passed
        summary_parts = []
        if test_detail:
            summary_parts.append(test_detail)
        if review_detail:
            summary_parts.append(review_detail)
        summary = "\n".join(summary_parts) or "Validation complete."

        return self._make_result(
            task    = task,
            output  = summary,
            success = overall,
            data    = {
                "tests_passed":  test_passed,
                "review_passed": review_passed,
            },
            error   = summary if not overall else None,
        )
