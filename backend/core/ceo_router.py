"""
core/ceo_router.py — CEO Router: the ONLY entry point for all user requests.

Every request flows through route_request(). Nothing executes before CEO decides.

Flow:
  1.  emit: request_received
  2.  detect intent             (detection/intent_classifier.py)
  3.  detect complexity         (detection/complexity_detector.py)
  4.  select module             (decision/module_selector.py)
  5.  decide tier visibility    (decision/tier_controller.py)
  6.  decide memory             (decision/memory_decider.py)
  7.  decide web                (decision/web_decider.py)
  8.  check clarification       (decision/clarification_engine.py)
  9.  build execution plan      (planner/execution_planner.py)
  10. emit: decision_complete
  11. return RouterDecision

CEO does NOT execute. CEO decides only.
No module self-triggers. No bypass. No shortcut.

Integration with image_system streaming:
  - call route_request() first
  - pass RouterDecision to module_executor.execute_plan()
  - module_executor calls the existing pipelines in order
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from .router_types    import RouterRequest, RouterDecision
from .router_context  import RouterContext

from .detection.intent_classifier    import detect_intent
from .detection.complexity_detector  import detect_complexity

from .decision.module_selector       import select_module
from .decision.memory_decider        import decide_memory
from .decision.web_decider           import decide_web
from .decision.clarification_engine  import check_clarification
from .decision.tier_controller       import decide_tier_visibility

from .planner.execution_planner      import build_execution_plan
from .truth.truth_classifier         import classify as classify_truth, get_current_time

import core.events.event_emitter as _ev

log = logging.getLogger("ceo_router")

# ---------------------------------------------------------------------------
# Billing + protection (lazy imports to avoid circular imports at module load)
# ---------------------------------------------------------------------------

def _billing_engine():
    from billing.ceo_billing_engine import process_request
    return process_request

def _probe_detector():
    from billing.probe_detector import detect, build_probe_response
    return detect, build_probe_response

def _cost_resolver():
    from billing.cost_resolver import resolve_action_type
    return resolve_action_type


async def route_request(request: RouterRequest) -> RouterDecision:
    """
    Main CEO Router entry point.

    Accepts a RouterRequest, returns a RouterDecision.
    No execution happens here.
    """
    t0 = time.perf_counter()
    events: list[dict] = []

    # ── Step 0a: rate limiting (before anything else) ────────────────────────
    if request.user_id:
        try:
            from billing.rate_limiter import check_rate_limit
            rl = check_rate_limit(request.user_id, request.user_tier)
            if not rl["allowed"]:
                log.info(
                    "CEO: rate limit user=%s retry_after=%ds",
                    request.user_id, rl["retry_after_seconds"],
                )
                return RouterDecision(
                    intent="rate_limited",
                    complexity="simple",
                    selected_module="core_chat",
                    requires_memory=False, memory_scope=None,
                    requires_web=False, web_mode=None,
                    requires_backend=False,
                    needs_user_input=True,
                    clarification_question=(
                        f"You're sending requests too quickly. "
                        f"Please wait {rl['retry_after_seconds']} second(s) and try again."
                    ),
                    execution_plan=[],
                    validation_required=False,
                    tier_visibility="free",
                    message=request.message,
                    truth_type="stable_knowledge",
                    truth_can_answer=True,
                )
        except Exception as _rle:
            log.debug("CEO: rate limit check error (non-fatal) — %s", _rle)

    # ── Step 0b: probe detection (before any processing) ─────────────────────
    if request.message:
        try:
            detect, build_probe_response = _probe_detector()
            probe = detect(request.message)
            if probe["is_probe"]:
                log.info("CEO: probe detected type=%s — returning safe response", probe["probe_type"])
                events.append(_ev.emit(
                    "probe_detected", "ceo", "blocked",
                    f"Internal probe detected: {probe['probe_type']}",
                    session_id=request.session_id,
                ))
                safe = build_probe_response(probe)
                # Return as a RouterDecision with needs_user_input so executor skips
                return RouterDecision(
                    intent="probe_response",
                    complexity="simple",
                    selected_module="core_chat",
                    requires_memory=False, memory_scope=None,
                    requires_web=False, web_mode=None,
                    requires_backend=False,
                    needs_user_input=True,
                    clarification_question=safe["message"],
                    execution_plan=[],
                    validation_required=False,
                    tier_visibility="free",
                    message=request.message,
                    truth_type="stable_knowledge",
                    truth_can_answer=True,
                )
        except Exception as _pe:
            log.debug("CEO: probe check error (non-fatal) — %s", _pe)

    # ── Step 1: request received ──────────────────────────────────────────────
    ctx = RouterContext(
        message          = request.message,
        user_tier        = request.user_tier,
        has_attachments  = bool(request.attachments),
        mode_hint        = request.mode_hint,
        session_id       = request.session_id,
        user_id          = request.user_id,
    )
    events.append(_ev.request_received(ctx.session_id, ctx.user_tier, ctx.has_attachments))

    # ── Step 2: detect intent ─────────────────────────────────────────────────
    primary, secondary, confidence = detect_intent(request.message, request.attachments)
    ctx.primary_intent    = primary
    ctx.secondary_intent  = secondary
    ctx.intent_confidence = confidence
    events.append(_ev.intent_detected(ctx.session_id, primary, secondary, confidence))

    # ── Step 3: detect complexity ─────────────────────────────────────────────
    complexity, is_underspecified = detect_complexity(request.message)
    ctx.complexity        = complexity
    ctx.is_underspecified = is_underspecified
    events.append(_ev.complexity_detected(ctx.session_id, complexity, is_underspecified))

    # ── Step 3b: classify truth type ─────────────────────────────────────────
    truth = classify_truth(request.message)
    ctx.truth_type     = truth["truth_type"]
    ctx.tool_required  = truth["tool_required"]
    ctx.truth_can_answer = truth["can_answer"]

    # Handle live_current time queries directly (system_clock tool is always available)
    if truth["truth_type"] == "live_current" and truth["tool_name"] == "system_clock":
        time_data = get_current_time()
        ctx.injected_tool_result = time_data
        log.debug("CEO: injected system_clock result for live_current query")

    # If truth can't be answered without a tool → note it for module_executor to surface
    if not truth["can_answer"]:
        ctx.cannot_verify_reason = truth.get("cannot_verify_reason", "")
        log.info("CEO: truth_type=%s cannot_answer — will surface cannot_verify response", truth["truth_type"])

    # ── Step 4: select module ─────────────────────────────────────────────────
    module = select_module(primary)

    # Override: search_dependent → route to web_search module if available
    if truth["truth_type"] in ("search_dependent", "mixed") and truth["can_answer"]:
        if module == "general_chat":
            module  = "web_search"
            primary = "search"
            log.info("CEO: search_dependent → routing to web_search")

    # ── Step 5: decide tier visibility ────────────────────────────────────────
    tier_vis = decide_tier_visibility(module, request.user_tier)
    if tier_vis == "blocked":
        log.info("CEO: module %s blocked for free tier — routing to core_chat", module)
        module  = "core_chat"
        primary = "general_chat"
        tier_vis = "free"

    ctx.selected_module = module
    ctx.tier_visibility = tier_vis
    events.append(_ev.module_selected(ctx.session_id, module, tier_vis))
    events.append(_ev.tier_decided(ctx.session_id, tier_vis))

    # ── Step 6: decide memory ─────────────────────────────────────────────────
    requires_memory, memory_scope = decide_memory(module, primary, request.message)
    ctx.requires_memory = requires_memory
    ctx.memory_scope    = memory_scope

    mem_available = False
    if requires_memory and memory_scope and request.user_id:
        try:
            from .memory.tr_loader import memory_available as _mem_avail
            mem_available = _mem_avail(request.user_id, module, memory_scope)
        except Exception:
            mem_available = False

    # ── Step 7: decide web ────────────────────────────────────────────────────
    requires_web, web_mode = decide_web(request.message, primary, mem_available)
    ctx.requires_web = requires_web
    ctx.web_mode     = web_mode
    if requires_web and web_mode:
        events.append(_ev.web_needed(ctx.session_id, web_mode))

    # ── Step 8: check clarification ───────────────────────────────────────────
    needs_input, clarification_q = check_clarification(
        intent            = primary,
        complexity        = complexity,
        is_underspecified = is_underspecified,
        has_attachments   = ctx.has_attachments,
        requires_memory   = requires_memory,
        memory_available  = mem_available,
    )
    ctx.needs_user_input       = needs_input
    ctx.clarification_question = clarification_q
    if needs_input and clarification_q:
        events.append(_ev.clarification_needed(ctx.session_id, clarification_q))

    # ── Step 8b: CEO BILLING GATE (FAIL-CLOSED) ──────────────────────────────
    # Billing runs BEFORE execution_planner. If blocked → no plan, no execution.
    billing_result: dict = {"status": "approved", "credits_used": 0, "warning": None}
    if request.user_id and not needs_input:
        try:
            process_billing = _billing_engine()
            resolve_atype   = _cost_resolver()
            meta = {
                "complexity":      ctx.complexity,
                "has_attachment":  ctx.has_attachments,
                "is_regeneration": False,
            }
            action_type = resolve_atype(module, meta)
            billing_result = await process_billing(
                user_id       = request.user_id,
                module        = module,
                session_id    = request.session_id,
                metadata      = meta,
                action_type   = action_type,
                authorization = request.authorization,
            )
            if billing_result["status"] == "blocked":
                log.info(
                    "CEO: billing BLOCKED user=%s module=%s reason=%s",
                    request.user_id, module, billing_result.get("block_reason"),
                )
                events.append(_ev.emit(
                    "billing_blocked", "ceo", "blocked",
                    f"Billing blocked: {billing_result.get('block_reason', 'insufficient_credits')}",
                    session_id=request.session_id,
                ))
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
                ctx.events_emitted = events
                return RouterDecision(
                    intent="billing_blocked",
                    complexity="simple",
                    selected_module="core_chat",
                    requires_memory=False, memory_scope=None,
                    requires_web=False, web_mode=None,
                    requires_backend=False,
                    needs_user_input=True,
                    clarification_question=billing_result.get("block_message", ""),
                    execution_plan=[],
                    validation_required=False,
                    tier_visibility="free",
                    message=request.message,
                    truth_type="stable_knowledge",
                    truth_can_answer=True,
                )
        except Exception as _be:
            # FAIL CLOSED — billing exception blocks execution
            log.error("CEO: billing exception — BLOCKING execution: %s", _be, exc_info=True)
            return RouterDecision(
                intent="billing_error",
                complexity="simple",
                selected_module="core_chat",
                requires_memory=False, memory_scope=None,
                requires_web=False, web_mode=None,
                requires_backend=False,
                needs_user_input=True,
                clarification_question="Billing system unavailable. Please try again in a moment.",
                execution_plan=[],
                validation_required=False,
                tier_visibility="free",
                message=request.message,
                truth_type="stable_knowledge",
                truth_can_answer=True,
            )

    # ── Step 9: build execution plan ──────────────────────────────────────────
    plan = build_execution_plan(ctx)
    step_types = [s.type for s in plan]
    events.append(_ev.plan_built(ctx.session_id, len(plan), step_types))

    # ── Step 10: assemble decision ────────────────────────────────────────────
    requires_backend = (complexity == "full_system" and not needs_input)

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    events.append(_ev.decision_complete(ctx.session_id, module, primary, elapsed_ms))

    # ── Step 9b: load session context (Phase 62) ─────────────────────────────
    session_ctx: dict | None = None
    if request.session_id:
        try:
            from context.context_store import load as load_ctx
            mode = request.mode_hint or "chat"
            if mode in ("chat", "image_edit"):
                session_ctx = load_ctx(request.session_id, mode)
        except Exception:
            pass

    decision = RouterDecision(
        intent                 = primary,
        complexity             = complexity,
        selected_module        = module,
        requires_memory        = requires_memory,
        memory_scope           = memory_scope,
        requires_web           = requires_web,
        web_mode               = web_mode,
        requires_backend       = requires_backend,
        needs_user_input       = needs_input,
        clarification_question = clarification_q,
        execution_plan         = plan,
        validation_required    = True,
        tier_visibility        = tier_vis,
        message                = request.message,
        session_id             = request.session_id,
        attachments            = request.attachments,
        truth_type             = ctx.truth_type,
        truth_can_answer       = ctx.truth_can_answer,
        cannot_verify_reason   = ctx.cannot_verify_reason,
        injected_tool_result   = ctx.injected_tool_result,
        session_context        = session_ctx,
        billing_status         = billing_result.get("status", "approved"),
        billing_warning        = billing_result.get("warning"),
    )

    ctx.events_emitted = events

    log.info(
        "CEO decision | intent=%-18s module=%-18s complexity=%-12s tier=%-12s ms=%.1f",
        primary, module, complexity, tier_vis, elapsed_ms,
    )

    return decision
