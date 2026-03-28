"""
Live Updates — Phase 2

Manages the real-time task event stream sent to the frontend via SSE.
Events are generated here and consumed by the /api/orchestrate/stream endpoint.

Event types (kept simple for frontend rendering):
  task_started       | task:id, title
  step_started       | step:id, title, index, total
  step_completed     | step:id, title, output_summary
  step_failed        | step:id, title, error
  checkpoint_created | checkpoint:id, label
  approval_required  | step:id, title, risk_level
  retry_started      | step:id, attempt:int
  task_completed     | task:id, summary
  task_failed        | task:id, error
  task_cancelled     | task:id

Each event is a dict that serializes to an SSE `data:` line.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Optional

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_event(event_type: str, **kwargs) -> Dict[str, Any]:
    """Build a structured event dict."""
    return {
        "type":       event_type,
        "timestamp":  _now(),
        **kwargs,
    }


def encode_sse(event: Dict[str, Any]) -> str:
    """Encode a dict as an SSE data frame."""
    return f"data: {json.dumps(event)}\n\n"


# ---------------------------------------------------------------------------
# In-memory event queue per task
# ---------------------------------------------------------------------------

_task_queues: Dict[str, asyncio.Queue] = {}


def get_or_create_queue(task_id: str) -> asyncio.Queue:
    if task_id not in _task_queues:
        _task_queues[task_id] = asyncio.Queue(maxsize=200)
    return _task_queues[task_id]


def cleanup_queue(task_id: str) -> None:
    _task_queues.pop(task_id, None)


async def push_event(task_id: str, event_type: str, **kwargs) -> None:
    """Push an event to a task's live feed queue."""
    q = get_or_create_queue(task_id)
    event = make_event(event_type, task_id=task_id, **kwargs)
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        logger.warning("[LiveUpdates] queue full for task %s, dropping event %s", task_id, event_type)


async def event_stream(task_id: str, timeout: float = 300.0) -> AsyncIterator[str]:
    """
    Async generator that yields SSE frames for a task.
    Closes when a terminal event (task_completed, task_failed, task_cancelled) is received.
    """
    q = get_or_create_queue(task_id)
    terminal_types = {"task_completed", "task_failed", "task_cancelled"}
    elapsed = 0.0
    interval = 0.2

    while elapsed < timeout:
        try:
            event = q.get_nowait()
        except asyncio.QueueEmpty:
            await asyncio.sleep(interval)
            elapsed += interval
            # Keepalive ping every 15 seconds
            if int(elapsed) % 15 == 0:
                yield ": keepalive\n\n"
            continue

        yield encode_sse(event)

        if event.get("type") in terminal_types:
            break

    cleanup_queue(task_id)


# ---------------------------------------------------------------------------
# Convenience helpers — called by executor and orchestrator
# ---------------------------------------------------------------------------

async def emit_task_started(task_id: str, title: str) -> None:
    await push_event(task_id, "task_started", title=title)


async def emit_step_started(task_id: str, step_id: str, title: str, index: int, total: int) -> None:
    await push_event(task_id, "step_started", step_id=step_id, title=title, index=index, total=total)


async def emit_step_completed(task_id: str, step_id: str, title: str, output_summary: str = "") -> None:
    await push_event(task_id, "step_completed", step_id=step_id, title=title, output_summary=output_summary)


async def emit_step_failed(task_id: str, step_id: str, title: str, error: str = "") -> None:
    await push_event(task_id, "step_failed", step_id=step_id, title=title, error=error)


async def emit_checkpoint(task_id: str, checkpoint_id: str, label: str) -> None:
    await push_event(task_id, "checkpoint_created", checkpoint_id=checkpoint_id, label=label)


async def emit_approval_required(task_id: str, step_id: str, title: str, risk_level: str) -> None:
    await push_event(task_id, "approval_required", step_id=step_id, title=title, risk_level=risk_level)


async def emit_retry(task_id: str, step_id: str, attempt: int) -> None:
    await push_event(task_id, "retry_started", step_id=step_id, attempt=attempt)


async def emit_task_completed(task_id: str, summary: str = "") -> None:
    await push_event(task_id, "task_completed", summary=summary)


async def emit_task_failed(task_id: str, error: str = "") -> None:
    await push_event(task_id, "task_failed", error=error)


async def emit_task_cancelled(task_id: str) -> None:
    await push_event(task_id, "task_cancelled")
