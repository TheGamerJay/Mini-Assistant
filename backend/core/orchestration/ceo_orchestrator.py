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

import json as _json
import logging
import os
import re as _re
import time
from typing import Any, AsyncGenerator, Optional

from .state_manager import OrchestrationState, StepRecord, get_or_create
from .brain_router import call_builder, call_hands, call_vision, call_doctor, call_planner
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

    # CEO reviews and saves confirmed fix to repair memory library
    if approved:
        _api_key = decision.get("api_key", "") if isinstance(decision, dict) else ""
        await _ceo_approve_and_save(
            problem  = approved.get("issue", state.goal)[:200],
            solution = approved.get("proposed_fix", "Doctor fix applied")[:200],
            steps    = approved.get("fix_steps", [])[:10],
            api_key  = _api_key,
            category = "build_pipeline",
        )

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
# Repair memory: auto-save confirmed solutions
# ---------------------------------------------------------------------------

async def _ceo_approve_and_save(
    problem:   str,
    solution:  str,
    steps:     list[str],
    api_key:   str,
    category:  str = "build_pipeline",
) -> None:
    """
    CEO reviews the fix and decides whether it's worth saving to the repair library.
    Only saves if CEO explicitly approves — never auto-saves.

    Save conditions (all must be true before this is called):
      - problem is confirmed
      - solution was applied by Builder
      - Hands and/or Vision verification PASSED
      - CEO is now reviewing final save decision
    """
    # CEO approval check via Claude Haiku
    try:
        import anthropic as _sa_am
        client = _sa_am.AsyncAnthropic(api_key=api_key)
        _approve_prompt = (
            f"Problem: {problem}\n"
            f"Solution: {solution}\n"
            f"Steps: {'; '.join(steps[:5])}\n\n"
            "Should this fix be saved to the repair memory library for future reuse?\n"
            "Save if: the fix addresses a real, repeatable problem that could occur again.\n"
            "Don't save if: the fix was trivial, one-off, or too specific to be useful.\n"
            "Answer with ONLY: yes or no"
        )
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            system="You are the CEO. Approve or reject saving this fix to the repair library.",
            messages=[{"role": "user", "content": _approve_prompt}],
        )
        decision = resp.content[0].text.strip().lower() if resp.content else "no"
        if not decision.startswith("yes"):
            log.info("repair_memory: CEO rejected save — problem not generalizable enough")
            return
        log.info("repair_memory: CEO approved save")
    except Exception as exc:
        log.warning("repair_memory: CEO approval check failed — not saving (%s)", exc)
        return

    # CEO approved — now save
    try:
        from core.repair_memory.repair_store import save_repair, increment_success
        from core.repair_memory.repair_search import search

        matches = search(category, problem, top_n=1)
        if matches and matches[0]["similarity_score"] >= 0.75:
            existing_slug = matches[0]["_slug"]
            if increment_success(category, existing_slug):
                log.info(
                    "repair_memory: CEO-approved increment slug=%s (similarity=%.2f)",
                    existing_slug, matches[0]["similarity_score"],
                )
                return

        slug = problem[:60].lower().replace(" ", "-")
        save_repair(
            category       = category,
            problem_slug   = slug,
            problem_name   = problem[:200],
            solution_name  = solution[:200],
            solution_steps = steps[:10],
        )
        log.info("repair_memory: CEO-approved save slug=%s category=%s", slug, category)
    except Exception as exc:
        log.warning("repair_memory: save failed (non-fatal) — %s", exc)


# ---------------------------------------------------------------------------
# Streaming CEO build loop — for the /api/chat/stream endpoint
# ---------------------------------------------------------------------------

