"""
Generation metadata sidecar writer.

Saves a JSON file alongside each output image containing:
  - original and rewritten prompts
  - route decision (checkpoint, workflow, confidence)
  - generation parameters (seed, size, steps, cfg)
  - review result from the vision brain
  - timing and session information

Uses file locking to prevent concurrent write corruption.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .file_lock import safe_write

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def build_metadata(
    original_prompt: str,
    positive_prompt: str,
    negative_prompt: str,
    route: Dict[str, Any],
    checkpoint: str,
    workflow: str,
    seed: int,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    quality: str,
    review_result: Optional[Dict] = None,
    session_id: Optional[str] = None,
    generation_ms: Optional[float] = None,
) -> Dict[str, Any]:
    """Build the metadata dict to be saved alongside the output image."""
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "generation_ms": round(generation_ms, 1) if generation_ms else None,
        "prompt": {
            "original":  original_prompt,
            "positive":  positive_prompt,
            "negative":  negative_prompt,
        },
        "route": {
            "intent":             route.get("intent"),
            "style_family":       route.get("style_family"),
            "anime_genre":        route.get("anime_genre"),
            "visual_mode":        route.get("visual_mode"),
            "confidence":         route.get("confidence"),
            "anime_score":        route.get("anime_score"),
            "realism_score":      route.get("realism_score"),
            "fantasy_score":      route.get("fantasy_score"),
            "low_conf_warning":   route.get("_low_confidence_warning"),
            "compat_warning":     route.get("_compatibility_warning"),
        },
        "generation": {
            "checkpoint": checkpoint,
            "workflow":   workflow,
            "seed":       seed,
            "width":      width,
            "height":     height,
            "steps":      steps,
            "cfg":        cfg,
            "quality":    quality,
        },
        "review": review_result,
    }


def save_metadata(image_path: Path, metadata: Dict[str, Any]) -> Path:
    """Write metadata JSON beside the image file (same stem, .json extension)."""
    meta_path = Path(image_path).with_suffix(".json")
    with safe_write(meta_path):
        meta_path.write_text(
            json.dumps(metadata, indent=2, default=str), encoding="utf-8"
        )
    logger.debug("Metadata saved: %s", meta_path)
    return meta_path


def save_output_image(
    image_bytes: bytes, session_id: str, seed: int
) -> Path:
    """Save raw image bytes to the output directory with a timestamped filename."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in (session_id or "img"))
    filename = f"{safe_id}_{ts}_{seed}.png"
    out_path = OUTPUT_DIR / filename
    with safe_write(out_path):
        out_path.write_bytes(image_bytes)
    logger.info("Image saved: %s", out_path)
    return out_path
