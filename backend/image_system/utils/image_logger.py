"""
Centralized structured logging for the image system.

Three dedicated log files written to image_system/logs/:
  router.log   — every routing decision (model, checkpoint, confidence, timing)
  comfyui.log  — every ComfyUI execution (checkpoint, workflow, size, seed, output path)
  review.log   — every review/retry event (scores, retry reason, final output)

All entries are newline-delimited JSON for easy grep / parsing.
"""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _make_file_logger(name: str, filename: str) -> logging.Logger:
    """Create a logger that writes JSON lines to a dedicated file."""
    log = logging.getLogger(f"image_system.{name}")
    if log.handlers:
        return log
    log.setLevel(logging.DEBUG)
    log.propagate = False

    # File handler — structured JSON lines
    fh = logging.FileHandler(LOG_DIR / filename, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(fh)

    # Console handler — human-readable prefix
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(f"[{name}] %(message)s"))
    log.addHandler(ch)

    return log


router_log  = _make_file_logger("router",  "router.log")
comfyui_log = _make_file_logger("comfyui", "comfyui.log")
review_log  = _make_file_logger("review",  "review.log")


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Public logging functions ──────────────────────────────────────────────────

def log_router_decision(
    request: str,
    route: Dict[str, Any],
    elapsed_ms: float,
    session_id: Optional[str] = None,
) -> None:
    """Log a router classification decision."""
    router_log.info(json.dumps({
        "event":              "router_decision",
        "ts":                 _ts(),
        "session_id":         session_id,
        "request_snippet":    request[:120],
        "intent":             route.get("intent"),
        "style_family":       route.get("style_family"),
        "anime_genre":        route.get("anime_genre"),
        "visual_mode":        route.get("visual_mode"),
        "selected_checkpoint":route.get("selected_checkpoint"),
        "selected_workflow":  route.get("selected_workflow"),
        "confidence":         route.get("confidence"),
        "anime_score":        route.get("anime_score"),
        "realism_score":      route.get("realism_score"),
        "fantasy_score":      route.get("fantasy_score"),
        "low_conf_warning":   route.get("_low_confidence_warning"),
        "compat_warning":     route.get("_compatibility_warning"),
        "elapsed_ms":         round(elapsed_ms, 1),
    }))


def log_comfyui_execution(
    session_id: Optional[str],
    checkpoint: str = "",
    workflow: str = "",
    width: int = 0,
    height: int = 0,
    steps: int = 0,
    cfg: float = 0.0,
    seed: int = -1,
    elapsed_ms: float = 0.0,
    output_path: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """No-op stub — ComfyUI removed. Image generation uses OpenAI DALL-E."""
    pass


def log_review_event(
    session_id: Optional[str],
    quality_score: float,
    retry: bool,
    retry_reason: Optional[str],
    alt_checkpoint: Optional[str],
    attempt: int,
    elapsed_ms: float,
    final_output: Optional[str],
) -> None:
    """Log a vision-review result and whether a retry was triggered."""
    review_log.info(json.dumps({
        "event":           "review_result",
        "ts":              _ts(),
        "session_id":      session_id,
        "quality_score":   quality_score,
        "retry_recommended": retry,
        "retry_reason":    retry_reason,
        "alt_checkpoint":  alt_checkpoint,
        "attempt":         attempt,
        "elapsed_ms":      round(elapsed_ms, 1),
        "final_output":    final_output,
    }))
