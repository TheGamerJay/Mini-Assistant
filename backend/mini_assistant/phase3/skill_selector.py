"""
skill_selector.py — Skill Selector
────────────────────────────────────
Sits between the Planner and the Supervisor.

After the Planner produces a plan, the Skill Selector checks whether
any registered skill matches the intent + message. If a match is found,
the Supervisor uses the skill's refined execution steps instead of the
Planner's generic ones.

If no skill matches (or confidence is below threshold), execution
continues with the Planner's steps unchanged — the Skill Selector
never blocks the pipeline.

Confidence scoring:
  +0.40  intent match (skill.intents contains plan.intent)
  +0.35  trigger pattern match (any skill pattern fires on message)
  +0.15  slash command match (command name hints at skill)
  +0.10  prior success in reflection log (skill has been used before)

  Threshold to activate: >= skill.min_confidence (default 0.50)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from ..phase1.intent_planner import PlannerOutput
from .skill_registry import Skill, all_skills, active_skills

logger = logging.getLogger(__name__)


# ── Output type ───────────────────────────────────────────────────────────────

@dataclass
class SkillMatch:
    """Result of the Skill Selector pass."""
    matched:          bool
    skill:            Optional[Skill]  = None
    confidence:       float            = 0.0
    score_breakdown:  dict             = field(default_factory=dict)
    override_steps:   list[dict]       = field(default_factory=list)
    selector_ms:      float            = 0.0

    def to_dict(self) -> dict:
        return {
            "matched":         self.matched,
            "skill_name":      self.skill.name if self.skill else None,
            "skill_desc":      self.skill.description if self.skill else None,
            "skill_status":    self.skill.status if self.skill else None,
            "confidence":      round(self.confidence, 3),
            "score_breakdown": self.score_breakdown,
            "steps_overridden":len(self.override_steps) > 0,
            "selector_ms":     self.selector_ms,
        }


# ── Selector ──────────────────────────────────────────────────────────────────

class SkillSelector:
    """
    Match a Planner output to a registered skill.

    Usage:
        selector = SkillSelector()
        match = selector.select(plan, message, slash_command="fix")
        if match.matched:
            # use match.override_steps instead of plan.sequential_tasks
    """

    def __init__(self, reflection_log_path: Optional[str] = None):
        self._reflection_path = reflection_log_path
        self._known_successful_skills: set[str] = self._load_successful_skills()

    def _load_successful_skills(self) -> set[str]:
        """Load skill names that have at least one successful entry in the reflection log."""
        try:
            import json
            from pathlib import Path
            path = self._reflection_path or "./memory_store/reflections.json"
            p = Path(path)
            if not p.exists():
                return set()
            entries = json.loads(p.read_text(encoding="utf-8"))
            return {
                e["skill_used"]
                for e in entries
                if e.get("skill_used") and e.get("result") == "success"
            }
        except Exception:
            return set()

    def _score(
        self,
        skill: Skill,
        plan: PlannerOutput,
        message: str,
        slash_command: Optional[str],
    ) -> tuple[float, dict]:
        """Score a single skill against the current request."""
        score = 0.0
        breakdown: dict[str, float] = {}

        # Intent match
        if plan.intent in skill.intents:
            score += 0.40
            breakdown["intent_match"] = 0.40

        # Pattern match
        if skill.pattern_matches(message):
            score += 0.35
            breakdown["pattern_match"] = 0.35

        # Slash command hint
        if slash_command:
            # Check if command name appears in skill name
            if slash_command in skill.name:
                score += 0.15
                breakdown["slash_hint"] = 0.15

        # Prior success
        if skill.name in self._known_successful_skills:
            score += 0.10
            breakdown["prior_success"] = 0.10

        return round(score, 3), breakdown

    def select(
        self,
        plan: PlannerOutput,
        message: str,
        slash_command: Optional[str] = None,
    ) -> SkillMatch:
        """
        Select the best matching skill for the given Planner output.

        Args:
            plan:          PlannerOutput from Phase 1.
            message:       Effective user message.
            slash_command: Parsed slash command name (e.g. "fix"), or None.

        Returns:
            SkillMatch — always succeeds. matched=False if no skill qualifies.
        """
        t0 = time.perf_counter()

        best_skill:     Optional[Skill] = None
        best_score:     float           = 0.0
        best_breakdown: dict            = {}

        # Only score active skills (stubs require Phase 9)
        candidates = active_skills()

        for skill in candidates:
            score, breakdown = self._score(skill, plan, message, slash_command)
            if score > best_score:
                best_score     = score
                best_skill     = skill
                best_breakdown = breakdown

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

        if best_skill and best_score >= best_skill.min_confidence:
            logger.info(
                "SkillSelector matched: %s (score=%.2f, breakdown=%s)",
                best_skill.name, best_score, best_breakdown,
            )
            return SkillMatch(
                matched         = True,
                skill           = best_skill,
                confidence      = best_score,
                score_breakdown = best_breakdown,
                override_steps  = best_skill.steps,
                selector_ms     = elapsed_ms,
            )

        logger.debug(
            "SkillSelector: no match (best=%.2f for %s)",
            best_score, best_skill.name if best_skill else "none",
        )
        return SkillMatch(
            matched     = False,
            confidence  = best_score,
            selector_ms = elapsed_ms,
        )

    def refresh_successful_skills(self) -> None:
        """Reload the successful-skills set from disk (call after reflection logging)."""
        self._known_successful_skills = self._load_successful_skills()


# ── Module-level singleton ────────────────────────────────────────────────────

_selector: Optional[SkillSelector] = None


def get_selector() -> SkillSelector:
    global _selector
    if _selector is None:
        _selector = SkillSelector()
    return _selector
