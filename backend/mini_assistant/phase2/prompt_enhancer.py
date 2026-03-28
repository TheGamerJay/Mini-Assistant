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

# ── Available if any AI API key is configured (OpenAI or Anthropic) ──────────

def _enhancer_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))


# ── Edit request analyzer (routes to PIL vs AI inpainting) ───────────────────

_EDIT_ANALYZER_SYSTEM = """\
You are an image-editing assistant that breaks user requests into ordered edit steps.

RULE 1 — SAFE COLOR-BASED EDITS (hair color, eye color, shirt color, shoe color, jacket color, pants color):
- Only use when the target region is clearly a SINGLE isolated color not shared by skin/fur.
- Do NOT use AI inpainting.
- Use the PIL color-replacement pipeline.
- Identify the exact source color name and target color name.
- edit_type: "color_change"

RULE 2 — STRUCTURAL EDITS — use for ALL of the following:
  • Skin color, fur color, body color (PIL cannot isolate skin from clothing with the same color)
  • Remove object, add object, change background, add/remove accessories
  • Change pose, add hat, change clothing pattern or style, change hairstyle
- Use vision analysis to locate the object or region.
- Produce a tight bounding box (top/left/width/height as % of image).
- The final_instruction MUST end with: "Show the full character head-to-toe, do not crop or zoom in, preserve the original framing exactly."
- edit_type: "structural_edit"

RULE 3 — DECISION LOGIC:
- Skin color / fur color — DEFAULT → RULE 2 (structural_edit)
  EXCEPTION → RULE 1 (color_change) when the user EXPLICITLY says to change ONLY the skin/fur AND
  specifies that other same-colored elements (hair, clothing, background) must NOT change.
  Trigger phrases: "only the skin", "just the skin", "not the hair", "not the rest", "only his/her/its skin",
  "keep everything else", "skin color only", "body color only (not the hair)", etc.
  When this exception fires:
    • edit_type: "color_change"
    • preserve_regions: list every same-colored element the user said NOT to change
    • mask_box: top=15, left=10, width=80, height=75  ← excludes hair at top; covers face + body
    • primary_tier: "region_pil"
    • color_overlap_risk: true
    • allow_reconstruction_fallback: false
- Isolated clothing/accessory color where that color is unique to that item → RULE 1
- Shape/structure/add/remove → RULE 2
- If ambiguous → RULE 2

RULE 4 — MULTI-STEP:
- If the user requests MORE THAN ONE distinct change, split them into separate steps.
- Order: color changes first, then structural changes.
- Each step is one focused edit.

RULE 5 — PRIMARY TIER ROUTING:
Assign primary_tier to each step using this routing table:
- hair color → "semantic"    (gpt-image-1 with explicit region isolation)
- eye color  → "semantic"
- eyebrow color → "semantic"
- skin/fur/body/complexion/tone color → "semantic"  (gpt-image-1 with pre-flight scan to name preserve elements)
- clothing/accessory color → "semantic"  (gpt-image-1 understands clothing semantics)
- unknown/ambiguous color region → "semantic"

NOTE: skin/fur is always "semantic" — the pipeline does a pre-flight GPT-4o vision scan to identify
every element sharing the from_color, then explicitly names them in the gpt-image-1 prompt as
elements to preserve. This prevents "change all blue" behavior.

RULE 6 — COLOR OVERLAP RISK:
Set color_overlap_risk: true when the from_color is likely shared between skin/fur AND clothing
(e.g. character has blue skin AND is wearing blue clothing — replacing "blue" globally would
affect both). If the from_color appears only on a clearly isolated region, set it to false.

OUTPUT: Return ONLY valid JSON, no explanation, no markdown.

Always return this wrapper:
{
  "steps": [ <one or more step objects> ]
}

Each step is one of:

color_change step:
{
  "edit_type": "color_change",
  "region_description": "<what body part/area>",
  "from_color": "<exact color name to replace>",
  "to_color": "<exact color name to apply>",
  "preserve_regions": ["<other body parts / accessories that must NOT change, even if same color>"],
  "mask_box": {"top": 0-100, "left": 0-100, "width": 0-100, "height": 0-100},
  "primary_tier": "region_pil",
  "color_overlap_risk": true | false,
  "allow_reconstruction_fallback": false,
  "confidence": 0.0-1.0
}

MASK_BOX GUIDANCE for color_change steps — estimate where the region lives in a typical
character portrait (values are % of full image dimension):
  hair:                       top=0  left=15 width=70 height=25
  face + head (no hair):      top=15 left=25 width=50 height=20
  eyes only:                  top=18 left=30 width=40 height=12
  torso / shirt / body:       top=30 left=20 width=60 height=35
  skin body only (no eyes, no hair):  top=15 left=10 width=80 height=75
  arms / sleeves:             top=30 left=5  width=90 height=40
  legs / pants:               top=60 left=20 width=60 height=35
  shoes / feet:               top=80 left=20 width=60 height=20
  tail:                       top=50 left=50 width=50 height=50

  ★ For skin/fur where you want to EXCLUDE the hair and eyes, use:
    top=15 left=10 width=80 height=75 — this crops the top hair area and covers face+body

structural_edit step:
{
  "edit_type": "structural_edit",
  "region_description": "<what object/area>",
  "mask_box": {"top": 0-100, "left": 0-100, "width": 0-100, "height": 0-100},
  "final_instruction": "<precise instruction for gpt-image-1>",
  "from_color": "<source color if this is a skin/fur color change, else null>",
  "to_color": "<target color if this is a skin/fur color change, else null>",
  "primary_tier": "semantic" | "vision" | "region_pil" | "pil_global",
  "color_overlap_risk": true | false,
  "confidence": 0.0-1.0
}
"""