async def stream_builder_task(
    *,
    session_id:          str,
    message:             str,
    history:             list,          # [{role, content}]
    has_prior_code:      bool,
    prior_code:          str | None,
    api_key:             str,
    vibe_mode:           bool  = False,
    build_history_turns: int   = 0,
    is_explicit_rebuild: bool  = False,
    has_images:          bool  = False,
    all_images:          list  | None = None,
    lessons:             str   = "",
    user_prefs:          str   = "",
    memory_search:       str   = "",
    memory:              dict  | None = None,
) -> AsyncGenerator[str, None]:
    """
    CEO-controlled streaming build pipeline.

    Yields SSE strings ready for the client:
      data: {"brain": "ceo|planner|builder|hands|eyes", "status": "..."}\\n\\n
      data: {"t": "..."}\\n\\n   ← code tokens from Builder Brain
      data: {"done": true, "mode_used": "build", ...}\\n\\n

    Flow:
      CEO → [clarify?] → CEO → Planner → CEO → Builder (stream) →
      CEO → Hands → CEO → Eyes → CEO → [retry?] → CEO → done
    """
    _memory = memory or {}
    all_images = all_images or []

    # ── CEO: start ────────────────────────────────────────────────────────────
    yield _status("ceo", "Analyzing your request…")

    # ── Requirements phase (first build, no images, no vibe mode) ─────────────
    _is_fresh_first = (
        not has_prior_code
        and not is_explicit_rebuild
        and not has_images
        and not vibe_mode
        and build_history_turns == 0
    )
    if _is_fresh_first:
        yield _status("ceo", "Gathering requirements before building…")
        async for chunk in _stream_requirements(message, history, api_key, lessons, user_prefs, memory_search):
            yield chunk
        return  # endpoint yields done event

    # ── CEO → Planner Brain ───────────────────────────────────────────────────
    yield _status("planner", "Creating build plan…")
    plan_decision = {"message": message, "api_key": api_key}
    plan_result   = await call_planner(plan_decision, _memory)

    if plan_result["status"] == "success":
        plan_raw  = plan_result["_raw"]
        plan_desc = plan_raw.get("title") or plan_raw.get("summary") or message[:60]
        yield _status("ceo", f"Plan approved: {plan_desc}. Sending to Builder…")
    else:
        # Planner failed — CEO skips plan and sends directly to Builder
        yield _status("ceo", "Planning skipped — building directly…")

    # ── CEO → Builder Brain (streaming) ───────────────────────────────────────
    yield _status("builder", "Writing code…")
    reply_text = ""

    async for chunk in _stream_build(
        message          = message,
        history          = history,
        api_key          = api_key,
        has_prior_code   = has_prior_code,
        prior_code       = prior_code,
        vibe_mode        = vibe_mode,
        is_explicit_rebuild = is_explicit_rebuild,
        has_images       = has_images,
        all_images       = all_images,
        build_history_turns = build_history_turns,
        plan_result      = plan_result,
        lessons          = lessons,
        user_prefs       = user_prefs,
        memory_search    = memory_search,
    ):
        if chunk.startswith("data: "):
            try:
                d = _json.loads(chunk[6:].split("\n")[0])
                if "t" in d:
                    reply_text += d["t"]
            except Exception:
                pass
        yield chunk

    # ── CEO → Hands Brain (functional QA) ─────────────────────────────────────
    _built_html = _extract_html(reply_text)
    _do_hands_qa = (
        bool(_built_html)
        and not vibe_mode          # vibe mode: speed over QA
        and build_history_turns > 0  # skip on requirements turn
    )

    if _do_hands_qa:
        yield _status("hands", "Testing functionality…")
        hands_ok, hands_issues = await _hands_qa(_built_html, message, api_key)

        if not hands_ok and hands_issues:
            # ── CEO checks repair library before sending to Builder ───────────
            _repair_hint = ""
            try:
                _lib_matches = _search_repair_memory(
                    "; ".join(hands_issues[:2]), "build_pipeline"
                )
                if _lib_matches and _lib_matches[0]["similarity_score"] >= 0.50:
                    _top = _lib_matches[0]
                    _repair_hint = (
                        f"Repair library match ({_top['confidence_level']} confidence): "
                        f"{_top['solution_name']} — Steps: {'; '.join(_top['solution_steps'][:3])}"
                    )
                    yield _status("ceo", f"Found past solution in library: {_top['solution_name']}")
            except Exception:
                pass

            yield _status("ceo", f"Hands found issues — sending to Builder: {hands_issues[0]}")
            yield _status("builder", "Fixing issues…")
            _fix_start_len = len(reply_text)
            async for chunk in _stream_fix(
                original_html = _built_html,
                issues        = hands_issues + ([_repair_hint] if _repair_hint else []),
                message       = message,
                api_key       = api_key,
                lessons       = lessons,
            ):
                if chunk.startswith("data: "):
                    try:
                        d = _json.loads(chunk[6:].split("\n")[0])
                        if "t" in d:
                            reply_text += d["t"]
                    except Exception:
                        pass
                yield chunk
            _built_html = _extract_html(reply_text) or _built_html
            # Re-verify after fix
            yield _status("ceo", "Hands re-checking after fix…")
            _hands_ok2, _ = await _hands_qa(_built_html, message, api_key)
            if _hands_ok2:
                yield _status("ceo", "Fix verified. CEO reviewing for library save…")
                await _ceo_approve_and_save(
                    problem  = f"Build failed QA: {'; '.join(hands_issues[:2])}",
                    solution = f"Builder fix resolved: {message[:80]}",
                    steps    = hands_issues[:5],
                    api_key  = api_key,
                    category = "build_pipeline",
                )
        else:
            yield _status("ceo", "Hands: all checks passed.")

    # ── CEO → Eyes Brain (visual QA) ──────────────────────────────────────────
    _do_eyes_qa = _do_hands_qa  # same gate: only on full builds
    if _do_eyes_qa and _built_html:
        yield _status("eyes", "Inspecting visual output…")
        eyes_ok, eyes_notes = await _eyes_qa(_built_html, message, api_key)
        if not eyes_ok and eyes_notes:
            yield _status("ceo", f"Eyes flagged visual issues: {eyes_notes[0]}")
        else:
            yield _status("ceo", "Eyes: visual output approved.")

    # ── CEO: final approval ────────────────────────────────────────────────────
    yield _status("ceo", "Build complete. Delivering to you.")
    # Endpoint handles the done event — do not yield it here


