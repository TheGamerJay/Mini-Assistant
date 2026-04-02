"""
decision/clarification_engine.py — Decide when CEO must ask before acting.

Clarification is triggered when:
  1. full_system complexity + underspecified request
  2. full_system (all cases) — scope confirmation before large build
  3. image_edit intent but no attachment provided
  4. task_assist but memory is missing and user hasn't provided the data
  5. debug (doctor) intent without error logs or code — needs evidence

Output format (structured):
  {
      "type":     "clarification",
      "question": str,
      "options":  list[str],   # concrete choices if applicable, else []
      "reason":   str,         # why clarification is needed
  }

Rules:
- must be specific — no vague "please provide more info"
- must reduce ambiguity — options must be meaningful choices
- must not over-ask — only trigger for genuinely required inputs
- must not guess when critical info is missing
- execution is completely halted until clarification resolves
"""

from __future__ import annotations

import re
from typing import Optional


def check_clarification(
    intent:            str,
    complexity:        str,
    is_underspecified: bool,
    has_attachments:   bool,
    requires_memory:   bool,
    memory_available:  bool,
) -> tuple[bool, Optional[str]]:
    """
    Returns:
        (needs_user_input, clarification_question | None)

    The question string is formatted for direct display.
    Call build_clarification_response() for the full structured dict.
    """
    result = _check(intent, complexity, is_underspecified, has_attachments,
                    requires_memory, memory_available)
    if result:
        return True, result["question"]
    return False, None


def build_clarification_response(
    intent:            str,
    complexity:        str,
    is_underspecified: bool,
    has_attachments:   bool,
    requires_memory:   bool,
    memory_available:  bool,
) -> Optional[dict]:
    """
    Returns full structured clarification dict or None if no clarification needed.

    Structure:
        {
            "type":     "clarification",
            "question": str,
            "options":  list[str],
            "reason":   str,
        }
    """
    return _check(intent, complexity, is_underspecified, has_attachments,
                  requires_memory, memory_available)


def _check(
    intent:            str,
    complexity:        str,
    is_underspecified: bool,
    has_attachments:   bool,
    requires_memory:   bool,
    memory_available:  bool,
) -> Optional[dict]:
    """Core logic — returns structured clarification dict or None."""

    # ── full_system + underspecified ───────────────────────────────────────────
    if complexity == "full_system" and is_underspecified:
        return {
            "type": "clarification",
            "question": (
                "This looks like a full-system build (backend, database, API). "
                "Which version do you want?"
            ),
            "options": [
                "A. Simple local version — runs in the browser, no server",
                "B. Full version — backend, database, user accounts, and API",
                "C. Tell me more about what you need",
            ],
            "reason": "full_system complexity detected but scope is underspecified",
        }

    # ── full_system (specified) — confirm approach before large build ──────────
    if complexity == "full_system" and not is_underspecified:
        return {
            "type": "clarification",
            "question": (
                "This is a full-system request (backend + database + API). "
                "How do you want to proceed?"
            ),
            "options": [
                "A. Scaffold the full architecture (backend, DB schema, API routes, frontend)",
                "B. Build a simplified working version first, then expand",
            ],
            "reason": "full_system complexity requires approach confirmation before execution",
        }

    # ── image_edit without attachment ─────────────────────────────────────────
    if intent == "image_edit" and not has_attachments:
        return {
            "type": "clarification",
            "question": "Please attach the image you'd like me to modify.",
            "options": [],
            "reason": "image_edit requires an attached image — none was provided",
        }

    # ── image_analyze without attachment ──────────────────────────────────────
    if intent == "image_analyze" and not has_attachments:
        return {
            "type": "clarification",
            "question": "Please attach the image or screenshot you'd like me to analyze.",
            "options": [],
            "reason": "image_analyze requires an attached image — none was provided",
        }

    # ── task_assist — memory required but not available ───────────────────────
    if intent == "task_assist" and requires_memory and not memory_available:
        return {
            "type": "clarification",
            "question": (
                "I'll help with that — I'll need your resume or professional background first."
            ),
            "options": [
                "Paste your resume text here",
                "Describe your experience and I'll build from there",
            ],
            "reason": "task_assist requires resume/profile memory — none found for this user",
        }

    # ── debug (doctor) — no evidence ──────────────────────────────────────────
    if intent == "debug" and not has_attachments:
        # Only clarify if message has no code or traceback
        return None  # clarification_engine defers to doctor's confidence logic

    return None


# ---------------------------------------------------------------------------
# Helpers used by module_executor (parse options from question string)
# ---------------------------------------------------------------------------

_OPTION_PAT = re.compile(r"^[A-C]\.\s+.+", re.MULTILINE)


def parse_options_from_question(question: str) -> list[str]:
    """
    Extract lettered options (A., B., C.) from a question string.
    Used when the structured dict is not available (legacy path).
    """
    return [m.strip() for m in _OPTION_PAT.findall(question)]
