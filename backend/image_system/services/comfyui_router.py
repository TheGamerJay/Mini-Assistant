"""
backend/image_system/services/comfyui_router.py

Smart routing for ComfyUI generation modes.

Determines whether a request should use text-to-image, reference-guided,
or inpainting/edit based on the prompt keywords and attached images.

This is the route_image_request() function built by the user for the
Mini Assistant ComfyUI integration, packaged as a proper service module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword sets
# ---------------------------------------------------------------------------

_EDIT_KEYWORDS: frozenset[str] = frozenset({
    "replace", "change", "modify", "edit", "remove", "erase", "add",
    "insert", "swap", "alter", "transform", "adjust", "fix", "correct",
    "repaint", "redraw", "inpaint", "fill", "extend", "delete", "update",
    "recolor", "recolour", "reshape", "resize", "crop", "enlarge",
})

_POSE_KEYWORDS: frozenset[str] = frozenset({
    "pose", "stance", "posture", "position", "stand", "sit", "lean",
    "crouch", "kneel", "arms", "hands", "gesture", "action", "movement",
})

_STYLE_KEYWORDS: tuple[str, ...] = (
    "style",
    "like",
    "inspired by",
    "in the style of",
    "art style",
    "aesthetic",
    "look like",
    "similar to",
    "resembling",
    "imitating",
    "same art",
)

# ---------------------------------------------------------------------------
# Workflow file keys (stems of JSON files in config/workflows/)
# ---------------------------------------------------------------------------

# "generate" mode → build_standard_workflow() — no JSON file needed
WORKFLOW_GENERATE  = "__standard__"
WORKFLOW_REFERENCE = "image_reference_match"
WORKFLOW_EDIT      = "image_edit_inpaint"

# UI tab names (used for frontend tab routing)
TAB_TEXT_TO_IMAGE   = "Text to Image"
TAB_REFERENCE       = "Reference Guided"
TAB_INPAINTING_EDIT = "Inpainting Edit"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RouteDecision:
    mode: str        # "generate" | "reference" | "edit"
    target_tab: str  # UI tab label
    workflow: str    # workflow key (WORKFLOW_* constant)
    reason: str      # human-readable explanation

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Main routing function
# ---------------------------------------------------------------------------

def route_image_request(
    prompt: str,
    reference_image: Optional[str] = None,
    mask_image: Optional[str] = None,
    pose_image: Optional[str] = None,
    style_image: Optional[str] = None,
) -> RouteDecision:
    """
    Determine which ComfyUI generation mode to use.

    Priority order (highest to lowest):
    1. mask_image present          → inpainting/edit mode
    2. edit keyword + reference    → inpainting/edit mode
    3. reference/pose/style image  → reference-guided mode
    4. pure text prompt            → standard text-to-image

    Args:
        prompt:          The user's text prompt.
        reference_image: Base64 string (or truthy) if a reference image is attached.
        mask_image:      Base64 string (or truthy) if a mask image is attached.
        pose_image:      Base64 string (or truthy) if a pose image is attached.
        style_image:     Base64 string (or truthy) if a style image is attached.

    Returns:
        RouteDecision with mode, target_tab, workflow key, and reason.
    """
    prompt_lower = prompt.lower()
    prompt_words = set(prompt_lower.split())

    has_reference = bool(reference_image)
    has_mask      = bool(mask_image)
    has_pose      = bool(pose_image)
    has_style     = bool(style_image)
    any_image     = has_reference or has_mask or has_pose or has_style

    has_edit_keywords  = bool(prompt_words & _EDIT_KEYWORDS)
    has_style_keywords = any(kw in prompt_lower for kw in _STYLE_KEYWORDS)

    # Rule 1: mask image → inpainting edit
    if has_mask:
        logger.debug("ComfyUI route: edit (mask image present)")
        return RouteDecision(
            mode="edit",
            target_tab=TAB_INPAINTING_EDIT,
            workflow=WORKFLOW_EDIT,
            reason="mask_image provided → inpainting edit",
        )

    # Rule 2: edit keyword + any reference image → inpainting/guided edit
    if has_edit_keywords and has_reference:
        logger.debug("ComfyUI route: edit (edit keyword + reference image)")
        return RouteDecision(
            mode="edit",
            target_tab=TAB_INPAINTING_EDIT,
            workflow=WORKFLOW_EDIT,
            reason="edit keyword in prompt + reference_image → inpainting edit",
        )

    # Rule 3: any reference / pose / style image → reference-guided
    if any_image:
        detail_parts = []
        if has_reference: detail_parts.append("reference_image")
        if has_pose:      detail_parts.append("pose_image")
        if has_style:     detail_parts.append("style_image")
        detail = ", ".join(detail_parts)
        logger.debug("ComfyUI route: reference (%s)", detail)
        return RouteDecision(
            mode="reference",
            target_tab=TAB_REFERENCE,
            workflow=WORKFLOW_REFERENCE,
            reason=f"{detail} → reference-guided generation",
        )

    # Rule 4: pure text prompt → standard text-to-image
    logger.debug("ComfyUI route: generate (pure text prompt)")
    return RouteDecision(
        mode="generate",
        target_tab=TAB_TEXT_TO_IMAGE,
        workflow=WORKFLOW_GENERATE,
        reason="pure text prompt → standard text-to-image",
    )
