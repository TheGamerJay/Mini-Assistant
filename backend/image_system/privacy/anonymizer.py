"""
Anonymizer — strip or hash sensitive tokens before any Tier B/C persistence.

Patterns scrubbed
-----------------
  • API keys / bearer tokens  (Bearer …, sk-…, key=…)
  • Email addresses
  • IPv4 addresses
  • Credit-card-like digit runs
  • File system paths containing a username segment
  • URLs with embedded credentials  (http://user:pass@…)

All replacements use stable placeholder strings so records remain readable
without leaking PII.  No external libraries required.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict


# ---------------------------------------------------------------------------
# Scrub patterns  (applied in order)
# ---------------------------------------------------------------------------

_RULES: list[tuple[re.Pattern, str]] = [
    # Bearer tokens / Authorization headers
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/]+=*"), r"\1[REDACTED_TOKEN]"),

    # OpenAI / Anthropic-style API keys
    (re.compile(r"\b(sk|pk|ak)-[A-Za-z0-9]{20,}"), "[REDACTED_KEY]"),

    # Generic key=value secrets in query strings / env blocks
    (re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*=\s*\S+"), r"\1=[REDACTED]"),

    # URL credentials  http://user:pass@host
    (re.compile(r"(?i)(https?://)([^@\s]+:[^@\s]+)@"), r"\1[REDACTED]@"),

    # Email addresses
    (re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"), "[EMAIL]"),

    # IPv4 addresses
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "[IP]"),

    # Credit-card-like runs (13-19 consecutive digits, possibly space-separated)
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[CC_NUMBER]"),

    # Windows-style paths with a username  C:\Users\<name>\...
    (re.compile(r"(?i)C:\\Users\\[^\\]+\\"), r"C:\\Users\\[USER]\\"),

    # Unix-style paths  /home/<name>/  or  /Users/<name>/
    (re.compile(r"(?i)/(home|Users)/[^/\s]+/"), r"/\1/[USER]/"),
]


def scrub(text: str) -> str:
    """
    Return `text` with all PII patterns replaced by stable placeholders.

    Args:
        text: Raw string (prompt, output snippet, error message, etc.)

    Returns:
        Scrubbed string — safe for Tier B/C persistence.
    """
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text


def scrub_dict(data: Dict[str, Any], fields: list[str]) -> Dict[str, Any]:
    """
    Scrub specific string fields in a dict, returning a shallow copy.

    Args:
        data:   Source dict (will not be mutated).
        fields: List of top-level keys whose string values should be scrubbed.

    Returns:
        New dict with specified fields scrubbed.
    """
    result = dict(data)
    for key in fields:
        if key in result and isinstance(result[key], str):
            result[key] = scrub(result[key])
    return result


def hash_id(raw_id: str) -> str:
    """
    One-way hash a user/session identifier for analytics grouping without
    storing the real identifier.

    Returns an 8-char hex prefix (32-bit collision space — sufficient for
    grouping, not unique enough to reverse).
    """
    return hashlib.sha256(raw_id.encode()).hexdigest()[:8]
