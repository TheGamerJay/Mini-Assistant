"""
billing/credit_store.py — RETIRED (credit system removed 2026-04).

All functions are no-ops returning safe defaults.
Execution gating is now handled by billing.access_gate.can_execute().

DO NOT DELETE — referenced by ceo_billing_engine and other legacy callers.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger("billing.credit_store")

MAX_GRACE_MESSAGES = 0  # Grace system retired


async def get_balance(user_id: str) -> int:
    """RETIRED — returns 0. Credits no longer exist."""
    return 0


async def get_user_record(user_id: str) -> Optional[dict[str, Any]]:
    """RETIRED — returns None. Use DB directly in auth_routes."""
    return None


async def get_plan_limit(user_id: str) -> int:
    """RETIRED — returns 0."""
    return 0


async def get_grace_used(user_id: str) -> int:
    """RETIRED — returns 0. Grace system removed."""
    return 0


async def increment_grace(user_id: str) -> int:
    """RETIRED — no-op, returns 0."""
    return 0


async def reset_grace(user_id: str) -> None:
    """RETIRED — no-op."""
    return
