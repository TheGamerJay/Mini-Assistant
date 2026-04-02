"""
context/context_store.py — Session-based context storage.

Stores per-session, per-mode context as JSON files on disk.
CEO loads and updates context. Brains NEVER access this directly.

Modes:
  chat        → context/chat/{session_id}.json
  image_edit  → context/image_edit/{session_id}.json

CHAT CONTEXT SCHEMA:
  {
    "session_id":      str,
    "mode":            "chat",
    "updated_at":      ISO 8601,
    "recent_messages": [last ~20 messages],
    "facts_learned":   {key: value},
    "tools_used":      [list of tool names used],
    "failures":        [list of failure summaries],
    "preferences":     {key: value},
  }

IMAGE EDIT CONTEXT SCHEMA:
  {
    "session_id":      str,
    "mode":            "image_edit",
    "updated_at":      ISO 8601,
    "last_image_id":   str | null,
    "last_edit":       str,
    "target_object":   str,
    "mask_strategy":   str,
    "edit_history":    [list of edit records],
  }

Rules:
  - context is session-scoped and mode-scoped
  - DO NOT mix contexts between modes
  - context files are never shared across sessions
  - CEO loads minimum required subset
  - stale sessions (> 24h) are ignored but not auto-deleted
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("context_store")

_BASE    = Path(__file__).resolve().parent
_LOCK    = threading.Lock()
_MODES   = {"chat", "image_edit"}

# Default schemas per mode
_DEFAULTS: dict[str, dict[str, Any]] = {
    "chat": {
        "recent_messages": [],
        "facts_learned":   {},
        "tools_used":      [],
        "failures":        [],
        "preferences":     {},
    },
    "image_edit": {
        "last_image_id":  None,
        "last_edit":      "",
        "target_object":  "",
        "mask_strategy":  "",
        "edit_history":   [],
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load(session_id: str, mode: str) -> dict[str, Any]:
    """
    Load context for a session+mode.
    Returns default schema if file doesn't exist.
    Never raises — returns defaults on any error.
    """
    _validate_mode(mode)
    try:
        path = _path(session_id, mode)
        if not path.exists():
            return _empty(session_id, mode)
        with _LOCK:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        # Backfill any missing keys from defaults
        defaults = _DEFAULTS[mode]
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data
    except Exception as exc:
        log.warning("context_store.load(%s, %s) failed — %s", session_id, mode, exc)
        return _empty(session_id, mode)


def save(session_id: str, mode: str, context: dict[str, Any]) -> None:
    """
    Save the full context dict for a session+mode.
    Overwrites existing file. Thread-safe.
    """
    _validate_mode(mode)
    try:
        path = _path(session_id, mode)
        path.parent.mkdir(parents=True, exist_ok=True)
        context["session_id"] = session_id
        context["mode"]       = mode
        context["updated_at"] = _now_iso()
        with _LOCK:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(context, f, indent=2, ensure_ascii=False, default=str)
    except Exception as exc:
        log.warning("context_store.save(%s, %s) failed — %s", session_id, mode, exc)


def update(session_id: str, mode: str, key: str, value: Any) -> None:
    """
    Load, update a single key, save back.
    Convenience method for incremental updates.
    """
    ctx = load(session_id, mode)
    ctx[key] = value
    save(session_id, mode, ctx)


def append_to(session_id: str, mode: str, key: str, item: Any, max_len: int = 20) -> None:
    """
    Append an item to a list field. Truncates to max_len (oldest first).
    """
    ctx = load(session_id, mode)
    lst = ctx.get(key, [])
    if not isinstance(lst, list):
        lst = []
    lst.append(item)
    if max_len and len(lst) > max_len:
        lst = lst[-max_len:]
    ctx[key] = lst
    save(session_id, mode, ctx)


def merge_facts(session_id: str, new_facts: dict[str, Any]) -> None:
    """
    Merge new facts into the facts_learned dict for chat mode.
    Existing keys are overwritten by newer values.
    """
    ctx = load(session_id, "chat")
    facts = ctx.get("facts_learned", {})
    facts.update(new_facts)
    ctx["facts_learned"] = facts
    save(session_id, "chat", ctx)


def clear(session_id: str, mode: str) -> None:
    """Delete context file for a session+mode."""
    try:
        path = _path(session_id, mode)
        if path.exists():
            with _LOCK:
                path.unlink()
    except Exception as exc:
        log.warning("context_store.clear(%s, %s) failed — %s", session_id, mode, exc)


def exists(session_id: str, mode: str) -> bool:
    """Return True if a context file exists for this session+mode."""
    return _path(session_id, mode).exists()


# ---------------------------------------------------------------------------
# Chat-specific helpers (CEO uses these for common updates)
# ---------------------------------------------------------------------------

def add_message(session_id: str, role: str, content: str) -> None:
    """Append a message to recent_messages (max 20)."""
    append_to(session_id, "chat", "recent_messages", {
        "role": role, "content": content[:2000], "at": _now_iso(),
    }, max_len=20)


def record_tool(session_id: str, tool_name: str) -> None:
    """Record that a tool was used in this session."""
    ctx = load(session_id, "chat")
    tools = ctx.get("tools_used", [])
    if tool_name not in tools:
        tools.append(tool_name)
    ctx["tools_used"] = tools
    save(session_id, "chat", ctx)


def record_failure(session_id: str, summary: str) -> None:
    """Append a failure summary (max 10)."""
    append_to(session_id, "chat", "failures", {"summary": summary, "at": _now_iso()}, max_len=10)


# ---------------------------------------------------------------------------
# Image edit helpers
# ---------------------------------------------------------------------------

def update_image_context(
    session_id:    str,
    image_id:      Optional[str] = None,
    edit:          Optional[str] = None,
    target_object: Optional[str] = None,
    mask_strategy: Optional[str] = None,
) -> None:
    """Update image edit context fields after an edit operation."""
    ctx = load(session_id, "image_edit")
    if image_id:
        ctx["last_image_id"] = image_id
    if edit:
        ctx["last_edit"]     = edit
        history = ctx.get("edit_history", [])
        history.append({"edit": edit, "image_id": image_id or ctx.get("last_image_id"), "at": _now_iso()})
        ctx["edit_history"]  = history[-20:]
    if target_object:
        ctx["target_object"] = target_object
    if mask_strategy:
        ctx["mask_strategy"] = mask_strategy
    save(session_id, "image_edit", ctx)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _path(session_id: str, mode: str) -> Path:
    safe_id = session_id.replace("/", "_").replace("..", "_")[:64]
    return _BASE / mode / f"{safe_id}.json"


def _empty(session_id: str, mode: str) -> dict[str, Any]:
    ctx = {"session_id": session_id, "mode": mode, "updated_at": _now_iso()}
    ctx.update(_DEFAULTS.get(mode, {}))
    return ctx


def _validate_mode(mode: str) -> None:
    if mode not in _MODES:
        raise ValueError(f"context_store: unsupported mode '{mode}' — must be one of {_MODES}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
