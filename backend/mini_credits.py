"""
mini_credits.py — RETIRED (credit system removed 2026-04).

The credit-based billing system has been replaced by the BYOK + subscription model.
All functions in this module are now no-ops that return safe defaults.

Execution gating is now handled exclusively by:
    from billing.access_gate import can_execute

Activity history in MongoDB (activity_logs collection) is preserved for
admin review and chargeback defense — this module no longer writes to it.

DO NOT DELETE this file — legacy imports from server.py and other modules
reference these symbols. Safe to leave as stubs indefinitely.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Preserved for any code that imports these constants
CREDIT_COSTS: dict[str, int] = {}
PLAN_CREDIT_LIMITS: dict[str, int] = {}
PLAN_MONTHLY_PRICE_USD: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Public API — all no-ops
# ---------------------------------------------------------------------------

async def get_user_credits(authorization: str | None) -> int | None:
    """RETIRED — always returns 0. Credits no longer exist."""
    return 0


async def check_and_deduct(
    authorization: str | None,
    cost: int | None = None,
    action_type: str = "chat_message",
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> tuple[bool, int]:
    """
    RETIRED — always returns (True, 0).
    Execution gating is now handled by billing.access_gate.can_execute().
    """
    return True, 0


async def rollback_credits(
    authorization: str | None,
    cost: int,
    action_type: str = "chat_message",
) -> bool:
    """RETIRED — no-op, always returns True."""
    return True


async def check_image_limit(user_id: str) -> dict:
    """
    RETIRED — image limits are no longer credit-based.
    Returns unlimited access for subscribed users (access_gate handles the gate).
    """
    return {"allowed": True, "used": 0, "limit": 999999, "resets_on": None}


async def log_image_generated(user_id: str, prompt: str = "") -> None:
    """RETIRED — no-op."""
    return
