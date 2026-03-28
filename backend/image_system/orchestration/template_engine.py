"""
Template Engine — Phase 6

Stores and retrieves reusable execution templates from successful tasks.
When a new task closely matches a past successful template, the system
reuses the proven step structure instead of decomposing from scratch.

Templates are auto-generated from completed tasks and manually curated.

Storage: memory_store/task_templates.json
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TEMPLATE_FILE = Path(__file__).parent.parent.parent / "memory_store" / "task_templates.json"
_MIN_SCORE_TO_STORE = 0.8   # only save templates from highly successful tasks
_MATCH_THRESHOLD    = 0.45  # min similarity to reuse a template


@dataclass
class TaskTemplate:
    template_id:        str
    template_name:      str
    task_type:          str          # "build" | "patch" | "image"
    mode:               str
    keywords:           List[str]    # key terms from the goal
    recommended_steps:  List[Dict[str, Any]]   # from TaskStep dicts
    typical_risks:      List[str]
    average_confidence: float
    average_cost:       float
    success_rate:       float
    use_count:          int = 0
    created_at:         str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _load() -> List[Dict]:
    if not _TEMPLATE_FILE.exists():
        return []
    try:
        return json.loads(_TEMPLATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(templates: List[Dict]) -> None:
    _TEMPLATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        _TEMPLATE_FILE.write_text(
            json.dumps(templates[-500:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("[TemplateEngine] could not save templates: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_template(
    template_name:   str,
    task_type:       str,
    mode:            str,
    goal:            str,
    steps:           List[Dict[str, Any]],
    confidence:      float,
    cost:            float,
    success:         bool,
    typical_risks:   Optional[List[str]] = None,
) -> Optional[TaskTemplate]:
    """
    Save a successful task execution as a reusable template.
    Only stores if success=True and confidence >= _MIN_SCORE_TO_STORE.
    """
    if not success or confidence < _MIN_SCORE_TO_STORE:
        return None

    keywords = _extract_keywords(goal)

    # Check deduplication
    existing = _load()
    for t in existing[-20:]:
        existing_kw = set(t.get("keywords", []))
        overlap = len(set(keywords) & existing_kw) / max(1, len(keywords))
        if overlap > 0.7 and t.get("task_type") == task_type:
            # Update the existing template's stats
            t["use_count"] = t.get("use_count", 0) + 1
            t["average_cost"] = (t.get("average_cost", cost) * 0.7 + cost * 0.3)
            _save(existing)
            logger.debug("[TemplateEngine] updated existing template '%s'", t.get("template_name"))
            return None

    template = TaskTemplate(
        template_id=str(uuid.uuid4())[:8],
        template_name=template_name,
        task_type=task_type,
        mode=mode,
        keywords=keywords,
        recommended_steps=steps,
        typical_risks=typical_risks or [],
        average_confidence=confidence,
        average_cost=cost,
        success_rate=1.0,
        use_count=0,
    )

    existing.append(asdict(template))
    _save(existing)
    logger.info("[TemplateEngine] saved new template: %s (%s)", template_name, task_type)
    return template


def find_matching_template(
    task_type: str,
    mode:      str,
    goal:      str,
) -> Optional[TaskTemplate]:
    """
    Find the best-matching template for a given task.
    Returns None if no template exceeds _MATCH_THRESHOLD.
    """
    templates = _load()
    goal_kw   = set(_extract_keywords(goal))

    best_score  = 0.0
    best_tmpl   = None

    for t in templates:
        if t.get("task_type") != task_type or t.get("mode") != mode:
            continue
        tmpl_kw = set(t.get("keywords", []))
        if not tmpl_kw:
            continue
        overlap = len(goal_kw & tmpl_kw) / max(1, len(goal_kw | tmpl_kw))
        if overlap > best_score:
            best_score = overlap
            best_tmpl  = t

    if best_score < _MATCH_THRESHOLD or best_tmpl is None:
        return None

    # Increment use count
    best_tmpl["use_count"] = best_tmpl.get("use_count", 0) + 1
    _save(templates)

    logger.info("[TemplateEngine] matched template '%s' (score=%.2f)", best_tmpl.get("template_name"), best_score)

    try:
        return TaskTemplate(**{k: v for k, v in best_tmpl.items() if k in TaskTemplate.__dataclass_fields__})
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "be", "to", "of", "and",
    "or", "in", "it", "this", "that", "for", "with", "on", "at",
    "i", "me", "my", "we", "you", "they", "do", "did", "does",
    "build", "make", "create", "add", "app", "page",
})


def _extract_keywords(text: str) -> List[str]:
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    return list(set(w for w in words if w not in _STOP_WORDS))[:20]
