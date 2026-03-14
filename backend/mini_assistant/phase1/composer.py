"""
composer.py — Phase 1 Response Composer
─────────────────────────────────────────
Merges Planner metadata + Critic result + brain reply into the
single response dict the frontend receives.

The composer is the LAST step before the API returns to the client.
It ensures:
  • A consistent response shape across all intents
  • Planner pipeline metadata is included (for CognitiveStream)
  • Critic corrections are applied
  • No raw debug noise leaks unless intent warrants it
  • Slash command metadata is surfaced to the frontend
"""

from __future__ import annotations

from .intent_planner import PlannerOutput
from .critic import CriticResult


def compose(
    reply: str,
    plan: PlannerOutput,
    critic: CriticResult,
    session_id: str,
    route_result: dict | None = None,
) -> dict:
    """
    Assemble the final API response.

    Args:
        reply:        Raw reply from the brain (before Critic correction).
        plan:         PlannerOutput for this request.
        critic:       CriticResult (provides corrected_reply).
        session_id:   Session identifier.
        route_result: Optional dict from the execution router (image_system RouterBrain).

    Returns:
        dict — the complete response body sent to the frontend.
    """
    return {
        # Primary reply — always the Critic-corrected version
        "reply": critic.corrected_reply,

        # Intent and confidence (from Planner)
        "intent":        plan.intent,
        "confidence":    plan.confidence,
        "response_mode": plan.response_mode,

        # Full plan (for CognitiveStream pipeline visualization)
        "plan": plan.to_dict(),

        # Critic metadata
        "critic": {
            "passed": critic.passed,
            "issues": critic.issues,
            "ms":     critic.critic_ms,
        },

        # Execution router result (image_system RouterBrain — may be None)
        "route_result": route_result or {},

        # Session
        "session_id": session_id,

        # Slash command info (None if natural language)
        "slash_command": plan.slash_command,
    }
