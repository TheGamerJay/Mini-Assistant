"""
Search Brain — parallel memory retrieval for Claude
=====================================================
Runs before Claude generates a response. Searches all memory stores
for content relevant to the current user message, then returns a
compact block that gets injected into Claude's system prompt.

Memory sources searched:
  - conversation_store    → past sessions (what was built, what was fixed)
  - builder_lessons.json  → bug patterns learned over time
  - user_prefs.json       → style, app type preferences
  - session_memory/*.json → per-session facts (language, framework, etc.)
  - reflections.json      → past decisions / noteworthy events

Design: pure keyword search — no embeddings needed.
Fast enough to run synchronously before each request (<5ms on local files).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MEM_ROOT = Path(__file__).parent.parent.parent.parent / "memory_store"
_CONV_DIR  = _MEM_ROOT / "conversations"
_LESSONS_FILE    = _MEM_ROOT / "builder_lessons.json"
_PREFS_FILE      = _MEM_ROOT / "user_prefs.json"
_REFLECTIONS_FILE= _MEM_ROOT / "reflections.json"
_SESSION_MEM_DIR = _MEM_ROOT / "session_memory"

# Words that carry no search signal
_STOP = {
    "a","an","the","is","it","in","on","at","to","of","and","or","but","for",
    "with","this","that","i","my","me","you","your","we","us","can","do","did",
    "be","was","are","have","has","had","not","no","so","just","like","make",
    "get","set","use","new","add","fix","bug","code","html","app","how","what",
    "please","want","need","help","also","good","bad","now","then","when",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokens(text: str) -> set[str]:
    """Lowercase alphanumeric tokens, stop-words removed, min length 3."""
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOP}


def _score(query_tokens: set[str], text: str) -> int:
    """Count how many query tokens appear in text."""
    t = text.lower()
    return sum(1 for tok in query_tokens if tok in t)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Per-source search functions
# ---------------------------------------------------------------------------

def _search_lessons(query_tokens: set[str], top_n: int = 3) -> list[str]:
    data = _load_json(_LESSONS_FILE)
    if not data:
        return []
    scored = []
    for lesson in data:
        text = f"{lesson.get('pattern','')} {lesson.get('root_cause','')} {lesson.get('fix','')}"
        s = _score(query_tokens, text)
        if s > 0:
            scored.append((s, lesson))
    scored.sort(key=lambda x: (-x[0], -x[1].get("count", 1)))
    results = []
    for _, lesson in scored[:top_n]:
        results.append(
            f"• Bug pattern: {lesson.get('pattern','?')} → "
            f"Fix: {lesson.get('fix','?')} (seen {lesson.get('count',1)}x)"
        )
    return results


def _search_prefs() -> list[str]:
    data = _load_json(_PREFS_FILE)
    if not data:
        return []
    lines = []
    if data.get("app_types"):
        lines.append(f"• User usually builds: {', '.join(data['app_types'][:4])}")
    if data.get("themes"):
        lines.append(f"• Preferred themes: {', '.join(data['themes'][:4])}")
    if data.get("color_palette"):
        lines.append(f"• Color palette: {', '.join(data['color_palette'][:4])}")
    if data.get("style_signals"):
        lines.append(f"• Style signals: {', '.join(data['style_signals'][:4])}")
    return lines


def _search_session_memory(session_id: str | None) -> list[str]:
    if not session_id or not _SESSION_MEM_DIR.exists():
        return []
    session_file = _SESSION_MEM_DIR / f"{session_id}.json"
    data = _load_json(session_file)
    if not data:
        return []
    facts = data if isinstance(data, list) else data.get("facts", [])
    lines = []
    for fact in facts[:8]:
        key = fact.get("key", "")
        val = fact.get("value", "")
        if key and val:
            lines.append(f"• {key}: {val}")
    return lines


def _search_past_conversations(query_tokens: set[str], current_session_id: str | None, top_n: int = 3) -> list[str]:
    """Search OTHER sessions (not the current one) for relevant context."""
    if not _CONV_DIR.exists():
        return []
    results = []
    for conv_file in sorted(_CONV_DIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)[:20]:
        if not conv_file.suffix == ".json":
            continue
        if current_session_id and conv_file.stem == current_session_id:
            continue  # skip current session — it's already in context
        data = _load_json(conv_file)
        if not isinstance(data, list):
            continue
        # Score each assistant message
        for msg in reversed(data):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            # Skip pure HTML blobs
            if content.strip().startswith("<!DOCTYPE") or content.strip().startswith("```html"):
                continue
            s = _score(query_tokens, content)
            if s >= 2:  # require at least 2 token hits across sessions
                snippet = content[:300].replace("\n", " ")
                results.append((s, snippet, conv_file.stem))
                break
    results.sort(key=lambda x: -x[0])
    return [f"• Past session ({sid[:8]}…): {snip}" for _, snip, sid in results[:top_n]]


def _search_reflections(query_tokens: set[str], top_n: int = 2) -> list[str]:
    data = _load_json(_REFLECTIONS_FILE)
    if not isinstance(data, list):
        return []
    scored = []
    for ref in data:
        text = f"{ref.get('summary','')} {ref.get('decision','')} {ref.get('outcome','')}"
        s = _score(query_tokens, text)
        if s > 0:
            scored.append((s, ref))
    scored.sort(key=lambda x: -x[0])
    lines = []
    for _, ref in scored[:top_n]:
        lines.append(f"• Reflection: {ref.get('summary', '')[:200]}")
    return lines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search(user_message: str, session_id: str | None = None) -> str:
    """
    Search all memory sources for content relevant to user_message.
    Returns a formatted block to inject into Claude's system prompt.
    Returns an empty string if nothing relevant is found.
    """
    query_tokens = _tokens(user_message)
    if not query_tokens:
        return ""

    sections: list[tuple[str, list[str]]] = []

    # 1. User preferences (always include if available — shapes every build)
    prefs = _search_prefs()
    if prefs:
        sections.append(("User style profile", prefs))

    # 2. Session-specific facts (language, framework, DB, etc.)
    session_facts = _search_session_memory(session_id)
    if session_facts:
        sections.append(("Session context", session_facts))

    # 3. Bug patterns relevant to this request
    lessons = _search_lessons(query_tokens)
    if lessons:
        sections.append(("Relevant bug patterns (learned)", lessons))

    # 4. Past conversations from other sessions
    past = _search_past_conversations(query_tokens, session_id)
    if past:
        sections.append(("Related past work", past))

    # 5. Reflections
    refs = _search_reflections(query_tokens)
    if refs:
        sections.append(("Past decisions", refs))

    if not sections:
        return ""

    lines = ["## 🔍 Memory Search Results (injected by Search Brain)"]
    for title, items in sections:
        lines.append(f"\n### {title}")
        lines.extend(items)
    lines.append("")  # trailing newline

    return "\n".join(lines)
