"""
billing/credit_store.py — Credit balance queries and grace tracking.

Thin async wrapper over the MongoDB users collection.
Used by ceo_billing_engine to check balances before deduction.

All writes (deductions) are delegated to mini_credits.check_and_deduct()
to preserve the atomic dual-credit logic and race-condition protections.

NEVER call this directly from a module — only CEO billing engine uses it.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger("billing.credit_store")

MAX_GRACE_MESSAGES = 3


# ---------------------------------------------------------------------------
# Balance queries
# ---------------------------------------------------------------------------

async def get_balance(user_id: str) -> int:
    """Return current credit balance for a user (0 if not found)."""
    try:
        db = await _get_db()
        if db is None:
            return 0
        user = await db["users"].find_one(
            {"id": user_id},
            {"credits": 1, "subscription_credits": 1, "topup_credits": 1},
        )
        if not user:
            return 0
        return _total_credits(user)
    except Exception as exc:
        log.warning("credit_store.get_balance(%s) failed — %s", user_id, exc)
        return 0


async def get_user_record(user_id: str) -> Optional[dict[str, Any]]:
    """Return lightweight user record for billing decisions."""
    try:
        db = await _get_db()
        if db is None:
            return None
        return await db["users"].find_one(
            {"id": user_id},
            {
                "id": 1, "plan": 1, "role": 1,
                "credits": 1, "subscription_credits": 1, "topup_credits": 1,
                "grace_messages_used": 1,
            },
        )
    except Exception as exc:
        log.warning("credit_store.get_user_record(%s) failed — %s", user_id, exc)
        return None


async def get_plan_limit(user_id: str) -> int:
    """Return the credit limit for the user's current plan."""
    from mini_credits import PLAN_CREDIT_LIMITS
    try:
        db = await _get_db()
        if db is None:
            return PLAN_CREDIT_LIMITS["free"]
        user = await db["users"].find_one({"id": user_id}, {"plan": 1})
        plan = (user.get("plan") or "free").lower() if user else "free"
        return PLAN_CREDIT_LIMITS.get(plan, PLAN_CREDIT_LIMITS["free"])
    except Exception as exc:
        log.warning("credit_store.get_plan_limit(%s) failed — %s", user_id, exc)
        return PLAN_CREDIT_LIMITS["free"]


# ---------------------------------------------------------------------------
# Grace buffer
# ---------------------------------------------------------------------------

async def get_grace_used(user_id: str) -> int:
    """Return number of grace messages used after credits hit 0."""
    try:
        db = await _get_db()
        if db is None:
            return 0
        user = await db["users"].find_one({"id": user_id}, {"grace_messages_used": 1})
        if not user:
            return 0
        return int(user.get("grace_messages_used", 0))
    except Exception as exc:
        log.warning("credit_store.get_grace_used(%s) failed — %s", user_id, exc)
        return 0


async def increment_grace(user_id: str) -> int:
    """
    Atomically increment grace_messages_used by 1, ONLY if still below the limit.

    Uses a conditional update ($lt filter) to prevent the TOCTOU race:
    two concurrent requests at grace_used=2 can't both succeed — only one
    will match the filter and increment; the other will get no match and
    be treated as grace exhausted.

    Returns the NEW value after increment, or MAX_GRACE_MESSAGES if limit reached.
    """
    try:
        db = await _get_db()
        if db is None:
            return MAX_GRACE_MESSAGES  # fail closed
        result = await db["users"].find_one_and_update(
            {
                "id": user_id,
                # Only increment if still below the limit (atomic guard)
                "grace_messages_used": {"$lt": MAX_GRACE_MESSAGES},
            },
            {"$inc": {"grace_messages_used": 1}},
            return_document=True,
            projection={"grace_messages_used": 1},
        )
        if result is None:
            # No document matched — either user not found OR grace already exhausted
            return MAX_GRACE_MESSAGES
        return int(result.get("grace_messages_used", MAX_GRACE_MESSAGES))
    except Exception as exc:
        log.warning("credit_store.increment_grace(%s) failed — %s", user_id, exc)
        return MAX_GRACE_MESSAGES  # fail closed


async def reset_grace(user_id: str) -> None:
    """Reset grace counter when credits are restored."""
    try:
        db = await _get_db()
        if db is None:
            return
        await db["users"].update_one(
            {"id": user_id},
            {"$set": {"grace_messages_used": 0}},
        )
    except Exception as exc:
        log.warning("credit_store.reset_grace(%s) failed — %s", user_id, exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _total_credits(user: dict) -> int:
    sub_c = user.get("subscription_credits")
    if sub_c is not None:
        return max(0, sub_c) + max(0, user.get("topup_credits", 0))
    return max(0, user.get("credits", 0))


async def _get_db():
    try:
        import server as _srv
        return _srv.db
    except Exception:
        return None
