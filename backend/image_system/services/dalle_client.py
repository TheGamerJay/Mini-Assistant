"""
image_system/services/dalle_client.py
──────────────────────────────────────
DALL-E 3 image generation client (OpenAI API).

Replaces the ComfyUI pipeline with a simple, hosted API call.
Built-in safety filtering, no local GPU required.

Usage:
    client = DalleClient()
    b64 = await client.generate("a red panda coding in space", quality="high")
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Literal

logger = logging.getLogger(__name__)

# DALL-E 3 valid sizes
VALID_SIZES = {"1024x1024", "1024x1792", "1792x1024"}
DEFAULT_SIZE = "1024x1024"


class DalleClient:
    """Async wrapper around the OpenAI images.generate endpoint."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise RuntimeError("openai package not installed") from exc

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY environment variable is not set. "
                    "Add it to your Railway / .env config."
                )
            self._client = AsyncOpenAI(api_key=api_key)
        return self._client

    async def generate(
        self,
        prompt: str,
        quality: str = "balanced",
        size: str = DEFAULT_SIZE,
    ) -> str:
        """
        Generate one image via DALL-E 3 and return it as a base64 string.

        quality mapping:
            fast / balanced → "standard"   (cheaper, ~$0.04/image)
            high            → "hd"         (sharper details, ~$0.08/image)
        """
        if size not in VALID_SIZES:
            size = DEFAULT_SIZE

        # DALL-E 3 hard API limit is 4000 chars — truncate at word boundary
        _PROMPT_MAX = 4000
        if len(prompt) > _PROMPT_MAX:
            prompt = prompt[:_PROMPT_MAX].rsplit(" ", 1)[0]
            logger.warning("Prompt truncated to %d chars for DALL-E 3", _PROMPT_MAX)

        dalle_quality: Literal["standard", "hd"] = (
            "hd" if quality == "high" else "standard"
        )

        client = self._get_client()
        logger.info(
            "DALL-E 3 generate: quality=%s dalle_quality=%s size=%s prompt=%.80s",
            quality, dalle_quality, size, prompt,
        )

        response = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,  # type: ignore[arg-type]
            quality=dalle_quality,
            n=1,
            response_format="b64_json",
        )

        b64 = response.data[0].b64_json
        if not b64:
            raise RuntimeError("DALL-E 3 returned an empty image response")

        logger.info("DALL-E 3 generation complete (%d bytes b64)", len(b64))
        return b64

    async def health(self) -> dict:
        """Quick health check — verifies the API key is set and the client initialises."""
        try:
            self._get_client()
            return {"status": "ok", "provider": "dall-e-3"}
        except RuntimeError as exc:
            return {"status": "error", "provider": "dall-e-3", "detail": str(exc)}
