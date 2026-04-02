"""
xray/xray_reader.py — Low-level reader for X-Ray data sources.

Reads from:
  1. logs/events.log, logs/errors.log, logs/validation.log  (NDJSON)
  2. core/api/xray_endpoint.py in-memory store
  3. core/orchestration/state_manager.py in-memory state

Never writes. Never interferes with execution.
Used by xray_service.py to assemble dashboard data.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger("xray.reader")


def read_recent_events(limit: int = 100, session_id: Optional[str] = None) -> list[dict]:
    """
    Read recent events from the NDJSON log pipeline.
    If session_id is provided, filter to that session only.
    """
    try:
        from logs.event_logger import read_events
        events = read_events(limit=limit * 2)  # over-fetch to allow filtering
        if session_id:
            events = [e for e in events if e.get("session_id") == session_id]
        return events[:limit]
    except Exception as exc:
        log.warning("xray_reader: read_recent_events failed — %s", exc)
        return []


def read_recent_errors(limit: int = 50) -> list[dict]:
    """Read recent errors from errors.log."""
    try:
        from logs.event_logger import read_errors
        return read_errors(limit=limit)
    except Exception as exc:
        log.warning("xray_reader: read_recent_errors failed — %s", exc)
        return []


def read_validation_events(limit: int = 100, failed_only: bool = False) -> list[dict]:
    """Read validation events from validation.log."""
    try:
        from logs.event_logger import read_validation
        return read_validation(limit=limit, failed_only=failed_only)
    except Exception as exc:
        log.warning("xray_reader: read_validation_events failed — %s", exc)
        return []


def get_log_stats() -> dict[str, Any]:
    """Return size/count stats for all log files."""
    try:
        from logs.event_logger import get_log_stats
        return get_log_stats()
    except Exception as exc:
        log.warning("xray_reader: get_log_stats failed — %s", exc)
        return {}


def get_orchestration_state(session_id: str) -> Optional[Any]:
    """Return OrchestrationState for a session if it exists."""
    try:
        from core.orchestration.state_manager import get as get_state
        return get_state(session_id)
    except Exception as exc:
        log.debug("xray_reader: get_orchestration_state failed — %s", exc)
        return None


def get_xray_endpoint_data(session_id: str) -> dict[str, Any]:
    """Return raw execution data stored by xray_endpoint."""
    try:
        from core.api.xray_endpoint import get_xray_data
        return get_xray_data(session_id) or {}
    except Exception as exc:
        log.debug("xray_reader: get_xray_endpoint_data failed — %s", exc)
        return {}


def get_approval_history(session_id: str) -> list[dict]:
    """Return approval history for a session."""
    try:
        from core.orchestration.approval_gate import get_history
        return get_history(session_id)
    except Exception as exc:
        log.debug("xray_reader: get_approval_history failed — %s", exc)
        return []


def list_active_sessions() -> list[str]:
    """
    Return session IDs that have in-memory orchestration state.
    Used by admin dashboard to list sessions without querying logs.
    """
    try:
        from core.orchestration.state_manager import list_sessions
        return list_sessions()
    except Exception as exc:
        log.debug("xray_reader: list_active_sessions failed — %s", exc)
        return []


def get_sessions_from_logs(limit: int = 20) -> list[str]:
    """
    Extract unique session IDs from recent events log.
    Used when in-memory state is gone (e.g. after server restart).
    """
    try:
        from logs.event_logger import read_events
        events = read_events(limit=500)
        seen: list[str] = []
        for e in events:
            sid = e.get("session_id")
            if sid and sid not in seen:
                seen.append(sid)
            if len(seen) >= limit:
                break
        return seen
    except Exception as exc:
        log.warning("xray_reader: get_sessions_from_logs failed — %s", exc)
        return []
