"""
Prompt safety and structural validation layer.

Handles:
  - Empty / too-short prompts
  - Overly long prompts (truncation with warning)
  - Null bytes and control characters that crash JSON serialization
  - Excessive whitespace
  - Non-string inputs (auto-cast with warning)

NOTE: This is NOT content moderation — it is pipeline crash prevention only.
"""
import re
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

MAX_PROMPT_LENGTH = 8_000
MIN_PROMPT_LENGTH = 1

# Control characters (except tab \x09, newline \x0a, CR \x0d)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize(prompt: str) -> Tuple[str, List[str]]:
    """
    Clean a raw prompt string.
    Returns (cleaned_prompt, list_of_warnings).
    """
    warnings: List[str] = []

    if not isinstance(prompt, str):
        prompt = str(prompt)
        warnings.append(f"Prompt was not a string (type={type(prompt).__name__}); converted.")

    prompt = prompt.strip()

    if len(prompt) < MIN_PROMPT_LENGTH:
        return "", [f"Prompt is too short (min {MIN_PROMPT_LENGTH} chars)."]

    if len(prompt) > MAX_PROMPT_LENGTH:
        prompt = prompt[:MAX_PROMPT_LENGTH]
        warnings.append(f"Prompt truncated to {MAX_PROMPT_LENGTH} characters.")

    # Strip control characters
    cleaned = _CONTROL_RE.sub("", prompt)
    if cleaned != prompt:
        warnings.append("Removed non-printable control characters from prompt.")
    prompt = cleaned

    # Collapse excessive whitespace
    prompt = _WHITESPACE_RE.sub(" ", prompt).strip()

    return prompt, warnings


def validate(prompt: str) -> Tuple[bool, str, str]:
    """
    Validate and sanitize a prompt.
    Returns (is_valid, cleaned_prompt, error_message).
    error_message is empty string when is_valid is True.
    """
    cleaned, warnings = sanitize(prompt)

    if warnings:
        logger.debug("prompt_safety warnings: %s", warnings)

    if not cleaned:
        error = warnings[0] if warnings else "Empty prompt."
        logger.warning("prompt_safety rejected prompt: %s", error)
        return False, "", error

    return True, cleaned, ""
