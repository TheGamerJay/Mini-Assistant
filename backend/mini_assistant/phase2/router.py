"""
phase2/router.py — Unified multi-model async router
─────────────────────────────────────────────────────
Single entry point for all LLM calls across the agent hierarchy.
Routes to OpenAI or Anthropic based on role config, with automatic
cross-provider fallback if the primary call fails.

Usage:
    from mini_assistant.phase2.router import call_model

    reply = await call_model("WORKER", prompt, context="You are a coder.")
    reply = await call_model("QA",     review_prompt)

Logging per call:
    role | provider | model | time_ms | status
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── OpenAI call ───────────────────────────────────────────────────────────────

async def _call_openai(model: str, prompt: str, context: Optional[str]) -> str:
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise RuntimeError("openai package not installed") from exc

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    client = AsyncOpenAI(api_key=api_key)
    messages = []
    if context:
        messages.append({"role": "system", "content": context})
    messages.append({"role": "user", "content": prompt})

    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=4096,
    )
    return (resp.choices[0].message.content or "").strip()


# ── Anthropic call ────────────────────────────────────────────────────────────

async def _call_claude(model: str, prompt: str, context: Optional[str]) -> str:
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("anthropic package not installed") from exc

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    system = context or "You are a helpful AI assistant."

    resp = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return (resp.content[0].text if resp.content else "").strip()


# ── Public router ─────────────────────────────────────────────────────────────

async def call_model(
    role: str,
    prompt: str,
    context: Optional[str] = None,
) -> str:
    """
    Route a prompt to the correct model for the given agent role.

    Fallback chain:
      OpenAI fails  → try Claude WORKER model
      Claude fails  → try OpenAI FAST model
      Both fail     → raise RuntimeError

    Args:
        role:    Agent role — CEO | MANAGER | WORKER | QA (case-insensitive)
        prompt:  User / task prompt
        context: Optional system prompt / context string

    Returns:
        Model reply as a plain string.
    """
    from .models import MODEL_CONFIG

    cfg      = MODEL_CONFIG.get(role.upper(), MODEL_CONFIG["WORKER"])
    provider = cfg["provider"]
    model    = cfg["model"]
    t0       = time.perf_counter()

    # ── Primary call ──────────────────────────────────────────────────────────
    try:
        if provider == "openai":
            result = await _call_openai(model, prompt, context)
        else:
            result = await _call_claude(model, prompt, context)

        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        logger.info(
            "call_model OK  | role=%-8s provider=%-10s model=%-24s time=%7.1f ms",
            role, provider, model, elapsed,
        )
        return result

    except Exception as primary_exc:
        logger.warning(
            "call_model FAIL | role=%s provider=%s model=%s — %s  → trying fallback",
            role, provider, model, primary_exc,
        )

    # ── Fallback call ─────────────────────────────────────────────────────────
    try:
        if provider == "openai":
            # OpenAI failed → try Claude Sonnet
            fb_model = MODEL_CONFIG["WORKER"]["model"]
            result = await _call_claude(fb_model, prompt, context)
            fb_provider = "anthropic"
        else:
            # Claude failed → try OpenAI fast model
            fb_model = MODEL_CONFIG["MANAGER"]["model"]
            result = await _call_openai(fb_model, prompt, context)
            fb_provider = "openai"

        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        logger.info(
            "call_model FALLBACK OK | role=%s fallback_provider=%s model=%s time=%.1f ms",
            role, fb_provider, fb_model, elapsed,
        )
        return result

    except Exception as fallback_exc:
        logger.error(
            "call_model FALLBACK FAIL | role=%s — %s",
            role, fallback_exc,
        )
        raise RuntimeError(
            f"Both primary and fallback models failed for role {role}: {fallback_exc}"
        ) from fallback_exc
