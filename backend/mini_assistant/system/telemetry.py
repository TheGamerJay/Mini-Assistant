"""
Mini Assistant — Telemetry / Structured Logging
Lightweight JSON logger. No external dependencies.
"""

import json
import logging
import os
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def new_request_id() -> str:
    """Generate a fresh request ID and bind it to the current context."""
    rid = uuid.uuid4().hex[:12]
    _request_id.set(rid)
    return rid


def get_request_id() -> str:
    return _request_id.get()

_logger = logging.getLogger("mini_assistant.system")

def _setup() -> None:
    if _logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(logging.DEBUG if is_debug() else logging.INFO)


def is_debug() -> bool:
    return os.getenv("MA_DEBUG", "").lower() in ("1", "true", "yes")


def log_event(event: str, data: dict) -> None:
    payload = {
        "ts":         datetime.now(timezone.utc).isoformat(),
        "request_id": get_request_id() or "unset",
        "event":      event,
        **data,
    }
    _logger.info(json.dumps(payload))


def log_request(
    *,
    detected_intent: str,
    confidence: float,
    mode_selected: str | None,
    multi_intent: bool,
    context_summary: dict,
    act_decision: bool,
    act_reason: str,
) -> None:
    # strip any sensitive fields before logging context
    safe_ctx = {k: v for k, v in context_summary.items()
                if k not in {"user_confirmed", "missing_field"}}
    log_event("request", {
        "detected_intent":  detected_intent,
        "confidence":       round(confidence, 3),
        "mode_selected":    mode_selected,
        "multi_intent":     multi_intent,
        "context":          safe_ctx,
        "act":              act_decision,
        "act_reason":       act_reason,
    })


def log_tool(*, tool: str, success: bool, reason: str = "ok", timed_out: bool = False) -> None:
    log_event("tool", {
        "tool":      tool,
        "success":   success,
        "timed_out": timed_out,
        "reason":    reason,
    })


def log_validation(*, valid: bool, reason: str, response_snapshot: str | None = None) -> None:
    data: dict = {"valid": valid, "reason": reason}
    if not valid and response_snapshot:
        data["snapshot"] = response_snapshot[:300]   # truncate — no bloat
    log_event("validation", data)


def debug_view(
    *,
    intent_result,
    context: dict,
    act_decision: bool,
    act_reason: str,
    validation_result=None,
) -> dict | None:
    if not is_debug():
        return None
    out: dict = {
        "debug": {
            "intent":     intent_result.intent,
            "confidence": round(intent_result.confidence, 3),
            "multiple":   intent_result.multiple,
            "context":    {k: v for k, v in context.items()
                          if k not in {"user_confirmed"}},
            "act":        act_decision,
            "act_reason": act_reason,
        }
    }
    if validation_result is not None:
        out["debug"]["validation"] = {
            "valid":  validation_result.valid,
            "reason": validation_result.reason,
        }
    return out


_setup()