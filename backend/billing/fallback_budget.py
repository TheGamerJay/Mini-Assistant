"""
billing/fallback_budget.py

Per-user fallback budget tracking for the hybrid BYOK + missing-provider model.

Business rules:
  - $9.00 included fallback budget per missing provider per 30-day rolling cycle
  - Usable budget = budget × SAFETY_FACTOR (10% buffer against overspend)
  - Rolling window: first use starts the clock; resets 30 days after start
  - All timestamps are server-side Unix time — client time is never trusted

Wave 1 scope (this file):
  - Schema constants + default field values for new user documents
  - Status queries: remaining, pct, reset date
  - Reset detection + patch generation (caller writes to DB)
  - Helper to check whether a provider needs fallback

Wave 2 (Phase 5) will add:
  - Pre-request cost estimation + hard cap enforcement
  - Post-request actual-cost deduction
  - Per-request max-cost limit + rate limiting
"""

from __future__ import annotations

import logging
import time
from typing import Literal

log = logging.getLogger("fallback_budget")

Provider = Literal["anthropic", "openai"]

# ── Constants ──────────────────────────────────────────────────────────────────

FALLBACK_BUDGET_USD = 9.00          # included budget per provider per cycle (USD)
SAFETY_FACTOR       = 0.90          # usable = budget × factor (10% buffer)
ROLLOVER_SECONDS    = 30 * 86_400   # 30-day rolling window


# ── Schema defaults ───────────────────────────────────────────────────────────

def default_fallback_fields() -> dict:
    """
    Return all fallback budget fields for embedding in a new user document.
    Called when creating a user via email/Google registration.

    All budgets start at the configured amount; usage starts at zero.
    Reset timestamps are None — first use initialises the rolling window.
    """
    return {
        "fallback_budget_anthropic":     FALLBACK_BUDGET_USD,
        "fallback_budget_openai":        FALLBACK_BUDGET_USD,
        "fallback_used_anthropic":       0.0,
        "fallback_used_openai":          0.0,
        "fallback_started_at_anthropic": None,
        "fallback_started_at_openai":    None,
        "fallback_reset_at_anthropic":   None,
        "fallback_reset_at_openai":      None,
    }


# ── Status query ──────────────────────────────────────────────────────────────

def get_fallback_status(user_doc: dict, provider: Provider) -> dict:
    """
    Return the current fallback status for a provider.

    Handles rolling 30-day reset detection but does NOT write to DB.
    If _reset_occurred is True in the returned dict, call get_reset_patch()
    to get the MongoDB $set update to apply.

    Returns:
        budget          — configured total budget (USD)
        used            — amount used this cycle (USD)
        usable          — budget × SAFETY_FACTOR
        remaining       — max(0, usable − used)
        pct_remaining   — 0–100 integer
        started_at      — unix timestamp when cycle started (None if never used)
        reset_at        — unix timestamp when cycle resets (None if never used)
        is_exhausted    — True when remaining <= 0
        _reset_occurred — True if the DB needs a reset update (call get_reset_patch)
    """
    now        = time.time()
    budget     = float(user_doc.get(f"fallback_budget_{provider}", FALLBACK_BUDGET_USD))
    used       = float(user_doc.get(f"fallback_used_{provider}", 0.0))
    started_at = user_doc.get(f"fallback_started_at_{provider}")
    reset_at   = user_doc.get(f"fallback_reset_at_{provider}")

    reset_occurred = bool(reset_at and now > reset_at)
    if reset_occurred:
        used       = 0.0
        started_at = now
        reset_at   = now + ROLLOVER_SECONDS

    usable    = budget * SAFETY_FACTOR
    remaining = max(0.0, usable - used)

    return {
        "budget":          budget,
        "used":            round(used, 6),
        "usable":          round(usable, 6),
        "remaining":       round(remaining, 6),
        "pct_remaining":   int((remaining / usable * 100) if usable > 0 else 0),
        "started_at":      started_at,
        "reset_at":        reset_at,
        "is_exhausted":    remaining <= 0.0,
        "_reset_occurred": reset_occurred,
    }


def get_reset_patch(provider: Provider, status: dict) -> dict | None:
    """
    If get_fallback_status() returned _reset_occurred=True, return the
    MongoDB $set dict to apply the reset. Returns None if no reset needed.

    Usage:
        status = get_fallback_status(user, provider)
        patch  = get_reset_patch(provider, status)
        if patch:
            await db["users"].update_one({"id": user["id"]}, {"$set": patch})
    """
    if not status.get("_reset_occurred"):
        return None
    return {
        f"fallback_used_{provider}":         0.0,
        f"fallback_started_at_{provider}":   status["started_at"],
        f"fallback_reset_at_{provider}":     status["reset_at"],
    }


# ── Convenience helpers ───────────────────────────────────────────────────────

def needs_fallback(provider: Provider, user_doc: dict) -> bool:
    """
    Returns True if the user is missing a verified key for this provider
    and would need platform fallback to use provider-specific features.
    """
    from billing.key_router import get_user_providers  # noqa: PLC0415
    providers = get_user_providers(user_doc)
    return not providers.get(provider, False)
