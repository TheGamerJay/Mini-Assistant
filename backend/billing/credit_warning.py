"""
billing/credit_warning.py — Credit warning system + chat access control.

CEO uses these functions to decide:
  - can_user_chat()    → is chat permitted?
  - get_credit_warning() → what warning (if any) to show?

Chat access rules:
  STATE 1: credits > 0           → full access
  STATE 2: credits = 0, grace left → limited chat (grace buffer)
  STATE 3: credits = 0, grace exhausted → paused

Warning thresholds:
  30% remaining → "running low" warning
  10% remaining → "almost out" warning
  0%            → "paused" state
"""

from __future__ import annotations

from typing import Any

from .credit_store import MAX_GRACE_MESSAGES


# ---------------------------------------------------------------------------
# Chat access control
# ---------------------------------------------------------------------------

def can_user_chat(
    balance:       int,
    grace_used:    int,
    plan:          str = "free",
) -> dict[str, Any]:
    """
    Determine whether a user may send a chat message.

    Returns:
      {
        allowed:       bool,
        state:         "active" | "grace" | "paused",
        grace_left:    int,         # remaining grace messages (0 if not in grace)
        block_message: str | None,  # user-facing message if blocked
      }
    """
    # Admin and max users always have access
    if plan in ("admin", "max"):
        return {"allowed": True, "state": "active", "grace_left": 0, "block_message": None}

    # Active: credits > 0
    if balance > 0:
        return {"allowed": True, "state": "active", "grace_left": 0, "block_message": None}

    # credits == 0 — check grace
    grace_left = MAX_GRACE_MESSAGES - grace_used
    if grace_left > 0:
        return {
            "allowed":       True,
            "state":         "grace",
            "grace_left":    grace_left,
            "block_message": None,
        }

    # Fully paused
    return {
        "allowed":       False,
        "state":         "paused",
        "grace_left":    0,
        "block_message": _paused_message(),
    }


# ---------------------------------------------------------------------------
# Credit warnings
# ---------------------------------------------------------------------------

def get_credit_warning(balance: int, plan_limit: int) -> dict[str, Any]:
    """
    Return a warning dict based on credit percentage remaining.

    Returns:
      {
        show_warning: bool,
        level:        "low" | "critical" | "exhausted" | None,
        message:      str | None,
        percentage:   float,
      }
    """
    if plan_limit <= 0:
        return {"show_warning": False, "level": None, "message": None, "percentage": 100.0}

    pct = (balance / plan_limit) * 100.0

    if balance == 0:
        return {
            "show_warning": True,
            "level":        "exhausted",
            "message":      "⚡ No credits remaining. Chat is free but requires an active balance — using grace messages now.",
            "percentage":   0.0,
        }

    if pct <= 10:
        return {
            "show_warning": True,
            "level":        "critical",
            "message":      "⚡ Almost out of credits. Top up to keep the assistant running.",
            "percentage":   round(pct, 1),
        }

    if pct <= 30:
        return {
            "show_warning": True,
            "level":        "low",
            "message":      "⚠️ You're running low on credits.",
            "percentage":   round(pct, 1),
        }

    return {"show_warning": False, "level": None, "message": None, "percentage": round(pct, 1)}


# ---------------------------------------------------------------------------
# Standard user-facing messages
# ---------------------------------------------------------------------------

def paused_response() -> dict[str, Any]:
    """Structured paused-state response for the CEO to return."""
    return {
        "type":          "billing_paused",
        "status":        "blocked",
        "title":         "⚡ Assistant Paused",
        "message":       _paused_message(),
        "credits_used":  0,
        "action_needed": "upgrade_or_topup",
    }


def low_credit_warning_response(balance: int, plan_limit: int) -> dict[str, Any] | None:
    """
    Return a warning to attach to the response when credits are low.
    Returns None if no warning is needed.
    """
    w = get_credit_warning(balance, plan_limit)
    if not w["show_warning"]:
        return None
    return {
        "credit_warning":    True,
        "warning_level":     w["level"],
        "warning_message":   w["message"],
        "credits_remaining": balance,
        "percentage":        w["percentage"],
    }


def assert_chat_allowed(balance: int, grace_used: int, plan: str) -> dict:
    """
    Hard check: is the user allowed to send ANY message right now?

    Returns {allowed: bool, state: str, reason: str | None}.
    This is the single source of truth for chat access — never bypass this.

    Guarantees:
      - credits > 0           → always allowed
      - credits = 0, grace < MAX → grace (allowed, counter will increment)
      - credits = 0, grace >= MAX → paused (not allowed)
      - admin/max plan         → always allowed regardless of credits
    """
    result = can_user_chat(balance, grace_used, plan)
    return {
        "allowed": result["allowed"],
        "state":   result["state"],
        "reason":  result["block_message"] if not result["allowed"] else None,
    }


def _paused_message() -> str:
    return (
        "Your credit balance has run out.\n\n"
        "Chat is free — it costs 0 credits per message. But the assistant needs an "
        "active credit balance to keep running. Credits power building, generating, "
        "image creation, web research, and advanced actions.\n\n"
        "When your balance hits 0, you get 3 grace messages before the assistant pauses. "
        "You've used them all.\n\n"
        "To continue:\n"
        "• Top up your credits\n"
        "• Or upgrade your plan\n\n"
        "Your work is saved and will be ready when you return."
    )
