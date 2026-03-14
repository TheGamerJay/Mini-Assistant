"""
critic.py — Phase 1 Basic Critic Pass
──────────────────────────────────────
Validates brain replies before they reach the user.

Checks:
  - Not empty
  - Not a leaked Python traceback
  - Not a raw brain error string
  - Not suspiciously short for a complex intent
  - No obvious JSON leakage in non-code intents

The Critic does NOT call an LLM — it is a fast rule-based pass.
Phase 2+ will add an LLM-based Critic for deeper quality assessment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .intent_planner import PlannerOutput


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class CriticResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    corrected_reply: str = ""   # same as input reply if no correction needed
    critic_ms: float = 0.0


# ── Patterns ──────────────────────────────────────────────────────────────────

_TRACEBACK     = re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE)
_BRAIN_ERR     = re.compile(
    r"^(coding brain error|vision brain error|research brain error|"
    r"I.?m having trouble responding|brain error|internal error):",
    re.IGNORECASE,
)
_RAW_JSON      = re.compile(r'^\s*[\[{].*[}\]]\s*$', re.DOTALL)
_ONLY_CODE     = re.compile(r"^```", re.MULTILINE)

# Intents where a very short reply is suspicious
_COMPLEX_INTENTS = {
    "debugging", "code_runner", "app_builder",
    "planning", "web_search", "image_analysis",
}

# Intents where raw JSON/code blocks in the reply are expected and fine
_CODE_INTENTS = {"code_runner", "debugging", "app_builder", "file_analysis"}


# ── Correctors ────────────────────────────────────────────────────────────────

def _strip_traceback(reply: str) -> str:
    """Replace a full traceback with just the final error line."""
    lines   = reply.strip().splitlines()
    # Last non-blank, non-indented line is usually the exception itself
    error   = next(
        (l.strip() for l in reversed(lines) if l.strip() and not l.startswith(" ")),
        "An internal error occurred.",
    )
    return f"An error was encountered internally: `{error}`\n\nPlease try again or rephrase your request."


def _format_short_reply(reply: str, intent: str) -> str:
    """Pad suspiciously short replies with a follow-up prompt."""
    return (
        f"{reply}\n\n"
        f"*(Response seems incomplete for a `{intent}` request — "
        f"please ask for more detail if needed.)*"
    )


# ── Public API ────────────────────────────────────────────────────────────────

def critique(reply: str, plan: PlannerOutput) -> CriticResult:
    """
    Run a quick quality check on a brain reply.

    Args:
        reply: The raw reply string from the brain.
        plan:  The PlannerOutput for this request (provides intent context).

    Returns:
        CriticResult — corrected_reply is safe to send to the user.
    """
    import time
    t0 = time.perf_counter()

    intent    = plan.intent
    corrected = reply.strip() if reply else ""
    issues: list[str] = []

    # 1. Empty reply
    if not corrected:
        issues.append("Brain returned an empty reply.")
        corrected = (
            "I wasn't able to generate a response for that request. "
            "Please try again or rephrase."
        )

    # 2. Leaked Python traceback
    elif _TRACEBACK.search(corrected):
        issues.append("Reply contains a Python traceback.")
        corrected = _strip_traceback(corrected)

    # 3. Brain returned an error string
    elif _BRAIN_ERR.match(corrected):
        issues.append("Brain returned a raw error string.")
        corrected = (
            "I ran into a problem processing that request. "
            "The service may be temporarily unavailable — please try again."
        )

    # 4. Suspiciously short for a complex intent
    elif intent in _COMPLEX_INTENTS and len(corrected) < 30:
        issues.append(
            f"Reply length ({len(corrected)} chars) is very short for intent '{intent}'."
        )
        corrected = _format_short_reply(corrected, intent)

    # 5. Raw JSON leaked in a non-code-related intent
    elif intent not in _CODE_INTENTS and _RAW_JSON.match(corrected):
        issues.append("Reply appears to be raw JSON — may indicate a brain formatting failure.")
        corrected = (
            "*(The response was in an unexpected format.)*\n\n"
            "Raw output:\n```json\n" + corrected + "\n```"
        )

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    return CriticResult(
        passed         = len(issues) == 0,
        issues         = issues,
        corrected_reply= corrected,
        critic_ms      = elapsed_ms,
    )