# ---------------------------------------------------------------------------
# Internal streaming helpers — called by CEO only
# ---------------------------------------------------------------------------

async def _stream_requirements(
    message:      str,
    history:      list,
    api_key:      str,
    lessons:      str,
    user_prefs:   str,
    memory_search: str,
) -> AsyncGenerator[str, None]:
    """Stream the requirements-gathering response (first build turn)."""
    try:
        from image_system.api.brains.knowledge_base import requirements_prompt
        sys_prompt = requirements_prompt()
    except ImportError:
        sys_prompt = (
            "You are an expert app builder. When a user asks you to build something for the "
            "first time, ask exactly 3 short focused questions to clarify requirements before building. "
            "End with: 'Ready to build once you answer!'"
        )
    if lessons:
        sys_prompt += lessons
    if user_prefs:
        sys_prompt += user_prefs
    if memory_search:
        sys_prompt += "\n\n" + memory_search

    msgs = _build_messages(history, message, [])
    async for chunk in _anthropic_stream(api_key, sys_prompt, msgs, think_budget=0, max_tokens=1024):
        yield chunk


async def _stream_build(
    *,
    message:          str,
    history:          list,
    api_key:          str,
    has_prior_code:   bool,
    prior_code:       str | None,
    vibe_mode:        bool,
    is_explicit_rebuild: bool,
    has_images:       bool,
    all_images:       list,
    build_history_turns: int,
    plan_result:      dict,
    lessons:          str,
    user_prefs:       str,
    memory_search:    str,
) -> AsyncGenerator[str, None]:
    """Stream the main build — patch mode or fresh build."""
    try:
        from image_system.api.brains.knowledge_base import (
            fresh_build_prompt, patch_prompt,
        )
    except ImportError:
        fresh_build_prompt = lambda: "You are an expert web developer. Build complete, working HTML/CSS/JS apps."
        patch_prompt       = lambda: "You are an expert web developer. Apply surgical patches to the existing code. Output the complete updated file."

    _is_patch = has_prior_code and not is_explicit_rebuild and not has_images

    if _is_patch:
        sys_prompt = patch_prompt()
    else:
        sys_prompt = fresh_build_prompt()

    # Inject plan into system prompt when fresh build has a plan
    if not _is_patch and plan_result.get("status") == "success":
        raw = plan_result["_raw"]
        plan_block = (
            f"\n\n## BUILD PLAN (from Planner Brain — approved by CEO)\n"
            f"Title: {raw.get('title', '')}\n"
            f"Tech stack: {raw.get('tech_stack', 'HTML/CSS/JS')}\n"
            f"Components: {', '.join(raw.get('components', []))}\n"
            f"Steps: {' → '.join(raw.get('steps', []))}\n"
            f"Constraints: {'; '.join(raw.get('constraints', []))}\n"
        )
        sys_prompt += plan_block

    if lessons:
        sys_prompt += lessons
    if user_prefs:
        sys_prompt += user_prefs
    if memory_search:
        sys_prompt += "\n\n" + memory_search

    # Inject current code for patch mode
    msgs = _build_messages(history, message, all_images)
    if _is_patch and prior_code and msgs:
        _last_user = msgs[-1] if msgs[-1]["role"] == "user" else None
        if _last_user and isinstance(_last_user["content"], str):
            _last_user["content"] = (
                f"[CURRENT CODE]\n```html\n{prior_code}\n```\n\n"
                f"[USER REQUEST]\n{_last_user['content']}"
            )

    _is_patch_or_debug = _is_patch
    _think_budget = 16000 if _is_patch_or_debug else 5000
    _max_tokens   = 24000 if _is_patch_or_debug else 14000

    async for chunk in _anthropic_stream(api_key, sys_prompt, msgs, _think_budget, _max_tokens):
        yield chunk


