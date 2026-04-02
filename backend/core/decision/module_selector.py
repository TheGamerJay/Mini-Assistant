"""
decision/module_selector.py — Map CEO intent to a module name.

Rules:
- mapping only — no business logic
- modules never call each other directly
- mixed requests → CEO composes multi-step execution plan;
  module_selector still returns the PRIMARY module only
"""

from __future__ import annotations

# Valid module names — must match filenames in core/modules/
MODULE_NAMES = {
    "core_chat",
    "task_assist",
    "campaign_lab",
    "web_intelligence",
    "builder",
    "image",
    "image_edit",
    "doctor",
    "vision",
    "hands",
}

_INTENT_TO_MODULE: dict[str, str] = {
    "general_chat":   "core_chat",
    "task_assist":    "task_assist",
    "campaign_lab":   "campaign_lab",
    "web_lookup":     "web_intelligence",
    "builder":        "builder",
    "image_generate": "image",
    "image_edit":     "image_edit",
    "debug":          "doctor",
    "image_analyze":  "vision",
    "execute":        "hands",
}


def select_module(intent: str) -> str:
    """
    Return the module name for the given CEO intent.
    Falls back to core_chat if intent is unknown.
    """
    return _INTENT_TO_MODULE.get(intent, "core_chat")
