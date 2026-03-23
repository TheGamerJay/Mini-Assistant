"""
Persistent per-session conversation store.

Saves every user + assistant message to disk under:
  memory_store/conversations/{session_id}.json

Each entry is a dict: { "role": str, "content": str, "timestamp": str }
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_CONV_DIR = Path(__file__).parent.parent.parent / "memory_store" / "conversations"


def _ensure_dir() -> None:
    _CONV_DIR.mkdir(parents=True, exist_ok=True)


def _session_path(session_id: str) -> Path:
    # Sanitise to avoid path traversal
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", session_id)
    return _CONV_DIR / f"{safe}.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_conversation(session_id: str) -> list[dict]:
    """Return stored messages for *session_id*, or [] if none / corrupt."""
    path = _session_path(session_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("conversation_store: could not load %s — %s", path.name, exc)
        return []


def save_message(session_id: str, role: str, content: str) -> None:
    """Append one message to the session file, creating it if needed."""
    _ensure_dir()
    path = _session_path(session_id)
    messages = load_conversation(session_id)
    messages.append({
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    try:
        path.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("conversation_store: could not save %s — %s", path.name, exc)


# ---------------------------------------------------------------------------
# HTML trimming helper
# ---------------------------------------------------------------------------

_HTML_FENCE_RE = re.compile(r"```html\s*\n[\s\S]+?```", re.IGNORECASE)
_DOCTYPE_RE = re.compile(r"<!DOCTYPE\s+html[\s\S]+", re.IGNORECASE)


def _contains_html(content: str) -> bool:
    return bool(_HTML_FENCE_RE.search(content) or _DOCTYPE_RE.search(content))


def _replace_html_blocks(content: str) -> str:
    """Replace HTML blocks in *content* with a compact placeholder."""

    def _fence_replacer(m: re.Match) -> str:
        lines = m.group(0).splitlines()
        n = len(lines)
        return f"```html\n[HTML code - {n} lines]\n```"

    result = _HTML_FENCE_RE.sub(_fence_replacer, content)

    # Handle raw <!DOCTYPE … blocks (no fence)
    raw_m = _DOCTYPE_RE.search(result)
    if raw_m:
        lines = result[raw_m.start():].splitlines()
        n = len(lines)
        result = result[: raw_m.start()] + f"[HTML code - {n} lines]"

    return result


def trim_html_in_old_messages(messages: list[dict]) -> list[dict]:
    """
    Find the LAST assistant message that contains an HTML block and keep it
    verbatim. Replace HTML blocks in ALL earlier messages with a compact
    placeholder so the context window stays manageable.

    Returns a new list; the originals are not mutated.
    """
    if not messages:
        return messages

    # Find index of the last assistant HTML message
    last_html_idx = -1
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant" and _contains_html(msg.get("content", "")):
            last_html_idx = i

    if last_html_idx == -1:
        # No HTML anywhere — nothing to trim
        return list(messages)

    result: list[dict] = []
    for i, msg in enumerate(messages):
        if i < last_html_idx and msg.get("role") == "assistant" and _contains_html(msg.get("content", "")):
            trimmed_content = _replace_html_blocks(msg["content"])
            result.append({**msg, "content": trimmed_content + "\n[HTML - see most recent version above]"})
        else:
            result.append(msg)

    return result
