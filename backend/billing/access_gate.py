"""
billing/access_gate.py — Single execution gate for the BYOK + subscription model.

Replaces ALL credit-based gating with two checks:
  1. is_subscribed == True   (active Stripe subscription)
  2. api_key_verified == True (user has added + tested a valid API key)

Admins bypass both checks.

Usage:
  from billing.access_gate import can_execute, ExecutionBlock

  allowed, block = can_execute(user)
  if not allowed:
      return block.to_response()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("billing.access_gate")


# ---------------------------------------------------------------------------
# Block result
# ---------------------------------------------------------------------------

@dataclass
class ExecutionBlock:
    reason: str          # machine-readable: "not_subscribed" | "no_api_key" | "admin_bypass"
    message: str         # human-readable, shown in UI
    http_status: int     # 402 for subscription, 403 for no key (both tell frontend to show specific UI)
    action: str          # "subscribe" | "add_api_key" | "none"

    def to_response(self) -> dict[str, Any]:
        return {
            "status":      "blocked",
            "reason":      self.reason,
            "message":     self.message,
            "http_status": self.http_status,
            "action":      self.action,
        }


# ---------------------------------------------------------------------------
# Public gate
# ---------------------------------------------------------------------------

def can_execute(user: dict[str, Any]) -> tuple[bool, ExecutionBlock | None]:
    """
    Returns (allowed: bool, block: ExecutionBlock | None).

    If allowed is True, block is None.
    If allowed is False, block contains the reason and suggested action.

    Call this once per request BEFORE any AI/execution logic.
    Admins always pass.
    """
    if not user:
        log.warning("access_gate: can_execute called with empty user dict")
        return False, ExecutionBlock(
            reason="no_user",
            message="Authentication required.",
            http_status=401,
            action="none",
        )

    # Admins bypass everything
    if user.get("role") == "admin" or user.get("plan") == "admin":
        return True, None

    # Check 1: active subscription
    if not user.get("is_subscribed", False):
        log.info("access_gate: blocked — not subscribed user_id=%s", user.get("id"))
        return False, ExecutionBlock(
            reason="not_subscribed",
            message=(
                "An active subscription is required to run tasks. "
                "Subscribe to unlock the full platform."
            ),
            http_status=402,
            action="subscribe",
        )

    # Check 2: verified API key
    if not user.get("api_key_verified", False):
        log.info("access_gate: blocked — no verified API key user_id=%s", user.get("id"))
        return False, ExecutionBlock(
            reason="no_api_key",
            message=(
                "Add and verify your API key to start executing tasks. "
                "Your key is encrypted and never shared."
            ),
            http_status=403,
            action="add_api_key",
        )

    return True, None


def require_full_access(user: dict[str, Any]) -> ExecutionBlock | None:
    """
    Convenience wrapper — returns None if allowed, ExecutionBlock if blocked.
    Use when you want to handle the block inline.
    """
    allowed, block = can_execute(user)
    return None if allowed else block


def is_subscribed(user: dict[str, Any]) -> bool:
    """Quick read-only check for subscription status (no side effects)."""
    if user.get("role") == "admin" or user.get("plan") == "admin":
        return True
    return bool(user.get("is_subscribed", False))


def has_verified_key(user: dict[str, Any]) -> bool:
    """Quick read-only check for API key status (no side effects)."""
    if user.get("role") == "admin" or user.get("plan") == "admin":
        return True
    return bool(user.get("api_key_verified", False))
