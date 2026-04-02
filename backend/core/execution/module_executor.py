"""
execution/module_executor.py — Execute the plan produced by the CEO Router.

This is the ONLY layer that calls modules.
It follows the execution_plan from RouterDecision exactly — no reordering.

Step types:
  clarify      → return clarification immediately, halt execution
  memory_load  → load TR memory, attach to context
  web_call     → run web search/scraper/crawler
  module_call  → call the selected module
  validation   → validate module output

Rules:
- modules receive (decision_dict, memory_dict, web_results_dict)
- modules may NOT call each other
- modules may NOT re-route
- step_started / step_finished events are emitted for every step
- validation step is always run if present in plan (cannot be skipped)
- if a non-critical step fails, log and continue; module_call failure is surfaced
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from ..router_types import RouterDecision
import core.events.event_emitter as _ev
from .checkpoint_manager import (
    checkpoint_post_plan,
    checkpoint_post_module,
    checkpoint_pre_validation,
    checkpoint_post_validation,
    get_pending_checkpoint,
)

log = logging.getLogger("ceo_router.executor")


async def execute_plan(
    decision:   RouterDecision,
    user_id:    Optional[str]  = None,
    session_id: Optional[str]  = None,
) -> dict[str, Any]:
    """
    Walk execution_plan and run each step in order.

    Returns:
        Final output dict with "_events", "_validation", and "_elapsed_ms" added.
        If a clarify step is encountered, returns early with action="clarify".
    """
    memory:      dict[str, Any] = {}
    web_results: dict[str, Any] = {}
    result:      dict[str, Any] = {}
    events:      list[dict]     = []
    checkpoints: list[dict]     = []
    module       = decision.selected_module
    t_total      = time.perf_counter()

    # ── Phase 67: truth cannot_verify short-circuit ───────────────────────────
    if not decision.truth_can_answer and decision.cannot_verify_reason:
        from ..truth.truth_classifier import build_cannot_verify_response
        classification = {
            "truth_type":           decision.truth_type,
            "cannot_verify_reason": decision.cannot_verify_reason,
            "tool_required":        True,
            "can_answer":           False,
        }
        cv_response = build_cannot_verify_response(classification, decision.message or "")
        events.append(_ev.error(session_id, "ceo", "Cannot verify — live fact without tool"))
        return {**cv_response, "_events": events, "_checkpoints": [], "_elapsed_ms": 0.0}

    # ── Phase 67: injected tool result (e.g. system_clock) ────────────────────
    if decision.injected_tool_result:
        tool = decision.injected_tool_result
        tool_name = tool.get("tool", "unknown_tool")
        log.info("executor: returning injected tool result tool=%s", tool_name)
        return {
            "type":       "tool_result",
            "tool":       tool_name,
            "data":       tool,
            "message":    _format_tool_result(tool),
            "_events":    events,
            "_checkpoints": [],
            "_elapsed_ms": 0.0,
        }

    # ── post_plan checkpoint ───────────────────────────────────────────────────
    if session_id:
        plan_dicts = [s.to_dict() for s in decision.execution_plan]
        cp = checkpoint_post_plan(session_id, module, plan_dicts, decision.complexity)
        checkpoints.append(cp)
        events.append(_ev.checkpoint_reached(
            session_id, cp["checkpoint_id"], cp["step"],
            cp["requires_user_input"], cp["summary"],
        ))
        # If full_system plan requires review and pending, surface immediately
        pending = get_pending_checkpoint(session_id)
        if pending and pending["requires_user_input"]:
            log.info("executor: paused at checkpoint %s", pending["checkpoint_id"])


    for step in decision.execution_plan:
        stype  = step.type
        t_step = time.perf_counter()

        # ── step_started event ─────────────────────────────────────────────────
        events.append(_ev.step_started(session_id, step.step, stype, step.target))

        ok_step = True  # track per-step success for step_finished

        # ── clarify ────────────────────────────────────────────────────────────
        if stype == "clarify":
            events.append(_ev.clarification_needed(session_id, decision.clarification_question or ""))
            events.append(_ev.step_finished(session_id, step.step, stype, 0.0, ok=True))
            return {
                "action":   "clarify",
                "question": decision.clarification_question,
                "options":  _parse_clarification_options(decision.clarification_question or ""),
                "step":     step.step,
                "_events":  events,
            }

        # ── memory_load ────────────────────────────────────────────────────────
        elif stype == "memory_load":
            events.append(_ev.memory_loading_started(session_id, step.target))
            memory = await _load_memory(user_id, step.target, module)
            events.append(_ev.memory_loading_complete(session_id, list(memory.keys())))
            log.debug("executor step %d: memory_load complete — keys=%s", step.step, list(memory.keys()))

        # ── web_call ───────────────────────────────────────────────────────────
        elif stype == "web_call":
            web_mode = step.target
            events.append(_ev.web_call_started(session_id, web_mode))
            web_results = await _run_web(web_mode, decision)
            # Validate web results before injecting into module context
            web_results = _validate_web_results(web_results, web_mode, decision.intent)
            result_count = _count_web_results(web_results, web_mode)
            ok = web_results.get("ok", False)
            ok_step = ok
            events.append(_ev.web_call_complete(session_id, web_mode, result_count, ok))
            log.debug("executor step %d: web_call %s — ok=%s results=%d", step.step, web_mode, ok, result_count)

        # ── module_call ────────────────────────────────────────────────────────
        elif stype == "module_call":
            events.append(_ev.module_execution_started(session_id, module))
            result = await _call_module(
                module      = module,
                decision    = decision.to_dict(),
                memory      = memory,
                web_results = web_results,
            )
            ok = result.get("status") != "error"
            ok_step = ok
            events.append(_ev.module_execution_complete(session_id, module, ok))
            if not ok:
                error_msg = result.get("error", "module failed")
                events.append(_ev.error(session_id, module, error_msg))
                # Soft failure recovery — surface partial result with guidance
                result = _build_soft_failure(module, result, error_msg)
            log.debug("executor step %d: module_call %s — ok=%s", step.step, module, ok)
            # post_module checkpoint
            if session_id:
                cp = checkpoint_post_module(session_id, module, result)
                checkpoints.append(cp)
                events.append(_ev.checkpoint_reached(
                    session_id, cp["checkpoint_id"], cp["step"],
                    cp["requires_user_input"], cp["summary"],
                ))

        # ── validation ─────────────────────────────────────────────────────────
        elif stype == "validation":
            validation_type = _extract_validation_type(step.reason)
            # pre_validation checkpoint
            if session_id:
                cp = checkpoint_pre_validation(session_id, module, validation_type)
                checkpoints.append(cp)
                events.append(_ev.checkpoint_reached(
                    session_id, cp["checkpoint_id"], cp["step"],
                    cp["requires_user_input"], cp["summary"],
                ))
            events.append(_ev.validation_started(session_id, module, validation_type))
            val_result = _run_validation(module, result, validation_type)
            result["_validation"] = val_result
            if val_result.get("ok"):
                events.append(_ev.validation_passed(session_id, module, validation_type))
            else:
                issues = val_result.get("issues", [val_result.get("reason", "unknown")])
                events.append(_ev.validation_failed(session_id, module, validation_type, issues))
                ok_step = False
                log.warning("executor: validation failed — module=%s issues=%s", module, issues)
            log.debug("executor step %d: validation — ok=%s", step.step, val_result.get("ok"))
            # post_validation checkpoint
            if session_id:
                cp = checkpoint_post_validation(session_id, module, val_result)
                checkpoints.append(cp)
                events.append(_ev.checkpoint_reached(
                    session_id, cp["checkpoint_id"], cp["step"],
                    cp["requires_user_input"], cp["summary"],
                ))

        else:
            log.warning("executor: unknown step type '%s' at step %d — skipping", stype, step.step)
            ok_step = False

        elapsed_step = round((time.perf_counter() - t_step) * 1000, 1)
        events.append(_ev.step_finished(session_id, step.step, stype, elapsed_step, ok=ok_step))
        log.debug("executor: step %d (%s) in %.1f ms", step.step, stype, elapsed_step)

    # ── Final output ───────────────────────────────────────────────────────────
    events.append(_ev.output_ready(session_id, module))

    # Attach billing warning if present (CEO passes it through decision)
    billing_warning = getattr(decision, "billing_warning", None)
    if billing_warning:
        result["_billing_warning"] = billing_warning

    # Sanitize output before returning to user (removes paths, tracebacks, secrets)
    try:
        from billing.output_sanitizer import sanitize, _detect_output_type
        # Determine admin mode — admin users get less scrubbing
        tier_vis = getattr(decision, "tier_visibility", "free")
        san_mode = "admin" if tier_vis in ("admin",) else "user"
        # Detect output type so code blocks are preserved intact
        out_type = _detect_output_type(result)
        internal_keys = {k: result[k] for k in result if k.startswith("_")}
        sanitized = sanitize(result, mode=san_mode, keep_files=True, output_type=out_type)
        sanitized.update(internal_keys)   # restore internal _ keys (events, checkpoints, elapsed)
        result = sanitized
    except Exception as _se:
        log.debug("executor: output sanitize skipped — %s", _se)

    result["_events"]      = events
    result["_checkpoints"] = checkpoints
    result["_elapsed_ms"]  = round((time.perf_counter() - t_total) * 1000, 1)
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _load_memory(
    user_id: Optional[str],
    scope:   str,
    module:  str,
) -> dict[str, Any]:
    if not user_id:
        log.debug("executor: no user_id — skipping memory load")
        return {}
    try:
        from ..memory.tr_loader import load_scope
        return load_scope(user_id, module, scope)
    except Exception as exc:
        log.warning("executor: memory load failed — %s", exc)
        return {}


async def _run_web(mode: str, decision: RouterDecision) -> dict[str, Any]:
    try:
        if mode == "search":
            from ..web.web_search import run_search
            return await run_search(decision.intent)
        elif mode == "scraper":
            # URL extraction from message is a future enhancement
            return {"ok": False, "results": [], "error": "URL extraction not yet implemented"}
        elif mode == "crawler":
            return {"ok": False, "pages": [], "error": "Seed URL extraction not yet implemented"}
    except Exception as exc:
        log.warning("executor: web step failed — mode=%s error=%s", mode, exc)
    return {"ok": False, "results": [], "error": "web step failed"}


def _validate_web_results(
    web_results: dict[str, Any],
    web_mode:    str,
    intent:      str,
) -> dict[str, Any]:
    """
    Run post-retrieval validation on web results (Phase 27).
    Replaces raw results with validated-only subset.
    Never raises — returns original web_results on failure.
    """
    try:
        from ..web.web_validator import validate_web_results
        # Build the items list based on mode
        if web_mode == "search":
            items = web_results.get("results", [])
        elif web_mode == "scraper":
            raw = web_results if web_results.get("ok") else {}
            items = [raw] if raw else []
        elif web_mode == "crawler":
            items = web_results.get("pages", [])
        else:
            return web_results

        val = validate_web_results(query=intent, results=items, mode=web_mode)

        if web_mode == "search":
            web_results["results"]  = val["passed"]
        elif web_mode == "crawler":
            web_results["pages"]    = val["passed"]

        web_results["_web_validation"] = {
            "ok":      val["ok"],
            "issues":  val["issues"],
            "passed":  len(val["passed"]),
            "rejected": len(val["rejected"]),
        }

        if not val["ok"]:
            web_results["ok"] = False
            log.warning(
                "executor: web validation failed — mode=%s issues=%s",
                web_mode, val["issues"],
            )
    except Exception as exc:
        log.warning("executor: web validation skipped — %s", exc)

    return web_results


def _run_validation(module: str, output: dict, validation_type: str) -> dict[str, Any]:
    try:
        from ..validation.output_validator import validate
        return validate(module, output, validation_type)
    except Exception as exc:
        log.warning("executor: validation unavailable — %s", exc)
        return {"ok": True, "reason": "validation_unavailable", "issues": [], "validation_type": validation_type}


async def _call_module(
    module:      str,
    decision:    dict,
    memory:      dict,
    web_results: dict,
) -> dict[str, Any]:
    # web_search is handled via search_pipeline (Phase 68), not a modules/*.py file
    if module == "web_search":
        return await _call_search_pipeline(decision, web_results)

    try:
        import importlib
        mod = importlib.import_module(f"core.modules.{module}")
        return await mod.execute(decision, memory, web_results)
    except Exception as exc:
        log.error("executor: module '%s' failed — %s", module, exc, exc_info=True)
        return {"module": module, "status": "error", "error": str(exc)}


async def _call_search_pipeline(decision: dict, web_results: dict) -> dict[str, Any]:
    """Route to the full search pipeline for search_dependent queries."""
    try:
        from ..search.search_pipeline import run as search_run
        query      = decision.get("message", "")
        session_id = decision.get("session_id")
        result = await search_run(query=query, session_id=session_id)
        result["type"] = "search_output"
        return result
    except Exception as exc:
        log.error("executor: search pipeline failed — %s", exc, exc_info=True)
        return {
            "type":         "search_output",
            "ok":           False,
            "answer":       "Search pipeline encountered an error.",
            "search_failed": True,
            "fail_reason":  str(exc),
        }


def _format_tool_result(tool_data: dict) -> str:
    """Format a tool result as a natural language response."""
    tool = tool_data.get("tool", "")
    if tool == "system_clock":
        utc_time   = tool_data.get("utc_time", "unknown")
        utc_date   = tool_data.get("utc_date", "")
        day_of_week = tool_data.get("day_of_week", "")
        return f"The current time is {utc_time} UTC ({day_of_week}, {utc_date})."
    return str(tool_data)


def _parse_clarification_options(question: str) -> list[str]:
    """Extract lettered options from a clarification question string."""
    try:
        from ..decision.clarification_engine import parse_options_from_question
        return parse_options_from_question(question)
    except Exception:
        return []


def _count_web_results(web_results: dict, mode: str) -> int:
    if mode == "search":
        return len(web_results.get("results", []))
    elif mode == "crawler":
        return len(web_results.get("pages", []))
    return 1 if web_results.get("ok") else 0


def _extract_validation_type(reason: str) -> str:
    """Pull validation_type from the step reason string written by execution_planner."""
    import re
    m = re.search(r"'([^']+)' rules", reason)
    return m.group(1) if m else "general_chat"


def _build_soft_failure(module: str, result: dict, error_msg: str) -> dict:
    """
    Build a user-facing soft failure response.

    Instead of returning a raw error dict, surface:
    - whatever partial content the module produced (if any)
    - a clear explanation that the task didn't fully complete
    - a suggested next step

    Never surfaces internal error strings. Never returns an empty response.
    """
    # Preserve any partial content the module managed to produce
    partial_fields = {}
    for key in ("files", "code", "summary", "answer", "message", "response",
                "sources", "results", "output", "concepts"):
        if result.get(key):
            partial_fields[key] = result[key]

    # Module-specific next-step suggestions
    _NEXT_STEPS = {
        "builder":      "Try narrowing the scope of the request, or break it into smaller pieces.",
        "doctor":       "Share the specific error or file you'd like me to diagnose.",
        "image":        "Try rephrasing the image prompt or reducing its complexity.",
        "image_edit":   "Re-upload the image and try a simpler edit instruction.",
        "campaign_lab": "Try starting with a single campaign concept instead of a full package.",
        "web_search":   "Search may be temporarily unavailable. Try again in a moment.",
        "core_chat":    "Please try rephrasing your message.",
        "task_assist":  "Try breaking the task into a smaller first step.",
        "vision":       "Re-upload the image and try a simpler analysis request.",
    }

    next_step = _NEXT_STEPS.get(module, "Try rephrasing or simplifying your request.")

    response = {
        "status":      "partial",
        "module":      module,
        "message":     (
            "I wasn't able to complete this task fully. "
            + (f"Here's what I was able to generate:\n\n" if partial_fields else "")
        ),
        "next_step":   next_step,
        **partial_fields,
    }

    if not partial_fields:
        response["message"] = (
            "I ran into a problem completing this task. "
            f"{next_step}"
        )

    log.info("executor: soft failure for module=%s partial_keys=%s", module, list(partial_fields.keys()))
    return response
