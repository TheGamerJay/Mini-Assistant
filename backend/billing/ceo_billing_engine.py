"""
billing/ceo_billing_engine.py — CEO Execution Gate (BYOK + subscription model).

Replaced credit-based gating with two checks:
  1. is_subscribed == True   (active Stripe subscription)
  2. api_key_verified == True (user has added + tested a valid API key)

Admins bypass both checks.
Fail-closed: on DB error or missing user → block.

Return structure:
  {
    status:        "approved" | "blocked",
    action_type:   str,
    block_message: str | None,
    block_reason:  str | None,
    # Legacy fields preserved so callers don't need updates:
    credits_used:      0,
    remaining_credits: 0,
    cost:              0,
    warning:           None,
  }
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .access_gate import can_execute
from .usage_logger import log_usage, log_blocked

log = logging.getLogger("billing.ceo_engine")


async def process_request(
    user_id:       str,
    module:        str,
    session_id:    Optional[str] = None,
    metadata:      Optional[dict[str, Any]] = None,
    action_type:   Optional[str] = None,
    authorization: Optional[str] = None,
) -> dict[str, Any]:
    """
    Main execution gate. Call this BEFORE building the execution plan.
    Returns a BillingResult dict. If status != "approved" → do NOT proceed.
    """
    meta = metadata or {}
    t0   = time.perf_counter()
    resolved_action = action_type or _resolve_action(module, meta)

    try:
        user = await _load_user(user_id)
        if user is None:
            await log_blocked(user_id, session_id, resolved_action, module, "user_not_found")
            return _blocked("User account not found.", "user_not_found", resolved_action)

        allowed, block = can_execute(user)

        elapsed = round((time.perf_counter() - t0) * 1000, 1)

        if not allowed:
            await log_blocked(user_id, session_id, resolved_action, module, block.reason)
            return _blocked(block.message, block.reason, resolved_action)

        await log_usage(
            user_id      = user_id,
            session_id   = session_id,
            action_type  = resolved_action,
            module_used  = module,
            credits_used = 0,
            status       = "approved",
            duration_ms  = elapsed,
        )
        return _approved(resolved_action)

    except Exception as exc:
        log.error("billing.ceo_engine: unexpected error user=%s module=%s — %s", user_id, module, exc)
        await log_blocked(user_id, session_id, resolved_action, module, "engine_error")
        return _blocked("Billing check failed — please try again.", "engine_error", resolved_action)


# ---------------------------------------------------------------------------
# Module → action_type (preserved for logging continuity)
# ---------------------------------------------------------------------------

_MODULE_ACTION_MAP: dict[str, str] = {
    "builder":      "builder_generation",
    "doctor":       "doctor_full_scan",
    "hands":        "builder_generation",
    "vision":       "image_analyze",
    "general_chat": "chat_basic",
    "core_chat":    "chat_basic",
    "web_search":   "web_search_basic",
    "task_assist":  "chat_basic",
    "campaign_lab": "campaign_concept",
    "image":        "image_generation",
    "image_edit":   "image_edit",
}


def _resolve_action(module: str, meta: dict) -> str:
    base = _MODULE_ACTION_MAP.get(module, module)
    if meta.get("is_regeneration") and base.endswith("_generation"):
        return base.replace("_generation", "_regeneration")
    return base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _load_user(user_id: str) -> dict | None:
    try:
        import server as _srv
        if _srv.db is None:
            return None
        return await _srv.db["users"].find_one(
            {"id": user_id},
            {"id": 1, "role": 1, "plan": 1, "is_subscribed": 1, "api_key_verified": 1},
        )
    except Exception as exc:
        log.warning("ceo_engine: failed to load user %s — %s", user_id, exc)
        return None


def _approved(action_type: str) -> dict[str, Any]:
    return {
        "status":            "approved",
        "action_type":       action_type,
        "block_message":     None,
        "block_reason":      None,
        # Legacy fields — kept so existing callers don't need changes
        "credits_used":      0,
        "remaining_credits": 0,
        "cost":              0,
        "warning":           None,
    }


def _blocked(message: str, reason: str, action_type: str) -> dict[str, Any]:
    return {
        "status":            "blocked",
        "action_type":       action_type,
        "block_message":     message,
        "block_reason":      reason,
        "credits_used":      0,
        "remaining_credits": 0,
        "cost":              0,
        "warning":           None,
    }
