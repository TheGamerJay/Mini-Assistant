"""
api_key_manager.py — Per-user API key encryption, storage helpers, and live test.

Security model:
  - Keys encrypted with AES-256-GCM before storage (authenticated encryption)
  - 12-byte random nonce prepended to ciphertext, whole thing base64-encoded
  - Raw key NEVER logged, NEVER returned to frontend after save
  - API_KEY_ENCRYPTION_SECRET: 32-byte secret held only in env (required)

Key verification:
  - test_key() makes a minimal provider call (1-token prompt)
  - Only after success is api_key_verified set to True in DB
  - Caller is responsible for DB update

Usage:
  from api_key_manager import encrypt_key, decrypt_key, make_hint, test_key
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Literal

log = logging.getLogger("api_key_manager")

# ---------------------------------------------------------------------------
# Encryption secret — validated at import time so startup guard catches it
# ---------------------------------------------------------------------------

_SECRET_B64 = os.environ.get("API_KEY_ENCRYPTION_SECRET", "")
if _SECRET_B64:
    try:
        _KEY_BYTES = base64.b64decode(_SECRET_B64)
        if len(_KEY_BYTES) != 32:
            raise ValueError(f"Expected 32 bytes, got {len(_KEY_BYTES)}")
    except Exception as _e:
        raise RuntimeError(
            f"API_KEY_ENCRYPTION_SECRET is set but invalid: {_e}. "
            "Generate with: python -c \"import os,base64; print(base64.b64encode(os.urandom(32)).decode())\""
        ) from _e
else:
    _KEY_BYTES = b""  # Will be caught by server.py startup validation


# ---------------------------------------------------------------------------
# AES-256-GCM encrypt / decrypt
# ---------------------------------------------------------------------------

def encrypt_key(raw_key: str) -> str:
    """
    Encrypt a raw API key string.
    Returns base64(nonce + ciphertext_with_tag).
    Never logs the raw key.
    """
    if not _KEY_BYTES:
        raise RuntimeError("API_KEY_ENCRYPTION_SECRET not configured")

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    aes = AESGCM(_KEY_BYTES)
    ct = aes.encrypt(nonce, raw_key.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_key(enc: str) -> str:
    """
    Decrypt a stored encrypted key.
    Raises ValueError on tampering / wrong secret.
    Never logs the result.
    """
    if not _KEY_BYTES:
        raise RuntimeError("API_KEY_ENCRYPTION_SECRET not configured")

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = base64.b64decode(enc)
    nonce, ct = raw[:12], raw[12:]
    aes = AESGCM(_KEY_BYTES)
    return aes.decrypt(nonce, ct, None).decode("utf-8")


def make_hint(raw_key: str) -> str:
    """
    Return a masked display string: 'sk-ant-••••••••' + last 4 chars.
    Safe to store and return to frontend.
    """
    if not raw_key:
        return ""
    suffix = raw_key[-4:] if len(raw_key) >= 4 else raw_key
    if raw_key.startswith("sk-ant-"):
        prefix = "sk-ant-"
    elif raw_key.startswith("sk-"):
        prefix = "sk-"
    else:
        prefix = raw_key[:4] + "-" if len(raw_key) >= 4 else ""
    return f"{prefix}{'•' * 8}{suffix}"


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

Provider = Literal["anthropic", "openai", "unknown"]

def detect_provider(raw_key: str) -> Provider:
    """Infer provider from key format."""
    if raw_key.startswith("sk-ant-"):
        return "anthropic"
    if raw_key.startswith("sk-") and not raw_key.startswith("sk-ant-"):
        return "openai"
    return "unknown"


def validate_key_format(raw_key: str) -> tuple[bool, str]:
    """
    Fast format-only check before hitting the network.
    Returns (ok, error_message).
    """
    raw_key = raw_key.strip()
    if not raw_key:
        return False, "API key cannot be empty."
    if len(raw_key) < 20:
        return False, "Key is too short to be valid."
    provider = detect_provider(raw_key)
    if provider == "unknown":
        return False, "Key format not recognised. Anthropic keys start with sk-ant-, OpenAI keys start with sk-."
    return True, ""


# ---------------------------------------------------------------------------
# Live key test — minimal provider call
# ---------------------------------------------------------------------------

async def test_key(raw_key: str) -> tuple[bool, str]:
    """
    Make a minimal API call to verify the key is live and has valid permissions.
    Returns (success: bool, error_message: str).

    Costs:
      Anthropic haiku: ~$0.00025 per call (1-token prompt)
      OpenAI gpt-4o-mini: ~$0.00015 per call
    Never logs the raw key.
    """
    raw_key = raw_key.strip()
    ok, err = validate_key_format(raw_key)
    if not ok:
        return False, err

    provider = detect_provider(raw_key)

    if provider == "anthropic":
        return await _test_anthropic(raw_key)
    if provider == "openai":
        return await _test_openai(raw_key)
    return False, "Unknown provider — cannot test this key."


async def _test_anthropic(raw_key: str) -> tuple[bool, str]:
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=raw_key)
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        # Any response (even a 1-token reply) means the key is valid
        _ = msg
        return True, ""
    except Exception as e:
        err = str(e)
        log.info("api_key_manager: anthropic test failed (key not logged): %s", _sanitise_error(err))
        if "401" in err or "authentication" in err.lower() or "invalid" in err.lower():
            return False, "This key is not valid — check it and try again."
        if "403" in err or "permission" in err.lower():
            return False, "Key is valid but lacks required permissions."
        return False, "Could not verify key — network error. Try again."


async def _test_openai(raw_key: str) -> tuple[bool, str]:
    try:
        import openai
        client = openai.AsyncOpenAI(api_key=raw_key)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        _ = resp
        return True, ""
    except Exception as e:
        err = str(e)
        log.info("api_key_manager: openai test failed (key not logged): %s", _sanitise_error(err))
        if "401" in err or "Incorrect API key" in err or "invalid_api_key" in err:
            return False, "This key is not valid — check it and try again."
        if "403" in err or "permission" in err.lower():
            return False, "Key is valid but lacks required permissions."
        return False, "Could not verify key — network error. Try again."


def _sanitise_error(err: str) -> str:
    """Remove anything that looks like a key fragment from error strings."""
    import re
    return re.sub(r"sk-[a-zA-Z0-9\-_]{6,}", "sk-[REDACTED]", err)
