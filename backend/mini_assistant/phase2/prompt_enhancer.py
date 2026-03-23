"""
phase2/prompt_enhancer.py — AI-powered prompt enhancement
───────────────────────────────────────────────────────────
Uses the CEO model (GPT-5.4) to rewrite user prompts into richer,
more precise instructions before they hit the image or code pipeline.

All functions fail silently — if the CEO model is unavailable or slow,
the original user prompt is returned unchanged so nothing breaks.

Functions:
  analyze_edit_request(user_msg)      → structured edit plan (color vs structural)
  enhance_image_prompt(user_msg)      → enriched DALL-E generation prompt
  enhance_edit_instruction(user_msg)  → precise pixel-level edit instruction
  enhance_reference_prompt(desc, msg) → fused reference + request prompt
  enhance_code_context(user_msg, intent) → enriched system context for coding
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# ── Only enhance if an OpenAI key + reasoning model are configured ────────────

def _enhancer_available() -> bool:
    return bool(
        os.getenv("OPENAI_API_KEY") and
        os.getenv("OPENAI_REASONING_MODEL")
    )


# ── Edit request analyzer (routes to PIL vs AI inpainting) ───────────────────

_EDIT_ANALYZER_SYSTEM = """\
You are an image-editing assistant that chooses the correct editing method based on the user's request.

RULE 1 — COLOR-BASED EDITS (hair color, eye color, skin color, fur color, shirt color, shoe color):
- Do NOT use AI inpainting.
- Use the PIL color-replacement pipeline.
- Identify the exact source color name and target color name.
- Output edit_type: "color_change"

RULE 2 — STRUCTURAL EDITS (remove object, add object, change background, add/remove accessories, change pose, add hat, change clothing pattern or style):
- Use vision analysis to locate the object or region.
- Produce a tight bounding box description (top/left/width/height as % of image).
- Pass the original image + mask + instruction to the AI inpainting model.
- The final_instruction MUST end with: "Show the full character head-to-toe, do not crop or zoom in, preserve the original framing exactly."
- Output edit_type: "structural_edit"

RULE 3 — DECISION LOGIC:
- If the edit is purely about changing a COLOR → RULE 1
- If the edit changes shape, structure, or adds/removes elements → RULE 2
- If ambiguous, prefer RULE 1 for any request mentioning a color word

OUTPUT: Return ONLY valid JSON, no explanation, no markdown.

For color_change:
{
  "edit_type": "color_change",
  "region_description": "<what body part/area>",
  "from_color": "<exact color name to replace>",
  "to_color": "<exact color name to apply>",
  "confidence": 0.0-1.0
}

For structural_edit:
{
  "edit_type": "structural_edit",
  "region_description": "<what object/area>",
  "mask_box": {"top": 0-100, "left": 0-100, "width": 0-100, "height": 0-100},
  "final_instruction": "<precise instruction for gpt-image-1>",
  "confidence": 0.0-1.0
}
"""

_EDIT_ANALYZER_USER = "User edit request: {msg}\n\nAnalyze and output the edit plan as JSON."


async def analyze_edit_request(user_msg: str) -> dict | None:
    """
    Use GPT-5.4 to classify the edit request and return a structured routing plan.

    Returns a dict with edit_type + routing data, or None if unavailable/failed.

    color_change → PIL hue rotation (pixel-perfect, no AI)
    structural_edit → vision mask + gpt-image-1 inpainting

    Never raises — returns None on any failure so caller falls back to old path.
    """
    if not _enhancer_available():
        return None

    import json as _json
    from .router import call_model

    try:
        raw = await call_model(
            "CEO",
            _EDIT_ANALYZER_USER.format(msg=user_msg),
            context=_EDIT_ANALYZER_SYSTEM,
        )
        # Strip markdown code fences if model added them
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        plan = _json.loads(raw.strip())
        logger.info(
            "analyze_edit_request | type=%s confidence=%.2f region=%s",
            plan.get("edit_type"), plan.get("confidence", 0), plan.get("region_description", "")[:50],
        )
        return plan
    except Exception as exc:
        logger.warning("analyze_edit_request failed (non-fatal): %s", exc)
        return None


# ── Image generation prompt enhancer ─────────────────────────────────────────

_IMAGE_GEN_SYSTEM = (
    "You are an expert AI image prompt engineer. "
    "Your job is to expand a short user request into a rich, detailed image generation prompt. "
    "Add: art style, lighting, color palette, composition, quality modifiers. "
    "Preserve the user's exact subject and intent — only enrich the visual detail. "
    "Return ONLY the enhanced prompt. No explanations, no labels, no quotes."
)

_IMAGE_GEN_USER = """\
User request: {msg}

