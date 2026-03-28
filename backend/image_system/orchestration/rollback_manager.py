"""
Rollback Manager — Phase 3

Handles failure recovery:
  1. Capture error / classify failure type
  2. Retry with adjusted strategy (bounded)
  3. Rollback to last good checkpoint if retries exhausted
  4. Escalate with a clear next-best move

Failure classes:
  - TRANSIENT:  network/timeout — safe to retry immediately
  - MODEL:      LLM output quality issue — retry with adjusted prompt
  - SCOPE:      model went out of scope — retry with tighter constraints
  - STRUCTURAL: code syntax/structure error — retry or rollback
  - FATAL:      cannot recover — rollback and report

MAX_RETRIES = 3 per step (not per task).
Never retry destructive actions blindly.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class FailureClass(str, Enum):
    TRANSIENT  = "transient"   # safe to retry now
    MODEL      = "model"       # retry with prompt adjustment
    SCOPE      = "scope"       # model went off-rails — retry with stricter prompt
    STRUCTURAL = "structural"  # code has syntax issues — retry with fix instructions
    FATAL      = "fatal"       # cannot recover — escalate


@dataclass
class RecoveryPlan:
    failure_class:  FailureClass
    retry:          bool            # should we retry?
    attempt:        int             # which retry attempt this is
    max_retries:    int             # ceiling
    prompt_patch:   Optional[str]   # additional instruction to inject on retry
    rollback_to:    Optional[str]   # checkpoint_id to restore if retries exhausted
    escalation_msg: str             # user-facing message if we can't recover


_TRANSIENT_SIGNALS = re.compile(
    r"(timeout|connection\s+error|network|rate.limit|503|502|504|"
    r"service\s+unavailable|overloaded)", re.I
)

_MODEL_QUALITY_SIGNALS = re.compile(
    r"(placeholder|todo|coming\s+soon|not\s+implemented|lorem\s+ipsum|"
    r"example\.com|your\s+content\s+here)", re.I
)

_SCOPE_SIGNALS = re.compile(
    r"(rewriting\s+everything|complete\s+rewrite|from\s+scratch|"
    r"I've\s+redesigned|I\s+rebuilt|starting\s+over)", re.I
)

_STRUCTURAL_SIGNALS = re.compile(
    r"(SyntaxError|ReferenceError|TypeError|unexpected\s+token|"
    r"is\s+not\s+defined|cannot\s+read\s+propert|uncaught)", re.I
)


def classify_failure(error: str, output: str = "") -> FailureClass:
    """Classify a failure from its error message and/or output content."""
    combined = f"{error}\n{output}"

    if _TRANSIENT_SIGNALS.search(combined):
        return FailureClass.TRANSIENT

    if _SCOPE_SIGNALS.search(combined):
        return FailureClass.SCOPE

    if _MODEL_QUALITY_SIGNALS.search(combined):
        return FailureClass.MODEL

    if _STRUCTURAL_SIGNALS.search(combined):
        return FailureClass.STRUCTURAL

    return FailureClass.FATAL


def build_recovery_plan(
    failure_class:   FailureClass,
    attempt:         int,
    step_title:      str,
    last_checkpoint: Optional[str] = None,
    is_destructive:  bool = False,
) -> RecoveryPlan:
    """
    Build a recovery plan for a failed step.

    Args:
        failure_class:    Classified failure type.
        attempt:          Current attempt number (1-indexed).
        step_title:       Human-readable step name.
        last_checkpoint:  checkpoint_id to roll back to if retries exhausted.
        is_destructive:   If True, NEVER retry — rollback immediately.
    """
    retry = (attempt < MAX_RETRIES) and not is_destructive

    # No retries for fatal failures or destructive actions
    if failure_class == FailureClass.FATAL or is_destructive:
        retry = False

    # Build retry prompt patch
    prompt_patch: Optional[str] = None
    if retry:
        if failure_class == FailureClass.TRANSIENT:
            prompt_patch = None  # just retry same prompt

        elif failure_class == FailureClass.SCOPE:
            prompt_patch = (
                "\n\n⛔ STRICT SCOPE REMINDER: Do NOT rewrite or rebuild the existing code. "
                "Apply ONLY the minimum targeted change requested. "
                "Output the complete file with ONLY the requested modification."
            )

        elif failure_class == FailureClass.MODEL:
            prompt_patch = (
                "\n\n⚠️ OUTPUT QUALITY REMINDER: No placeholders, TODOs, or stubs. "
                "Every feature must be fully implemented and working. "
                "Do not use lorem ipsum, example.com, or any placeholder content."
            )

        elif failure_class == FailureClass.STRUCTURAL:
            prompt_patch = (
                "\n\n🔧 FIX REMINDER: The previous output had syntax/runtime errors. "
                "Check: brackets balanced, all variables declared, no undefined references, "
                "no missing closing tags. Output clean, working code."
            )

    # Escalation message
    if retry:
        escalation_msg = (
            f"Retrying step '{step_title}' (attempt {attempt + 1}/{MAX_RETRIES}) "
            f"with adjusted approach…"
        )
    elif last_checkpoint:
        escalation_msg = (
            f"Step '{step_title}' failed after {attempt} attempt(s). "
            f"Rolling back to last checkpoint and stopping."
        )
    else:
        escalation_msg = (
            f"Step '{step_title}' failed after {attempt} attempt(s). "
            f"Unable to recover automatically. "
            f"Try simplifying the request or breaking it into smaller steps."
        )

    logger.info(
        "[RollbackManager] failure_class=%s attempt=%d retry=%s",
        failure_class, attempt, retry
    )

    return RecoveryPlan(
        failure_class=failure_class,
        retry=retry,
        attempt=attempt,
        max_retries=MAX_RETRIES,
        prompt_patch=prompt_patch,
        rollback_to=last_checkpoint if not retry else None,
        escalation_msg=escalation_msg,
    )
