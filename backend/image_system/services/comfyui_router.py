"""comfyui_router.py — ComfyUI removed. Stubs kept for import compatibility."""
from dataclasses import dataclass

WORKFLOW_GENERATE = "generate"


@dataclass
class ComfyDecision:
    workflow: str = WORKFLOW_GENERATE
    mode: str = "generate"
    target_tab: str = "preview"


def route(
    *,
    reference_bytes=None,
    mask_bytes=None,
    pose_bytes=None,
    style_bytes=None,
    prompt="",
    **kw,
) -> ComfyDecision:
    return ComfyDecision()
