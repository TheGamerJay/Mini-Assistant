"""
modules/vision.py — Vision module: image understanding, UI analysis, validation.

Analyzes image attachments — describes content, identifies issues, provides
recommendations. Used for UI review, image validation, and visual Q&A.

Output format:
  {
      "type":            "vision_output",
      "analysis":        str,      # grounded description of what is visible
      "issues":          [str],    # problems found (empty if none)
      "recommendations": [str],    # actionable suggestions (empty if none)
  }

Rules:
- must be grounded in visible data — no hallucinated elements
- analysis must describe what IS in the image, not what might be
- issues and recommendations must be specific
- if no attachment is provided, return error immediately — do not generate fake analysis
- modules NEVER call each other — Vision does not call Builder or Doctor
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

log = logging.getLogger("ceo_router.modules.vision")

_ANTHROPIC_MODEL = "claude-sonnet-4-6"


async def execute(
    decision:    dict[str, Any],
    memory:      dict[str, Any],
    web_results: dict[str, Any],
) -> dict[str, Any]:
    """
    Analyze image(s) in the decision attachments.
    Returns a structured vision_output dict.
    """
    message     = decision.get("message", "")
    attachments = decision.get("attachments", [])

    if not attachments:
        return _error("No image attachment provided — Vision requires an image to analyze.")

    # Build vision prompt
    image_content = _prepare_images(attachments)
    if not image_content:
        return _error("Attachment present but no valid image data could be extracted.")

    system_prompt = _build_system_prompt()
    user_content  = _build_user_content(message, image_content, memory)

    raw = await _call_llm(system_prompt, user_content)
    if raw is None:
        return _error("LLM call failed — no response returned")

    return _structure_output(raw)


# ---------------------------------------------------------------------------
# Image preparation
# ---------------------------------------------------------------------------

def _prepare_images(attachments: list) -> list[dict]:
    """
    Convert attachments to Anthropic vision content blocks.
    Supports base64 data URI strings or dicts with 'data'/'url' keys.
    """
    blocks = []
    for att in attachments[:4]:  # cap at 4 images
        block = _to_image_block(att)
        if block:
            blocks.append(block)
    return blocks


def _to_image_block(att: Any) -> dict | None:
    """Convert an attachment to an Anthropic image content block."""
    if isinstance(att, str):
        return _parse_data_uri(att)

    if isinstance(att, dict):
        # data URI format
        if att.get("data"):
            return _parse_data_uri(att["data"])
        # URL format
        if att.get("url"):
            return {
                "type": "image",
                "source": {"type": "url", "url": att["url"]},
            }
        # base64 raw with media_type
        if att.get("base64") and att.get("media_type"):
            return {
                "type": "image",
                "source": {
                    "type":       "base64",
                    "media_type": att["media_type"],
                    "data":       att["base64"],
                },
            }
    return None


def _parse_data_uri(data_uri: str) -> dict | None:
    """Parse a data:image/...;base64,... string into an Anthropic image block."""
    if not data_uri.startswith("data:"):
        return None
    try:
        header, b64data = data_uri.split(",", 1)
        media_type = header.split(";")[0].replace("data:", "")
        if not media_type.startswith("image/"):
            return None
        return {
            "type": "image",
            "source": {
                "type":       "base64",
                "media_type": media_type,
                "data":       b64data,
            },
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_system_prompt() -> str:
    return """You are a visual analysis expert. Analyze images accurately and honestly.

RULES:
1. Return ONLY valid JSON — no markdown wrapper, no extra text.
2. analysis must describe ONLY what is visibly present — no invented details.
3. issues must list specific, observable problems.
4. recommendations must be concrete and actionable.
5. If the image is clear and has no issues, issues may be an empty list.

OUTPUT SCHEMA:
{
  "type": "vision_output",
  "analysis": "<grounded description of what is visible>",
  "issues": ["<specific observable issue>", ...],
  "recommendations": ["<concrete actionable suggestion>", ...]
}"""


def _build_user_content(message: str, image_blocks: list[dict], memory: dict) -> list[dict]:
    """Build the multi-modal content list for the Anthropic API."""
    content: list[dict] = []

    # Add images first
    content.extend(image_blocks)

    # Add text prompt
    prompt = message.strip() or "Analyze this image. Describe what you see, identify any issues, and provide recommendations."

    context_hint = ""
    if memory.get("source_metadata"):
        context_hint = f"\nContext: {memory['source_metadata']}"

    content.append({
        "type": "text",
        "text": f"{prompt}{context_hint}\n\nReturn the vision_output JSON now.",
    })

    return content


# ---------------------------------------------------------------------------
# LLM call (multi-modal)
# ---------------------------------------------------------------------------

async def _call_llm(system_prompt: str, user_content: list[dict]) -> str | None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("vision: ANTHROPIC_API_KEY not set")
        return None
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model      = _ANTHROPIC_MODEL,
            max_tokens = 2048,
            system     = system_prompt,
            messages   = [{"role": "user", "content": user_content}],
        )
        return resp.content[0].text if resp.content else None
    except Exception as exc:
        log.error("vision: LLM call failed — %s", exc, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Output structuring
# ---------------------------------------------------------------------------

def _structure_output(raw: str) -> dict[str, Any]:
    import json

    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("vision: JSON parse failed — %s", exc)
        # Degrade gracefully — use raw text as analysis
        return {
            "type":            "vision_output",
            "analysis":        raw[:1000],
            "issues":          [],
            "recommendations": [],
            "status":          "parse_error",
        }

    data["type"] = "vision_output"
    data.setdefault("analysis", "")
    data.setdefault("issues", [])
    data.setdefault("recommendations", [])

    if not isinstance(data["issues"], list):
        data["issues"] = [str(data["issues"])]
    if not isinstance(data["recommendations"], list):
        data["recommendations"] = [str(data["recommendations"])]

    log.info(
        "vision: issues=%d recommendations=%d",
        len(data["issues"]), len(data["recommendations"]),
    )
    return data


def _error(reason: str) -> dict[str, Any]:
    return {
        "type":            "vision_output",
        "status":          "error",
        "error":           reason,
        "analysis":        "",
        "issues":          [reason],
        "recommendations": [],
    }
