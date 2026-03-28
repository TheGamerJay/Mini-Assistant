"""
image_gen.py – Image Generation Tool
──────────────────────────────────────
Uses OpenAI DALL-E 3 for image generation.
Returns a dict with base64 image data and metadata.
"""

import base64
import logging
import os
from typing import Optional

import openai

logger = logging.getLogger(__name__)


# ─── DALL-E 3 ────────────────────────────────────────────────────────────────

def _dalle_generate(prompt: str, width: int = 1024, height: int = 1024) -> dict:
    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    resp = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        n=1,
        size=f"{width}x{height}",
        response_format="b64_json",
    )
    b64 = resp.data[0].b64_json
    return {"success": True, "image_b64": b64, "backend": "dalle3", "prompt": prompt}


# ─── Public function ──────────────────────────────────────────────────────────

def generate_image(
    prompt: str,
    negative_prompt: str = "ugly, blurry, low quality, watermark, text",
    width: int = 1024,
    height: int = 1024,
    steps: int = 20,
    cfg_scale: float = 7.0,
    backend: Optional[str] = None,
) -> dict:
    """
    Generate an image from a text prompt using DALL-E 3.

    Returns:
        dict with keys: success, image_b64, backend, prompt, (error if failed)
    """
    logger.info("Image generation: backend=dalle3 prompt=%r", prompt[:80])

    try:
        return _dalle_generate(prompt, width, height)
    except openai.OpenAIError as exc:
        logger.error("DALL-E generation failed: %s", exc)
        return {
            "success": False,
            "error":   str(exc),
            "backend": "dalle3",
            "prompt":  prompt,
        }
    except Exception as exc:
        logger.error("Image generation failed: %s", exc)
        return {"success": False, "error": str(exc), "backend": "dalle3", "prompt": prompt}
