"""
phase2/models.py — Centralized model config layer
──────────────────────────────────────────────────
All model names are read from environment variables so they can be
updated in Railway without a code redeploy.

Required env vars (set in Railway / .env):
  OPENAI_REASONING_MODEL   e.g. gpt-5.3 / o3 / gpt-4o
  OPENAI_FAST_MODEL        e.g. gpt-4o-mini / gpt-4.1-mini
  CLAUDE_SONNET_MODEL      e.g. claude-sonnet-4-6

If a var is missing the fallback strings below are used so the system
stays alive, but callers should always prefer explicit env config.
"""

from __future__ import annotations

import os

# ── Sensible fallbacks (update these when models change) ─────────────────────

_OPENAI_REASONING = os.getenv("OPENAI_REASONING_MODEL", "gpt-4o")
_OPENAI_FAST      = os.getenv("OPENAI_FAST_MODEL",      "gpt-4o-mini")
_CLAUDE_SONNET    = os.getenv("CLAUDE_SONNET_MODEL",    "claude-sonnet-4-6")

# ── Role → provider + model mapping ──────────────────────────────────────────

MODEL_CONFIG: dict[str, dict] = {
    "CEO": {
        "provider": "openai",
        "model":    _OPENAI_REASONING,
        "desc":     "Planner / Orchestrator — strongest reasoning",
    },
    "MANAGER": {
        "provider": "openai",
        "model":    _OPENAI_FAST,
        "desc":     "Task splitter — fast & balanced",
    },
    "WORKER": {
        "provider": "anthropic",
        "model":    _CLAUDE_SONNET,
        "desc":     "Code generator — Claude Sonnet",
    },
    "QA": {
        "provider": "openai",
        "model":    _OPENAI_REASONING,
        "desc":     "Reviewer — catches logic flaws",
    },
}


def get_model(role: str) -> dict:
    """Return the provider+model dict for a given role (case-insensitive)."""
    return MODEL_CONFIG.get(role.upper(), MODEL_CONFIG["WORKER"])
