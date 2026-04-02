"""
validation/output_validator.py — Per-module output validation for the CEO pipeline.

Validates module output BEFORE returning to the caller.
Rules are applied based on validation_type, not the module name directly,
so the same rule set can be reused across similar modules.

Validation types and their rules:
  general_chat        — response exists, non-empty
  professional_content — response exists, sufficient length, structure markers
  marketing_content   — response exists, CTA indicators present
  web_content         — results list exists, at least one result
  structured_code     — response/code exists, code block or structured markers
  image_output        — image_url or base64 data present in output

Rules:
- never raises — always returns a result dict
- if validation system is unavailable, returns ok=True with note
- validation_type controls which rules run
- issues list is empty on pass; non-empty on failure
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("ceo_router.output_validator")

# ── CTA indicators for marketing_content ──────────────────────────────────────
_CTA_PATTERNS = re.compile(
    r"\b(buy|get|try|sign\s+up|subscribe|learn\s+more|shop|order|download|"
    r"start|join|book|reserve|contact|call\s+us|click|register|claim)\b",
    re.IGNORECASE,
)

# ── Code structure markers for structured_code ────────────────────────────────
_CODE_MARKERS = re.compile(
    r"(```|def |class |function |import |const |let |var |return |<[a-zA-Z]+>|"
    r"\bpublic\b|\bprivate\b|\bstatic\b)",
)


def validate(module: str, output: dict[str, Any], validation_type: str = "general_chat") -> dict[str, Any]:
    """
    Validate output for a given module using the specified validation_type rules.

    Returns:
        {
            "ok":              bool,
            "issues":          list[str],
            "validation_type": str,
        }
    """
    # First try the existing validation layer for modules it supports
    legacy_result = _try_legacy_validate(module, output)
    if legacy_result is not None:
        # Merge legacy result into our format
        ok = legacy_result.get("ok", True)
        reason = legacy_result.get("reason", "")
        issues = [] if ok else [reason] if reason else ["validation_failed"]
        return {"ok": ok, "issues": issues, "validation_type": validation_type}

    # Fall back to built-in per-type rules
    return _apply_rules(output, validation_type)


def _apply_rules(output: dict[str, Any], validation_type: str) -> dict[str, Any]:
    """Apply the rule set for the given validation_type."""
    dispatch = {
        "general_chat":        _validate_general_chat,
        "professional_content": _validate_professional_content,
        "marketing_content":   _validate_marketing_content,
        "web_content":         _validate_web_content,
        "structured_code":     _validate_structured_code,
        "image_output":        _validate_image_output,
        "repair_output":       _validate_repair_output,
        "vision_output":       _validate_vision_output,
        "hands_output":        _validate_hands_output,
    }
    fn = dispatch.get(validation_type, _validate_general_chat)
    issues = fn(output)
    return {
        "ok":              len(issues) == 0,
        "issues":          issues,
        "validation_type": validation_type,
    }


# ---------------------------------------------------------------------------
# Per-type rule functions — each returns a list[str] of issue descriptions.
# Empty list = passed.
# ---------------------------------------------------------------------------

def _validate_general_chat(output: dict) -> list[str]:
    issues: list[str] = []
    text = _extract_text(output)
    if not text or not text.strip():
        issues.append("response is empty")
    return issues


def _validate_professional_content(output: dict) -> list[str]:
    """
    task_assist rules:
    - response exists and is non-empty
    - minimum content length (>= 50 chars — rules out stub/error replies)
    - no fabrication indicators (hallucination tell-tales)
    """
    issues: list[str] = []
    text = _extract_text(output)

    if not text or not text.strip():
        issues.append("response is empty")
        return issues

    stripped = text.strip()

    if len(stripped) < 50:
        issues.append("response is too short for professional content")

    # Check for common hallucination tell-tales in assistant output
    fabrication_markers = [
        "as an ai language model",
        "i cannot provide specific",
        "i don't have access to real",
    ]
    lower = stripped.lower()
    for marker in fabrication_markers:
        if marker in lower:
            issues.append(f"possible fabricated-limitation response: '{marker}'")
            break

    return issues


def _validate_marketing_content(output: dict) -> list[str]:
    """
    campaign_lab rules:
    - response exists and is non-empty
    - CTA indicator must be present
    - no hallucinated product claim indicators
    """
    issues: list[str] = []
    text = _extract_text(output)

    if not text or not text.strip():
        issues.append("response is empty")
        return issues

    stripped = text.strip()

    if not _CTA_PATTERNS.search(stripped):
        issues.append("no CTA (call-to-action) indicator found in marketing output")

    # Guard against hallucinated numbers/statistics presented as fact
    fabricated_stat = re.search(r"\b(100%|guaranteed|\bproven\b.*\b\d+%)", stripped, re.IGNORECASE)
    if fabricated_stat:
        issues.append(f"possible unverified claim detected: '{fabricated_stat.group()}'")

    return issues


def _validate_web_content(output: dict) -> list[str]:
    """
    web_intelligence rules:
    - results list exists
    - at least one result returned
    - no pure error state
    """
    issues: list[str] = []

    if output.get("status") == "error":
        issues.append("module returned error status")
        return issues

    results = output.get("results") or output.get("web_results") or []
    if not results:
        issues.append("no web results found in output")
        return issues

    if len(results) < 1:
        issues.append("web_intelligence returned zero results")

    return issues


def _validate_structured_code(output: dict) -> list[str]:
    """
    builder rules:
    - response/code present
    - contains code structure markers
    """
    issues: list[str] = []

    text = (
        output.get("code")
        or output.get("files")
        or _extract_text(output)
    )

    if not text:
        issues.append("no code or structured output found")
        return issues

    if isinstance(text, list):
        # files list — just check it's non-empty
        if len(text) == 0:
            issues.append("files list is empty")
        return issues

    if not _CODE_MARKERS.search(str(text)):
        issues.append("structured_code output contains no recognizable code markers")

    return issues


def _validate_repair_output(output: dict) -> list[str]:
    """
    doctor rules:
    - type field must be "repair_output"
    - issue field present and non-empty
    - root_cause field present and non-empty (no guessing without diagnosis)
    - fix field present and non-empty
    - files_updated list present (may be empty for explanation-only fixes)
    - confidence field present
    """
    issues: list[str] = []

    if output.get("type") != "repair_output":
        issues.append("repair_output: 'type' field must be 'repair_output'")

    for required in ("issue", "root_cause", "fix", "confidence"):
        val = output.get(required)
        if not val or not str(val).strip():
            issues.append(f"repair_output: '{required}' field is missing or empty")

    if "files_updated" not in output:
        issues.append("repair_output: 'files_updated' field is missing")

    # root_cause must not be a vague non-answer
    root_cause = str(output.get("root_cause", "")).lower()
    vague = ["unknown", "unclear", "not sure", "might be", "possibly", "could be"]
    if any(v in root_cause for v in vague):
        issues.append("repair_output: root_cause appears vague — diagnosis required")

    return issues


def _validate_vision_output(output: dict) -> list[str]:
    """
    vision rules:
    - type field must be "vision_output"
    - analysis field present and non-empty
    - analysis must be grounded (minimum length)
    - issues list present (may be empty)
    - recommendations list present (may be empty)
    """
    issues: list[str] = []

    if output.get("type") != "vision_output":
        issues.append("vision_output: 'type' field must be 'vision_output'")

    analysis = output.get("analysis", "")
    if not analysis or not str(analysis).strip():
        issues.append("vision_output: 'analysis' field is missing or empty")
    elif len(str(analysis).strip()) < 20:
        issues.append("vision_output: 'analysis' is too short to be grounded")

    for field in ("issues", "recommendations"):
        if field not in output:
            issues.append(f"vision_output: '{field}' list is missing")
        elif not isinstance(output[field], list):
            issues.append(f"vision_output: '{field}' must be a list")

    return issues


def _validate_hands_output(output: dict) -> list[str]:
    """
    hands rules:
    - type must be "hands_output"
    - actions list must be present
    - summary must be present
    """
    issues: list[str] = []
    if output.get("type") != "hands_output":
        issues.append("hands_output: 'type' field must be 'hands_output'")
    if "actions" not in output or not isinstance(output.get("actions"), list):
        issues.append("hands_output: 'actions' list is missing")
    if not output.get("summary"):
        issues.append("hands_output: 'summary' field is missing")
    return issues


def _validate_image_output(output: dict) -> list[str]:
    """
    image / image_edit rules:
    - image_url or base64 data present
    - not an error state
    """
    issues: list[str] = []

    if output.get("status") == "error":
        issues.append("module returned error status")
        return issues

    has_url  = bool(output.get("image_url") or output.get("url"))
    has_b64  = bool(output.get("image_base64") or output.get("base64"))
    has_data = bool(output.get("data"))

    if not (has_url or has_b64 or has_data):
        issues.append("no image data (url, base64, or data) found in image output")

    return issues


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text(output: dict) -> str:
    """Pull the primary text field from a module output dict."""
    for key in ("response", "text", "content", "message", "reply", "output"):
        val = output.get(key)
        if val and isinstance(val, str):
            return val
    return ""


def _try_legacy_validate(module: str, output: dict) -> dict | None:
    """
    Attempt to use mini_assistant/system/validation.py.
    Returns None if unavailable (caller falls back to built-in rules).
    """
    from ..execution.validation_router import _MODULE_TO_MODE
    mode = _MODULE_TO_MODE.get(module, "chat")

    try:
        from mini_assistant.system.validation import validate_response
        result = validate_response(output, mode)
        return {
            "ok":    result.valid,
            "reason": result.reason or "ok",
            "mode":  mode,
        }
    except Exception:
        return None