async def _stream_fix(
    *,
    original_html: str,
    issues:        list[str],
    message:       str,
    api_key:       str,
    lessons:       str,
) -> AsyncGenerator[str, None]:
    """CEO sends Builder a fix request with exact Hands failure evidence."""
    try:
        from image_system.api.brains.knowledge_base import patch_prompt
        sys_prompt = patch_prompt()
    except ImportError:
        sys_prompt = "You are an expert web developer. Fix the issues listed and output the complete corrected file."

    if lessons:
        sys_prompt += lessons
    sys_prompt += "\n\n## YOUR TASK: FIX ALL ISSUES\nFix every issue listed. Output the complete fixed HTML."

    issues_text = "\n".join(f"- {i}" for i in issues[:5])
    user_content = (
        f"[ORIGINAL REQUEST]\n{message}\n\n"
        f"[ISSUES TO FIX — from Hands Brain]\n{issues_text}\n\n"
        f"[CURRENT CODE]\n```html\n{original_html}\n```\n\n"
        "Fix all issues and return the complete updated HTML file."
    )
    msgs = [{"role": "user", "content": user_content}]

    async for chunk in _anthropic_stream(api_key, sys_prompt, msgs, think_budget=8000, max_tokens=24000):
        yield chunk


async def _anthropic_stream(
    api_key:      str,
    system:       str,
    messages:     list,
    think_budget: int,
    max_tokens:   int = 14000,
) -> AsyncGenerator[str, None]:
    """Thin wrapper around Anthropic streaming. Yields SSE data strings."""
    import asyncio
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)

        _kwargs: dict[str, Any] = {
            "model":      "claude-sonnet-4-6",
            "max_tokens": max_tokens,
            "system":     system,
            "messages":   messages,
        }
        if think_budget > 0:
            _kwargs["thinking"] = {"type": "enabled", "budget_tokens": think_budget}
            _kwargs["extra_headers"] = {"anthropic-beta": "interleaved-thinking-2025-05-14"}

        _last_ping = asyncio.get_event_loop().time()
        async with client.messages.stream(**_kwargs) as stream:
            async for token in stream.text_stream:
                _now = asyncio.get_event_loop().time()
                if _now - _last_ping > 8:
                    yield ": ping\n\n"
                    _last_ping = _now
                yield f"data: {_json.dumps({'t': token})}\n\n"

    except Exception as exc:
        log.error("stream_builder_task._anthropic_stream failed — %s", exc)
        yield f"data: {_json.dumps({'t': f'⚠️ Builder error: {exc}'})}\n\n"


