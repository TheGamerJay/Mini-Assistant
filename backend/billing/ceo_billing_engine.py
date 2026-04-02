"""
billing/ceo_billing_engine.py — CEO Billing Engine.

The single billing gatekeeper. CEO calls this BEFORE building the
execution plan. If billing blocks → no plan is built, no module runs.

Fail-closed: if billing fails for any reason → execution is blocked.
No partial execution. No silent free usage. No negative credits.

Flow:
  1. Resolve action_type from module + metadata
  2. Get credit cost from cost_resolver
  3. Get user balance from credit_store
  4. Check grace buffer if credits = 0
  5. Approve or block
  6. If approved + cost > 0 → deduct via mini_credits.check_and_deduct()
  7. Log usage (approved and blocked)
  8. Return BillingResult

Return structure:
  {
    status:            "approved" | "blocked" | "grace",
    credits_used:      int,
    remaining_credits: int,
    action_type:       str,
    cost:              int,
    warning:           dict | None,    # low-credit warning (attach to response)
    block_message:     str | None,
    block_reason:      str | None,
  }

RULES:
  - CEO is the ONLY caller
  - modules may NOT call this
  - if exception occurs → block (fail closed)
  - unauthenticated → block
  - DB unavailable → block paid features, allow chat_basic only with warning
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .cost_resolver import (
    get_action_cost,
    resolve_action_type,
    is_free_gated,
)
from .credit_store import (
    get_balance,
    get_plan_limit,
    get_user_record,
    get_grace_used,
    increment_grace,
    reset_grace,
    MAX_GRACE_MESSAGES,
)
from .credit_warning import (
    can_user_chat,
    low_credit_warning_response,
    paused_response,
)
from .usage_logger import log_usage, log_blocked, log_grace

log = logging.getLogger("billing.ceo_engine")


async def process_request(
    user_id:     str,
    module:      str,
    session_id:  Optional[str] = None,
    metadata:    Optional[dict[str, Any]] = None,
    action_type: Optional[str] = None,
    authorization: Optional[str] = None,
) -> dict[str, Any]:
    """
    Main CEO billing gate. Call this BEFORE building the execution plan.

    Args:
        user_id:       authenticated user ID
        module:        selected module name (e.g. "builder", "general_chat")
        session_id:    current session ID (for logging)
        metadata:      optional context: {is_regeneration, complexity, has_attachment, ...}
        action_type:   explicit action_type override (if None, resolved from module)
        authorization: Bearer token (forwarded to mini_credits for deduction)

    Returns:
        BillingResult dict. If status != "approved" → do NOT proceed.
    """
    meta = metadata or {}
    t0   = time.perf_counter()

    try:
        # ── Step 1: Resolve action type ───────────────────────────────────────
        resolved_action = action_type or resolve_action_type(module, meta)
        cost = get_action_cost(resolved_action, meta)

        log.debug(
            "billing: user=%s module=%s action=%s cost=%d",
            user_id, module, resolved_action, cost,
        )

        # ── Step 2: Load user record ──────────────────────────────────────────
        user = await get_user_record(user_id)
        if user is None:
            await log_blocked(user_id, session_id, resolved_action, module, "user_not_found")
            return _blocked("User account not found.", "user_not_found", resolved_action, cost)

        plan    = (user.get("plan") or "free").lower()
        balance = _total_credits(user)

        # Admin/max bypass billing gate (still logs)
        if plan in ("admin",) or user.get("role") == "admin":
            elapsed = round((time.perf_counter() - t0) * 1000, 1)
            await log_usage(user_id, session_id, resolved_action, module, 0, "approved",
                            duration_ms=elapsed)
            return _approved(0, balance, resolved_action, cost, balance, plan)

        # ── Step 3: Grace buffer (credits = 0, chat only) ─────────────────────
        if balance == 0 and cost == 0 and is_free_gated(resolved_action):
            grace_used = await get_grace_used(user_id)
            chat_access = can_user_chat(balance, grace_used, plan)

            if chat_access["state"] in ("grace", "active"):
                # Atomic conditional increment — returns MAX_GRACE_MESSAGES if exhausted
                new_grace = await increment_grace(user_id)

                if new_grace >= MAX_GRACE_MESSAGES:
                    # Race condition caught atomically — grace just exhausted
                    await log_blocked(user_id, session_id, resolved_action, module, "grace_exhausted")
                    pr = paused_response()
                    return {**_blocked(pr["message"], "grace_exhausted", resolved_action, cost), **pr}

                grace_left = MAX_GRACE_MESSAGES - new_grace
                elapsed = round((time.perf_counter() - t0) * 1000, 1)
                await log_grace(user_id, session_id, grace_left)
                plan_limit = await get_plan_limit(user_id)
                warning = low_credit_warning_response(balance, plan_limit)
                log.info(
                    "billing: grace user=%s grace_left=%d",
                    user_id, grace_left,
                )
                return {
                    "status":            "grace",
                    "credits_used":      0,
                    "remaining_credits": 0,
                    "action_type":       resolved_action,
                    "cost":              0,
                    "grace_left":        grace_left,
                    "warning":           warning,
                    "block_message":     None,
                    "block_reason":      None,
                }

            if chat_access["state"] == "paused":
                await log_blocked(user_id, session_id, resolved_action, module, "grace_exhausted")
                pr = paused_response()
                return {**_blocked(pr["message"], "grace_exhausted", resolved_action, cost), **pr}

        # ── Step 4: Check balance vs cost ─────────────────────────────────────
        if balance < cost:
            reason = "insufficient_credits" if balance > 0 else "zero_credits"
            await log_blocked(user_id, session_id, resolved_action, module, reason)

            if balance == 0:
                pr = paused_response()
                return {**_blocked(pr["message"], reason, resolved_action, cost), **pr}

            msg = (
                f"This action requires {cost} credits. "
                f"You have {balance} credits remaining. "
                "Top up or upgrade to continue."
            )
            return _blocked(msg, reason, resolved_action, cost, remaining=balance)

        # ── Step 5: Deduct credits (only if cost > 0) ─────────────────────────
        remaining = balance
        if cost > 0 and authorization:
            ok, remaining = await _deduct(authorization, resolved_action, cost)
            if not ok:
                # Race condition: another request consumed credits first
                fresh_balance = await get_balance(user_id)
                await log_blocked(user_id, session_id, resolved_action, module, "race_condition")
                msg = (
                    f"Unable to confirm credit deduction. "
                    f"Current balance: {fresh_balance}. Please try again."
                )
                return _blocked(msg, "race_condition", resolved_action, cost, remaining=fresh_balance)
        elif cost > 0 and not authorization:
            # No auth token — cannot deduct. Fail closed for paid features.
            await log_blocked(user_id, session_id, resolved_action, module, "no_auth_for_deduction")
            return _blocked(
                "Authentication required for this action.",
                "no_auth_for_deduction",
                resolved_action,
                cost,
            )

        # If user has credits (restored or always had them), reset grace counter
        # so they get the full 3 messages next time credits run out.
        if balance > 0:
            await reset_grace(user_id)

        # ── Step 6: Log + return approval ─────────────────────────────────────
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        await log_usage(
            user_id, session_id, resolved_action, module,
            cost, "approved", duration_ms=elapsed,
        )

        plan_limit = await get_plan_limit(user_id)
        warning = low_credit_warning_response(remaining, plan_limit)

        log.info(
            "billing: approved user=%s action=%s cost=%d remaining=%d",
            user_id, resolved_action, cost, remaining,
        )
        return _approved(cost, remaining, resolved_action, cost, plan_limit, plan, warning)

    except Exception as exc:
        # FAIL CLOSED — any unexpected error blocks execution
        log.error("billing: EXCEPTION — blocking execution user=%s: %s", user_id, exc, exc_info=True)
        try:
            await log_blocked(user_id, session_id, action_type or module, module, f"exception: {exc}")
        except Exception:
            pass
        return _blocked(
            "Billing system encountered an error. Please try again.",
            "billing_exception",
            action_type or module,
            0,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _deduct(authorization: str, action_type: str, cost: int) -> tuple[bool, int]:
    """Delegate actual deduction to mini_credits.check_and_deduct()."""
    try:
        from mini_credits import check_and_deduct
        return await check_and_deduct(
            authorization=authorization,
            cost=cost,
            action_type=action_type,
        )
    except Exception as exc:
        log.error("billing: deduction via mini_credits failed — %s", exc)
        return False, 0


def _total_credits(user: dict) -> int:
    sub_c = user.get("subscription_credits")
    if sub_c is not None:
        return max(0, sub_c) + max(0, user.get("topup_credits", 0))
    return max(0, user.get("credits", 0))


def _approved(
    credits_used:      int,
    remaining:         int,
    action_type:       str,
    cost:              int,
    plan_limit:        int,
    plan:              str = "free",
    warning:           Any = None,
) -> dict[str, Any]:
    return {
        "status":            "approved",
        "credits_used":      credits_used,
        "remaining_credits": remaining,
        "action_type":       action_type,
        "cost":              cost,
        "plan":              plan,
        "warning":           warning,
        "block_message":     None,
        "block_reason":      None,
    }


def _blocked(
    message:     str,
    reason:      str,
    action_type: str,
    cost:        int,
    remaining:   int = 0,
) -> dict[str, Any]:
    return {
        "status":            "blocked",
        "credits_used":      0,
        "remaining_credits": remaining,
        "action_type":       action_type,
        "cost":              cost,
        "warning":           None,
        "block_message":     message,
        "block_reason":      reason,
    }
