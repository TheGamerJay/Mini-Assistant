"""
billing/cost_resolver.py — BYOK model: access-required module list.

Credit costs removed. This module now defines which modules require
full access (is_subscribed + api_key_verified) vs. which are freely browsable.

The actual gate is enforced by billing.access_gate.can_execute().
This file exists for reference and future per-module feature flags.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Modules that require full access (subscription + API key)
# ---------------------------------------------------------------------------

EXECUTION_REQUIRED: set[str] = {
    "builder",
    "builder_generation",
    "builder_regeneration",
    "image",
    "image_generation",
    "image_regeneration",
    "image_edit",
    "campaign_lab",
    "campaign_concept",
    "campaign_copy",
    "campaign_full_package",
    "doctor",
    "doctor_light",
    "doctor_full_scan",
    "doctor_deep_analysis",
    "hands",
    "web_search",
    "web_search_basic",
    "web_deep_search",
    "web_scrape",
    "general_chat",
    "core_chat",
    "chat_basic",
    "task_assist",
    "vision",
    "image_analyze",
    "app_build",
    "code_review",
    "fixloop_analyze",
    "tester_generate",
}

# Modules that are always free (no execution gate needed)
FREE_MODULES: set[str] = {
    "export_zip",    # exporting already-built artifacts
}

# ---------------------------------------------------------------------------
# Legacy shims — kept so any callers that imported these don't break
# ---------------------------------------------------------------------------

COST_MAP: dict[str, int] = {}

MODULE_ACTION_MAP: dict[str, str] = {
    "builder":      "builder_generation",
    "doctor":       "doctor_full_scan",
    "hands":        "builder_generation",
    "vision":       "image_analyze",
    "general_chat": "chat_basic",
    "core_chat":    "chat_basic",
    "web_search":   "web_search_basic",
    "task_assist":  "chat_basic",
    "campaign_lab": "campaign_concept",
    "image":        "image_generation",
    "image_edit":   "image_edit",
}


def get_action_cost(action_type: str, metadata: dict | None = None) -> int:
    """RETIRED — always returns 0. Credits no longer exist."""
    return 0


def resolve_action_type(module: str, metadata: dict | None = None) -> str:
    """Resolve a canonical action type string from a module name."""
    meta = metadata or {}
    base = MODULE_ACTION_MAP.get(module, module)
    if meta.get("is_regeneration") and base.endswith("_generation"):
        return base.replace("_generation", "_regeneration")
    return base


def is_free_gated(action_type: str) -> bool:
    """RETIRED — returns False. Grace system removed."""
    return False


def requires_execution_access(module: str) -> bool:
    """Returns True if this module needs subscription + API key."""
    return module not in FREE_MODULES
