"""
billing/key_router.py

Provider key routing layer for the hybrid BYOK + missing-provider fallback model.

Routing rule (in priority order):
  1. User's own verified key — decrypted from MongoDB on demand
  2. Platform fallback key — from env vars (ANTHROPIC_API_KEY / OPENAI_API_KEY)
  3. KeyUnavailableError — raised cleanly so callers can return a 402/block

Source values returned alongside the key:
  'user'     — decrypted from user's MongoDB document
  'platform' — platform-owned env var key (fallback, budget-tracked separately)

IMPORTANT:
  - Platform env keys are NEVER returned to the frontend
  - User keys are NEVER logged
  - All routing decisions are server-side only
"""

from __future__ import annotations

import logging
import os
from typing import Literal

log = logging.getLogger("key_router")

Provider = Literal["anthropic", "openai"]
KeySource = Literal["user", "platform"]


# ---------------------------------------------------------------------------
# Public error type
# ---------------------------------------------------------------------------

class KeyUnavailableError(Exception):
    """
    Raised when no key exists for a provider.
    Caller should treat this as a 402/block and show the appropriate UI.
    """
    def __init__(self, provider: Provider):
        self.provider = provider
        super().__init__(
            f"No {provider} key available — user has no verified key and the "
            f"platform fallback for {provider} is not configured."
        )


# ---------------------------------------------------------------------------
# Main routing entry point
# ---------------------------------------------------------------------------

async def get_provider_key(provider: Provider, user_doc: dict) -> tuple[str, KeySource]:
    """
    Select and return the best available key for a provider.

    Checks user key first. Falls back to platform key. Raises if neither available.

    Returns:
        (api_key, source) where source is 'user' or 'platform'

    Raises:
        KeyUnavailableError — if no key is available for this provider
    """
    # 1. User's own key (highest priority)
    user_key = await _get_user_key(provider, user_doc)
    if user_key:
        return user_key, "user"

    # 2. Platform fallback key
    platform_key = _get_platform_key(provider)
    if platform_key:
        log.debug(
            "key_router: using platform fallback provider=%s user=%s",
            provider, user_doc.get("id", "?"),
        )
        return platform_key, "platform"

    # 3. Nothing available — block cleanly
    raise KeyUnavailableError(provider)


# ---------------------------------------------------------------------------
# User key helpers
# ---------------------------------------------------------------------------

async def _get_user_key(provider: Provider, user_doc: dict) -> str | None:
    """
    Decrypt and return the user's stored key for a provider, or None.

    Checks new per-provider fields first, then backward-compat single-key field.
    Never raises — returns None on any decryption failure.
    """
    from api_key_manager import decrypt_key  # noqa: PLC0415

    enc_field      = f"api_key_{provider}_enc"
    verified_field = f"api_key_{provider}_verified"

    # New per-provider schema (primary path)
    if user_doc.get(verified_field) and user_doc.get(enc_field):
        try:
            return decrypt_key(user_doc[enc_field])
        except Exception:
            log.warning(
                "key_router: failed to decrypt %s key for user=%s",
                provider, user_doc.get("id", "?"),
            )
            return None

    # Backward compat: old single-key schema (written before per-provider support)
    if (
        user_doc.get("api_key_verified")
        and user_doc.get("api_key_provider") == provider
        and user_doc.get("api_key_enc")
    ):
        try:
            return decrypt_key(user_doc["api_key_enc"])
        except Exception:
            log.warning(
                "key_router: failed to decrypt legacy key for user=%s",
                user_doc.get("id", "?"),
            )
            return None

    return None


# ---------------------------------------------------------------------------
# Platform key helper
# ---------------------------------------------------------------------------

def _get_platform_key(provider: Provider) -> str | None:
    """Read platform fallback key from env. Returns None if not set."""
    if provider == "anthropic":
        return os.environ.get("ANTHROPIC_API_KEY") or None
    if provider == "openai":
        return os.environ.get("OPENAI_API_KEY") or None
    return None


def platform_key_available(provider: Provider) -> bool:
    """Returns True if a platform fallback key exists in env for this provider."""
    return bool(_get_platform_key(provider))


# ---------------------------------------------------------------------------
# Provider status helpers (no decryption, no I/O)
# ---------------------------------------------------------------------------

def get_user_providers(user_doc: dict) -> dict[str, bool]:
    """
    Return which providers the user has verified keys for.

    Checks new per-provider fields and backward-compat single-key field.
    Does NOT decrypt — read-only check on verified flags.

    Returns:
        {"anthropic": bool, "openai": bool}
    """
    has_anthropic = bool(
        user_doc.get("api_key_anthropic_verified")
        or (
            user_doc.get("api_key_verified")
            and user_doc.get("api_key_provider") == "anthropic"
        )
    )
    has_openai = bool(
        user_doc.get("api_key_openai_verified")
        or (
            user_doc.get("api_key_verified")
            and user_doc.get("api_key_provider") == "openai"
        )
    )
    return {"anthropic": has_anthropic, "openai": has_openai}


def needs_platform_fallback(provider: Provider, user_doc: dict) -> bool:
    """
    Returns True if the user lacks a verified key for this provider,
    meaning platform fallback would be required to serve that provider.
    """
    providers = get_user_providers(user_doc)
    return not providers.get(provider, False)
