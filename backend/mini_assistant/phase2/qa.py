"""
phase2/qa.py — QA Reviewer
────────────────────────────
Async QA pass that reviews a Worker's output using the OpenAI
reasoning model and optionally returns an improved version.

Flow (called from server.py after the main reply is assembled):

    result = await review(request=user_msg, output=reply)
    if not result["approved"] and result["improved_output"]:
        reply = result["improved_output"]

Only runs when:
  - CEO posture priority == "quality"  (builder / debug / architect / research)
  - execution_intent is a code/builder intent (not simple chat or image)
  - ENABLE_QA_LOOP env var == "true"  (opt-in safety gate)

Fails silently — QA issues never surface as errors to the user.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Intents that warrant a QA review ─────────────────────────────────────────

_QA_ELIGIBLE_INTENTS = {
    "coding",
    "debugging",
    "app_builder",
    "code_runner",
    "planning",
    "architect",
}

# ── QA prompt templates ───────────────────────────────────────────────────────

_QA_SYSTEM = (
    "You are a senior software engineer and code reviewer. "
    "Your job is to check if an AI-generated response fully and correctly addresses "
    "the user's request. Be strict about correctness and completeness, but do not "
    "flag style preferences or minor formatting choices. "
    "Keep feedback concise and actionable."
)

_QA_PROMPT = """\
USER REQUEST:
{request}

AI OUTPUT TO REVIEW:
{output}

---
Review the output above.

If it fully and correctly addresses the request, reply with exactly one word:
APPROVED

Otherwise reply in this format:
ISSUES:
- <issue 1>
- <issue 2>

IMPROVED OUTPUT:
<corrected full output — not a summary, the complete improved version>
"""


# ── Public API ────────────────────────────────────────────────────────────────

def should_run_qa(execution_intent: str, priority: str) -> bool:
    """
    Return True if this request warrants a QA review pass.

    Checks:
      1. ENABLE_QA_LOOP env var must be "true"
      2. CEO priority must be "quality"
      3. Intent must be a code/builder intent
    """
    if os.getenv("ENABLE_QA_LOOP", "false").lower() != "true":
        return False
    if priority != "quality":
        return False
    return execution_intent in _QA_ELIGIBLE_INTENTS


async def review(
    request: str,
    output: str,
    role: str = "QA",
) -> dict:
    """
    Run a QA review of a worker output.

    Args:
        request: The original user request / task description.
        output:  The worker's generated output to review.
        role:    Agent role for model routing (default: QA).

    Returns:
        {
          "approved":        bool,
          "issues":          list[str],      # empty if approved
          "improved_output": str | None,     # set if not approved + model provided one
          "qa_ms":           float,
        }

    Never raises — returns approved=True on any internal error so the
    original reply is always returned to the user.
    """
    from .router import call_model

    t0 = time.perf_counter()
    prompt = _QA_PROMPT.format(
        request=request[:2000],
        output=output[:4000],
    )

    try:
        result = await call_model(role, prompt, context=_QA_SYSTEM)
    except Exception as exc:
        logger.warning("QA review call failed (non-fatal, returning approved): %s", exc)
        return {"approved": True, "issues": [], "improved_output": None, "qa_ms": 0.0}

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    # ── Parse response ────────────────────────────────────────────────────────

    if result.strip().upper().startswith("APPROVED"):
        logger.info("QA review | APPROVED  time=%.1f ms", elapsed_ms)
        return {"approved": True, "issues": [], "improved_output": None, "qa_ms": elapsed_ms}

    # Extract issues list
    issues: list[str] = []
    issues_match = re.search(
        r"ISSUES:\s*(.*?)(?=IMPROVED OUTPUT:|$)",
        result,
        re.DOTALL | re.IGNORECASE,
    )
    if issues_match:
        raw = issues_match.group(1).strip()
        issues = [
            line.lstrip("-•* ").strip()
            for line in raw.splitlines()
            if line.strip() and line.strip() not in ("-", "•", "*")
        ]

    # Extract improved output
    improved: Optional[str] = None
    improved_match = re.search(
        r"IMPROVED OUTPUT:\s*(.*)",
        result,
        re.DOTALL | re.IGNORECASE,
    )
    if improved_match:
        improved = improved_match.group(1).strip()

    logger.info(
        "QA review | NOT APPROVED  issues=%d  improved=%s  time=%.1f ms",
        len(issues), improved is not None, elapsed_ms,
    )

    return {
        "approved":        False,
        "issues":          issues,
        "improved_output": improved,
        "qa_ms":           elapsed_ms,
    }
