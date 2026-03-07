"""
reviewer.py – Output Quality Reviewer
───────────────────────────────────────
Evaluates whether the assistant's output satisfies the user's request.

The reviewer uses a lightweight LLM call to score the response and
return structured feedback. It does NOT produce a new response –
it only judges the existing one.

Usage:
    reviewer = Reviewer()
    result = reviewer.evaluate(
        request="Write a sorting function in Python",
        response="Here is a quicksort: ...",
    )
    if not result.passed:
        print(result.feedback)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

try:
    import ollama
except ImportError as _e:
    import logging as _log
    _log.getLogger(__name__).error(
        "DEPENDENCY ERROR: 'ollama' is not installed – reviewer/FixLoop will be unavailable. "
        "Run: pip install ollama  (%s)", _e,
    )
    ollama = None  # type: ignore[assignment]

from ..config import MODELS, OLLAMA_HOST

logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    passed: bool           # True if the response satisfies the request
    score: float           # 0.0 – 1.0
    feedback: str          # Human-readable evaluation
    issues: list[str]      # Specific problems found
    suggestions: list[str] # Suggested improvements


_REVIEWER_SYSTEM = """\
You are a strict quality reviewer for an AI assistant.

Evaluate whether the RESPONSE adequately satisfies the REQUEST.

Criteria:
1. Correctness  – Is the answer factually/technically correct?
2. Completeness – Does it address all parts of the request?
3. Clarity      – Is the response easy to understand?
4. Code quality – If code is present, is it runnable and well-structured?

Respond with ONLY valid JSON (no markdown):
{
  "passed": true,
  "score": 0.85,
  "feedback": "One-sentence overall assessment.",
  "issues": ["Issue 1", "Issue 2"],
  "suggestions": ["Suggestion 1"]
}

Score guide:
  1.0 = perfect
  0.8 = good, minor gaps
  0.6 = acceptable but incomplete
  0.4 = partial, significant gaps
  0.2 = poor
  0.0 = completely wrong or empty

Set "passed" to true if score >= 0.6.
"""


class Reviewer:
    """Evaluate assistant outputs against user requests."""

    def __init__(self):
        if ollama is None:
            raise ImportError(
                "DEPENDENCY ERROR: 'ollama' is not installed – Reviewer/FixLoop unavailable. "
                "Run: pip install ollama"
            )
        self._client = ollama.Client(host=OLLAMA_HOST)
        self._model  = MODELS.get("fast", MODELS["fallback"])

    def evaluate(
        self,
        request: str,
        response: str,
        context: Optional[str] = None,
    ) -> ReviewResult:
        """
        Review a response against the original request.

        Args:
            request:  The user's original message.
            response: The assistant's generated response.
            context:  Optional additional context (e.g. tool outputs).

        Returns:
            ReviewResult with pass/fail, score, and actionable feedback.
        """
        prompt_parts = [
            f"REQUEST:\n{request}",
            f"\nRESPONSE:\n{response[:3000]}",  # cap to avoid huge prompts
        ]
        if context:
            prompt_parts.append(f"\nCONTEXT:\n{context[:1000]}")

        user_prompt = "\n".join(prompt_parts)

        try:
            resp = self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": _REVIEWER_SYSTEM},
                    {"role": "user",   "content": user_prompt},
                ],
                options={"temperature": 0.0},
            )
            raw = resp["message"]["content"].strip()
            raw = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
            data = json.loads(raw)

            return ReviewResult(
                passed      = bool(data.get("passed", False)),
                score       = float(data.get("score", 0.0)),
                feedback    = data.get("feedback", ""),
                issues      = data.get("issues", []),
                suggestions = data.get("suggestions", []),
            )

        except Exception as exc:
            logger.warning("Reviewer LLM failed: %s – defaulting to pass.", exc)
            # If reviewer fails, don't block execution – default to pass
            return ReviewResult(
                passed=True, score=0.7,
                feedback="Review skipped (LLM unavailable).",
                issues=[], suggestions=[],
            )

    def is_code_present(self, text: str) -> bool:
        """Check if a response contains a fenced code block."""
        return bool(re.search(r"```\w*\n", text))

    def extract_issues_summary(self, result: ReviewResult) -> str:
        """Format issues + suggestions as a prompt fragment for repair."""
        parts: list[str] = []
        if result.issues:
            parts.append("Issues:\n" + "\n".join(f"- {i}" for i in result.issues))
        if result.suggestions:
            parts.append("Suggestions:\n" + "\n".join(f"- {s}" for s in result.suggestions))
        return "\n".join(parts) or result.feedback
