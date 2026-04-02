"""
billing/usage_logger.py — CEO billing usage logger.

Every CEO-approved action logs here — approved AND blocked.
No silent deductions. No missing billing logs.

Log destination: MongoDB activity_logs collection (same as mini_credits).
Falls back gracefully if DB unavailable — never raises.

LOG SCHEMA:
  {
    user_id:       str,
    session_id:    str | None,
    action_type:   str,
    module_used:   str,
    credits_used:  int,
    status:        "approved" | "blocked" | "grace" | "error",
    block_reason:  str | None,
    duration_ms:   float | None,
    timestamp:     float,        # Unix timestamp
    month_key:     str,          # "YYYY-MM"
    billing_layer: "ceo",        # identifies this as CEO billing log
  }
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("billing.usage_logger")


async def log_usage(
    user_id:      str,
    session_id:   Optional[str],
    action_type:  str,
    module_used:  str,
    credits_used: int,
    status:       str,
    block_reason: Optional[str] = None,
    duration_ms:  Optional[float] = None,
    metadata:     Optional[dict[str, Any]] = None,
) -> None:
    """
    Record a CEO billing event.

    status: "approved" | "blocked" | "grace" | "error"
    Never raises — logging must not crash execution.
    """
    try:
        db = await _get_db()
        if db is None:
            log.debug("usage_logger: DB unavailable — skipping log for %s/%s", user_id, action_type)
            return

        now = datetime.now(timezone.utc)
        record: dict[str, Any] = {
            "user_id":      user_id,
            "session_id":   session_id,
            "action_type":  action_type,
            "module_used":  module_used,
            "credits_used": credits_used,
            "status":       status,
            "block_reason": block_reason,
            "duration_ms":  duration_ms,
            "timestamp":    time.time(),
            "month_key":    f"{now.year:04d}-{now.month:02d}",
            "billing_layer": "ceo",
        }
        if metadata:
            record["meta"] = {k: v for k, v in metadata.items() if k not in record}

        await db["activity_logs"].insert_one(record)

    except Exception as exc:
        log.warning("usage_logger: insert failed for %s/%s — %s", user_id, action_type, exc)


async def log_blocked(
    user_id:     str,
    session_id:  Optional[str],
    action_type: str,
    module_used: str,
    reason:      str,
) -> None:
    """Convenience wrapper for blocked actions (credits_used = 0)."""
    await log_usage(
        user_id      = user_id,
        session_id   = session_id,
        action_type  = action_type,
        module_used  = module_used,
        credits_used = 0,
        status       = "blocked",
        block_reason = reason,
    )


async def log_grace(
    user_id:     str,
    session_id:  Optional[str],
    grace_left:  int,
) -> None:
    """Log a grace-period chat message."""
    await log_usage(
        user_id      = user_id,
        session_id   = session_id,
        action_type  = "chat_basic",
        module_used  = "general_chat",
        credits_used = 0,
        status       = "grace",
        block_reason = f"grace_messages_remaining={grace_left}",
    )


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

async def _get_db():
    try:
        import server as _srv
        return _srv.db
    except Exception:
        return None
