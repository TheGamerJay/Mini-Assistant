"""
execution/validation_router.py — Route module output to the correct validator.

Called after module_executor returns a result.
Uses the existing mini_assistant/system/validation.py as the backend.

Mode mapping:
  core_chat      → "chat"
  task_assist    → "chat"
  campaign_lab   → "chat"
  web_intelligence → "chat"
  builder        → "build"
  image          → "image"
  image_edit     → "image_edit"
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("ceo_router.validation_router")

_MODULE_TO_MODE: dict[str, str] = {
    "core_chat":        "chat",
    "task_assist":      "chat",
    "campaign_lab":     "chat",
    "web_intelligence": "chat",
    "builder":          "build",
    "image":            "image",
    "image_edit":       "image_edit",
    "doctor":           "chat",   # falls back to legacy validator; built-in uses repair_output rules
    "vision":           "chat",   # falls back to legacy validator; built-in uses vision_output rules
    "hands":            "chat",   # acknowledgement output — minimal validation
}


def validate_output(module: str, output: dict[str, Any]) -> dict[str, Any]:
    """
    Validate module output using the existing validation layer.

    Returns the original output dict with a "_validation" key added.
    Does not raise — validation failures are logged, not thrown.
    """
    mode = _MODULE_TO_MODE.get(module, "chat")

    try:
        from mini_assistant.system.validation import safe_return as _sr
        val = _sr(output, mode)
        output["_validation"] = {
            "ok":     val.get("ok", True),
            "reason": val.get("reason", "ok"),
            "mode":   mode,
        }
    except Exception as exc:
        log.warning("validation_router: validation failed for module=%s — %s", module, exc)
        output["_validation"] = {"ok": True, "reason": "validation_unavailable", "mode": mode}

    return output
