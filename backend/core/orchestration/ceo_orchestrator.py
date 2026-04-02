"""
orchestration/ceo_orchestrator.py — CEO-controlled multi-brain orchestration.

THE ONLY ENTRY POINT for Builder Mode multi-brain execution.

CEO controls all routing. NO brain-to-brain communication. NO autonomous action.

Execution flow:
  User → CEO → Builder → CEO
  CEO → Hands → CEO (if fail: CEO → Builder → CEO → Hands → CEO)
  CEO → Vision → CEO (if fail: CEO → Builder → CEO → Vision → CEO)
  If deeper issue: CEO → Doctor → CEO → (ask user) → Builder → re-verify

All results return to CEO before the next step runs.

Max retry limits (anti-loop):
  Builder:  3 attempts
  Hands QA: 2 attempts before escalating to Doctor
  Vision QA: 2 attempts before escalating to Doctor
  Doctor:   1 attempt (diagnosis only)

Output: structured orchestration result for chat_endpoint to return.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .state_manager import OrchestrationState, StepRecord, get_or_create
from .brain_router import call_builder, call_hands, call_vision, call_doctor
from .approval_gate import request_approval, build_approval_message

log = logging.getLogger("ceo_router.orchestrator")

_MAX_BUILD_RETRIES  = 3
_MAX_QA_RETRIES     = 2
_MAX_DOCTOR_RETRIES = 1


async def execute_builder_task(
    session_id:  str,
    decision:    dict[str, Any],
    memory:      dict[str, Any],
    web_results: dict[str, Any],
) -> dict[str, Any]:
    """
    CEO-controlled multi-brain build + QA loop.

    Returns a structured result dict ready for the API response.
    If approval is needed, returns status="needs_approval" — execution pauses.
    """
    goal       = decision.get("message", "")
    complexity = decision.get("complexity", "simple")
    state      = get_or_create(session_id, goal, complexity)
    state.current_step = "orchestration_started"

    log.info("orchestrator: started session=%s complexity=%s", session_id, complexity)

    # ── Step 1: Build loop ─────────────────────────────────────────────────────
    build_result = await _build_loop(state, decision, memory, web_results)

    if build_result["status"] == "fail" and state.get_retry("builder") >= _MAX_BUILD_RETRIES:
        return await _escalate_to_doctor(
            state, decision, memory,
            issue    = build_result["summary"],
            evidence = build_result["evidence"],
        )

    if build_result["status"] == "fail":
        return _needs_input_response(state, "Builder could not complete the task. More details needed.")

    # ── Step 2: Functional QA loop (Hands) ────────────────────────────────────
    hands_result = await _qa_loop(
        state, "hands", build_result, decision, memory,
        call_fn = call_hands,
    )

    if hands_result["status"] == "fail":
        return await _escalate_to_doctor(
            state, decision, memory,
            issue    = hands_result["summary"],
            evidence = hands_result["evidence"],
        )

    # ── Step 3: Visual QA loop (Vision) — only for full_system / frontend ─────
    if _has_visual_output(build_result):
        vision_result = await _qa_loop(
            state, "vision", build_result, decision, memory,
            call_fn = call_vision,
        )
        if vision_result["status"] == "fail":
            return await _escalate_to_doctor(
                state, decision, memory,
                issue    = vision_result["summary"],
                evidence = vision_result["evidence"],
            )

    # ── Step 4: Finalize ───────────────────────────────────────────────────────
    state.current_step  = "complete"
    state.final_status  = "complete"
    state.final_result  = build_result["_raw"]
    state.end_time      = time.perf_counter()

    log.info("orchestrator: complete session=%s elapsed_ms=%.0f", session_id, state.elapsed_ms())

    return {
        "status":       "success",
        "orchestrated": True,
        "summary":      build_result["summary"],
        "brains_used":  state.brains_used(),
        "steps":        len(state.evidence_history),
        "elapsed_ms":   state.elapsed_ms(),
        **build_result["_raw"],
    }


# ---------------------------------------------------------------------------
# Loops
# ---------------------------------------------------------------------------

async def _build_loop(
    state:       OrchestrationState,
    decision:    dict[str, Any],
    memory:      dict[str, Any],
    web_results: dict[str, Any],
    fix_hint:    str = "",
) -> dict[str, Any]:
    """
    Attempt to build. Retries are handled by the caller after Doctor diagnosis.
    Returns the latest BrainResult.
    """
    state.active_brain  = "builder"
    state.current_step  = f"build_attempt_{state.get_retry('builder') + 1}"

    t0 = time.perf_counter()
    result = await call_builder(decision, memory, web_results, fix_hint=fix_hint)
    elapsed = round((time.perf_counter() - t0) * 1000, 1)

    step = StepRecord(
        step_num    = state.next_step_num(),
        brain       = "builder",
        action      = "build",
        status      = result["status"],
        summary     = result["summary"],
        confidence  = result["confidence"],
        evidence    = result["evidence"],
        elapsed_ms  = elapsed,
        reason      = "CEO routed to Builder for initial build",
        proposed_fix = result.get("proposed_fix", ""),
    )
    state.record_step(step)

    if result["status"] == "fail":
        state.increment_retry("builder")

    log.info(
        "orchestrator: build status=%s confidence=%.2f retry=%d",
        result["status"], result["confidence"], state.get_retry("builder"),
    )
    return result


async def _qa_loop(
    state:       OrchestrationState,
    qa_brain:    str,
    build_result: dict[str, Any],
    decision:    dict[str, Any],
    memory:      dict[str, Any],
    call_fn:     Any,
) -> dict[str, Any]:
    """
    Run up to _MAX_QA_RETRIES QA passes.
    On failure: attempt one re-build with QA evidence, then return result.
    Returns the final QA BrainResult.
    """
    for attempt in range(_MAX_QA_RETRIES):
        state.active_brain = qa_brain
        state.current_step = f"{qa_brain}_qa_attempt_{attempt + 1}"

        t0 = time.perf_counter()
        result = await call_fn(build_result, decision, memory)
        elapsed = round((time.perf_counter() - t0) * 1000, 1)

        step = StepRecord(
            step_num   = state.next_step_num(),
            brain      = qa_brain,
            action     = "qa_check",
            status     = result["status"],
            summary    = result["summary"],
            confidence = result["confidence"],
            evidence   = result["evidence"],
            elapsed_ms = elapsed,
            reason     = f"CEO routed to {qa_brain} for QA verification (attempt {attempt + 1})",
        )
        state.record_step(step)

        log.info("orchestrator: %s qa status=%s attempt=%d", qa_brain, result["status"], attempt + 1)

        if result["status"] == "success":
            return result

        # QA failed — try one re-build with the failure as a hint
        if attempt < _MAX_QA_RETRIES - 1:
            fix_hint = f"{qa_brain} QA failed: {'; '.join(result['evidence'][:3])}"
            build_result = await _build_loop(
                state, decision, memory, {}, fix_hint=fix_hint,
            )
            if build_result["status"] == "fail":
                return result  # build failed too — escalate

    return result  # final QA result (still failing)


async def _escalate_to_doctor(
    state:    OrchestrationState,
    decision: dict[str, Any],
    memory:   dict[str, Any],
    issue:    str,
    evidence: list[str],
) -> dict[str, Any]:
    """
    Route to Doctor for diagnosis, then surface approval request to user via CEO.
    Doctor diagnoses ONLY — never applies.
    """
    state.active_brain = "doctor"
    state.current_step = "doctor_diagnosis"

    # Search repair memory before calling Doctor
    repair_matches = _search_repair_memory(issue, decision.get("intent", "builder"))
    if repair_matches:
        state.repair_memory_used    = True
        state.repair_memory_matches = repair_matches
        state.repair_memory_guidance = repair_matches[0].get("solution_name", "")

    t0 = time.perf_counter()
    doctor_result = await call_doctor(
        issue         = issue,
        evidence      = evidence,
        decision      = decision,
        memory        = memory,
        repair_matches = repair_matches,
    )
    elapsed = round((time.perf_counter() - t0) * 1000, 1)

    step = StepRecord(
        step_num     = state.next_step_num(),
        brain        = "doctor",
        action       = "diagnose",
        status       = doctor_result["status"],
        summary      = doctor_result["summary"],
        confidence   = doctor_result["confidence"],
        evidence     = doctor_result["evidence"],
        elapsed_ms   = elapsed,
        reason       = "CEO escalated to Doctor due to repeated failure",
        proposed_fix = doctor_result.get("proposed_fix", ""),
    )
    state.record_step(step)

    if doctor_result["status"] == "fail":
        state.final_status = "failed"
        return _error_response(state, "Doctor could not diagnose the issue.", doctor_result)

    # Doctor succeeded — create approval request
    fix_steps = doctor_result["_raw"].get("files_updated", [])
    approval  = request_approval(
        session_id     = state.session_id,
        module         = "builder",
        issue          = issue,
        proposed_fix   = doctor_result.get("proposed_fix", ""),
        fix_steps      = [step.get("description", "") for step in (fix_steps if isinstance(fix_steps, list) else [])],
        affected_files = doctor_result.get("affected_files", []),
        severity       = "medium",
    )
    state.set_approval_pending(approval)
    state.final_status = "needs_approval"

    return {
        "status":           "needs_approval",
        "orchestrated":     True,
        "summary":          f"Doctor found an issue. CEO needs your approval before applying a fix.",
        "issue":            issue,
        "diagnosis":        doctor_result["_raw"].get("root_cause", ""),
        "proposed_fix":     doctor_result.get("proposed_fix", ""),
        "approval_message": build_approval_message(approval),
        "approval_id":      approval["proposal_id"],
        "brains_used":      state.brains_used(),
        "steps":            len(state.evidence_history),
        "elapsed_ms":       state.elapsed_ms(),
        "repair_memory_used": state.repair_memory_used,
    }


# ---------------------------------------------------------------------------
# Post-approval resume
# ---------------------------------------------------------------------------

async def resume_after_approval(
    session_id: str,
    decision:   dict[str, Any],
    memory:     dict[str, Any],
    web_results: dict[str, Any],
) -> dict[str, Any]:
    """
    Called by CEO after user approves a Doctor fix.
    Routes the approved fix to Builder, then re-runs full QA.
    """
    from .approval_gate import get_history

    state = get_or_create(session_id, decision.get("message", ""), decision.get("complexity", "simple"))

    # Get the most recent approved proposal
    history = get_history(session_id)
    approved = next((h for h in reversed(history) if h["status"] == "approved"), None)
    if not approved:
        return _error_response(state, "No approved fix found to resume from.", {})

    fix_hint = f"Apply this fix: {approved['proposed_fix']}"
    if approved.get("fix_steps"):
        fix_hint += f"\nSteps: {'; '.join(approved['fix_steps'][:5])}"

    log.info("orchestrator: resuming after approval session=%s", session_id)

    # Re-build with approved fix
    build_result = await _build_loop(state, decision, memory, web_results, fix_hint=fix_hint)
    if build_result["status"] == "fail":
        state.final_status = "failed"
        return _error_response(state, "Build failed after applying approved fix.", build_result)

    # Full QA again (required — even for reused fixes)
    hands_result = await _qa_loop(state, "hands", build_result, decision, memory, call_fn=call_hands)
    if hands_result["status"] == "fail":
        state.final_status = "failed"
        return _error_response(state, "Hands QA failed after fix application.", hands_result)

    if _has_visual_output(build_result):
        vision_result = await _qa_loop(state, "vision", build_result, decision, memory, call_fn=call_vision)
        if vision_result["status"] == "fail":
            state.final_status = "failed"
            return _error_response(state, "Vision QA failed after fix application.", vision_result)

    state.final_status = "complete"
    state.end_time     = time.perf_counter()

    return {
        "status":       "success",
        "orchestrated": True,
        "resumed":      True,
        "summary":      build_result["summary"],
        "brains_used":  state.brains_used(),
        "steps":        len(state.evidence_history),
        "elapsed_ms":   state.elapsed_ms(),
        **build_result["_raw"],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_visual_output(build_result: dict[str, Any]) -> bool:
    """Return True if the build has frontend files that need visual QA."""
    files = build_result.get("_raw", {}).get("files", [])
    return any(f.get("type") == "frontend" for f in files)


def _search_repair_memory(issue: str, intent: str) -> list[dict]:
    """Search repair memory for similar problems."""
    # Determine likely category from intent
    category_map = {
        "builder":    "build_pipeline",
        "debug":      "backend_logic",
        "image_edit": "image_pipeline",
    }
    category = category_map.get(intent, "unknown")

    try:
        from core.repair_memory.repair_search import search, search_all_categories
        matches = search(category, issue, top_n=3)
        if not matches:
            matches = search_all_categories(issue, top_n=2)
        return matches
    except Exception as exc:
        log.warning("orchestrator: repair memory search failed — %s", exc)
        return []


def _needs_input_response(state: OrchestrationState, message: str) -> dict[str, Any]:
    state.final_status     = "needs_input"
    state.waiting_for_input = True
    return {
        "status":       "needs_input",
        "orchestrated": True,
        "summary":      message,
        "brains_used":  state.brains_used(),
        "steps":        len(state.evidence_history),
        "elapsed_ms":   state.elapsed_ms(),
    }


def _error_response(state: OrchestrationState, message: str, brain_result: dict) -> dict[str, Any]:
    return {
        "status":       "error",
        "orchestrated": True,
        "error":        message,
        "summary":      message,
        "evidence":     brain_result.get("evidence", []),
        "brains_used":  state.brains_used(),
        "steps":        len(state.evidence_history),
        "elapsed_ms":   state.elapsed_ms(),
    }
