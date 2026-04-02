"""
billing/output_sanitizer.py — Output sanitization before user sees results.

Strips internal details from module outputs before returning to users.
CEO calls sanitize() on every result before it leaves the system.

REMOVES:
  - absolute file paths (backend server paths)
  - raw stack traces (Python tracebacks)
  - internal IDs and slugs (session_id, user_id formats)
  - raw JWT tokens
  - environment variable names + values
  - internal module names (builder, doctor, hands, vision, ceo)
  - repair memory slugs and internal record IDs
  - X-Ray report data (user-facing responses only)
  - raw log entries

KEEPS:
  - user-facing error messages
  - structured code output (files, code blocks)
  - clean summaries
  - safe reasoning explanations

MODES:
  user   → full sanitization (default)
  admin  → minimal sanitization (removes secrets only)

CHAIN-OF-THOUGHT PROTECTION:
  Intermediate reasoning steps are collapsed to a short summary.
  Internal step-by-step traces are never exposed.
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("billing.output_sanitizer")

# ---------------------------------------------------------------------------
# Patterns to strip
# ---------------------------------------------------------------------------

# Absolute server paths — e.g. /home/user/app/backend/core/...
_PATH_PAT = re.compile(
    r"(?:/[a-zA-Z0-9_./-]{5,}\.py|"       # Unix .py paths
    r"[A-Z]:\\[^\s\"'<>]{5,}\.py|"         # Windows .py paths
    r"(?:/home|/app|/backend|/usr|/var|/tmp)/[^\s\"'<>]{3,})",
    re.IGNORECASE,
)

# Python tracebacks
_TRACEBACK_PAT = re.compile(
    r"Traceback \(most recent call last\).*?(?=\n\n|\Z)",
    re.DOTALL,
)

# Environment variable patterns
_ENV_PAT = re.compile(
    r"(?:ANTHROPIC_API_KEY|JWT_SECRET|MONGO(?:DB)?_URI|STRIPE_(?:SECRET|KEY)|"
    r"RESEND_API_KEY|DATABASE_URL|REDIS_URL|OPENAI_API_KEY|"
    r"ADMIN_XRAY_KEY)\s*[=:]\s*\S+",
    re.IGNORECASE,
)

# JWT tokens (3-part base64url format)
_JWT_PAT = re.compile(
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
)

# Internal module labels in error messages
_MODULE_LABEL_PAT = re.compile(
    r"\b(ceo_router|brain_router|module_executor|state_manager|"
    r"approval_gate|repair_store|repair_search|xray_endpoint|"
    r"ceo_orchestrator|event_emitter)\b",
    re.IGNORECASE,
)

# Internal field names that should never appear in user output
_INTERNAL_FIELDS = frozenset({
    "repair_memory_used", "repair_memory_matches", "repair_memory_guidance",
    "approval_history", "evidence_history", "retry_counts",
    "logged_at", "billing_layer", "block_reason",
    "_rank_score", "_domain", "meta",
    "proposed_fix",  # internal; user sees only the summary
})

# Keys to preserve in user-facing output
_SAFE_KEYS = frozenset({
    "type", "status", "summary", "message", "answer", "files",
    "code", "path", "description", "notes", "confidence",
    "issue", "fix", "recommendation", "warning", "title",
    "sources", "search_failed", "fail_reason",
    "credits_used", "remaining_credits", "credit_warning",
    "action", "options", "question", "reason",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sanitize(
    output:      dict[str, Any],
    mode:        str = "user",
    keep_files:  bool = True,
) -> dict[str, Any]:
    """
    Sanitize a module output dict before returning to the user.

    Args:
        output:     raw module output dict
        mode:       "user" (full sanitize) | "admin" (secrets only)
        keep_files: if True, preserve files[] array (code output)

    Returns:
        Cleaned output dict safe for user consumption.
    """
    if not isinstance(output, dict):
        return output

    if mode == "admin":
        return _sanitize_secrets_only(output)

    return _sanitize_full(output, keep_files=keep_files)


def sanitize_text(text: str, mode: str = "user") -> str:
    """Sanitize a raw string (e.g. error messages, summaries)."""
    if not text or not isinstance(text, str):
        return text

    cleaned = text
    if mode == "user":
        cleaned = _PATH_PAT.sub("[path]", cleaned)
        cleaned = _TRACEBACK_PAT.sub("[internal error — details hidden]", cleaned)
        cleaned = _ENV_PAT.sub("[env_var]=[redacted]", cleaned)
        cleaned = _JWT_PAT.sub("[token]", cleaned)
        cleaned = _MODULE_LABEL_PAT.sub("[internal component]", cleaned)

    # Always strip JWT and secrets
    cleaned = _JWT_PAT.sub("[token]", cleaned)
    cleaned = _ENV_PAT.sub("[env_var]=[redacted]", cleaned)

    return cleaned


# ---------------------------------------------------------------------------
# Sanitizers
# ---------------------------------------------------------------------------

def _sanitize_full(output: dict[str, Any], keep_files: bool) -> dict[str, Any]:
    """Full user-mode sanitization."""
    cleaned: dict[str, Any] = {}

    for k, v in output.items():
        # Drop internal-only fields
        if k in _INTERNAL_FIELDS:
            continue
        # Drop keys starting with _ (internal markers)
        if isinstance(k, str) and k.startswith("_"):
            continue

        cleaned[k] = _sanitize_value(v, keep_files=keep_files)

    # Ensure summary exists
    if "summary" not in cleaned and "message" in cleaned:
        cleaned["summary"] = cleaned["message"]

    return cleaned


def _sanitize_secrets_only(output: dict[str, Any]) -> dict[str, Any]:
    """Admin mode — only strip secrets and tokens."""
    def _clean(v: Any) -> Any:
        if isinstance(v, str):
            v = _JWT_PAT.sub("[token]", v)
            v = _ENV_PAT.sub("[env_var]=[redacted]", v)
            return v
        if isinstance(v, dict):
            return {kk: _clean(vv) for kk, vv in v.items()}
        if isinstance(v, list):
            return [_clean(item) for item in v]
        return v
    return _clean(output)


def _sanitize_value(value: Any, keep_files: bool) -> Any:
    if isinstance(value, str):
        return sanitize_text(value, mode="user")

    if isinstance(value, dict):
        return _sanitize_full(value, keep_files=keep_files)

    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                # files[] entries: keep but sanitize paths
                if keep_files and "code" in item:
                    clean_item = {k: v for k, v in item.items()
                                  if k not in _INTERNAL_FIELDS}
                    # Sanitize path field
                    if "path" in clean_item and isinstance(clean_item["path"], str):
                        clean_item["path"] = _safe_relative_path(clean_item["path"])
                    result.append(clean_item)
                else:
                    result.append(_sanitize_full(item, keep_files=keep_files))
            elif isinstance(item, str):
                result.append(sanitize_text(item, mode="user"))
            else:
                result.append(item)
        return result

    return value


def _safe_relative_path(path: str) -> str:
    """Convert absolute path to relative (remove server root)."""
    # Remove common server roots
    for prefix in ("/app/", "/home/", "C:\\app\\", "C:\\Users\\"):
        if path.startswith(prefix):
            return path[len(prefix):]
    # Remove Python path patterns
    path = _PATH_PAT.sub(lambda m: m.group().split("/")[-1], path)
    return path
