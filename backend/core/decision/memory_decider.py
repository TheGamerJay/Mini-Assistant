"""
decision/memory_decider.py — Decide whether TR memory is needed and which scope.

Rules:
- no module may load memory independently — CEO decides
- retrieve only scoped, relevant data — no full history dumps
- no embeddings/vector DB — flat JSON TR files only
- if required memory is missing → needs_user_input = True, do not fabricate

For task_assist and campaign_lab, the scope is task-type-specific:
  - task_assist  : scope selected by task_assist_retrieval.get_scope(message)
  - campaign_lab : scope selected by campaign_lab_retrieval.get_scope(message)

For all other modules, a fixed default scope is used.

Memory scopes per module (defaults — overridden by retrieval modules where applicable):
  task_assist     : task-type-specific (cover_letter, resume_update, etc.)
  campaign_lab    : task-type-specific (concept, copy, image, ab_variant, etc.)
  builder         : project_context, task_state, prior_code
  core_chat       : recent_turns
  web_intelligence: none (live data only)
  image           : style_preferences
  image_edit      : source_metadata
"""

from __future__ import annotations

from typing import Optional

# Default fixed scopes for modules that don't use task-type-specific retrieval
_FIXED_SCOPES: dict[str, Optional[str]] = {
    "builder":          "builder:project_context,task_state,prior_code",
    "core_chat":        "core_chat:recent_turns",
    "web_intelligence": None,
    "image":            "image:style_preferences",
    "image_edit":       "image_edit:source_metadata",
    "doctor":           "doctor:repair_memory",
    "vision":           "vision:source_metadata",
    "hands":            None,
}

# Modules that always require memory
_ALWAYS_NEEDS_MEMORY = {"task_assist", "campaign_lab", "builder", "doctor"}

# Modules that never need memory
_NEVER_NEEDS_MEMORY = {"web_intelligence", "hands"}


def decide_memory(
    module:  str,
    intent:  str,
    message: str = "",
) -> tuple[bool, Optional[str]]:
    """
    Returns (requires_memory, memory_scope | None).

    For task_assist and campaign_lab, message is used to detect task_type
    and select the minimum required scope.
    For other modules, a fixed default scope is used.
    """
    if module in _NEVER_NEEDS_MEMORY:
        return False, None

    # task_assist — task-type-specific retrieval
    if module == "task_assist":
        scope = _get_task_assist_scope(message)
        return True, scope

    # campaign_lab — task-type-specific retrieval
    if module == "campaign_lab":
        scope = _get_campaign_lab_scope(message)
        return True, scope

    # All other modules — fixed scope
    if module in _ALWAYS_NEEDS_MEMORY:
        scope = _FIXED_SCOPES.get(module)
        return True, scope

    scope = _FIXED_SCOPES.get(module)
    return scope is not None, scope


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_task_assist_scope(message: str) -> str:
    """Delegate to task_assist_retrieval for task-type-specific scope."""
    try:
        from ..memory.task_assist_retrieval import get_scope
        return get_scope(message)
    except Exception:
        # Fallback to safe default if retrieval module unavailable
        return "task_assist:resume,user_profile"


def _get_campaign_lab_scope(message: str) -> str:
    """Delegate to campaign_lab_retrieval for task-type-specific scope."""
    try:
        from ..memory.campaign_lab_retrieval import get_scope
        return get_scope(message)
    except Exception:
        return "campaign_lab:campaign_profile"