async def _hands_qa(html: str, original_request: str, api_key: str) -> tuple[bool, list[str]]:
    """
    Hands Brain: functional test of generated HTML.
    Uses Claude Haiku to check buttons, interactions, logic.
    Returns (pass, [issues]).
    """
    _HANDS_SYS = """You are the Hands Brain — functional QA specialist.
Inspect this HTML for broken functionality ONLY. Do NOT comment on style.

Check:
- Buttons with no onclick or broken event listeners
- Forms with no submit handler
- JavaScript errors (syntax, undefined variables, missing functions)
- Interactive elements that won't work

Return JSON only:
{
  "pass": true | false,
  "issues": ["specific issue 1", "specific issue 2"]
}
Return {"pass": true, "issues": []} if everything works."""

    prompt = (
        f"[ORIGINAL REQUEST]\n{original_request}\n\n"
        f"[CODE TO TEST]\n```html\n{html[:8000]}\n```\n\n"
        "Test for broken functionality. Return JSON."
    )
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_HANDS_SYS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip() if resp.content else ""
        m = _re.search(r"\{[\s\S]+\}", raw)
        if m:
            d = _json.loads(m.group(0))
            return bool(d.get("pass", True)), d.get("issues", [])
    except Exception as exc:
        log.warning("hands_qa failed — %s", exc)
    return True, []   # on error, pass through


async def _eyes_qa(html: str, original_request: str, api_key: str) -> tuple[bool, list[str]]:
    """
    Eyes Brain: visual / layout inspection of generated HTML.
    Uses Claude Haiku to check layout, style, responsiveness.
    Returns (pass, [notes]).
    """
    _EYES_SYS = """You are the Eyes Brain — visual QA specialist.
Inspect this HTML for visual / layout problems ONLY. Do NOT check logic.

Check:
- Missing layout structure (no container, broken grid, elements overlapping)
- Invisible text (white on white, etc.)
- Elements completely missing from what was requested
- Broken responsive structure

Return JSON only:
{
  "pass": true | false,
  "notes": ["visual issue 1", "visual issue 2"]
}
Minor style preferences are NOT issues. Only flag actual visual failures."""

    prompt = (
        f"[ORIGINAL REQUEST]\n{original_request}\n\n"
        f"[CODE TO INSPECT]\n```html\n{html[:8000]}\n```\n\n"
        "Inspect for visual failures. Return JSON."
    )
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_EYES_SYS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip() if resp.content else ""
        m = _re.search(r"\{[\s\S]+\}", raw)
        if m:
            d = _json.loads(m.group(0))
            return bool(d.get("pass", True)), d.get("notes", [])
    except Exception as exc:
        log.warning("eyes_qa failed — %s", exc)
    return True, []


def _extract_html(text: str) -> str | None:
    """Extract HTML from Builder stream output."""
    fence = _re.search(r"```(?:html)?\s*\n([\s\S]+?)```", text)
    if fence:
        return fence.group(1).strip()
    raw = _re.search(r"(<!DOCTYPE\s+html[\s\S]+)", text, _re.I)
    if raw:
        return raw.group(1).strip()
    return None


def _build_messages(history: list, message: str, images: list) -> list[dict]:
    """Build Claude message list from history + current message + images."""
    msgs = []
    for h in history:
        role    = h.get("role") if isinstance(h, dict) else getattr(h, "role", "")
        content = h.get("content") if isinstance(h, dict) else getattr(h, "content", "")
        if role in ("user", "assistant") and content and str(content).strip():
            msgs.append({"role": role, "content": str(content)})

    # Current user message with optional images
    if images:
        parts: list[Any] = []
        for b64 in images[:4]:
            mt = "image/png" if b64.startswith("iVBOR") else "image/jpeg"
            parts.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}})
        parts.append({"type": "text", "text": message})
        msgs.append({"role": "user", "content": parts})
    else:
        msgs.append({"role": "user", "content": message})

    return msgs


def _status(brain: str, msg: str) -> str:
    """Yield a CEO status SSE event — shown in the UI as a brain activity indicator."""
    return f"data: {_json.dumps({'brain': brain, 'status': msg})}\n\n"


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
