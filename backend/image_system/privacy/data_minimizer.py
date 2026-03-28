"""
Data Minimizer — privacy policy gate.

Every persistence call MUST pass through `should_collect(tier, mode)` before
writing data.  The decision is based solely on:
  1. The user's ai_data_usage_mode setting  ("private" | "improve_system")
  2. The data tier being collected

Tiers
-----
  A  — always-on metadata  (session_id, timestamps, mode, turn count)
       Collected in BOTH modes — essential for basic operation
  B  — structured summaries (intent_type, success, cost, failure class)
       Only collected when mode == "improve_system"
  C  — retention-limited content (prompt text, partial outputs)
       Only in "improve_system"; TTL enforced by retention_manager
  D  — opt-in raw content (full prompts, full outputs, images)
       Never collected automatically — requires explicit per-session consent

Usage
-----
    from backend.image_system.privacy.data_minimizer import should_collect, DataTier

    if should_collect(DataTier.B, user_mode):
        pipeline.record_intent_summary(...)
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class DataTier(str, Enum):
    A = "A"   # always-on metadata
    B = "B"   # structured summaries (improve_system only)
    C = "C"   # retention-limited content (improve_system + TTL)
    D = "D"   # opt-in raw content (never automatic)


class UsageMode(str, Enum):
    PRIVATE        = "private"
    IMPROVE_SYSTEM = "improve_system"


# ---------------------------------------------------------------------------
# Policy table
# ---------------------------------------------------------------------------
#
#  tier → set of modes where collection is allowed
#
_ALLOWED: dict[DataTier, set[UsageMode]] = {
    DataTier.A: {UsageMode.PRIVATE, UsageMode.IMPROVE_SYSTEM},
    DataTier.B: {UsageMode.IMPROVE_SYSTEM},
    DataTier.C: {UsageMode.IMPROVE_SYSTEM},
    DataTier.D: set(),   # never collected automatically
}


def should_collect(tier: DataTier, mode: Optional[str]) -> bool:
    """
    Return True if data of `tier` may be persisted under `mode`.

    Args:
        tier:  The DataTier of the data being collected.
        mode:  The user's ai_data_usage_mode string.
               Defaults to "private" when None or unrecognised.

    Returns:
        bool — True = safe to persist, False = must drop.
    """
    try:
        usage_mode = UsageMode(mode or "private")
    except ValueError:
        usage_mode = UsageMode.PRIVATE   # unknown value → most restrictive

    return usage_mode in _ALLOWED.get(tier, set())


def resolve_mode(raw: Optional[str]) -> UsageMode:
    """Normalise a raw string to a UsageMode, defaulting to PRIVATE."""
    try:
        return UsageMode(raw or "private")
    except ValueError:
        return UsageMode.PRIVATE
