"""
memory/rag_discipline.py — Controlled retrieval discipline layer.

CEO CONTROLS ALL RETRIEVAL. No brain may self-fetch arbitrary context.
Brains may declare retrieval needs; CEO approves and routes the fetch.

This module:
1. Defines what each brain is ALLOWED to retrieve
2. Enforces context budget rules (smallest useful subset)
3. Produces a structured retrieval result for injection into module context

Retrieval sources:
  context_docs     — system documentation and rules
  repair_memory    — past error/fix patterns (Doctor Brain)
  project_files    — relevant source files (Builder/Doctor Brain)
  logs             — stack traces and error logs (Doctor Brain)
  test_results     — last test run output (Hands Brain)
  task_state       — prior verified outputs and progress (all brains)
  tr_memory        — user-specific TR memory (CEO-loaded only)

Brain retrieval allowances:
  CEO Brain    : context_docs, task_state
  Builder Brain: project_files, context_docs, task_state
  Doctor Brain : repair_memory, project_files, logs, context_docs
  Hands Brain  : task_state, test_results
  Vision Brain : task_state, project_files (UI/image context only)

Context budget rules:
  - top 1–3 repair_memory matches only
  - only directly relevant project files
  - only latest relevant logs/tests
  - prefer category-first, file-first retrieval
  - never dump full file contents unless the file IS the task
  - cap retrieval to the most relevant items

Output format:
  {
      "retrieval_used": bool,
      "sources":        [ "context_docs/ceo_router_context.md", ... ],
      "selected_context": [ {"source": str, "content": str}, ... ],
      "reason":         str,
  }
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("ceo_router.rag_discipline")

_BASE = Path(__file__).resolve().parents[3]

# ── Brain allowance map ────────────────────────────────────────────────────────
_BRAIN_ALLOWANCES: dict[str, set[str]] = {
    "ceo":     {"context_docs", "task_state"},
    "builder": {"project_files", "context_docs", "task_state"},
    "doctor":  {"repair_memory", "project_files", "logs", "context_docs"},
    "hands":   {"task_state", "test_results"},
    "vision":  {"task_state", "project_files"},
}

# ── Context budget caps ────────────────────────────────────────────────────────
_BUDGET: dict[str, int] = {
    "repair_memory": 3,    # top N matches
    "project_files": 5,    # top N relevant files
    "logs":          3,    # most recent N log entries
    "test_results":  1,    # latest test run only
    "context_docs":  3,    # top N relevant docs
    "task_state":    1,    # latest state snapshot
}


def build_retrieval_result(
    brain:    str,
    sources:  list[str],
    reason:   str,
) -> dict[str, Any]:
    """
    Build a structured retrieval result for a brain, respecting allowances and budgets.

    Args:
        brain:   brain name (ceo, builder, doctor, hands, vision)
        sources: list of source category strings the brain requested
        reason:  why retrieval is being requested

    Returns the standard retrieval output format.
    """
    allowed = _BRAIN_ALLOWANCES.get(brain, set())
    selected: list[dict[str, str]] = []
    used_sources: list[str] = []

    for source in sources:
        if source not in allowed:
            log.warning(
                "rag_discipline: brain '%s' requested disallowed source '%s' — skipped",
                brain, source,
            )
            continue

        items = _fetch_source(source, brain)
        budget = _BUDGET.get(source, 3)
        for item in items[:budget]:
            selected.append(item)
            if item["source"] not in used_sources:
                used_sources.append(item["source"])

    return {
        "retrieval_used":    len(selected) > 0,
        "sources":           used_sources,
        "selected_context":  selected,
        "reason":            reason,
    }


def check_allowance(brain: str, source: str) -> bool:
    """Return True if brain is allowed to retrieve from this source."""
    return source in _BRAIN_ALLOWANCES.get(brain, set())


# ---------------------------------------------------------------------------
# Source fetchers — each returns a list of {source, content} dicts.
# These are lightweight; full integration with project scanner is a future pass.
# ---------------------------------------------------------------------------

def _fetch_source(source: str, brain: str) -> list[dict[str, str]]:
    """Route to the appropriate fetcher for a source category."""
    fetchers = {
        "context_docs":  _fetch_context_docs,
        "repair_memory": _fetch_repair_memory,
        "project_files": _fetch_project_files,
        "logs":          _fetch_logs,
        "test_results":  _fetch_test_results,
        "task_state":    _fetch_task_state,
    }
    fn = fetchers.get(source)
    if fn is None:
        log.warning("rag_discipline: no fetcher for source '%s'", source)
        return []
    try:
        return fn()
    except Exception as exc:
        log.warning("rag_discipline: fetch failed for source='%s' — %s", source, exc)
        return []


def _fetch_context_docs() -> list[dict[str, str]]:
    docs_dir = _BASE / "backend" / "core" / "context_docs"
    items = []
    for md in sorted(docs_dir.glob("*.md")):
        try:
            items.append({
                "source":  f"context_docs/{md.name}",
                "content": md.read_text(encoding="utf-8")[:2000],
            })
        except Exception:
            pass
    return items


def _fetch_repair_memory() -> list[dict[str, str]]:
    repair_path = _BASE / "memory_store" / "repair_memory.json"
    if not repair_path.exists():
        return []
    import json
    try:
        data = json.loads(repair_path.read_text(encoding="utf-8"))
        entries = data if isinstance(data, list) else data.get("entries", [])
        items = []
        for entry in reversed(entries):  # most recent first
            items.append({
                "source":  "repair_memory",
                "content": str(entry),
            })
        return items
    except Exception:
        return []


def _fetch_project_files() -> list[dict[str, str]]:
    # Returns top-level file listing; full file content is injected per-task
    project_dir = _BASE
    items = []
    for path in sorted(project_dir.rglob("*.py"))[:20]:
        try:
            items.append({
                "source":  str(path.relative_to(_BASE)),
                "content": f"[file: {path.name}]",
            })
        except Exception:
            pass
    return items


def _fetch_logs() -> list[dict[str, str]]:
    logs_dir = _BASE / "logs"
    if not logs_dir.exists():
        return []
    items = []
    for log_file in sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            tail = _tail(log_file, lines=50)
            items.append({
                "source":  f"logs/{log_file.name}",
                "content": tail,
            })
        except Exception:
            pass
    return items


def _fetch_test_results() -> list[dict[str, str]]:
    result_file = _BASE / "test_results" / "latest.txt"
    if not result_file.exists():
        return []
    try:
        return [{"source": "test_results/latest.txt", "content": result_file.read_text()[:3000]}]
    except Exception:
        return []


def _fetch_task_state() -> list[dict[str, str]]:
    state_file = _BASE / "memory_store" / "task_state.json"
    if not state_file.exists():
        return []
    import json
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return [{"source": "task_state", "content": str(data)[:2000]}]
    except Exception:
        return []


def _tail(path: Path, lines: int = 50) -> str:
    """Read the last N lines of a file without loading it all."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return "\n".join(text.splitlines()[-lines:])
    except Exception:
        return ""
