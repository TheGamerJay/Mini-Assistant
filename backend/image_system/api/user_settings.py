"""
User Settings Store

Persists durable user preferences to memory_store/user_settings.json.
Currently stores: ai_data_usage_mode ("private" | "improve_system")

All other preferences are stored here as well so this acts as a single
source of truth for per-installation settings (not per-session).

Format: flat JSON dict, e.g.
  {
    "ai_data_usage_mode": "private",
    "updated_at": "2026-03-27T12:00:00+00:00"
  }
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_STORE = Path(__file__).resolve().parent.parent.parent.parent / "memory_store" / "user_settings.json"
_VALID_MODES = {"private", "improve_system"}
_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULTS: Dict[str, Any] = {
    "ai_data_usage_mode": "private",
}


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load() -> Dict[str, Any]:
    if not _STORE.exists():
        return dict(_DEFAULTS)
    try:
        with open(_STORE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Backfill any missing keys with defaults
        for key, val in _DEFAULTS.items():
            data.setdefault(key, val)
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("user_settings: failed to load — %s", exc)
        return dict(_DEFAULTS)


def _save(data: Dict[str, Any]) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(_STORE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as exc:
        logger.error("user_settings: failed to save — %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_settings() -> Dict[str, Any]:
    """Return the full settings dict."""
    with _lock:
        return _load()


def get_ai_data_usage_mode() -> str:
    """Return 'private' | 'improve_system'."""
    return get_settings().get("ai_data_usage_mode", "private")


def set_ai_data_usage_mode(mode: str) -> Dict[str, Any]:
    """
    Update ai_data_usage_mode.

    Args:
        mode: 'private' | 'improve_system'

    Returns:
        Updated full settings dict.

    Raises:
        ValueError: if mode is not a recognised value.
    """
    if mode not in _VALID_MODES:
        raise ValueError(f"Invalid mode '{mode}'. Must be one of: {_VALID_MODES}")
    with _lock:
        data = _load()
        data["ai_data_usage_mode"] = mode
        _save(data)
        return data


def update_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge `patch` into settings (only whitelisted keys are accepted).

    Returns the updated settings dict.
    """
    _ALLOWED_KEYS = {"ai_data_usage_mode"}
    with _lock:
        data = _load()
        for key, val in patch.items():
            if key not in _ALLOWED_KEYS:
                logger.warning("user_settings: ignoring unknown key '%s'", key)
                continue
            if key == "ai_data_usage_mode" and val not in _VALID_MODES:
                raise ValueError(f"Invalid ai_data_usage_mode '{val}'")
            data[key] = val
        _save(data)
        return data
