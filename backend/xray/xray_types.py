"""
xray/xray_types.py — Shared types for the X-Ray service layer.

These are the data contracts used between xray_service, xray_reader,
and the admin dashboard API. Kept separate so they can be imported
by any layer without circular dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class XRaySession:
    """Aggregated X-Ray data for a single session."""
    session_id:      str
    total_events:    int
    error_count:     int
    validation_pass: int
    validation_fail: int
    start_time:      Optional[str]
    end_time:        Optional[str]
    modules_seen:    list[str]
    has_orch_state:  bool
    final_status:    Optional[str]
    elapsed_ms:      Optional[float]


@dataclass
class XRayEvent:
    """Single event record from the log pipeline."""
    event_type: str
    module:     str
    status:     str
    summary:    str
    timestamp:  str
    session_id: Optional[str]
    detail:     dict[str, Any] = field(default_factory=dict)


@dataclass
class LogStats:
    """Stats snapshot for the log viewer."""
    events_count:       int
    errors_count:       int
    validation_count:   int
    events_size_kb:     float
    errors_size_kb:     float
    validation_size_kb: float
