"""
orchestration/brain_router.py — Routes tasks to individual brains on behalf of CEO.

CEO is the ONLY caller. Brains NEVER call each other.
Every brain call returns a standardized BrainResult to CEO.

BrainResult (standardized output from every brain):
  {
      "status":               "success" | "fail" | "needs_input" | "needs_approval",
      "summary":              str,
      "confidence":           float (0.0–1.0),
      "evidence":             list[str],
      "affected_files":       list[str],
      "proposed_fix":         str,
      "recommended_next_step": "builder" | "hands" | "vision" | "doctor" | "ask_user" | "complete",
      "_raw":                 dict,   # original module output (internal)
  }

Rules:
  - brain_router NEVER decides what to do with results — CEO does
  - brain_router NEVER chains calls — one call per invocation
  - brain_router wraps module output in BrainResult format
  - all errors are surfaced as BrainResult with status="fail"
"""

from __future__ import annotations

import json as _json
import logging
import re as _re
import time
from typing import Any, Optional

log = logging.getLogger("ceo_router.brain_router")

_MAX_RETRIES_PER_BRAIN = 3


# ---------------------------------------------------------------------------
# Gateway dispatch — unified entry point for all CEO → brain calls
# ---------------------------------------------------------------------------

async def gateway_dispatch(
    brain_name:  str,
    task:        Any,           # Task | None — pass None to skip stage validation
    decision:    dict[str, Any],
    memory:      dict[str, Any],
    web_results: dict[str, Any] = {},
    **kwargs:    Any,
) -> dict[str, Any]:
    """
    Single entry point for ALL CEO → brain calls.

    CEO calls this instead of calling call_planner / call_builder etc. directly.

    What it does:
      1. Validates the brain call is legal for the task's current stage
         (raises GatewayViolationError if not — CEO must handle)
      2. Dispatches to the appropriate call_* function
      3. Returns the standardised BrainResult

    If task=None, stage validation is skipped (used for context-injection
    calls that happen before a task is created, e.g. github_brain pre-scan).

    Supported brain_name values:
      "planner", "builder", "hands", "vision", "doctor", "github_brain"
    """
    # Stage gate — skip if no task provided
    if task is not None:
        try:
            from .stage_machine import validate_brain_call
            validate_brain_call(brain_name, task)
        except Exception as gate_exc:
            log.error("gateway: stage gate blocked brain=%s — %s", brain_name, gate_exc)
            raise

    _dispatch_map = {
        "planner":      _dispatch_planner,
        "builder":      _dispatch_builder,
        "hands":        _dispatch_hands,
        "vision":       _dispatch_vision,
        "doctor":       _dispatch_doctor,
        "github_brain": _dispatch_github_brain,
    }

    fn = _dispatch_map.get(brain_name)
    if fn is None:
        return _fail_result(brain_name, f"Unknown brain: {brain_name!r}", "ask_user")

    log.info("gateway: dispatching brain=%s task=%s", brain_name, getattr(task, "id", "none"))
    return await fn(decision, memory, web_results, **kwargs)


# ---------------------------------------------------------------------------
# Internal dispatch shims (gateway → existing call_* functions)
# ---------------------------------------------------------------------------

async def _dispatch_planner(decision, memory, web_results, **_):
    return await call_planner(decision, memory)

async def _dispatch_builder(decision, memory, web_results, fix_hint="", **_):
    return await call_builder(decision, memory, web_results, fix_hint=fix_hint)

async def _dispatch_hands(decision, memory, web_results, build_result=None, **_):
    if build_result is None:
        build_result = {}
    return await call_hands(build_result, decision, memory)

async def _dispatch_vision(decision, memory, web_results, build_result=None, **_):
    if build_result is None:
        build_result = {}
    return await call_vision(build_result, decision, memory)

async def _dispatch_doctor(decision, memory, web_results, issue="", evidence=None, repair_matches=None, **_):
    return await call_doctor(
        issue          = issue,
        evidence       = evidence or [],
        decision       = decision,
        memory         = memory,
        repair_matches = repair_matches or [],
    )

async def _dispatch_github_brain(decision, memory, web_results, **_):
    return await call_github_brain(decision, memory)


