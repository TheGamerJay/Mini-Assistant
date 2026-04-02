"""
events/event_emitter.py — Structured event emitter for the CEO pipeline.

Events are the ONLY source of truth for UI state and X-Ray display.
UI may only display events that were actually emitted — never invent state.

Event format (all events):
    {
        "event_type": str,     # canonical event name
        "module":     str,     # which module this relates to (or "ceo")
        "status":     str,     # "started" | "complete" | "passed" | "failed" | "needed" | "ready" | "error"
        "summary":    str,     # human-readable one-liner for UI
        "timestamp":  str,     # ISO 8601 UTC
        "session_id": str | None,
        "detail":     dict,    # full detail — admin X-Ray only
    }

Visibility:
    - "summary" is user-facing — keep it plain
    - "detail" is admin/X-Ray — may contain full payloads

Canonical event types:
    CEO routing phase:
        request_received
        intent_detected
        complexity_detected
        module_selected
        tier_decided
        clarification_needed
        plan_built
        decision_complete

    Execution phase:
        step_started
        step_finished
        memory_loading_started
        memory_loading_complete
        web_needed
        web_call_started
        web_call_complete
        module_execution_started
        module_execution_complete
        validation_started
        validation_passed
        validation_failed
        output_ready
        partial_output

    Error:
        error

Streaming (SSE):
    Events are emitted as server-sent events when the API uses /stream endpoint.
    Each event is serialized as:
        data: <json>\n\n
    UI renders each event as it arrives — no polling required.
    Visibility rules:
        - "summary" only → user-facing (default)
        - "detail" included → admin/X-Ray mode only
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

log = logging.getLogger("ceo_router.events")


def emit(
    event_type: str,
    module:     str,
    status:     str,
    summary:    str,
    detail:     Optional[dict[str, Any]] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Build and log a structured event.

    Returns the event dict — callers may append to ctx.events_emitted.
    """
    event: dict[str, Any] = {
        "event_type": event_type,
        "module":     module,
        "status":     status,
        "summary":    summary,
        "timestamp":  _now_iso(),
        "session_id": session_id,
        "detail":     detail or {},
    }
    log.info(
        "[CEO EVENT] %-34s module=%-18s status=%-10s | %s",
        event_type, module, status, summary,
    )

    # Persist to disk log pipeline — must never crash execution
    try:
        from logs.event_logger import log_event
        log_event(event)
    except Exception:
        pass

    return event


# ---------------------------------------------------------------------------
# Convenience helpers — one per canonical event type
# These keep call sites clean and guarantee consistent format.
# ---------------------------------------------------------------------------

def request_received(session_id: Optional[str], tier: str, has_attach: bool) -> dict:
    return emit(
        "request_received", "ceo", "started",
        "Request received by CEO Router.",
        {"tier": tier, "has_attachments": has_attach},
        session_id,
    )


def intent_detected(session_id: Optional[str], primary: str, secondary: Optional[str], confidence: float) -> dict:
    return emit(
        "intent_detected", "ceo", "complete",
        f"Intent detected: {primary}" + (f" (secondary: {secondary})" if secondary else ""),
        {"primary": primary, "secondary": secondary, "confidence": confidence},
        session_id,
    )


def complexity_detected(session_id: Optional[str], complexity: str, underspecified: bool) -> dict:
    return emit(
        "complexity_detected", "ceo", "complete",
        f"Complexity: {complexity}" + (" (underspecified)" if underspecified else ""),
        {"complexity": complexity, "underspecified": underspecified},
        session_id,
    )


def module_selected(session_id: Optional[str], module: str, tier_vis: str) -> dict:
    return emit(
        "module_selected", module, "complete",
        f"Module selected: {module} (tier visibility: {tier_vis})",
        {"module": module, "tier_visibility": tier_vis},
        session_id,
    )


def tier_decided(session_id: Optional[str], tier_visibility: str) -> dict:
    return emit(
        "tier_decided", "ceo", "complete",
        f"Tier visibility set to: {tier_visibility}",
        {"tier_visibility": tier_visibility},
        session_id,
    )


def clarification_needed(session_id: Optional[str], question: str) -> dict:
    return emit(
        "clarification_needed", "ceo", "needed",
        "CEO requires clarification before proceeding.",
        {"question": question},
        session_id,
    )


def plan_built(session_id: Optional[str], step_count: int, step_types: list[str]) -> dict:
    return emit(
        "plan_built", "ceo", "complete",
        f"Execution plan built: {step_count} step(s).",
        {"step_count": step_count, "step_types": step_types},
        session_id,
    )


def decision_complete(session_id: Optional[str], module: str, intent: str, elapsed_ms: float) -> dict:
    return emit(
        "decision_complete", module, "complete",
        f"CEO decision complete in {elapsed_ms:.0f}ms → {module}",
        {"module": module, "intent": intent, "elapsed_ms": elapsed_ms},
        session_id,
    )


