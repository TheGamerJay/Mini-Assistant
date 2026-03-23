"""
Lesson Memory — Builder Brain long-term learning
=================================================
Every time the Auto-Fix loop or a patch successfully resolves a bug,
the pattern gets recorded here. Future sessions load these lessons
into their system prompt so the builder gets smarter over time.

Storage: memory_store/builder_lessons.json
Format:  [{pattern, root_cause, fix, count, last_seen}]
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_LESSONS_FILE = Path(__file__).parent.parent.parent.parent / "memory_store" / "builder_lessons.json"
_MAX_LESSONS  = 60   # keep the 60 most-seen patterns
_PROMPT_LIMIT = 6    # inject top-6 into system prompts


def load_lessons(limit: int = _PROMPT_LIMIT) -> list[dict]:
    """Return the top `limit` lessons sorted by frequency."""
    try:
        raw = json.loads(_LESSONS_FILE.read_text(encoding="utf-8"))
        return sorted(raw, key=lambda x: x.get("count", 1), reverse=True)[:limit]
    except Exception:
        return []


def save_lesson(pattern: str, root_cause: str, fix_approach: str) -> None:
    """
    Record a successfully identified + fixed bug pattern.
    If the same pattern has been seen before, increment its count.
    """
    try:
        _LESSONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            lessons: list[dict] = json.loads(_LESSONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            lessons = []

        pattern_key = pattern.lower()[:80]

        # Update existing lesson if pattern matches
        for lesson in lessons:
            if lesson.get("pattern", "").lower()[:80] == pattern_key:
                lesson["count"]     = lesson.get("count", 1) + 1
                lesson["last_seen"] = datetime.utcnow().isoformat()
                lesson["root_cause"] = root_cause[:300]
                lesson["fix"]        = fix_approach[:300]
                break
        else:
            # New pattern
            lessons.append({
                "pattern":    pattern[:120],
                "root_cause": root_cause[:300],
                "fix":        fix_approach[:300],
                "count":      1,
                "first_seen": datetime.utcnow().isoformat(),
                "last_seen":  datetime.utcnow().isoformat(),
            })

        # Keep only the most-seen patterns
        lessons = sorted(lessons, key=lambda x: x.get("count", 1), reverse=True)[:_MAX_LESSONS]
        _LESSONS_FILE.write_text(json.dumps(lessons, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("[LessonMemory] saved: %s (count=%s)", pattern[:60], lessons[0].get("count") if lessons else 1)

    except Exception as exc:
        logger.warning("[LessonMemory] save failed (non-fatal): %s", exc)


def format_lessons_for_prompt() -> str:
    """
    Return a formatted string ready to append to a system prompt.
    Returns empty string if no lessons are stored yet.
    """
    lessons = load_lessons(_PROMPT_LIMIT)
    if not lessons:
        return ""

    lines = [
        "\n## LESSONS LEARNED FROM PAST BUGS",
        "These are real bugs that appeared in previous sessions and were fixed.",
        "Recognise these patterns instantly and apply the known fix:\n",
    ]
    for i, l in enumerate(lessons, 1):
        count_label = f" (seen {l['count']}x)" if l.get("count", 1) > 1 else ""
        lines.append(f"{i}. **{l['pattern']}**{count_label}")
        lines.append(f"   Root cause: {l['root_cause']}")
        lines.append(f"   Fix: {l['fix']}\n")

    return "\n".join(lines)


def extract_lessons_from_fix_report(report: str) -> list[dict]:
    """
    Parse Claude's auto-fix response and extract structured lessons.
    Looks for the 'Found X bugs:' section and bullet list.
    Returns a list of {pattern, root_cause, fix} dicts.
    """
    import re
    lessons = []

    # Match "Found N bugs:" followed by bullet items
    bug_section = re.search(r"Found \d+ (?:issue|bug)s?:?\s*([\s\S]+?)(?:```|$)", report, re.IGNORECASE)
    if not bug_section:
        return lessons

    bullets = re.findall(r"[-•*]\s*(.+)", bug_section.group(1))
    for bullet in bullets[:5]:
        text = bullet.strip()
        if len(text) < 10:
            continue
        # Try to split "X → Y" or "X: Y"
        if "→" in text:
            parts = text.split("→", 1)
            pattern   = parts[0].strip()
            fix_approach = parts[1].strip()
            root_cause   = pattern
        elif ":" in text:
            parts = text.split(":", 1)
            pattern   = parts[0].strip()
            fix_approach = parts[1].strip()
            root_cause   = pattern
        else:
            pattern      = text[:80]
            root_cause   = text
            fix_approach = "See pattern description"

        if len(pattern) > 5:
            lessons.append({
                "pattern":    pattern,
                "root_cause": root_cause,
                "fix":        fix_approach,
            })

    return lessons