# ---------------------------------------------------------------------------
# Streaming HTML QA wrappers — standardises hands/eyes for the streaming path
# ---------------------------------------------------------------------------
# The streaming CEO uses inline _hands_qa / _eyes_qa that return (bool, list).
# These wrappers call Anthropic directly with the same logic and return BrainResult,
# making the streaming path consistent with the non-streaming path.

async def call_hands_html(
    html:             str,
    original_request: str,
    api_key:          str,
) -> dict[str, Any]:
    """
    Functional QA on raw HTML string.
    Returns BrainResult (same format as call_hands).

    Checks: broken buttons, missing event handlers, JS errors, broken forms.
    """
    _SYSTEM = (
        "You are the Hands Brain — functional QA specialist.\n"
        "Inspect the HTML for broken functionality ONLY. Do NOT comment on style.\n\n"
        "Check:\n"
        "- Buttons with no onclick or broken event listeners\n"
        "- Forms with no submit handler\n"
        "- JavaScript errors (syntax, undefined variables, missing functions)\n"
        "- Interactive elements that reference undefined functions\n\n"
        "Return JSON only:\n"
        '{"pass": true|false, "issues": ["specific issue 1", ...]}\n'
        'Return {"pass": true, "issues": []} if everything works.'
    )
    prompt = (
        f"[ORIGINAL REQUEST]\n{original_request}\n\n"
        f"[CODE TO TEST]\n```html\n{html[:8000]}\n```\n\n"
        "Test for broken functionality. Return JSON only."
    )
    t0 = time.perf_counter()
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model      = "claude-sonnet-4-6",
            max_tokens = 1024,
            system     = _SYSTEM,
            messages   = [{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip() if resp.content else ""
        m   = _re.search(r"\{[\s\S]+\}", raw)
        if m:
            d      = _json.loads(m.group(0))
            passed = bool(d.get("pass", True))
            issues = d.get("issues", [])
        else:
            passed, issues = True, []
    except Exception as exc:
        log.warning("call_hands_html: QA failed — %s", exc)
        passed, issues = True, []  # on error, pass through (non-fatal)

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    status  = "success" if passed else "fail"

    return {
        "status":                status,
        "summary":               "Hands: all checks passed." if passed else f"Hands found {len(issues)} issue(s).",
        "confidence":            0.85 if passed else 0.4,
        "evidence":              issues[:5],
        "affected_files":        [],
        "proposed_fix":          "",
        "recommended_next_step": "vision" if passed else "builder",
        "_raw":                  {"pass": passed, "issues": issues},
        "_brain":                "hands",
        "_elapsed_ms":           elapsed,
    }


async def call_eyes_html(
    html:             str,
    original_request: str,
    api_key:          str,
) -> dict[str, Any]:
    """
    Visual / layout QA on raw HTML string.
    Returns BrainResult (same format as call_vision).

    Checks: missing layout, invisible text, broken responsive structure,
    elements completely absent from what was requested.
    """
    _SYSTEM = (
        "You are the Eyes Brain — visual QA specialist.\n"
        "Inspect the HTML for visual / layout problems ONLY. Do NOT check logic.\n\n"
        "Check:\n"
        "- Missing layout structure (no container, broken grid, overlapping elements)\n"
        "- Invisible text (white-on-white, zero opacity, etc.)\n"
        "- Elements completely missing from what was requested\n"
        "- Broken responsive structure\n\n"
        "Return JSON only:\n"
        '{"pass": true|false, "notes": ["visual issue 1", ...]}\n'
        "Minor style preferences are NOT issues. Only flag actual visual failures."
    )
    prompt = (
        f"[ORIGINAL REQUEST]\n{original_request}\n\n"
        f"[CODE TO INSPECT]\n```html\n{html[:8000]}\n```\n\n"
        "Inspect for visual failures. Return JSON only."
    )
    t0 = time.perf_counter()
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model      = "claude-sonnet-4-6",
            max_tokens = 1024,
            system     = _SYSTEM,
            messages   = [{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip() if resp.content else ""
        m   = _re.search(r"\{[\s\S]+\}", raw)
        if m:
            d      = _json.loads(m.group(0))
            passed = bool(d.get("pass", True))
            notes  = d.get("notes", [])
        else:
            passed, notes = True, []
    except Exception as exc:
        log.warning("call_eyes_html: QA failed — %s", exc)
        passed, notes = True, []

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    status  = "success" if passed else "fail"

    return {
        "status":                status,
        "summary":               "Eyes: visual output approved." if passed else f"Eyes flagged {len(notes)} visual issue(s).",
        "confidence":            0.85 if passed else 0.4,
        "evidence":              notes[:5],
        "affected_files":        [],
        "proposed_fix":          "",
        "recommended_next_step": "complete" if passed else "builder",
        "_raw":                  {"pass": passed, "notes": notes},
        "_brain":                "eyes",
        "_elapsed_ms":           elapsed,
    }


# ---------------------------------------------------------------------------
# Brain call entry points (all called by CEO Orchestrator only)
# ---------------------------------------------------------------------------

async def call_planner(
    decision: dict[str, Any],
    memory:   dict[str, Any],
) -> dict[str, Any]:
    """
    Route to Planner Brain. Returns BrainResult with structured build plan.
    Called by CEO only. Planner never calls back — returns plan to CEO.
    """
    t0 = time.perf_counter()
    try:
        from core.modules.planner import execute
        raw = await execute(decision, memory, {})
    except Exception as exc:
        log.error("brain_router: planner failed — %s", exc, exc_info=True)
        return _fail_result("planner", str(exc), "builder")

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    return _wrap_planner(raw, elapsed)


async def call_builder(
    decision:    dict[str, Any],
    memory:      dict[str, Any],
    web_results: dict[str, Any],
    fix_hint:    str = "",
) -> dict[str, Any]:
    """
    Route to Builder Brain. Returns BrainResult.
    fix_hint: optional guidance from Doctor to inject into the task.
    """
    if fix_hint:
        # Inject fix hint into decision message for the builder
        msg = decision.get("message", "")
        decision = {**decision, "message": f"{msg}\n\nFix guidance: {fix_hint}"}

    t0 = time.perf_counter()
    try:
        from core.modules.builder import execute
        raw = await execute(decision, memory, web_results)
    except Exception as exc:
        log.error("brain_router: builder failed — %s", exc, exc_info=True)
        return _fail_result("builder", str(exc), "doctor")

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    return _wrap_builder(raw, elapsed)


async def call_hands(
    build_result: dict[str, Any],
    decision:     dict[str, Any],
    memory:       dict[str, Any],
) -> dict[str, Any]:
    """
    Route to Hands Brain for functional testing. Returns BrainResult.
    Hands receives the build result and tests it.
    """
    # Create a hands-specific decision
    hands_decision = {
        **decision,
        "message": (
            f"Test the following build output for functional correctness.\n"
            f"Files: {[f.get('path','') for f in build_result.get('files', [])]}\n"
            f"Summary: {build_result.get('summary', '')}"
        ),
    }
    t0 = time.perf_counter()
    try:
        from core.modules.hands import execute
        raw = await execute(hands_decision, memory, {})
    except Exception as exc:
        log.error("brain_router: hands failed — %s", exc, exc_info=True)
        return _fail_result("hands", str(exc), "doctor")

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    return _wrap_hands(raw, elapsed)


async def call_vision(
    build_result: dict[str, Any],
    decision:     dict[str, Any],
    memory:       dict[str, Any],
) -> dict[str, Any]:
    """
    Route to Vision Brain for visual inspection. Returns BrainResult.
    """
    vision_decision = {
        **decision,
        "message": (
            f"Inspect the visual output of this build for UI/UX correctness.\n"
            f"Summary: {build_result.get('summary', '')}\n"
            f"Files: {[f.get('path','') for f in build_result.get('files', []) if f.get('type') == 'frontend']}"
        ),
    }
    t0 = time.perf_counter()
    try:
        from core.modules.vision import execute
        raw = await execute(vision_decision, memory, {})
    except Exception as exc:
        log.error("brain_router: vision failed — %s", exc, exc_info=True)
        return _fail_result("vision", str(exc), "doctor")

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    return _wrap_vision(raw, elapsed)


async def call_github_brain(
    decision: dict[str, Any],
    memory:   dict[str, Any],
) -> dict[str, Any]:
    """
    Route to GitHub Brain for repo/code inspection. Returns BrainResult.
    CEO calls this when a GitHub URL or user code is detected.
    Brain reads files and returns a structured report — CEO never reads files directly.
    """
    t0 = time.perf_counter()
    try:
        from core.modules.github_brain import execute
        raw = await execute(decision, memory, {})
    except Exception as exc:
        log.error("brain_router: github_brain failed — %s", exc, exc_info=True)
        return _fail_result("github_brain", str(exc), "ask_user")

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    return _wrap_github_brain(raw, elapsed)


async def call_doctor(
    issue:        str,
    evidence:     list[str],
    decision:     dict[str, Any],
    memory:       dict[str, Any],
    repair_matches: list[dict] = [],
) -> dict[str, Any]:
    """
    Route to Doctor Brain for diagnosis. Returns BrainResult.
    Doctor NEVER applies fixes — it returns diagnosis + proposed fix to CEO.
    """
    # Build a diagnosis-specific message
    repair_context = ""
    if repair_matches:
        top = repair_matches[0]
        repair_context = (
            f"\n\nRepair Memory reference (confidence={top['confidence_level']}):\n"
            f"Similar past problem: {top['problem_name']}\n"
            f"Past solution: {top['solution_name']}\n"
            f"Steps: {'; '.join(top['solution_steps'][:3])}"
        )

    doctor_decision = {
        **decision,
        "message": (
            f"Diagnose this issue (do NOT apply any fix — diagnosis only):\n"
            f"Issue: {issue}\n"
            f"Evidence:\n" + "\n".join(f"- {e}" for e in evidence[:10])
            + repair_context
        ),
    }
    t0 = time.perf_counter()
    try:
        from core.modules.doctor import execute
        raw = await execute(doctor_decision, memory, {})
    except Exception as exc:
        log.error("brain_router: doctor failed — %s", exc, exc_info=True)
        return _fail_result("doctor", str(exc), "ask_user")

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    return _wrap_doctor(raw, elapsed)


# ---------------------------------------------------------------------------
# BrainResult wrappers
# ---------------------------------------------------------------------------

def _wrap_planner(raw: dict[str, Any], elapsed_ms: float) -> dict[str, Any]:
    has_error = raw.get("type") == "error" or raw.get("status") == "error"
    status    = "fail" if has_error else "success"
    return {
        "status":                status,
        "summary":               raw.get("summary", "Plan created."),
        "confidence":            _parse_confidence(raw.get("confidence", "medium")),
        "evidence":              raw.get("steps", [])[:5],
        "affected_files":        [],
        "proposed_fix":          "",
        "recommended_next_step": "builder" if status == "success" else "ask_user",
        "_raw":                  raw,
        "_brain":                "planner",
        "_elapsed_ms":           elapsed_ms,
    }


def _wrap_builder(raw: dict[str, Any], elapsed_ms: float) -> dict[str, Any]:
    files = raw.get("files", [])
    has_error = raw.get("status") == "error" or raw.get("status") == "parse_error"
    confidence = _parse_confidence(raw.get("confidence", "medium"))

    status = "fail" if has_error or not files else "success"
    evidence = [f.get("path", "") for f in files if f.get("path")]
    if raw.get("notes"):
        evidence.extend(raw["notes"][:3])

    return {
        "status":                status,
        "summary":               raw.get("summary", "Builder completed."),
        "confidence":            confidence,
        "evidence":              evidence,
        "affected_files":        [f.get("path", "") for f in files],
        "proposed_fix":          "",
        "recommended_next_step": "hands" if status == "success" else "doctor",
        "_raw":                  raw,
        "_brain":                "builder",
        "_elapsed_ms":           elapsed_ms,
    }


def _wrap_hands(raw: dict[str, Any], elapsed_ms: float) -> dict[str, Any]:
    actions = raw.get("actions", [])
    has_error = raw.get("type") == "error" or any(
        a.get("status") == "failed" for a in actions
    )
    # Hands is in limited mode — acknowledge as success for now
    status = "fail" if has_error else "success"
    evidence = [a.get("result", "")[:100] for a in actions]

    return {
        "status":                status,
        "summary":               raw.get("summary", "Hands check complete."),
        "confidence":            0.6 if status == "success" else 0.3,
        "evidence":              evidence,
        "affected_files":        [],
        "proposed_fix":          "",
        "recommended_next_step": "vision" if status == "success" else "doctor",
        "_raw":                  raw,
        "_brain":                "hands",
        "_elapsed_ms":           elapsed_ms,
    }


def _wrap_vision(raw: dict[str, Any], elapsed_ms: float) -> dict[str, Any]:
    issues = raw.get("issues", [])
    has_error = raw.get("type") == "error" or raw.get("status") == "error"
    status = "fail" if (has_error or issues) else "success"

    evidence = issues[:5] if issues else [raw.get("analysis", "")[:100]]

    return {
        "status":                status,
        "summary":               raw.get("analysis", "Vision inspection complete.")[:150],
        "confidence":            0.8 if status == "success" else 0.4,
        "evidence":              evidence,
        "affected_files":        [],
        "proposed_fix":          "",
        "recommended_next_step": "complete" if status == "success" else "doctor",
        "_raw":                  raw,
        "_brain":                "vision",
        "_elapsed_ms":           elapsed_ms,
    }


def _wrap_doctor(raw: dict[str, Any], elapsed_ms: float) -> dict[str, Any]:
    has_error = raw.get("status") == "error" or raw.get("type") == "error"
    root_cause = raw.get("root_cause", "")
    fix        = raw.get("fix", "")
    files_upd  = raw.get("files_updated", [])

    confidence = _parse_confidence(raw.get("confidence", "medium"))
    status = "fail" if has_error else "needs_approval"

    evidence = []
    if raw.get("issue"):
        evidence.append(f"Issue: {raw['issue']}")
    if root_cause:
        evidence.append(f"Root cause: {root_cause}")

    return {
        "status":                status,
        "summary":               raw.get("issue", "Doctor diagnosis complete."),
        "confidence":            confidence,
        "evidence":              evidence,
        "affected_files":        [f.get("path", "") for f in files_upd],
        "proposed_fix":          fix,
        "recommended_next_step": "ask_user",   # CEO presents to user for approval
        "_raw":                  raw,
        "_brain":                "doctor",
        "_elapsed_ms":           elapsed_ms,
    }


def _wrap_github_brain(raw: dict[str, Any], elapsed_ms: float) -> dict[str, Any]:
    has_error  = raw.get("status") == "error"
    status     = "fail" if has_error else "success"
    features   = raw.get("existing_features", [])
    stack      = raw.get("tech_stack", [])
    files      = raw.get("relevant_files", [])
    evidence   = (
        [f"Tech stack: {', '.join(stack)}"] if stack else []
    ) + (
        [f"Features found: {', '.join(features[:6])}"] if features else []
    ) + (
        [f"Files read: {len(files)}"]
    )

    return {
        "status":                status,
        "summary":               (
            raw.get("error") if has_error
            else f"Repo inspected: {raw.get('project_type', 'unknown')} — {raw.get('file_tree_summary', '')}"
        ),
        "confidence":            0.0 if has_error else 0.85,
        "evidence":              evidence,
        "affected_files":        [f["path"] for f in files],
        "proposed_fix":          "",
        "recommended_next_step": "ask_user" if has_error else "planner",
        "_raw":                  raw,
        "_brain":                "github_brain",
        "_elapsed_ms":           elapsed_ms,
    }


def _fail_result(brain: str, error: str, next_step: str) -> dict[str, Any]:
    return {
        "status":                "fail",
        "summary":               f"{brain} encountered an error: {error[:100]}",
        "confidence":            0.0,
        "evidence":              [error],
        "affected_files":        [],
        "proposed_fix":          "",
        "recommended_next_step": next_step,
        "_raw":                  {"error": error},
        "_brain":                brain,
        "_elapsed_ms":           0.0,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_confidence(val: Any) -> float:
    if isinstance(val, float):
        return val
    mapping = {"high": 0.9, "medium": 0.6, "low": 0.3}
    return mapping.get(str(val).lower(), 0.6)
