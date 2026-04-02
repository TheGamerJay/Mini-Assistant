"""
billing/cost_resolver.py — Central action cost map.

All credit costs live here. NO module may define its own cost.
CEO uses get_action_cost() to resolve every action before billing.

COST_MAP keys are CEO-level action_type strings.
mini_credits.py is the underlying deduction engine — costs here
override or extend its CREDIT_COSTS for the CEO billing layer.

Regeneration rule: regenerations always cost less than originals.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Canonical cost map (credits)
# ---------------------------------------------------------------------------

COST_MAP: dict[str, int] = {
    # Builder
    "builder_generation":       8,
    "builder_regeneration":     4,

    # Image
    "image_generation":         10,
    "image_regeneration":       6,
    "image_edit":               8,

    # Campaign Lab
    "campaign_concept":         5,
    "campaign_copy":            3,
    "campaign_full_package":    12,

    # Doctor
    "doctor_light":             2,
    "doctor_full_scan":         6,
    "doctor_deep_analysis":     10,

    # Web
    "web_search_basic":         0,
    "web_deep_search":          2,
    "web_scrape":               3,

    # Chat — 0 cost but requires credits > 0 to run
    "chat_basic":               0,

    # Pass-through for legacy mini_credits action types
    "chat_message":             0,   # CEO layer: free; underlying system may deduct separately
    "chat_stream":              0,
    "app_build":                8,
    "code_review":              2,
    "image_analyze":            3,
    "campaign_lab_concept":     5,
    "fixloop_analyze":          2,
    "tester_generate":          2,
    "export_zip":               0,
}

# ---------------------------------------------------------------------------
# Module → action_type mapping
# CEO uses this when a RouterDecision arrives without explicit action_type
# ---------------------------------------------------------------------------

MODULE_ACTION_MAP: dict[str, str] = {
    "builder":       "builder_generation",
    "doctor":        "doctor_full_scan",
    "hands":         "builder_generation",     # code execution ~ build cost
    "vision":        "image_analyze",
    "general_chat":  "chat_basic",
    "core_chat":     "chat_basic",
    "web_search":    "web_search_basic",
    "task_assist":   "chat_basic",
    "campaign_lab":  "campaign_concept",
    "image":         "image_generation",       # image generation module
    "image_edit":    "image_edit",
}

# Action types that cost 0 but still require credits > 0
FREE_BUT_GATED: frozenset[str] = frozenset({
    "chat_basic", "chat_message", "chat_stream",
    "web_search_basic", "export_zip",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_action_cost(action_type: str, metadata: dict[str, Any] | None = None) -> int:
    """
    Resolve credit cost for an action.

    Args:
        action_type: canonical CEO action type string
        metadata:    optional context for dynamic cost resolution
                     e.g. {"is_regeneration": True, "complexity": "full_system"}

    Returns:
        Credit cost (int, always ≥ 0).
    """
    meta = metadata or {}

    # Dynamic: regeneration reduces cost
    is_regen = meta.get("is_regeneration", False)
    if is_regen:
        regen_key = action_type.replace("_generation", "_regeneration")
        if regen_key in COST_MAP:
            return COST_MAP[regen_key]

    # Dynamic: complexity escalation for builder/doctor
    complexity = meta.get("complexity", "simple")
    if action_type == "builder_generation" and complexity == "full_system":
        return COST_MAP.get("builder_generation", 8)   # same base; orchestration adds value
    if action_type == "doctor_full_scan" and complexity == "multi_step":
        return COST_MAP.get("doctor_deep_analysis", 10)

    return COST_MAP.get(action_type, 1)


def resolve_action_type(module: str, metadata: dict[str, Any] | None = None) -> str:
    """
    Map a module name to its canonical action_type.
    CEO calls this when the action_type is not explicitly set.
    """
    meta = metadata or {}

    # Detect regeneration from metadata hint
    if meta.get("is_regeneration"):
        base = MODULE_ACTION_MAP.get(module, "chat_basic")
        regen = base.replace("_generation", "_regeneration")
        return regen if regen in COST_MAP else base

    # Image edit vs image generation
    if module in ("image_edit", "vision") and meta.get("has_attachment"):
        return "image_edit"

    # Doctor depth
    if module == "doctor":
        complexity = meta.get("complexity", "simple")
        if complexity == "full_system":
            return "doctor_deep_analysis"
        if complexity == "multi_step":
            return "doctor_full_scan"
        return "doctor_light"

    # Campaign sub-types
    if module == "campaign_lab":
        sub = meta.get("campaign_action", "concept")
        return {
            "concept":      "campaign_concept",
            "copy":         "campaign_copy",
            "full_package": "campaign_full_package",
        }.get(sub, "campaign_concept")

    return MODULE_ACTION_MAP.get(module, "chat_basic")


def is_free_gated(action_type: str) -> bool:
    """Return True if action costs 0 credits but still requires balance > 0."""
    return action_type in FREE_BUT_GATED
