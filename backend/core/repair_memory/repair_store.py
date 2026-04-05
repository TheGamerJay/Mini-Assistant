"""
repair_memory/repair_store.py — Repair Memory Library: storage layer.

ONE file = ONE confirmed problem + ONE proven solution.
This is a structured repair knowledge base, NOT a log or history.

Storage location:
  backend/internal_library/repair_memory/<category>/<problem-slug>.json

File format:
  {
      "problem_name":   str,
      "category":       str,
      "solution_name":  str,
      "solution_steps": list[str],
      "success_count":  int,
      "last_used":      str,        # ISO 8601
  }

Save rules (ALL must be true before saving):
  - problem is confirmed
  - root cause is identified
  - solution is approved by user (CEO-approved)
  - solution was applied successfully
  - Hands and/or Vision verification PASSED
  - CEO confirmed final success

ONLY CEO can approve saves.
NEVER auto-save. NEVER store partial fixes.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ceo_router.repair_store")

_BASE = Path(__file__).resolve().parents[2] / "internal_library" / "repair_memory"

ALLOWED_CATEGORIES = {
    "routing", "frontend_state", "backend_logic", "validation",
    "persistence", "billing", "tooling", "ui", "image_pipeline",
    "build_pipeline", "testing", "auth", "unknown",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_repair(
    category:       str,
    problem_slug:   str,
    problem_name:   str,
    solution_name:  str,
    solution_steps: list[str],
) -> dict[str, Any]:
    """
    Save a new repair record. Caller (CEO) must have verified all save conditions.

    Returns the saved record dict.
    Raises ValueError if the category is invalid.
    """
    if category not in ALLOWED_CATEGORIES:
        raise ValueError(f"Invalid repair category: '{category}'. Must be one of {ALLOWED_CATEGORIES}")

    slug = _slugify(problem_slug)
    path = _path(category, slug)

    # Check for existing (duplicate detection handled in repair_search — this is a safety net)
    if path.exists():
        log.warning("repair_store: file already exists for slug=%s — updating instead", slug)
        existing = _read(path)
        existing["solution_name"]  = solution_name
        existing["solution_steps"] = solution_steps
        existing["last_used"]      = _now()
        _write(path, existing)
        log.info("repair_store: updated existing record slug=%s category=%s", slug, category)
        return existing

    record = {
        "problem_name":   problem_name,
        "category":       category,
        "solution_name":  solution_name,
        "solution_steps": solution_steps,
        "success_count":  1,
        "last_used":      _now(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(path, record)
    log.info("repair_store: saved new record slug=%s category=%s", slug, category)
    return record


def upsert_repair(
    category:        str,
    problem_slug:    str,
    problem_name:    str,
    solution_name:   str,
    solution_steps:  list[str],
    new_confidence:  float = 0.5,
) -> tuple[dict[str, Any], str]:
    """
    Save or upgrade a repair record — never creates duplicates.

    Logic:
      - If no existing record: save fresh.
      - If existing record exists:
          - new confidence > existing (normalised from success_count): replace.
          - new confidence <= existing: keep existing, increment success_count.

    Returns (record, action) where action is 'created' | 'upgraded' | 'kept'.
    """
    if category not in ALLOWED_CATEGORIES:
        raise ValueError(f"Invalid repair category: '{category}'.")

    slug = _slugify(problem_slug)
    path = _path(category, slug)

    if not path.exists():
        record = {
            "problem_name":   problem_name,
            "category":       category,
            "solution_name":  solution_name,
            "solution_steps": solution_steps,
            "success_count":  1,
            "confidence":     round(new_confidence, 3),
            "last_used":      _now(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        _write(path, record)
        log.info("repair_store: created slug=%s category=%s", slug, category)
        return record, "created"

    existing = _read(path)
    existing_conf = existing.get("confidence", 0.0)

    if new_confidence > existing_conf:
        # New solution is more confident — upgrade
        existing["solution_name"]  = solution_name
        existing["solution_steps"] = solution_steps
        existing["confidence"]     = round(new_confidence, 3)
        existing["last_used"]      = _now()
        existing["success_count"]  = existing.get("success_count", 1) + 1
        _write(path, existing)
        log.info(
            "repair_store: upgraded slug=%s conf %.3f→%.3f",
            slug, existing_conf, new_confidence,
        )
        return existing, "upgraded"
    else:
        # Existing is better — just bump success count
        existing["success_count"] = existing.get("success_count", 1) + 1
        existing["last_used"]     = _now()
        _write(path, existing)
        log.info(
            "repair_store: kept existing slug=%s (existing_conf=%.3f >= new_conf=%.3f)",
            slug, existing_conf, new_confidence,
        )
        return existing, "kept"


def load_repair(category: str, problem_slug: str) -> Optional[dict[str, Any]]:
    """Load a specific repair record by category and slug. Returns None if not found."""
    slug = _slugify(problem_slug)
    path = _path(category, slug)
    if not path.exists():
        return None
    return _read(path)


def list_category(category: str) -> list[dict[str, Any]]:
    """
    Return all repair records in a category.
    Each item includes the slug for reference.
    """
    cat_dir = _BASE / category
    if not cat_dir.exists():
        return []
    records = []
    for f in sorted(cat_dir.glob("*.json")):
        data = _read(f)
        if data:
            data["_slug"] = f.stem
            records.append(data)
    return records


def increment_success(category: str, problem_slug: str) -> bool:
    """
    Increment success_count and update last_used for a repair record.
    Called by CEO after a reused fix passes verification again.
    Returns True if record was found and updated.
    """
    slug = _slugify(problem_slug)
    path = _path(category, slug)
    if not path.exists():
        log.warning("repair_store: increment_success — slug=%s not found", slug)
        return False
    record = _read(path)
    record["success_count"] = record.get("success_count", 0) + 1
    record["last_used"]     = _now()
    _write(path, record)
    log.debug("repair_store: incremented success slug=%s count=%d", slug, record["success_count"])
    return True


def slug_exists(category: str, problem_slug: str) -> bool:
    """Check if a slug already exists in a category."""
    return _path(category, _slugify(problem_slug)).exists()


def all_categories_with_counts() -> dict[str, int]:
    """Return {category: record_count} for all categories."""
    result: dict[str, int] = {}
    if not _BASE.exists():
        return result
    for cat_dir in _BASE.iterdir():
        if cat_dir.is_dir():
            result[cat_dir.name] = len(list(cat_dir.glob("*.json")))
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _path(category: str, slug: str) -> Path:
    return _BASE / category / f"{slug}.json"


def _slugify(text: str) -> str:
    """Convert text to a safe filename slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80]


def _read(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("repair_store: failed to read %s — %s", path, exc)
        return {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
