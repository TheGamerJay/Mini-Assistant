"""
detection/complexity_detector.py — Detect request complexity.

Returns one of:
  simple      — single output, no persistence, no external state
  multi_step  — multiple outputs or transformations, possible memory/tool use
  full_system — requires backend + database + API + persistence

CRITICAL:
  If full_system is detected AND the request is underspecified,
  CEO must not guess a simple solution. It must ask the user to choose scope.
  is_underspecified is returned as a second value so the clarification engine
  can act on it.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Full-system signals — any match upgrades to full_system
# ---------------------------------------------------------------------------

_FULL_SYSTEM = re.compile(
    r"\b(global leaderboard|global score|global stat|global user|"
    r"login system|sign.?in system|sign.?up system|authentication|"
    r"auth system|oauth|jwt|session management|"
    r"database|sql|mongodb|postgres|mysql|firebase|supabase|sqlite|"
    r"save (to )?(database|db|server|cloud)|persist|"
    r"sync(ed)?( across)?|real.?time (update|sync|score|data)|"
    r"rest api|graphql api|backend api|api endpoint|"
    r"admin panel|admin dashboard|admin access|"
    r"user account|user profile|multi.?user|multi.?player|multiplayer|"
    r"payment|stripe|subscription)\b",
    re.IGNORECASE,
)

# Multi-step signals — upgrades simple → multi_step (unless already full_system)
_MULTI_STEP = re.compile(
    r"\b(and then|after that|next step|step by step|"
    r"multiple (pages|screens|components|features|sections)|"
    r"with (filtering|sorting|search|pagination)|"
    r"(chart|graph|table|form|modal|sidebar|navbar|dashboard) (and|with|plus)|"
    r"upload|download|export|import|file (upload|download)|"
    r"email (notification|alert|confirmation)|"
    r"dark mode|light mode|theme|responsive|mobile.?friendly)\b",
    re.IGNORECASE,
)

# Underspecified patterns — full_system request without enough detail
_UNDERSPECIFIED = re.compile(
    r"\b(something|anything|some kind of|a (simple|basic|quick)|"
    r"maybe|i think|could be|whatever works|just make it work|"
    r"idk|not sure what|you decide|surprise me)\b",
    re.IGNORECASE,
)


def detect_complexity(message: str) -> tuple[str, bool]:
    """
    Returns:
        (complexity, is_underspecified)

        complexity: "simple" | "multi_step" | "full_system"
        is_underspecified: True when full_system + missing key details
    """
    if _FULL_SYSTEM.search(message):
        underspecified = bool(_UNDERSPECIFIED.search(message))
        return "full_system", underspecified

    if _MULTI_STEP.search(message):
        return "multi_step", False

    return "simple", False
