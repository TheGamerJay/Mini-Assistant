"""
Future-ready workflow extension stubs.

Provides properly-structured hooks for:
  - img2img          — initialise generation from an existing image
  - inpaint          — masked region re-generation
  - ControlNet       — pose/depth/edge guided generation
  - LoRA stacking    — per-route LoRA injection into the workflow graph

Each function is a documented stub that slots into the existing pipeline.
Add real implementations as ComfyUI node support matures on your system.
"""
import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── LoRA registry ─────────────────────────────────────────────────────────────
# Map: checkpoint_key → list of LoRA configs
# Add real LoRA filenames here once installed in ComfyUI/models/loras/
LORA_REGISTRY: Dict[str, List[Dict[str, Any]]] = {
    "anime_shonen":       [],  # e.g. {"lora_name": "shonen_v1.safetensors", "model_strength": 0.8, "clip_strength": 0.8}
    "anime_shojo":        [],
    "anime_seinen":       [],
    "anime_general":      [],
    "anime_slice_of_life":[],
    "realistic":          [],
    "fantasy":            [],
    "flux_premium":       [],
}


def get_loras_for_route(checkpoint_key: str) -> List[Dict[str, Any]]:
    """Return LoRA configs registered for the given checkpoint key."""
    return LORA_REGISTRY.get(checkpoint_key, [])


def inject_loras(workflow: Dict[str, Any], loras: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Inject LoraLoader nodes between CheckpointLoaderSimple and the CLIP/model
    inputs in the workflow graph.

    STUB — real implementation should:
      1. Find the CheckpointLoaderSimple node id
      2. For each LoRA, insert a LoraLoader node wired from the previous model/clip output
      3. Re-wire downstream nodes to use the final LoRA output
    """
    if not loras:
        return workflow
    logger.info("LoRA injection stub — %d LoRA(s) for this route (not yet implemented)", len(loras))
    # TODO: implement node graph manipulation when LoRAs are installed
    return workflow


# ── img2img ────────────────────────────────────────────────────────────────────

@dataclass
class Img2ImgParams:
    """Parameters for img2img (image-to-image) generation."""
    init_image_bytes: bytes
    denoise_strength: float = 0.75  # 0.0 = no change, 1.0 = full redraw

    def __post_init__(self):
        self.denoise_strength = max(0.0, min(1.0, self.denoise_strength))
        self.init_image_b64: str = base64.b64encode(self.init_image_bytes).decode()


def build_img2img_workflow(
    base_workflow: Dict[str, Any], params: Img2ImgParams
) -> Dict[str, Any]:
    """
    Modify a base workflow dict to perform img2img.

    STUB — real implementation should:
      1. Add a LoadImage node (using params.init_image_b64)
      2. Add a VAEEncode node wired from LoadImage
      3. Replace the EmptyLatentImage node connection to KSampler with VAEEncode output
      4. Set KSampler denoise to params.denoise_strength
    """
    logger.info("img2img workflow stub — denoise=%.2f (not yet implemented)", params.denoise_strength)
    return base_workflow


# ── Inpaint ────────────────────────────────────────────────────────────────────

@dataclass
class InpaintParams:
    """Parameters for inpainting (masked region re-generation)."""
    init_image_bytes: bytes
    mask_bytes: bytes
    denoise_strength: float = 0.85


def build_inpaint_workflow(
    base_workflow: Dict[str, Any], params: InpaintParams
) -> Dict[str, Any]:
    """
    Modify a base workflow dict to perform inpainting.

    STUB — real implementation should:
      1. Add LoadImage nodes for init_image and mask
      2. Add VAEEncodeForInpaint node
      3. Wire mask and image into the inpaint encoder
      4. Set KSampler denoise to params.denoise_strength
    """
    logger.info("Inpaint workflow stub — denoise=%.2f (not yet implemented)", params.denoise_strength)
    return base_workflow


# ── ControlNet ─────────────────────────────────────────────────────────────────

@dataclass
class ControlNetParams:
    """Parameters for ControlNet-guided generation."""
    control_image_bytes: bytes
    controlnet_name: str = "control_v11p_sd15_openpose.pth"
    strength: float = 0.8
    start_percent: float = 0.0
    end_percent: float = 1.0


def build_controlnet_workflow(
    base_workflow: Dict[str, Any], params: ControlNetParams
) -> Dict[str, Any]:
    """
    Inject ControlNet guidance into a workflow.

    STUB — real implementation should:
      1. Add a LoadImage node for the control image
      2. Add a ControlNetLoader node for params.controlnet_name
      3. Add a ControlNetApplyAdvanced node
      4. Wire it between the positive/negative conditioning and KSampler
    """
    logger.info(
        "ControlNet workflow stub — model=%s strength=%.2f (not yet implemented)",
        params.controlnet_name, params.strength,
    )
    return base_workflow
