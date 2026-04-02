"""
memory/campaign_lab_retrieval.py — Task-type-aware scope selector for campaign_lab.

CEO uses this to decide which TR memory keys to load based on what the user is
actually trying to do within the Campaign Lab. Each task_type needs a different
subset of campaign memory — loading all of it would bloat context unnecessarily.

Task types and their required memory keys:
  campaign_concept     → campaign_profile, past_campaigns, audience_patterns
  copy_generation      → concept, campaign_profile, hooks, cta_patterns
  image_generation     → concept, copy_summary, visual_style, image_prompts
  copy_regeneration    → concept, failed_copy_issues, hooks
  image_regeneration   → concept, image_prompts, validation_issues, hooks
  ab_variant_generation→ concept, variant_a, performance_scores, platform_tone
  platform_formatting  → campaign_profile, platform, platform_style
  general              → campaign_profile (safe default)

Prioritization:
  - most recent campaigns
  - matching platform
  - matching audience
  - matching offer
  - prefer exact matches
  - fallback to campaign_profile

Rules:
  - do NOT load full campaign history
  - do NOT fabricate missing memory (caller must surface this)
  - only load failed patterns when regeneration is requested
  - retrieve only what is needed for the detected task_type
"""

from __future__ import annotations

import re

# ── Task-type detection patterns ───────────────────────────────────────────────
_CONCEPT = re.compile(
    r"\b(campaign (concept|idea|brief|strategy)|come up with|plan a campaign|"
    r"new campaign|design a campaign)\b",
    re.IGNORECASE,
)
_COPY_GEN = re.compile(
    r"\b(write (the |some )?(copy|ad|headline|body copy|caption)|generate copy|"
    r"create (an? )?(ad|advertisement|post|tagline|slogan))\b",
    re.IGNORECASE,
)
_IMAGE_GEN = re.compile(
    r"\b(generate (an? )?(image|visual|creative|banner|thumbnail)|"
    r"create (an? )?(image|visual)|image prompt|design (an? )?(image|creative))\b",
    re.IGNORECASE,
)
_COPY_REGEN = re.compile(
    r"\b(rewrite (the )?copy|regenerate copy|try (the )?copy again|"
    r"different (version|copy|headline|variation)|redo (the )?copy|"
    r"copy (didn.t work|wasn.t right|needs work))\b",
    re.IGNORECASE,
)
_IMAGE_REGEN = re.compile(
    r"\b(regenerate (the )?image|redo (the )?image|try (the )?image again|"
    r"different (image|creative|visual)|image (didn.t work|wasn.t right|needs work))\b",
    re.IGNORECASE,
)
_AB_VARIANT = re.compile(
    r"\b(a/b (test|variant|version)|ab (test|variant|version)|variant|"
    r"alternative version|split test|test variant|compare versions)\b",
    re.IGNORECASE,
)
_PLATFORM_FORMAT = re.compile(
    r"\b(format for|adapt for|optimize for|resize for|"
    r"(facebook|instagram|tiktok|twitter|linkedin|youtube|google) (ad|format|spec|version))\b",
    re.IGNORECASE,
)

# ── Scope per task_type ────────────────────────────────────────────────────────
_TASK_SCOPES: dict[str, list[str]] = {
    "campaign_concept":      ["campaign_profile", "past_campaigns", "audience_patterns"],
    "copy_generation":       ["concept", "campaign_profile", "hooks", "cta_patterns"],
    "image_generation":      ["concept", "copy_summary", "visual_style", "image_prompts"],
    "copy_regeneration":     ["concept", "failed_copy_issues", "hooks"],
    "image_regeneration":    ["concept", "image_prompts", "validation_issues", "hooks"],
    "ab_variant_generation": ["concept", "variant_a", "performance_scores", "platform_tone"],
    "platform_formatting":   ["campaign_profile", "platform", "platform_style"],
    "general":               ["campaign_profile"],
}


def detect_task_type(message: str) -> str:
    """
    Detect which campaign_lab task type the message represents.

    Returns one of: campaign_concept, copy_generation, image_generation,
    copy_regeneration, image_regeneration, ab_variant_generation,
    platform_formatting, general.

    Regeneration patterns are checked before generation to pick up "redo" intent.
    """
    if _COPY_REGEN.search(message):
        return "copy_regeneration"
    if _IMAGE_REGEN.search(message):
        return "image_regeneration"
    if _AB_VARIANT.search(message):
        return "ab_variant_generation"
    if _PLATFORM_FORMAT.search(message):
        return "platform_formatting"
    if _CONCEPT.search(message):
        return "campaign_concept"
    if _COPY_GEN.search(message):
        return "copy_generation"
    if _IMAGE_GEN.search(message):
        return "image_generation"
    return "general"


def get_scope(message: str) -> str:
    """
    Return a scope string for campaign_lab based on the message content.
    Format: "campaign_lab:key1,key2,..."

    CEO calls this during memory_decider to get the minimum required scope.
    """
    task_type = detect_task_type(message)
    keys = _TASK_SCOPES[task_type]
    return f"campaign_lab:{','.join(keys)}"


def get_required_keys(task_type: str) -> list[str]:
    """
    Return the required memory keys for a task_type.
    """
    return _TASK_SCOPES.get(task_type, _TASK_SCOPES["general"])