Write an enhanced image generation prompt for this request."""


async def enhance_image_prompt(user_msg: str) -> str:
    """
    Expand a short user image request into a rich DALL-E prompt.

    Returns the enhanced prompt, or the original if enhancement fails.
    """
    if not _enhancer_available():
        return user_msg

    from .router import call_model
    try:
        enhanced = await call_model(
            "CEO",
            _IMAGE_GEN_USER.format(msg=user_msg),
            context=_IMAGE_GEN_SYSTEM,
        )
        if enhanced and len(enhanced) > len(user_msg):
            logger.info(
                "enhance_image_prompt | %d → %d chars",
                len(user_msg), len(enhanced),
            )
            return enhanced.strip()
    except Exception as exc:
        logger.warning("enhance_image_prompt failed (using original): %s", exc)
    return user_msg


# ── Image edit instruction enhancer ──────────────────────────────────────────

_EDIT_SYSTEM = (
    "You are an expert at writing precise image editing instructions for AI image models. "
    "Convert the user's vague or casual edit request into an unambiguous, specific instruction. "
    "Be explicit about WHAT to change and WHAT to keep. "
    "Return ONLY the instruction. No explanations, no labels, no quotes."
)

_EDIT_USER = """\
User edit request: {msg}

Write a precise, unambiguous editing instruction that:
1. Clearly states what specific visual element to change and how
2. Explicitly lists what must NOT change (face, hair, clothing, pose, etc. unless requested)
3. Is direct and specific — no ambiguity

Return only the instruction."""


async def enhance_edit_instruction(user_msg: str) -> str:
    """
    Convert a vague edit request into a precise pixel-level instruction.

    Example:
      "make him purple" →
      "Change the character's fur and skin color from blue to purple throughout
       the entire body. Do not change the hair color, eye color, clothing, shoes,
       accessories, facial expression, pose, or background."

    Returns the enhanced instruction, or the original if enhancement fails.
    """
    if not _enhancer_available():
        return user_msg

    from .router import call_model
    try:
        enhanced = await call_model(
            "CEO",
            _EDIT_USER.format(msg=user_msg),
            context=_EDIT_SYSTEM,
        )
        if enhanced:
            logger.info(
                "enhance_edit_instruction | %d → %d chars",
                len(user_msg), len(enhanced),
            )
            return enhanced.strip()
    except Exception as exc:
        logger.warning("enhance_edit_instruction failed (using original): %s", exc)
    return user_msg


# ── Image reference-generate prompt enhancer ─────────────────────────────────

_REF_GEN_SYSTEM = (
    "You are an expert AI image prompt engineer specializing in style-faithful generation. "
    "Given a visual description of a reference image and a user request, write the optimal "
    "DALL-E 3 generation prompt that: "
    "(1) faithfully preserves the art style, color palette, and character design of the reference, "
    "(2) fulfills the user's specific request, "
    "(3) includes rich visual detail — lighting, composition, quality modifiers. "
    "Return ONLY the final generation prompt. No explanations, no labels, no quotes."
)

_REF_GEN_USER = """\
Reference image visual description:
{description}

User request: {msg}

Write the optimal image generation prompt."""


async def enhance_reference_prompt(description: str, user_msg: str) -> str:
    """
    Use GPT-5.4 to fuse the vision description + user request into the
    best possible DALL-E 3 prompt for reference-based generation.

    Returns the enhanced prompt, or the raw combined fallback if enhancement fails.
    """
    if not _enhancer_available():
        return (
            f"Reference image description: {description}\n\n"
            f"User request: {user_msg}\n\n"
            "Generate a new image that fulfills the user request, visually inspired "
            "by the reference. Preserve the art style, color palette, and character "
            "design from the reference while applying the requested changes."
        )

    from .router import call_model
    try:
        enhanced = await call_model(
            "CEO",
            _REF_GEN_USER.format(description=description[:2000], msg=user_msg),
            context=_REF_GEN_SYSTEM,
        )
        if enhanced:
            logger.info(
                "enhance_reference_prompt | description=%d chars → prompt=%d chars",
                len(description), len(enhanced),
            )
            return enhanced.strip()
    except Exception as exc:
        logger.warning("enhance_reference_prompt failed (using fallback): %s", exc)

    return (
        f"Reference image description: {description}\n\n"
        f"User request: {user_msg}\n\n"
        "Generate a new image that fulfills the user request, visually inspired "
        "by the reference. Preserve the art style, color palette, and character "
        "design from the reference while applying the requested changes."
    )


# ── Code / chat context enhancer ─────────────────────────────────────────────

_CODE_SYSTEM = (
    "You are a senior software architect. "
    "Given a user's coding or building request, write a focused system context "
    "that will help a code-generation model produce the best possible output. "
    "Include: what to build, constraints, expected output format, quality standards. "
    "Return ONLY the context string. No explanations."
)

_CODE_USER = """\
User request: {msg}
Intent: {intent}

Write a focused system context for a code generation model handling this request."""


async def enhance_code_context(user_msg: str, intent: str) -> str | None:
    """
    Generate an enriched system context for coding/builder requests.

    Returns the context string, or None if enhancement is unavailable/fails.
    Only runs for complex intents (coding, debugging, app_builder, planning).
    """
    _eligible = {"coding", "debugging", "app_builder", "planning", "architect"}
    if intent not in _eligible:
        return None
    if not _enhancer_available():
        return None

    from .router import call_model
    try:
        ctx = await call_model(
            "CEO",
            _CODE_USER.format(msg=user_msg, intent=intent),
            context=_CODE_SYSTEM,
        )
        if ctx:
            logger.info("enhance_code_context | intent=%s chars=%d", intent, len(ctx))
            return ctx.strip()
    except Exception as exc:
        logger.warning("enhance_code_context failed (non-fatal): %s", exc)
    return None
