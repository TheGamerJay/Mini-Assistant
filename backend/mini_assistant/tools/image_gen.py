"""
image_gen.py – Image Generation Tool
──────────────────────────────────────
Connects to AUTOMATIC1111 (txt2img REST API) by default.
Falls back to ComfyUI if configured.
Returns a dict with base64 image data and metadata.
"""

import base64
import logging
from typing import Optional

import requests

from ..config import SD_HOST, SD_BACKEND

logger = logging.getLogger(__name__)


# ─── AUTOMATIC1111 ────────────────────────────────────────────────────────────

def _auto1111_generate(
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg_scale: float,
) -> dict:
    payload = {
        "prompt":          prompt,
        "negative_prompt": negative_prompt,
        "width":           width,
        "height":          height,
        "steps":           steps,
        "cfg_scale":       cfg_scale,
        "sampler_name":    "DPM++ 2M Karras",
    }
    resp = requests.post(f"{SD_HOST}/sdapi/v1/txt2img", json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    img_b64 = data["images"][0]
    return {
        "success":        True,
        "image_b64":      img_b64,
        "backend":        "auto1111",
        "prompt":         prompt,
        "negative_prompt": negative_prompt,
        "width":          width,
        "height":         height,
        "steps":          steps,
    }


# ─── ComfyUI (simple txt2img via default workflow) ────────────────────────────

def _comfyui_generate(prompt: str, width: int, height: int) -> dict:
    """Minimal ComfyUI API call using the default checkpoint workflow."""
    import json, uuid, time

    client_id = str(uuid.uuid4())
    workflow = {
        "3": {"inputs": {"seed": 42, "steps": 20, "cfg": 7, "sampler_name": "euler",
                         "scheduler": "normal", "denoise": 1,
                         "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0],
                         "latent_image": ["5", 0]}, "class_type": "KSampler"},
        "4": {"inputs": {"ckpt_name": "v1-5-pruned-emaonly.ckpt"}, "class_type": "CheckpointLoaderSimple"},
        "5": {"inputs": {"width": width, "height": height, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "6": {"inputs": {"text": prompt, "clip": ["4", 1]}, "class_type": "CLIPTextEncode"},
        "7": {"inputs": {"text": "ugly, blurry, low quality", "clip": ["4", 1]}, "class_type": "CLIPTextEncode"},
        "8": {"inputs": {"samples": ["3", 0], "vae": ["4", 2]}, "class_type": "VAEDecode"},
        "9": {"inputs": {"filename_prefix": "mini_assistant", "images": ["8", 0]}, "class_type": "SaveImage"},
    }

    resp = requests.post(f"{SD_HOST}/prompt", json={"prompt": workflow, "client_id": client_id}, timeout=10)
    resp.raise_for_status()
    prompt_id = resp.json()["prompt_id"]

    # Poll for completion
    for _ in range(60):
        time.sleep(2)
        hist = requests.get(f"{SD_HOST}/history/{prompt_id}", timeout=10).json()
        if prompt_id in hist:
            output_images = hist[prompt_id]["outputs"]["9"]["images"]
            img_name = output_images[0]["filename"]
            img_resp = requests.get(f"{SD_HOST}/view?filename={img_name}", timeout=30)
            img_b64 = base64.b64encode(img_resp.content).decode("utf-8")
            return {"success": True, "image_b64": img_b64, "backend": "comfyui", "prompt": prompt}

    return {"success": False, "error": "ComfyUI timed out", "backend": "comfyui"}


# ─── Public function ──────────────────────────────────────────────────────────

def generate_image(
    prompt: str,
    negative_prompt: str = "ugly, blurry, low quality, watermark, text",
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    cfg_scale: float = 7.0,
    backend: Optional[str] = None,
) -> dict:
    """
    Generate an image from a text prompt.

    Returns:
        dict with keys: success, image_b64, backend, prompt, (error if failed)
    """
    backend = (backend or SD_BACKEND).lower()
    logger.info("Image generation: backend=%s prompt=%r", backend, prompt[:80])

    try:
        if backend == "comfyui":
            return _comfyui_generate(prompt, width, height)
        else:
            return _auto1111_generate(prompt, negative_prompt, width, height, steps, cfg_scale)

    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error":   f"Cannot connect to {backend} at {SD_HOST}. Is Stable Diffusion running?",
            "backend": backend,
            "prompt":  prompt,
        }
    except Exception as exc:
        logger.error("Image generation failed: %s", exc)
        return {"success": False, "error": str(exc), "backend": backend, "prompt": prompt}
