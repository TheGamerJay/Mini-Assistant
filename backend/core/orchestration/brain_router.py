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

import logging
import time
from typing import Any

log = logging.getLogger("ceo_router.brain_router")

_MAX_RETRIES_PER_BRAIN = 3


# ---------------------------------------------------------------------------
# Brain call entry points (all called by CEO Orchestrator only)
# ---------------------------------------------------------------------------

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