def memory_loading_started(session_id: Optional[str], scope: str) -> dict:
    return emit(
        "memory_loading_started", "memory", "started",
        f"Loading TR memory: {scope}",
        {"scope": scope},
        session_id,
    )


def memory_loading_complete(session_id: Optional[str], keys_loaded: list[str]) -> dict:
    return emit(
        "memory_loading_complete", "memory", "complete",
        f"Memory loaded: {len(keys_loaded)} key(s)",
        {"keys_loaded": keys_loaded},
        session_id,
    )


def web_needed(session_id: Optional[str], mode: str) -> dict:
    return emit(
        "web_needed", "web", "needed",
        f"Web access required: mode={mode}",
        {"mode": mode},
        session_id,
    )


def web_call_started(session_id: Optional[str], mode: str) -> dict:
    return emit(
        "web_call_started", "web", "started",
        f"Web {mode} started.",
        {"mode": mode},
        session_id,
    )


def web_call_complete(session_id: Optional[str], mode: str, result_count: int, ok: bool) -> dict:
    return emit(
        "web_call_complete", "web", "complete" if ok else "failed",
        f"Web {mode} complete: {result_count} result(s)",
        {"mode": mode, "result_count": result_count, "ok": ok},
        session_id,
    )


def module_execution_started(session_id: Optional[str], module: str) -> dict:
    return emit(
        "module_execution_started", module, "started",
        f"Module {module} starting execution.",
        {"module": module},
        session_id,
    )


def module_execution_complete(session_id: Optional[str], module: str, ok: bool) -> dict:
    return emit(
        "module_execution_complete", module, "complete" if ok else "error",
        f"Module {module} execution {'complete' if ok else 'failed'}.",
        {"module": module, "ok": ok},
        session_id,
    )


def validation_started(session_id: Optional[str], module: str, validation_type: str) -> dict:
    return emit(
        "validation_started", module, "started",
        f"Validating {module} output ({validation_type}).",
        {"module": module, "validation_type": validation_type},
        session_id,
    )


def validation_passed(session_id: Optional[str], module: str, validation_type: str) -> dict:
    return emit(
        "validation_passed", module, "passed",
        f"Validation passed for {module}.",
        {"module": module, "validation_type": validation_type},
        session_id,
    )


def validation_failed(
    session_id: Optional[str], module: str, validation_type: str, issues: list[str]
) -> dict:
    return emit(
        "validation_failed", module, "failed",
        f"Validation failed for {module}: {len(issues)} issue(s).",
        {"module": module, "validation_type": validation_type, "issues": issues},
        session_id,
    )


def output_ready(session_id: Optional[str], module: str) -> dict:
    return emit(
        "output_ready", module, "ready",
        f"Output ready from {module}.",
        {"module": module},
        session_id,
    )


def step_started(
    session_id: Optional[str],
    step_num:   int,
    step_type:  str,
    target:     str,
) -> dict:
    return emit(
        "step_started", "executor", "started",
        f"Step {step_num}: {step_type} → {target}",
        {"step": step_num, "type": step_type, "target": target},
        session_id,
    )


def step_finished(
    session_id:  Optional[str],
    step_num:    int,
    step_type:   str,
    elapsed_ms:  float,
    ok:          bool = True,
) -> dict:
    status = "complete" if ok else "failed"
    return emit(
        "step_finished", "executor", status,
        f"Step {step_num}: {step_type} {status} in {elapsed_ms:.0f}ms",
        {"step": step_num, "type": step_type, "elapsed_ms": elapsed_ms, "ok": ok},
        session_id,
    )


def partial_output(
    session_id: Optional[str],
    module:     str,
    stage:      str,
    content:    Any,
) -> dict:
    """
    Emitted when meaningful intermediate output is ready before full completion.
    Examples: execution plan built, first component generated, etc.
    content is user-facing — keep it concise.
    """
    return emit(
        "partial_output", module, "started",
        f"Partial output from {module}: {stage}",
        {"stage": stage, "content": content},
        session_id,
    )


def checkpoint_reached(
    session_id:    Optional[str],
    checkpoint_id: str,
    step:          str,
    requires_input: bool,
    summary:       str,
) -> dict:
    return emit(
        "checkpoint_reached", "executor", "needed" if requires_input else "complete",
        summary,
        {
            "checkpoint_id":     checkpoint_id,
            "step":              step,
            "requires_user_input": requires_input,
        },
        session_id,
    )


def user_control(
    session_id: Optional[str],
    action:     str,
    detail:     Optional[dict] = None,
) -> dict:
    return emit(
        "user_control", "ceo", "started",
        f"User control: {action}",
        {"action": action, **(detail or {})},
        session_id,
    )


def error(session_id: Optional[str], module: str, message: str) -> dict:
    return emit(
        "error", module, "error",
        f"Error in {module}: {message}",
        {"message": message},
        session_id,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
