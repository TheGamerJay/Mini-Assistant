"""
decision/tier_controller.py — Decide feature visibility and depth based on user tier.

Rules:
- free tier users see limited output depth and no paid-only modules
- paid tier users get full depth and all modules
- CEO decides tier visibility — modules do not gate themselves
- visibility is about DEPTH not experience; execution is always consistent

Tier visibility values:
  "paid"         — full access, no restrictions
  "free"         — full access to the module, default depth
  "free_limited" — module available but depth-constrained (see DEPTH_CONSTRAINTS)
  "blocked"      — module requires paid tier; CEO reroutes to core_chat

Depth constraints (for free_limited modules):
  web_intelligence:
    - max_results: 3          (paid: unlimited)
    - max_content_length: 500 (paid: unlimited)
    - sources_shown: False    (paid: True)

  builder:
    - backend_scaffold: False (paid: True — full backend file generation)
    - max_files: 2            (paid: unlimited)
    - max_lines_per_file: 80  (paid: unlimited)
    - template_only: True     (paid: False — can generate novel code)

  image:
    - watermark: True         (paid: False)
    - max_resolution: "512"   (paid: "1024")

These constraints are advisory — modules read them from tier_controller if needed.
CEO does not enforce them during execution; modules must apply them.
"""

from __future__ import annotations

from typing import Any

# Modules that require paid tier — blocked for free users
_PAID_ONLY_MODULES: set[str] = {"campaign_lab"}

# Modules with reduced output on free tier
_FREE_TIER_LIMITED: set[str] = {"web_intelligence", "builder", "image"}

# Depth constraints per module for free_limited tier
DEPTH_CONSTRAINTS: dict[str, dict[str, Any]] = {
    "web_intelligence": {
        "max_results":         3,
        "max_content_length":  500,
        "sources_shown":       False,
    },
    "builder": {
        "backend_scaffold":    False,
        "max_files":           2,
        "max_lines_per_file":  80,
        "template_only":       True,
    },
    "image": {
        "watermark":           True,
        "max_resolution":      "512",
    },
}

# Full (paid) depth — no restrictions
_PAID_DEPTH: dict[str, Any] = {}


def decide_tier_visibility(
    module:    str,
    user_tier: str,
) -> str:
    """
    Returns the effective visibility tier for a module + user_tier combination.

    Return values:
      "paid"         — no restrictions
      "free"         — allowed, standard depth
      "free_limited" — allowed, see DEPTH_CONSTRAINTS[module]
      "blocked"      — module requires paid tier; caller must reroute
    """
    if user_tier == "paid":
        return "paid"

    if module in _PAID_ONLY_MODULES:
        return "blocked"

    if module in _FREE_TIER_LIMITED:
        return "free_limited"

    return "free"


def get_depth_constraints(module: str, tier_visibility: str) -> dict[str, Any]:
    """
    Return the depth constraint dict for this module + tier combination.

    Returns an empty dict (no constraints) for paid or free tiers.
    Returns the DEPTH_CONSTRAINTS entry for free_limited.
    Callers may pass this into module execute() to apply limits.
    """
    if tier_visibility in ("paid", "free"):
        return _PAID_DEPTH

    return DEPTH_CONSTRAINTS.get(module, _PAID_DEPTH)