_EDIT_ANALYZER_USER = "User edit request: {msg}\n\nAnalyze and output the edit plan as JSON."


async def analyze_edit_request(user_msg: str) -> list[dict] | None:
    """
    Use GPT to classify the edit request and return an ordered list of edit steps.

    Each step is either:
      {"edit_type": "color_change", "from_color": ..., "to_color": ..., ...}
      {"edit_type": "structural_edit", "mask_box": ..., "final_instruction": ..., ...}

    Multiple changes are split into separate steps so they can be chained.
    Returns None on failure — caller falls back to single enhanced-instruction path.
    Never raises.
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
        parsed = _json.loads(raw.strip())
        steps = parsed.get("steps", [])
        if not steps:
            # Fallback: model returned old single-step format
            steps = [parsed]
        # Discard if every step is missing edit_type — model returned junk
        if not any(s.get("edit_type") for s in steps):
            return None
        logger.info(
            "analyze_edit_request | %d step(s): %s",
            len(steps),
            [s.get("edit_type") for s in steps],
        )
        return steps
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
    "You are a senior software architect and game developer. "
    "Given a user's coding or building request, write a focused system context "
    "that will help a code-generation model produce the best possible output. "
    "\n\nFor GAME requests, always specify:\n"
    "- Single self-contained HTML file with embedded CSS + JS (no external deps)\n"
    "- Smooth requestAnimationFrame game loop\n"
    "- Keyboard AND touch controls\n"
    "- Score, lives, levels, game over + restart screen\n"
    "- Polished visuals: colors, gradients, animations, particle effects\n"
    "- Sound effects via Web Audio API (no external files)\n"
    "- Collision detection, difficulty scaling as score increases\n"
    "- Full playable experience — not a skeleton or demo\n"
    "\nFor APP requests, always specify:\n"
    "- Complete working UI, no placeholder content\n"
    "- All interactions wired up and functional\n"
    "- Clean modern design with proper spacing and colors\n"
    "\nReturn ONLY the context string. No explanations."
)

_CODE_USER = """\
User request: {msg}
Intent: {intent}

Write a focused, detailed system context for a code generation model handling this request.
If this is a game, be very specific about mechanics, controls, visuals, and what makes it fun."""


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
