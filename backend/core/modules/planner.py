"""
modules/planner.py — Planner Brain.

Takes a user goal and returns a structured build plan to the CEO.
Called by CEO ONLY. Returns plan to CEO. Does NOT build. Does NOT call other brains.

Output:
  {
      "type":       "plan_output",
      "title":      str,
      "summary":    str,
      "tech_stack": str,
      "components": [str],
      "steps":      [str],
      "constraints": [str],
      "confidence": "high" | "medium" | "low",
  }

Rules:
- Planner ONLY plans. Does NOT build.
- Returns plan to CEO — CEO decides what happens next.
- Never calls Builder, Hands, Vision, or Doctor.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

log = logging.getLogger("ceo_router.modules.planner")

_MODEL = "claude-sonnet-4-6"       # Sonnet for better structured plans

_SYSTEM = """You are the Planner Brain. Your ONLY job: create a structured build plan.

Rules:
- You PLAN only. You do NOT build anything.
- Return ONLY valid JSON — no markdown wrapper, no extra text.
- Be concise. The Builder Brain reads this plan.

Return exactly this JSON:
{
  "type": "plan_output",
  "title": "short title of what is being built",
  "summary": "one sentence description",
  "tech_stack": "HTML/CSS/JS or React or specify",
  "components": ["list", "of", "major", "components"],
  "steps": ["ordered build steps the builder should follow"],
  "constraints": ["must-haves", "must-nots", "style requirements"],
  "confidence": "high"
}"""


async def execute(
    decision:    dict[str, Any],
    memory:      dict[str, Any],
    _web:        dict[str, Any],
) -> dict[str, Any]:
    """
    Create a structured build plan for the CEO.
    Returns plan dict — CEO decides whether to approve and send to Builder.
    """
    message = decision.get("message", "")
    api_key = decision.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")

    if not api_key:
        return _error("No API key available for Planner Brain")

    # Enrich context from memory
    project_ctx = memory.get("project_context", {})
    ctx_hint = ""
    if project_ctx:
        stack = project_ctx.get("stack", "")
        if stack:
            ctx_hint = f"\n\nProject context — existing stack: {stack}"

    repo_ctx = decision.get("repo_context", "")
    user_prompt = f"Create a build plan for:\n{message}{ctx_hint}"
    if repo_ctx:
        user_prompt += f"\n\n{repo_ctx}"

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model=_MODEL,
            max_tokens=600,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = resp.content[0].text.strip() if resp.content else ""
        return _parse_plan(raw_text, message)
    except Exception as exc:
        log.error("planner: LLM call failed — %s", exc)
        return _error(str(exc))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_plan(raw: str, fallback_message: str) -> dict[str, Any]:
    """Parse JSON from planner response. Returns minimal plan on parse failure."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Try to extract JSON object from text
    m = re.search(r"\{[\s\S]+\}", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # Minimal fallback — plan is inferred from message
    log.warning("planner: JSON parse failed, using minimal fallback")
    return {
        "type":        "plan_output",
        "title":       fallback_message[:60],
        "summary":     f"Build: {fallback_message[:120]}",
        "tech_stack":  "HTML/CSS/JS",
        "components":  ["Main component"],
        "steps":       ["Build from requirements", "Test functionality", "Polish UI"],
        "constraints": [],
        "confidence":  "medium",
    }


def _error(message: str) -> dict[str, Any]:
    return {
        "type":        "error",
        "status":      "error",
        "error":       message,
        "title":       "Planning failed",
        "summary":     message,
        "tech_stack":  "",
        "components":  [],
        "steps":       [],
        "constraints": [],
        "confidence":  "low",
    }
