"""
logs/event_logger.py — Structured event and error log pipeline.

Writes real execution events from the CEO pipeline to disk.
Three log streams:
  events.log     — all CEO pipeline events (request → output_ready)
  errors.log     — error-status events only
  validation.log — validation_started / validation_passed / validation_failed

Format: one JSON object per line (newline-delimited JSON / NDJSON).
No fake events. Only events from real execution.

Usage:
  from logs.event_logger import log_event, log_error, log_validation

  log_event(event_dict)          # any CEO event dict
  log_error(event_dict)          # auto-called for status="error" events
  log_validation(event_dict)     # auto-called for validation_* events
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("event_logger")

_BASE    = Path(__file__).resolve().parent
_LOCK    = threading.Lock()

_EVENTS_LOG     = _BASE / "events.log"
_ERRORS_LOG     = _BASE / "errors.log"
_VALIDATION_LOG = _BASE / "validation.log"

# Max log size before rotation (5 MB)
_MAX_BYTES = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_event(event: dict[str, Any]) -> None:
    """
    Append a CEO pipeline event to events.log.
    Also routes to errors.log or validation.log based on event_type.
    Never raises — logging must not crash execution.
    """
    if not isinstance(event, dict):
        return
    try:
        _append(_EVENTS_LOG, event)

        event_type = event.get("event_type", "")
        status     = event.get("status", "")

        if status == "error" or event_type == "error":
            _append(_ERRORS_LOG, event)

        if event_type.startswith("validation_"):
            _append(_VALIDATION_LOG, event)

    except Exception as exc:
        log.warning("event_logger: write failed — %s", exc)


def log_error(event: dict[str, Any]) -> None:
    """Write directly to errors.log (and events.log)."""
    try:
        _append(_ERRORS_LOG, event)
        _append(_EVENTS_LOG, event)
    except Exception as exc:
        log.warning("event_logger: error write failed — %s", exc)


def log_validation(event: dict[str, Any]) -> None:
    """Write directly to validation.log (and events.log)."""
    try:
        _append(_VALIDATION_LOG, event)
        _append(_EVENTS_LOG, event)
    except Exception as exc:
        log.warning("event_logger: validation write failed — %s", exc)


def read_events(limit: int = 100, event_type: str = "", module: str = "", status: str = "") -> list[dict]:
    """Read events from events.log with optional filtering."""
    return _read(_EVENTS_LOG, limit, event_type=event_type, module=module, status=status)


def read_errors(limit: int = 100) -> list[dict]:
    """Read from errors.log (most recent first)."""
    return _read(_ERRORS_LOG, limit)


def read_validation(limit: int = 100, passed_only: bool = False, failed_only: bool = False) -> list[dict]:
    """Read from validation.log."""
    status_filter = ""
    if passed_only:
        status_filter = "passed"
    elif failed_only:
        status_filter = "failed"
    return _read(_VALIDATION_LOG, limit, status=status_filter)


def get_log_stats() -> dict[str, Any]:
    """Return basic stats about the log files."""
    return {
        "events_count":     _count_lines(_EVENTS_LOG),
        "errors_count":     _count_lines(_ERRORS_LOG),
        "validation_count": _count_lines(_VALIDATION_LOG),
        "events_size_kb":   _size_kb(_EVENTS_LOG),
        "errors_size_kb":   _size_kb(_ERRORS_LOG),
        "validation_size_kb": _size_kb(_VALIDATION_LOG),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _append(path: Path, event: dict[str, Any]) -> None:
    """Append one JSON line to a log file. Thread-safe."""
    # Add timestamp if not present
    if "logged_at" not in event:
        event = {**event, "logged_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds")}

    line = json.dumps(event, ensure_ascii=False, default=str) + "\n"

    with _LOCK:
        _rotate_if_needed(path)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


def _rotate_if_needed(path: Path) -> None:
    """Rotate log file if it exceeds _MAX_BYTES."""
    if path.exists() and path.stat().st_size > _MAX_BYTES:
        rotated = path.with_suffix(f".{_ts_compact()}.log")
        path.rename(rotated)
        log.info("event_logger: rotated %s → %s", path.name, rotated.name)


def _read(
    path:       Path,
    limit:      int,
    event_type: str = "",
    module:     str = "",
    status:     str = "",
) -> list[dict]:
    """Read last `limit` matching lines from a log file."""
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        results: list[dict] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

            if event_type and entry.get("event_type") != event_type:
                continue
            if module and entry.get("module") != module:
                continue
            if status and entry.get("status") != status:
                continue

            results.append(entry)
            if len(results) >= limit:
                break

        return results
    except Exception as exc:
        log.warning("event_logger: read failed %s — %s", path.name, exc)
        return []


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def _size_kb(path: Path) -> float:
    if not path.exists():
        return 0.0
    return round(path.stat().st_size / 1024, 1)


def _ts_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
