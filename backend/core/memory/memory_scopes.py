"""
memory/memory_scopes.py — Canonical scope definitions for all modules.

These define the FULL set of valid TR memory keys per module.
memory_decider.py uses task-specific retrieval for task_assist and campaign_lab
(they load a subset, not the full scope). Other modules load their full scope.

Format:
  MODULE_SCOPES[module] = "module:key1,key2,..."

Memory file locations:
  memory_store/tr/{user_id}/{module}/{key}.json

Adding a new module:
  1. Add an entry here
  2. Add memory_decider logic (or create a retrieval module)
  3. Create memory_store/tr/{user_id}/{module}/ directory structure

=============================================================================
TASK ASSIST — full key set
  user_profile      : name, experience, contact, preferences
  resume            : latest full resume text (structured JSON)
  skills            : skills list with proficiency levels
  applications      : list of {company, role, resume_used, cover_letter, status, date}
  last_followup     : last follow-up message sent (text + date)
  message_history   : past emails/messages (lightweight, last 5–10)
  tone_preferences  : preferred tone settings {formal, casual, assertive, ...}

CAMPAIGN LAB — full key set
  campaign_profile  : business/product, audience, offer, tone, platform, goals
  past_campaigns    : list of past campaign summaries
  audience_patterns : validated audience data points
  concept           : current or last campaign concept
  copy_summary      : summary of last generated copy
  hooks             : list of high-performing hook lines
  cta_patterns      : list of high-performing CTA styles
  visual_style      : visual style preferences (colors, tone, mood)
  image_prompts     : list of past strong image prompts
  failed_copy_issues: list of reasons past copy was rejected/poor
  validation_issues : list of past validation failure reasons
  variant_a         : A version of the current A/B test
  performance_scores: scoring data per variant/concept
  platform_tone     : platform-specific tone preferences
  platform          : current target platform
  platform_style    : style guide per platform

BUILDER — full key set
  project_context   : project name, stack, folder structure
  task_state        : current task progress and verified outputs
  prior_code        : past verified code snippets/files

CORE_CHAT
  recent_turns      : last 5 turns of conversation (lightweight)

IMAGE
  style_preferences : preferred image styles, aspect ratios, moods

IMAGE_EDIT
  source_metadata   : original image size, format, context
=============================================================================
"""

from __future__ import annotations

MODULE_SCOPES: dict[str, str] = {
    "task_assist": (
        "task_assist:user_profile,resume,skills,applications,"
        "last_followup,message_history,tone_preferences"
    ),
    "campaign_lab": (
        "campaign_lab:campaign_profile,past_campaigns,audience_patterns,"
        "concept,copy_summary,hooks,cta_patterns,visual_style,image_prompts,"
        "failed_copy_issues,validation_issues,variant_a,performance_scores,"
        "platform_tone,platform,platform_style"
    ),
    "builder":          "builder:project_context,task_state,prior_code",
    "core_chat":        "core_chat:recent_turns",
    "web_intelligence": "",   # no TR memory — web only
    "image":            "image:style_preferences",
    "image_edit":       "image_edit:source_metadata",
    "doctor":           "doctor:repair_memory",
    "vision":           "vision:source_metadata",
    "hands":            "",   # no TR memory — action only
}


def get_scope(module: str) -> str:
    """Return the full scope string for a module. Empty string = no memory needed."""
    return MODULE_SCOPES.get(module, "")
