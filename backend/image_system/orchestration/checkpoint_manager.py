"""
Checkpoint Manager — Phase 2

Creates, stores, and restores execution checkpoints.
Every checkpoint is a JSON snapshot stored on disk under:
  memory_store/checkpoints/{task_id}/{checkpoint_id}.json

Supports:
  - create_checkpoint(task_id, step_id, data)
  - restore_checkpoint(checkpoint_id) → data
  - list_checkpoints(task_id) → [CheckpointMeta]
  - delete_checkpoint(checkpoint_id)
"""

from __future__ import annotations

import json
import uuid
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CKPT_BASE = Path(__file__).parent.parent.parent / "memory_store" / "checkpoints"


@dataclass
class CheckpointMeta:
    checkpoint_id: str
    task_id:       str
    step_id:       str
    label:         str
    created_at:    str
    size_bytes:    int
    restorable:    bool = True


def _task_dir(task_id: str) -> Path:
    safe = task_id.replace("/", "_").replace("..", "_")
    d = _CKPT_BASE / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_checkpoint(
    task_id:  str,
    step_id:  str,
    data:     Dict[str, Any],
    label:    str = "",
) -> CheckpointMeta:
    """
    Persist a checkpoint snapshot.

    Args:
        task_id:  Owning task ID.
        step_id:  Step that triggered the checkpoint.
        data:     Arbitrary serializable dict (code, state, etc.).
        label:    Human-readable label.

    Returns:
        CheckpointMeta
    """
    ckpt_id = str(uuid.uuid4())[:12]
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "checkpoint_id": ckpt_id,
        "task_id":       task_id,
        "step_id":       step_id,
        "label":         label or f"Checkpoint @ step {step_id}",
        "created_at":    now,
        "data":          data,
    }
    raw = json.dumps(payload, ensure_ascii=False)
    path = _task_dir(task_id) / f"{ckpt_id}.json"
    try:
        path.write_text(raw, encoding="utf-8")
        size = path.stat().st_size
        logger.info("[CheckpointManager] created %s for task %s (%d bytes)", ckpt_id, task_id, size)
    except OSError as exc:
        logger.warning("[CheckpointManager] could not write checkpoint: %s", exc)
        size = len(raw.encode())

    return CheckpointMeta(
        checkpoint_id=ckpt_id,
        task_id=task_id,
        step_id=step_id,
        label=payload["label"],
        created_at=now,
        size_bytes=size,
    )


def restore_checkpoint(task_id: str, checkpoint_id: str) -> Optional[Dict[str, Any]]:
    """
    Load a checkpoint's data dict.

    Returns:
        The 'data' field from the checkpoint, or None if not found.
    """
    path = _task_dir(task_id) / f"{checkpoint_id}.json"
    if not path.exists():
        logger.warning("[CheckpointManager] checkpoint %s not found", checkpoint_id)
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("data")
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[CheckpointManager] could not read checkpoint %s: %s", checkpoint_id, exc)
        return None


def list_checkpoints(task_id: str) -> List[CheckpointMeta]:
    """Return all checkpoints for a task, sorted by creation time."""
    task_dir = _task_dir(task_id)
    result: List[CheckpointMeta] = []
    for path in sorted(task_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            result.append(CheckpointMeta(
                checkpoint_id=payload["checkpoint_id"],
                task_id=payload["task_id"],
                step_id=payload["step_id"],
                label=payload.get("label", ""),
                created_at=payload.get("created_at", ""),
                size_bytes=path.stat().st_size,
            ))
        except Exception:
            continue
    return result


def delete_checkpoint(task_id: str, checkpoint_id: str) -> bool:
    """Remove a checkpoint file. Returns True if deleted."""
    path = _task_dir(task_id) / f"{checkpoint_id}.json"
    if path.exists():
        try:
            path.unlink()
            return True
        except OSError:
            return False
    return False
