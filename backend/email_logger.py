"""
email_logger.py
Shared email send-with-retry + MongoDB logging for Mini Assistant AI.

Usage:
    from email_logger import send_with_log

    ok = await send_with_log(
        db=db,
        user_id="abc",
        email="user@example.com",
        email_type="welcome",          # "welcome" | "upgrade" | "topup"
        send_fn=resend.Emails.send,    # callable(params) → {"id": ...}
        params=resend_params_dict,
    )

The caller never needs to worry about logging or retries — all handled here.
Conversion tracking is done separately via mark_conversion().
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Callable

log = logging.getLogger(__name__)

# Retry schedule: [seconds to wait before attempt 2, before attempt 3]
_RETRY_DELAYS: list[float] = [2.0, 5.0]


# ---------------------------------------------------------------------------
# Core: send with retry + log
# ---------------------------------------------------------------------------

async def send_with_log(
    *,
    db,
    user_id: str,
    email: str,
    email_type: str,           # "welcome" | "upgrade" | "topup" | "followup_upgrade" | "low_credits" | "payment_failed"
    send_fn: Callable,         # synchronous callable: send_fn(params) → dict
    params: dict,
    subject: str = "",
    automated: bool = False,   # True for background-task triggered emails
) -> bool:
    """
    Call send_fn(params) with up to 2 retries.
    Writes a document to email_logs on final success or final failure.
    Never raises — always returns bool.
    """
    last_error: str = ""

    for attempt in range(len(_RETRY_DELAYS) + 1):   # attempts: 0, 1, 2
        if attempt > 0:
            delay = _RETRY_DELAYS[attempt - 1]
            log.info("email_logger: retry %d for %s (%s) after %.0fs", attempt, email_type, email, delay)
            await asyncio.sleep(delay)

        try:
            resp = send_fn(params)
            resend_id = resp.get("id") if isinstance(resp, dict) else None
            log.info("email_logger: sent %s to %s (attempt=%d id=%s)", email_type, email, attempt + 1, resend_id)

            await _write_log(
                db=db,
                user_id=user_id,
                email=email,
                email_type=email_type,
                subject=subject,
                status="sent",
                resend_id=resend_id,
                automated=automated,
            )
            return True

        except Exception as exc:
            last_error = str(exc)
            log.warning("email_logger: attempt %d failed for %s (%s): %s", attempt + 1, email_type, email, exc)

    # All attempts exhausted
    log.error("email_logger: all retries failed for %s (%s): %s", email_type, email, last_error)
    await _write_log(
        db=db,
        user_id=user_id,
        email=email,
        email_type=email_type,
        subject=subject,
        status="failed",
        error_message=last_error,
        automated=automated,
    )
    return False


# ---------------------------------------------------------------------------
# Conversion tracking
# ---------------------------------------------------------------------------

async def mark_conversion(
    db,
    user_id: str,
    conversion_type: str,   # "upgrade" | "topup"
    window_hours: int = 48,
) -> None:
    """
    Find the most recent welcome/upgrade email sent to this user within
    `window_hours` and mark it as converted.
    Non-fatal — any error is logged and swallowed.
    """
    try:
        cutoff = time.time() - (window_hours * 3600)
        # For upgrade conversions look at "welcome" emails;
        # for topup conversions look at "topup" emails within 24h
        email_type_filter = "welcome" if conversion_type == "upgrade" else "topup"

        await db["email_logs"].update_one(
            {
                "user_id":    user_id,
                "email_type": email_type_filter,
                "status":     "sent",
                "timestamp":  {"$gte": cutoff},
                "converted":  {"$ne": True},
            },
            {
                "$set": {
                    "converted":       True,
                    "conversion_type": conversion_type,
                    "converted_at":    time.time(),
                }
            },
            # Sort by most recent; Motor update_one doesn't support sort directly,
            # so we rely on the natural index sort (newest first via timestamp index).
        )
    except Exception as exc:
        log.warning("mark_conversion failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _write_log(
    *,
    db,
    user_id: str,
    email: str,
    email_type: str,
    subject: str,
    status: str,
    resend_id: str | None = None,
    error_message: str | None = None,
    automated: bool = False,
) -> None:
    """Insert one document into email_logs. Non-fatal."""
    if db is None:
        return
    try:
        doc: dict = {
            "user_id":    user_id,
            "email":      email,
            "email_type": email_type,
            "subject":    subject,
            "status":     status,
            "provider":   "resend",
            "automated":  automated,
            "timestamp":  time.time(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if resend_id:
            doc["resend_id"] = resend_id
        if error_message:
            doc["error_message"] = error_message
        await db["email_logs"].insert_one(doc)
    except Exception as exc:
        log.warning("email_logger: failed to write log (non-fatal): %s", exc)
