"""
Route confidence threshold enforcement and checkpoint/workflow compatibility validation.

Rules:
  - If router confidence is below threshold → replace with style-appropriate fallback + add warning
  - SD1.5 checkpoints must only pair with SD1.5 workflows
  - SDXL checkpoints must only pair with SDXL workflows
  - FLUX checkpoints must only pair with FLUX workflows
  - Never silently mix incompatible types — always fix and log
"""
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 0.55

# ── Type maps ─────────────────────────────────────────────────────────────────

CHECKPOINT_TYPES: Dict[str, str] = {
    "animagine-xl-4.0.safetensors":             "SDXL",
    "AbyssOrangeMix2_hard.safetensors":         "SD1.5",
    "MeinaMix_v11.safetensors":                 "SD1.5",
    "counterfeit_v30.safetensors":              "SD1.5",
    "anything-v5.safetensors":                  "SD1.5",
    "Realistic_Vision_V6.0_NV_B1_fp16.safetensors": "SD1.5",
    "DreamShaper_8_pruned.safetensors":         "SD1.5",
    "flux1-schnell.safetensors":                "FLUX",
}

WORKFLOW_TYPES: Dict[str, str] = {
    "anime_general.json":           "SDXL",
    "anime_shonen_action.json":     "SD1.5",
    "anime_seinen_cinematic.json":  "SD1.5",
    "anime_shojo_romance.json":     "SD1.5",
    "anime_slice_of_life.json":     "SD1.5",
    "realistic_photo.json":         "SD1.5",
    "fantasy_cinematic.json":       "SD1.5",
    "flux_high_realism.json":       "FLUX",
    "image_edit_inpaint.json":      "SD1.5",
    "image_reference_match.json":   "SD1.5",
}

# First compatible workflow per type (used for auto-fix)
_FIRST_BY_TYPE: Dict[str, str] = {
    "SDXL":  "anime_general.json",
    "SD1.5": "anime_shonen_action.json",
    "FLUX":  "flux_high_realism.json",
}

FALLBACK_ROUTES: Dict[str, Dict[str, str]] = {
    "anime":     {"checkpoint": "animagine-xl-4.0.safetensors",             "workflow": "anime_general.json"},
    "realistic": {"checkpoint": "Realistic_Vision_V6.0_NV_B1_fp16.safetensors", "workflow": "realistic_photo.json"},
    "fantasy":   {"checkpoint": "DreamShaper_8_pruned.safetensors",         "workflow": "fantasy_cinematic.json"},
    "default":   {"checkpoint": "animagine-xl-4.0.safetensors",             "workflow": "anime_general.json"},
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_checkpoint_type(checkpoint: str) -> str:
    return CHECKPOINT_TYPES.get(checkpoint, "SD1.5")


def get_workflow_type(workflow: str) -> str:
    return WORKFLOW_TYPES.get(workflow, "SD1.5")


def are_compatible(checkpoint: str, workflow: str) -> bool:
    return get_checkpoint_type(checkpoint) == get_workflow_type(workflow)


def fix_incompatible_pair(
    checkpoint: str, workflow: str
) -> Tuple[str, str, str]:
    """
    If checkpoint and workflow types don't match, fix by swapping to a compatible workflow.
    Returns (checkpoint, workflow, reason_string).
    reason_string is empty string if no fix was needed.
    """
    ct = get_checkpoint_type(checkpoint)
    wt = get_workflow_type(workflow)
    if ct == wt:
        return checkpoint, workflow, ""

    new_wf = _FIRST_BY_TYPE.get(ct, "anime_general.json")
    reason = (
        f"Incompatible pair fixed: {checkpoint} ({ct}) + {workflow} ({wt}) "
        f"→ workflow changed to {new_wf} ({ct})"
    )
    logger.warning(reason)
    return checkpoint, new_wf, reason


# ── Confidence threshold ──────────────────────────────────────────────────────

def enforce_confidence(
    route_result: Dict[str, Any],
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> Dict[str, Any]:
    """
    If router confidence is below threshold, replace checkpoint/workflow with
    a safe style-appropriate fallback and attach a warning field.
    """
    confidence = float(route_result.get("confidence", 0.0))
    if confidence >= threshold:
        return route_result

    style_family = route_result.get("style_family", "default")
    fallback = FALLBACK_ROUTES.get(style_family, FALLBACK_ROUTES["default"])
    warning = (
        f"Router confidence {confidence:.2f} is below threshold {threshold:.2f}. "
        f"Using safe fallback for style '{style_family}': "
        f"{fallback['checkpoint']} / {fallback['workflow']}."
    )
    logger.warning(warning)

    route_result = dict(route_result)
    route_result["_original_checkpoint"] = route_result.get("selected_checkpoint")
    route_result["_original_workflow"]   = route_result.get("selected_workflow")
    route_result["selected_checkpoint"]  = fallback["checkpoint"]
    route_result["selected_workflow"]    = fallback["workflow"]
    route_result["_low_confidence_warning"] = warning
    return route_result


# ── Full validation ────────────────────────────────────────────────────────────

def validate_route(
    route_result: Dict[str, Any],
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> Dict[str, Any]:
    """
    Full route validation:
      1. Enforce confidence threshold (may replace checkpoint/workflow with fallback)
      2. Ensure checkpoint/workflow types are compatible (auto-fix if not)
    Returns the (possibly modified) route_result with warning fields attached.
    """
    route_result = enforce_confidence(route_result, threshold)

    ckpt = route_result.get("selected_checkpoint", "")
    wf   = route_result.get("selected_workflow", "")
    ckpt, wf, compat_reason = fix_incompatible_pair(ckpt, wf)

    route_result["selected_checkpoint"] = ckpt
    route_result["selected_workflow"]   = wf
    if compat_reason:
        route_result["_compatibility_warning"] = compat_reason

    return route_result
