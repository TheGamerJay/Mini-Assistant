"""
reflection_layer.py — Phase 3 Reflection Layer
────────────────────────────────────────────────
Wraps the existing mini_assistant/self_improvement/reflection.py.
Runs AFTER the Critic and BEFORE the Composer finalises the response.

Responsibilities:
  1. Log the execution outcome (intent, skill used, critic result)
  2. Store skill-improvement metadata (confidence, override flag)
  3. Refresh the SkillSelector's successful-skill cache after a success
  4. Keep learning lightweight — no LLM call on success; lesson generation
     is deferred to the Ollama-based _generate_lesson() only on failures

Phase 3 rules honoured:
  - Does NOT auto-rewrite code
  - Does NOT replace the existing Reflection class
  - Lessons are inspectable via GET /api/project/context (future: /api/reflections)
  - Skill improvements are stored but never auto-applied
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from ..phase1.intent_planner import PlannerOutput
from ..phase1.critic import CriticResult

logger = logging.getLogger(__name__)


# ── Output type ───────────────────────────────────────────────────────────────

@dataclass
class ReflectionRecord:
    entry_id:      Optional[str]  # reflection log entry id (None if logging failed)
    logged:        bool
    lesson:        str
    reflection_ms: float

    def to_dict(self) -> dict:
        return {
            "logged":        self.logged,
            "entry_id":      self.entry_id,
            "lesson":        self.lesson,
            "reflection_ms": self.reflection_ms,
        }


# ── Reflection layer ──────────────────────────────────────────────────────────

def reflect(
    message:       str,
    plan:          PlannerOutput,
    critic:        CriticResult,
    skill_match:   Optional[object] = None,   # SkillMatch from phase3.skill_selector
    reply:         str              = "",
) -> ReflectionRecord:
    """
    Log a reflection entry for this request.

    Args:
        message:     Effective user message.
        plan:        PlannerOutput (intent, confidence, slash_command).
        critic:      CriticResult (passed, issues).
        skill_match: SkillMatch from SkillSelector (may be None).
        reply:       Final reply text (used for lesson generation on failure).

    Returns:
        ReflectionRecord — always succeeds (logging errors are non-fatal).
    """
    t0 = time.perf_counter()

    result    = "success" if critic.passed else "partial"
    errors    = critic.issues if not critic.passed else []
    skill_name: Optional[str] = None
    skill_conf: float         = 0.0

    if skill_match and getattr(skill_match, "matched", False):
        skill_name = skill_match.skill.name
        skill_conf = skill_match.confidence

    # Build a simple lesson without LLM (keeps reflection fast for passing requests)
    if critic.passed:
        lesson = f"Intent '{plan.intent}' resolved successfully via '{plan.routing_method}'."
        if skill_name:
            lesson += f" Skill '{skill_name}' (conf={skill_conf:.2f}) was effective."
    else:
        issue_summary = "; ".join(errors[:2]) if errors else "unknown issue"
        lesson = f"Intent '{plan.intent}' had quality issues: {issue_summary}"

    entry_id: Optional[str] = None
    try:
        from ..self_improvement.reflection import Reflection
        ref = Reflection()
        entry_id = ref.log(
            task          = message[:200],
            result        = result,
            brain         = plan.routing_method,
            attempts      = 1,
            errors_seen   = errors,
            fixes_applied = [],
            lesson        = lesson,
            metadata      = {
                "intent":          plan.intent,
                "confidence":      plan.confidence,
                "response_mode":   plan.response_mode,
                "slash_command":   plan.slash_command,
                "skill_used":      skill_name,
                "skill_confidence":skill_conf,
                "critic_passed":   critic.passed,
            },
        )

        # Refresh SkillSelector cache after a successful skill execution
        if critic.passed and skill_name:
            try:
                from .skill_selector import get_selector
                get_selector().refresh_successful_skills()
            except Exception:
                pass

    except Exception as exc:
        logger.warning("Reflection logging failed (non-fatal): %s", exc)
        entry_id = None

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    return ReflectionRecord(
        entry_id      = entry_id,
        logged        = entry_id is not None,
        lesson        = lesson,
        reflection_ms = elapsed_ms,
    )
