"""
xray/xray_service.py — X-Ray aggregation service.

The admin dashboard API calls this service to get structured data
for the X-Ray, Repair Memory, Log Viewer, and Health panels.

All reads are non-blocking and fault-tolerant — never raises to caller.
Data is always freshly read from logs/state on every call (no caching).

Public API:
  get_session_summary(session_id)     → dict (X-Ray panel main view)
  get_all_sessions(limit)             → list[dict] (session list)
  get_log_feed(limit, level)          → list[dict] (log viewer)
  get_error_feed(limit)               → list[dict] (error library view)
  get_validation_feed(limit)          → list[dict] (validation overview)
  get_health_snapshot()               → dict (system health panel)
  get_repair_memory_list(category)    → list[dict] (error library tab)
  search_repair_memory(cat, query)    → list[dict] (error library search)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .xray_reader import (
    read_recent_events,
    read_recent_errors,
    read_validation_events,
    get_log_stats,
    get_orchestration_state,
    get_xray_endpoint_data,
    get_approval_history,
    list_active_sessions,
    get_sessions_from_logs,
)

log = logging.getLogger("xray.service")


# ---------------------------------------------------------------------------
# Session X-Ray
# ---------------------------------------------------------------------------

def get_session_summary(session_id: str) -> dict[str, Any]:
    """
    Full X-Ray summary for a single session.
    Delegates heavy analysis to xray_analysis.generate_xray_report().
    Falls back to log-only report if orchestration state is unavailable.
    """
    try:
        from core.api.xray_analysis import generate_xray_report
        report = generate_xray_report(session_id)
        if report:
            return {"ok": True, "report": report}
    except Exception as exc:
        log.warning("xray_service: generate_xray_report failed — %s", exc)

    # Fallback: build from logs only
    events = read_recent_events(limit=200, session_id=session_id)
    errors = [e for e in events if e.get("status") == "error"]
    return {
        "ok": True,
        "report": {
            "session_id":   session_id,
            "report_type":  "xray_log_only",
            "note":         "Built from log pipeline — no orchestration state found.",
            "total_events": len(events),
            "error_count":  len(errors),
            "events":       [
                {
                    "event_type": e.get("event_type"),
                    "module":     e.get("module"),
                    "status":     e.get("status"),
                    "summary":    e.get("summary"),
                    "timestamp":  e.get("timestamp"),
                }
                for e in events
            ],
        },
    }


def get_all_sessions(limit: int = 20) -> list[dict[str, Any]]:
    """
    List all sessions we know about (in-memory + log history).
    Returns a lightweight summary per session for the admin session list.
    """
    sessions: list[dict[str, Any]] = []
    seen: set[str] = set()

    # In-memory sessions first (most recent)
    for sid in list_active_sessions():
        if sid in seen:
            continue
        seen.add(sid)
        state = get_orchestration_state(sid)
        sessions.append({
            "session_id":   sid,
            "source":       "memory",
            "final_status": getattr(state, "final_status", None),
            "elapsed_ms":   getattr(state, "elapsed_ms", lambda: None)() if state else None,
            "brains_used":  getattr(state, "brains_used", lambda: [])() if state else [],
            "steps":        len(getattr(state, "evidence_history", [])),
        })

    # Supplement from logs
    for sid in get_sessions_from_logs(limit=limit):
        if sid in seen or len(sessions) >= limit:
            break
        seen.add(sid)
        sessions.append({
            "session_id":   sid,
            "source":       "logs",
            "final_status": None,
            "elapsed_ms":   None,
            "brains_used":  [],
            "steps":        None,
        })

    return sessions[:limit]


# ---------------------------------------------------------------------------
# Log feeds
# ---------------------------------------------------------------------------

def get_log_feed(limit: int = 100, level: str = "") -> list[dict[str, Any]]:
    """
    Recent events from events.log for the Log Viewer panel.
    level: "" = all, "error" = errors only, "validation" = validation only
    """
    if level == "error":
        return read_recent_errors(limit=limit)
    if level == "validation":
        return read_validation_events(limit=limit)
    return read_recent_events(limit=limit)


def get_error_feed(limit: int = 50) -> list[dict[str, Any]]:
    """Recent error events for the Error Library live feed."""
    return read_recent_errors(limit=limit)


def get_validation_feed(limit: int = 100, failed_only: bool = False) -> list[dict[str, Any]]:
    """Validation events for the Validation panel."""
    return read_validation_events(limit=limit, failed_only=failed_only)


# ---------------------------------------------------------------------------
# System Health
# ---------------------------------------------------------------------------

def get_health_snapshot() -> dict[str, Any]:
    """
    System health snapshot for the Health panel.
    Checks: log pipeline, orchestration state store, repair memory, web tools.
    """
    health: dict[str, Any] = {
        "status":     "healthy",
        "components": {},
    }

    # Log pipeline
    try:
        stats = get_log_stats()
        health["components"]["log_pipeline"] = {
            "ok":         True,
            "events":     stats.get("events_count", 0),
            "errors":     stats.get("errors_count", 0),
            "validation": stats.get("validation_count", 0),
            "events_kb":  stats.get("events_size_kb", 0),
        }
    except Exception as exc:
        health["components"]["log_pipeline"] = {"ok": False, "error": str(exc)}
        health["status"] = "degraded"

    # Orchestration state store
    try:
        sessions = list_active_sessions()
        health["components"]["orchestration"] = {
            "ok":              True,
            "active_sessions": len(sessions),
        }
    except Exception as exc:
        health["components"]["orchestration"] = {"ok": False, "error": str(exc)}
        health["status"] = "degraded"

    # Repair memory
    try:
        from core.repair_memory.repair_store import list_category
        categories = ["build_pipeline", "backend_logic", "frontend_ui", "image_pipeline"]
        total = sum(len(list_category(c)) for c in categories)
        health["components"]["repair_memory"] = {
            "ok":            True,
            "total_records": total,
        }
    except Exception as exc:
        health["components"]["repair_memory"] = {"ok": False, "error": str(exc)}

    # Anthropic API key present
    import os
    api_key_set = bool(os.getenv("ANTHROPIC_API_KEY"))
    health["components"]["anthropic_api"] = {
        "ok":         api_key_set,
        "key_present": api_key_set,
    }
    if not api_key_set:
        health["status"] = "degraded"

    return health


# ---------------------------------------------------------------------------
# Repair Memory (Error Library)
# ---------------------------------------------------------------------------

def get_repair_memory_list(category: str = "") -> list[dict[str, Any]]:
    """
    List repair memory records for the Error Library tab.
    If category is empty, returns records across all known categories.
    """
    ALL_CATEGORIES = [
        "build_pipeline", "backend_logic", "frontend_ui", "image_pipeline",
        "database", "auth", "network", "config", "deployment", "testing",
        "memory", "file_io", "unknown",
    ]
    cats = [category] if category else ALL_CATEGORIES

    results: list[dict[str, Any]] = []
    try:
        from core.repair_memory.repair_store import list_category, load_repair
        for cat in cats:
            slugs = list_category(cat)
            for slug in slugs:
                record = load_repair(cat, slug)
                if record:
                    results.append({
                        "category":      cat,
                        "slug":          slug,
                        "problem_name":  record.get("problem_name", slug),
                        "solution_name": record.get("solution_name", ""),
                        "success_count": record.get("success_count", 0),
                        "created_at":    record.get("created_at", ""),
                        "step_count":    len(record.get("solution_steps", [])),
                    })
    except Exception as exc:
        log.warning("xray_service: get_repair_memory_list failed — %s", exc)

    return results


def search_repair_memory(category: str, query: str, top_n: int = 5) -> list[dict[str, Any]]:
    """Search repair memory for similar problems."""
    try:
        from core.repair_memory.repair_search import search, search_all_categories
        if category:
            return search(category, query, top_n=top_n)
        return search_all_categories(query, top_n=top_n)
    except Exception as exc:
        log.warning("xray_service: search_repair_memory failed — %s", exc)
        return []
