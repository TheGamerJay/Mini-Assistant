"""
mini_assistant/phase3 — Phase 3: Skill Library + Reflection
─────────────────────────────────────────────────────────────
Full request flow after Phase 3:

    Command Parser  (Phase 1)
    → Planner       intent + task list  (Phase 1)
    → CEO           posture  (Phase 2)
    → Manager       session context  (Phase 2)
    → Skill Selector  ← NEW: match Planner output to a known skill
    → Supervisor    task tracking  (Phase 2)
    → Brain         (image_system execution layer)
    → Critic        (Phase 1)
    → Reflection    ← NEW: log outcome, update skill success cache
    → Composer      (Phase 1)

Public surface:

    from mini_assistant.phase3 import get_selector, reflect
    from mini_assistant.phase3.skill_registry import all_skills, get as get_skill
"""

from .skill_selector  import get_selector, SkillSelector, SkillMatch
from .reflection_layer import reflect, ReflectionRecord
from .skill_registry   import (
    all_skills, active_skills, skills_for_intent,
    get as get_skill, register as register_skill, Skill,
)

__all__ = [
    "get_selector", "SkillSelector", "SkillMatch",
    "reflect", "ReflectionRecord",
    "all_skills", "active_skills", "skills_for_intent",
    "get_skill", "register_skill", "Skill",
]
