"""
repair_loop.py – Automatic Failure Repair
──────────────────────────────────────────
Orchestrates the full write → test → review → repair cycle.

Flow:
    1. Receive code response from coder brain.
    2. Tester generates + runs unit tests.
    3. If tests fail → coder brain generates a fix.
    4. Retry up to MAX_RETRIES times.
    5. Reviewer evaluates the final output.
    6. Return RepairResult with full audit trail.

Usage:
    loop   = RepairLoop(assistant)
    result = loop.run(
        request="Write a binary search function",
        response=coder_brain_response,
    )
    print(result.final_response)
    print(f"Tests passed: {result.tests_passed}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from .tester   import Tester, TestResult, extract_python_code
from .reviewer import Reviewer, ReviewResult

if TYPE_CHECKING:
    from ..main import MiniAssistant

logger = logging.getLogger(__name__)

MAX_RETRIES = int(__import__("os").getenv("REPAIR_MAX_RETRIES", "3"))


@dataclass
class RepairAttempt:
    attempt_number: int
    response: str
    test_result: Optional[TestResult] = None
    review_result: Optional[ReviewResult] = None
    fix_prompt: str = ""


@dataclass
class RepairResult:
    request: str
    final_response: str
    tests_passed: bool
    review_passed: bool
    attempts: list[RepairAttempt] = field(default_factory=list)
    errors_seen: list[str]        = field(default_factory=list)
    fixes_applied: list[str]      = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.tests_passed and self.review_passed

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    def to_reflection_dict(self) -> dict:
        return {
            "request":      self.request,
            "result":       "success" if self.success else "failure",
            "attempts":     self.attempt_count,
            "errors_seen":  self.errors_seen,
            "fixes_applied":self.fixes_applied,
        }


# ─── Fix prompt builder ───────────────────────────────────────────────────────

def _build_fix_prompt(
    original_request: str,
    current_code: str,
    test_result: TestResult,
    review_result: Optional[ReviewResult],
) -> str:
    parts = [
        f"You previously wrote code for this request:\n{original_request}",
        f"\nThe code has problems. Fix them and return the COMPLETE corrected code.",
        f"\nCurrent code:\n```python\n{current_code[:3000]}\n```",
    ]

    if test_result and not test_result.passed:
        parts.append(
            f"\nTest failures:\n```\n{test_result.failure_summary[:2000]}\n```"
        )
        if test_result.generated_tests:
            parts.append(
                f"\nTests that were run:\n```python\n{test_result.generated_tests[:1500]}\n```"
            )

    if review_result and not review_result.passed:
        if review_result.issues:
            parts.append(
                "\nReview issues:\n" + "\n".join(f"- {i}" for i in review_result.issues)
            )

    parts.append(
        "\nReturn ONLY the corrected Python code in a ```python ... ``` block."
    )
    return "\n".join(parts)


# ─── Repair loop ──────────────────────────────────────────────────────────────

class RepairLoop:
    """
    Automated test-run-review-repair cycle for generated code.
    """

    def __init__(self, assistant: "MiniAssistant"):
        self._assistant = assistant
        self._tester    = Tester()
        self._reviewer  = Reviewer()

    def run(
        self,
        request: str,
        response: str,
        run_tests: bool = True,
        run_review: bool = True,
        custom_tests: Optional[str] = None,
    ) -> RepairResult:
        """
        Run the repair loop on a code-containing LLM response.

        Args:
            request:      Original user request.
            response:     Initial coder brain response.
            run_tests:    Whether to run unit tests (disable for non-Python).
            run_review:   Whether to run quality review.
            custom_tests: Provide specific tests instead of auto-generating.

        Returns:
            RepairResult with full audit trail.
        """
        current_response = response
        attempts: list[RepairAttempt] = []
        errors_seen: list[str]  = []
        fixes_applied: list[str] = []

        for attempt_num in range(1, MAX_RETRIES + 2):  # +1 for the initial attempt
            logger.info("Repair loop attempt %d/%d", attempt_num, MAX_RETRIES + 1)
            attempt = RepairAttempt(
                attempt_number=attempt_num,
                response=current_response,
            )

            # ── 1. Test ───────────────────────────────────────────────────────
            test_result: Optional[TestResult] = None
            if run_tests:
                test_result = self._tester.test_response(
                    request=request,
                    response=current_response,
                    custom_tests=custom_tests,
                )
                attempt.test_result = test_result
                logger.info(
                    "Tests: passed=%s (%d/%d)",
                    test_result.passed,
                    test_result.tests_passed,
                    test_result.tests_run,
                )
                if test_result.failure_summary:
                    errors_seen.append(test_result.failure_summary[:300])

            # ── 2. Review ─────────────────────────────────────────────────────
            review_result: Optional[ReviewResult] = None
            if run_review:
                review_result = self._reviewer.evaluate(request, current_response)
                attempt.review_result = review_result
                logger.info(
                    "Review: passed=%s score=%.2f",
                    review_result.passed, review_result.score,
                )

            attempts.append(attempt)

            # ── 3. Check if done ──────────────────────────────────────────────
            tests_ok  = (not run_tests)  or (test_result  and test_result.passed)
            review_ok = (not run_review) or (review_result and review_result.passed)

            if tests_ok and review_ok:
                logger.info("Repair loop complete on attempt %d (success).", attempt_num)
                break

            # ── 4. Bail out if retries exhausted ─────────────────────────────
            if attempt_num > MAX_RETRIES:
                logger.warning("Repair loop exhausted %d retries. Returning best effort.", MAX_RETRIES)
                break

            # ── 5. Generate fix ───────────────────────────────────────────────
            current_code = extract_python_code(current_response) or current_response
            fix_prompt   = _build_fix_prompt(
                original_request=request,
                current_code=current_code,
                test_result=test_result,
                review_result=review_result,
            )
            attempt.fix_prompt = fix_prompt

            try:
                coder = self._assistant._get_brain("coding")
                fixed = coder.respond(fix_prompt)
                fixes_applied.append(
                    f"Attempt {attempt_num}: fixed {len(errors_seen)} issues"
                )
                current_response = fixed
                logger.info("Generated fix for attempt %d.", attempt_num)
            except Exception as exc:
                logger.error("Fix generation failed on attempt %d: %s", attempt_num, exc)
                break

        # Final evaluation state
        final_test_result   = attempts[-1].test_result   if attempts else None
        final_review_result = attempts[-1].review_result if attempts else None

        return RepairResult(
            request         = request,
            final_response  = current_response,
            tests_passed    = (not run_tests)  or bool(final_test_result   and final_test_result.passed),
            review_passed   = (not run_review) or bool(final_review_result and final_review_result.passed),
            attempts        = attempts,
            errors_seen     = errors_seen,
            fixes_applied   = fixes_applied,
        )
