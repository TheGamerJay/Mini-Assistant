"""
Mini Assistant — Response Validation Layer
Ensures model outputs are valid, safe, and mode-consistent before returning.
"""

import re
from dataclasses import dataclass


@dataclass
class ValidationResult:
    valid: bool
    reason: str = "ok"
    safe_fallback: str | None = None


# ─── HALLUCINATION SIGNALS (UNSAFE ONLY) ─────────────────────

HALLUCINATION_PATTERNS = [
    r"\b(100%|guaranteed|always works|never fails)\b",
    r"\bi (made up|fabricated|invented|assumed) (this|that|these|those)\b",
    r"\b(certainly|definitely|absolutely),?\s+here (is|are)\b",
    r"\bthis (is|was) confirmed (by|in)\b(?!.*\[verified\])",
]

# Valid transparency statements — do NOT block these
TRANSPARENCY_PATTERNS = [
    r"\bas of my (last|latest) (update|training|knowledge)\b",
    r"\bi (don't|do not) have access to real.?time\b",
    r"\bi (cannot|can't) browse\b",
    r"\bI cannot (verify|confirm) this\b",
    r"\bthis (may|might) be (outdated|incorrect)\b",
]


def _is_hallucination(text: str) -> bool:
    for pattern in TRANSPARENCY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False
    for pattern in HALLUCINATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


# ─── EMPTY SIGNALS ───────────────────────────────────────────

EMPTY_SIGNALS = [
    r"^\s*$",
    r"^(\.\.\.|…)+$",
    r"^(sure|okay|of course)[!.]?\s*$",
]


# ─── MODE CHECKS ─────────────────────────────────────────────

def _has_build_content(text: str) -> bool:
    if re.search(r"```[\w]*\n[\s\S]+?```", text):
        return True
    code_signals = [
        r"\bdef\s+\w+\s*\(",
        r"\bclass\s+\w+",
        r"\bfunction\s+\w+\s*\(",
        r"\bconst\s+\w+\s*=",
        r"\bimport\s+[\w{]",
        r"\bfrom\s+\w+\s+import\b",
        r"\basync\s+def\s+\w+",
        r"<\w+[\s>][\s\S]{10,}",
    ]
    return sum(bool(re.search(p, text)) for p in code_signals) >= 2


def _has_edit_content(text: str) -> bool:
    edit_signals = [
        r"^[-+]{1,3}\s+.+$",
        r"\b(changed|updated|replaced|renamed|removed|added):\s+",
        r"(before|after|old|new):\s*\n",
        r"```[\w]*\n[\s\S]+?```",
        r"\bwhat changed\b",
        r"~~.+~~",
        r"\[\[.+\]\]",
    ]
    hits = sum(bool(re.search(p, text, re.IGNORECASE | re.MULTILINE)) for p in edit_signals)
    return hits >= 1 and len(text.strip()) > 40


def _validate_image_response(response: dict) -> tuple[bool, str]:
    prompt = response.get("image_prompt", "").strip()
    canvas = response.get("canvas", "").strip()

    if not prompt:
        return False, "missing image_prompt"
    if len(prompt) < 15:
        return False, "image_prompt too short"
    if not canvas:
        return False, "missing canvas"
    if canvas not in {"vertical", "square", "horizontal", "wide"}:
        return False, f"invalid canvas value: '{canvas}'"

    neg = response.get("negative_prompt")
    if neg is not None:
        if not isinstance(neg, str) or len(neg.strip()) < 5:
            return False, "negative_prompt present but invalid"
        if "\n" in neg:
            return False, "negative_prompt must be single line"

    if response.get("text") and not prompt:
        return False, "text-only response in image mode"

    return True, "ok"


# ─── MODE FAILURE HINTS ───────────────────────────────────────

MODE_FAILURE_HINTS = {
    "build": "Response must contain code (fenced block or recognizable code structure).",
    "edit":  "Response must contain edited content, diff output, or a clear before/after.",
    "image": "Response must include image_prompt and canvas. Text-only is invalid.",
    "chat":  "Response must contain non-empty text.",
}


# ─── CORE VALIDATOR ──────────────────────────────────────────

def validate_response(response: dict, mode: str) -> ValidationResult:
    text = response.get("text", "")

    # 1. empty / broken output
    for pattern in EMPTY_SIGNALS:
        if re.match(pattern, text.strip(), re.IGNORECASE):
            return ValidationResult(
                valid=False,
                reason="empty_output",
                safe_fallback="I wasn't able to generate a valid response. Please try rephrasing.",
            )

    # 2. hallucination (unsafe signals only — transparency is allowed)
    if _is_hallucination(text):
        return ValidationResult(
            valid=False,
            reason="hallucination_signal",
            safe_fallback="I'm not confident enough in this answer to return it. "
                          "Provide more context or ask me to search for verified information.",
        )

    # 3. mode consistency
    if mode == "build" and not _has_build_content(text):
        return ValidationResult(
            valid=False,
            reason="mode_mismatch:build",
            safe_fallback=f"Something went wrong. {MODE_FAILURE_HINTS['build']}",
        )

    if mode == "edit" and not _has_edit_content(text):
        return ValidationResult(
            valid=False,
            reason="mode_mismatch:edit",
            safe_fallback=f"Something went wrong. {MODE_FAILURE_HINTS['edit']}",
        )

    if mode == "image":
        ok, reason = _validate_image_response(response)
        if not ok:
            return ValidationResult(
                valid=False,
                reason=f"mode_mismatch:image:{reason}",
                safe_fallback=f"Image response invalid ({reason}). {MODE_FAILURE_HINTS['image']}",
            )

    if mode == "chat" and not text.strip():
        return ValidationResult(
            valid=False,
            reason="mode_mismatch:chat",
            safe_fallback=MODE_FAILURE_HINTS["chat"],
        )

    return ValidationResult(valid=True)


# ─── SAFE RETURN WRAPPER ─────────────────────────────────────

def safe_return(response: dict, mode: str) -> dict:
    result = validate_response(response, mode)
    if not result.valid:
        return {"ok": False, "reason": result.reason, "message": result.safe_fallback}
    return {"ok": True, "response": response}