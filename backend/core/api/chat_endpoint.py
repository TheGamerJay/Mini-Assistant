"""
api/chat_endpoint.py — CEO Router API: full request lifecycle.

Endpoints:
    POST /api/ceo/route   — decision only (no execution); useful for pre-flight UI
    POST /api/ceo/chat    — full lifecycle: route → execute → validate → return

Full lifecycle (POST /api/ceo/chat):
    1. Receive request body
    2. Normalize into RouterRequest
    3. Call CEO Router → RouterDecision
    4. If clarification needed → return immediately (no execution)
    5. Execute plan via module_executor.execute_plan()
    6. Return: decision + result + validation + events

Response shape (POST /api/ceo/chat):
    {
        "action":     "respond" | "clarify",
        "decision":   RouterDecision.to_dict(),
        "result":     dict | None,         # module output
        "validation": dict | None,         # _validation from result
        "events":     list[dict],          # all events from routing + execution
        "elapsed_ms": float,
        # if clarify:
        "question":   str,
    }

Rules:
- CEO Router events + executor events are merged into a single "events" list
- clarification returns immediately — no execute_plan() call
- module error is surfaced in result.status = "error", not as HTTP 500
- only unrecoverable pipeline failures return HTTP 500
"""

from __future__ import annotations

import logging
import time
from typing import Optional

log = logging.getLogger("ceo_router.api")

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel

    router = APIRouter(prefix="/api/ceo", tags=["ceo-router"])

    # ── Shared request schema ──────────────────────────────────────────────────
    class ChatRouteRequest(BaseModel):
        message:    str
        user_id:    Optional[str] = None
        session_id: Optional[str] = None
        attachments: list = []
        mode_hint:  Optional[str] = None
        user_tier:  str = "free"
        context_available: dict = {}

    # ── POST /api/ceo/route — decision only ───────────────────────────────────
    @router.post("/route")
    async def ceo_route(body: ChatRouteRequest):
        """
        Run a message through the CEO Router and return the decision.
        No execution happens here — decision only.
        Useful for pre-flight checks or clarification UIs.
        """
        req, decision = await _route(body)
        return decision.to_dict()

    # ── POST /api/ceo/chat — full lifecycle ────────────────────────────────────
    @router.post("/chat")
    async def ceo_chat(body: ChatRouteRequest):
        """
        Full CEO pipeline: route → execute → validate → return.
        """
        t0 = time.perf_counter()

        try:
            req, decision = await _route(body)
        except HTTPException:
            raise
        except Exception as exc:
            log.error("CEO routing failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Routing failed: {exc}")

        routing_events: list[dict] = []  # CEO router doesn't return events in decision yet

        # ── Clarification short-circuit ────────────────────────────────────────
        if decision.needs_user_input:
            return {
                "action":     "clarify",
                "question":   decision.clarification_question,
                "decision":   decision.to_dict(),
                "result":     None,
                "validation": None,
                "events":     routing_events,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
            }

        # ── Execute plan ───────────────────────────────────────────────────────
        try:
            from ..execution.module_executor import execute_plan
            result = await execute_plan(
                decision   = decision,
                user_id    = body.user_id,
                session_id = body.session_id,
            )
        except Exception as exc:
            log.error("CEO execution failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Execution failed: {exc}")

        # ── Collect events + checkpoints ──────────────────────────────────────
        exec_events:   list[dict] = result.pop("_events", [])
        exec_elapsed:  float      = result.pop("_elapsed_ms", 0.0)
        checkpoints:   list[dict] = result.pop("_checkpoints", [])
        all_events = routing_events + exec_events

        # ── Apply tier output filter (Phase 47) ───────────────────────────────
        try:
            from ..execution.tier_output_filter import apply_tier_filter
            result = apply_tier_filter(
                module          = decision.selected_module,
                result          = result,
                tier_visibility = decision.tier_visibility,
            )
        except Exception:
            pass  # filtering is non-critical

        # ── Extract validation result ──────────────────────────────────────────
        validation = result.pop("_validation", None)

        # ── Determine action ───────────────────────────────────────────────────
        # A clarify action from the executor means clarification was embedded in plan
        if result.get("action") == "clarify":
            clarify_events = result.pop("_events", [])
            return {
                "action":     "clarify",
                "question":   result.get("question"),
                "decision":   decision.to_dict(),
                "result":     None,
                "validation": None,
                "events":     routing_events + clarify_events,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
            }

        total_elapsed = round((time.perf_counter() - t0) * 1000, 1)

        response = {
            "action":      "respond",
            "decision":    decision.to_dict(),
            "result":      result,
            "validation":  validation,
            "events":      all_events,
            "checkpoints": checkpoints,
            "elapsed_ms":  total_elapsed,
        }

        # Store X-Ray data for admin inspection
        if body.session_id:
            try:
                from ..api.xray_endpoint import store_xray_data
                store_xray_data(body.session_id, response)
            except Exception:
                pass

        return response

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _route(body: ChatRouteRequest):
        """Normalize body → RouterRequest, run CEO Router, return (req, decision)."""
        from ..router_types import RouterRequest
        from ..ceo_router   import route_request

        req = RouterRequest(
            message           = body.message,
            user_id           = body.user_id,
            session_id        = body.session_id,
            attachments       = body.attachments,
            mode_hint         = body.mode_hint,
            user_tier         = body.user_tier,
            context_available = body.context_available or {
                "task_assist":      True,
                "campaign_lab":     True,
                "web_intelligence": True,
            },
        )

        try:
            decision = await route_request(req)
        except Exception as exc:
            log.error("CEO route_request failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc))

        return req, decision

except ImportError:
    # FastAPI not available (e.g. during unit tests) — skip router registration
    router = None
    log.warning("api/chat_endpoint: FastAPI not available — endpoint not registered")
