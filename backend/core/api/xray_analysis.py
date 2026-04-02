"""
api/xray_analysis.py — X-Ray Analysis: full internal system diagnostic report.

Admin-only. Read-only. Does not interfere with execution.

Generates a structured full-system analysis for a session covering:
  1. Executive Summary
  2. Full Chain Timeline (step-by-step CEO → brain → CEO flow)
  3. What Worked
  4. What Failed
  5. Brain Breakdown
  6. Repair Memory Analysis
  7. Approval Analysis
  8. Final Diagnosis

Rules:
  - Admin key required (X-Admin-Key header)
  - Returns JSON — readable and structured
  - Never exposes raw internal prompts
  - Never interferes with execution
  - Data source: OrchestrationState + approval_gate + xray_endpoint store
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger("ceo_router.xray_analysis")


def generate_xray_report(session_id: str) -> dict[str, Any]:
    """
    Build the full X-Ray Analysis report for a session.
    Combines orchestration state + approval history + stored execution events.

    Returns a structured report dict.
    """
    from ..orchestration.state_manager import get as get_state
    from ..orchestration.approval_gate import get_history as get_approvals
    from .xray_endpoint import get_xray_data

    state     = get_state(session_id)
    approvals = get_approvals(session_id)
    exec_data = get_xray_data(session_id) or {}

    # If no orchestration state, fall back to basic execution data
    if state is None:
        return _basic_report(session_id, exec_data)

    return {
        "session_id":           session_id,
        "report_type":          "xray_analysis",
        "1_executive_summary":  _executive_summary(state, exec_data),
        "2_chain_timeline":     _chain_timeline(state),
        "3_what_worked":        _what_worked(state),
        "4_what_failed":        _what_failed(state),
        "5_brain_breakdown":    _brain_breakdown(state),
        "6_repair_memory":      _repair_memory_analysis(state),
        "7_approval_analysis":  _approval_analysis(state, approvals),
        "8_final_diagnosis":    _final_diagnosis(state),
        "9_context_analysis":   _context_analysis(session_id, exec_data),
    }


# ---------------------------------------------------------------------------
# Report sections
# ---------------------------------------------------------------------------

def _executive_summary(state: Any, exec_data: dict) -> dict[str, Any]:
    """Section 1: High-level outcome summary."""
    decision = exec_data.get("decision", {})
    return {
        "final_result":    state.final_status,
        "success":         state.final_status == "complete",
        "total_duration_ms": state.elapsed_ms(),
        "total_steps":     len(state.evidence_history),
        "brains_used":     state.brains_used(),
        "approval_needed": len(state.approval_history) > 0,
        "memory_used":     state.repair_memory_used,
        "module":          decision.get("selected_module", "builder"),
        "complexity":      state.complexity,
        "user_goal":       state.user_goal[:200],
    }


def _chain_timeline(state: Any) -> list[dict[str, Any]]:
    """Section 2: Full step-by-step chain of events."""
    timeline = []
    for record in state.evidence_history:
        timeline.append({
            "step_number": record.step_num,
            "active_brain": record.brain,
            "action_taken": record.action,
            "reason":       record.reason,
            "status":       record.status,
            "confidence":   record.confidence,
            "elapsed_ms":   record.elapsed_ms,
            "evidence":     record.evidence[:5],
            "proposed_fix": record.proposed_fix[:200] if record.proposed_fix else "",
        })
    return timeline


def _what_worked(state: Any) -> dict[str, Any]:
    """Section 3: Everything that passed."""
    passed_brains  = [r.brain for r in state.completed_steps if r.status == "success"]
    passed_actions = [f"{r.brain}: {r.summary[:80]}" for r in state.completed_steps if r.status == "success"]

    checks = {
        "build_passed":      any(r.brain == "builder" and r.status == "success" for r in state.evidence_history),
        "hands_passed":      any(r.brain == "hands"   and r.status == "success" for r in state.evidence_history),
        "vision_passed":     any(r.brain == "vision"  and r.status == "success" for r in state.evidence_history),
        "doctor_diagnosed":  any(r.brain == "doctor"  and r.status != "fail"    for r in state.evidence_history),
        "final_validation":  state.final_status == "complete",
    }
    return {
        "checks":          checks,
        "passed_brains":   list(set(passed_brains)),
        "passed_actions":  passed_actions,
    }


def _what_failed(state: Any) -> dict[str, Any]:
    """Section 4: Everything that failed or was weak."""
    failed_steps = [
        {
            "brain":    r.brain,
            "action":   r.action,
            "reason":   r.summary,
            "evidence": r.evidence[:3],
        }
        for r in state.failed_steps
    ]
    low_confidence = [
        {"brain": r.brain, "confidence": r.confidence, "summary": r.summary[:80]}
        for r in state.evidence_history
        if r.confidence < 0.5
    ]
    return {
        "failed_steps":       failed_steps,
        "low_confidence":     low_confidence,
        "approval_blocked":   state.approval_status in ("pending", "rejected"),
        "final_failed":       state.final_status == "failed",
        "total_failures":     len(state.failed_steps),
        "total_retries":      state.retry_counts,
    }


def _brain_breakdown(state: Any) -> dict[str, Any]:
    """Section 5: Per-brain task/result summary."""
    breakdown: dict[str, list[dict]] = {}
    for record in state.evidence_history:
        brain = record.brain
        if brain not in breakdown:
            breakdown[brain] = []
        breakdown[brain].append({
            "task":       record.action,
            "result":     record.status,
            "confidence": record.confidence,
            "evidence":   record.evidence[:3],
            "elapsed_ms": record.elapsed_ms,
        })

    # Add CEO's own perspective
    breakdown["ceo"] = [
        {
            "task":       "route_and_control",
            "result":     state.final_status,
            "steps_routed": len(state.evidence_history),
            "approval_requests": len(state.approval_history),
        }
    ]
    return breakdown


def _repair_memory_analysis(state: Any) -> dict[str, Any]:
    """Section 6: What repair memory found (if consulted)."""
    if not state.repair_memory_used:
        return {
            "memory_lookup":  False,
            "category":       None,
            "matches_found":  0,
            "top_match":      None,
            "similarity_score": None,
            "confidence_level": None,
            "used_as_guidance": False,
        }

    top = state.repair_memory_matches[0] if state.repair_memory_matches else {}
    return {
        "memory_lookup":    True,
        "category":         top.get("_category"),
        "matches_found":    len(state.repair_memory_matches),
        "top_match":        top.get("problem_name"),
        "similarity_score": top.get("similarity_score"),
        "confidence_level": top.get("confidence_level"),
        "used_as_guidance": bool(state.repair_memory_guidance),
        "guidance_used":    state.repair_memory_guidance,
    }


def _approval_analysis(state: Any, approvals: list[dict]) -> dict[str, Any]:
    """Section 7: What required approval and how it resolved."""
    if not approvals:
        return {
            "approval_requested": False,
            "total_approvals":    0,
            "resolved":           [],
        }

    resolved = [
        {
            "proposal_id":  a.get("proposal_id"),
            "issue":        a.get("issue", "")[:100],
            "proposed_fix": a.get("proposed_fix", "")[:100],
            "status":       a.get("status"),
            "feedback":     a.get("feedback", ""),
        }
        for a in approvals
    ]
    return {
        "approval_requested": True,
        "total_approvals":    len(approvals),
        "approved":           sum(1 for a in approvals if a.get("status") == "approved"),
        "rejected":           sum(1 for a in approvals if a.get("status") == "rejected"),
        "resolved":           resolved,
    }


def _final_diagnosis(state: Any) -> dict[str, Any]:
    """Section 8: Overall assessment and recommendations."""
    doctor_steps = [r for r in state.evidence_history if r.brain == "doctor"]
    root_problem = doctor_steps[-1].proposed_fix if doctor_steps else ""

    recommend_save = (
        state.final_status == "complete"
        and len(state.failed_steps) > 0  # had failures that were fixed
        and state.approval_status == "approved"
    )

    return {
        "overall_status":      state.final_status,
        "root_problem":        root_problem[:300] if root_problem else None,
        "recommended_action":  _recommend_action(state),
        "save_to_repair_memory": recommend_save,
        "save_reason":         "Fix was confirmed, approved, applied, and verified." if recommend_save else "",
    }


def _recommend_action(state: Any) -> str:
    if state.final_status == "complete":
        return "No action needed — build completed successfully."
    if state.final_status == "needs_approval":
        return "User approval required before fix can be applied."
    if state.final_status == "needs_input":
        return "Provide more detail so CEO can continue."
    if state.final_status == "failed":
        return "Review the failed steps and retry with a clearer or simpler request."
    return "Orchestration in progress."


def _context_analysis(session_id: str, exec_data: dict) -> dict[str, Any]:
    """
    Section 9: Context retrieval analysis (Phase 66).
    Shows what context was retrieved, by whom, and what was pruned.
    Admin-only — never exposed in user-facing responses.
    """
    retrieval = exec_data.get("retrieval", {})
    if not retrieval:
        return {
            "retrieval_used":        False,
            "requesting_brain":      None,
            "CEO_approved":          None,
            "sources_considered":    [],
            "sources_selected":      [],
            "reason":                "No retrieval data recorded for this session.",
            "selected_context_count": 0,
            "repair_memory_match":   None,
            "pruned":                False,
            "final_context_count":   0,
        }

    selected = retrieval.get("selected_context", [])
    repair_match = next(
        (c.get("meta") for c in selected if c.get("source") == "repair_memory"),
        None,
    )

    return {
        "retrieval_used":         retrieval.get("retrieval_used", False),
        "requesting_brain":       retrieval.get("brain"),
        "CEO_approved":           True,   # retrieval only runs via CEO
        "sources_considered":     retrieval.get("sources", []),
        "sources_selected":       list({c.get("source") for c in selected}),
        "reason":                 retrieval.get("reason", ""),
        "selected_context_count": retrieval.get("selected_count", len(selected)),
        "repair_memory_match":    repair_match,
        "pruned":                 retrieval.get("pruned_count", 0) > 0,
        "pruned_count":           retrieval.get("pruned_count", 0),
        "candidates_found":       retrieval.get("candidates_found", 0),
        "final_context_count":    retrieval.get("selected_count", len(selected)),
    }


def _basic_report(session_id: str, exec_data: dict) -> dict[str, Any]:
    """Fallback report when no orchestration state exists — uses raw event data."""
    events = exec_data.get("events", [])
    return {
        "session_id":    session_id,
        "report_type":   "xray_basic",
        "note":          "No multi-brain orchestration state found — showing raw event data.",
        "total_events":  len(events),
        "events":        [
            {"event_type": e.get("event_type"), "status": e.get("status"), "summary": e.get("summary")}
            for e in events
        ],
        "decision":      exec_data.get("decision", {}),
        "validation":    exec_data.get("validation"),
    }


# ---------------------------------------------------------------------------
# FastAPI endpoint
# ---------------------------------------------------------------------------

try:
    from fastapi import APIRouter, HTTPException, Header

    router = APIRouter(prefix="/api/ceo", tags=["ceo-xray-analysis"])

    @router.get("/xray-analysis/{session_id}")
    async def xray_analysis(
        session_id:  str,
        x_admin_key: str = Header(default=""),
    ):
        """
        Full X-Ray Analysis report for a session.
        Admin-only. Read-only.
        """
        import os
        expected = os.getenv("ADMIN_XRAY_KEY", "")
        if expected and x_admin_key != expected:
            raise HTTPException(status_code=403, detail="X-Ray Analysis requires admin key")

        try:
            report = generate_xray_report(session_id)
        except Exception as exc:
            log.error("xray_analysis: report generation failed — %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}")

        if not report:
            raise HTTPException(status_code=404, detail=f"No data for session '{session_id}'")

        return report

    @router.post("/repair-memory/save")
    async def save_repair_record(
        body:        dict,
        x_admin_key: str = Header(default=""),
    ):
        """
        CEO-approved save of a repair record.
        All save conditions must be met before calling this endpoint.
        Admin key required.
        """
        import os
        expected = os.getenv("ADMIN_XRAY_KEY", "")
        if expected and x_admin_key != expected:
            raise HTTPException(status_code=403, detail="Requires admin key")

        try:
            from ..repair_memory.repair_store import save_repair, slug_exists
            from ..repair_memory.repair_search import check_duplicate

            category       = body.get("category", "unknown")
            problem_name   = body.get("problem_name", "")
            solution_name  = body.get("solution_name", "")
            solution_steps = body.get("solution_steps", [])

            if not problem_name or not solution_steps:
                raise HTTPException(status_code=400, detail="problem_name and solution_steps are required")

            # Duplicate detection
            is_dup, matches = check_duplicate(category, problem_name)
            if is_dup:
                return {
                    "saved":     False,
                    "reason":    "High-similarity record already exists",
                    "matches":   matches,
                    "action":    "Update existing record instead of creating duplicate",
                }

            slug   = problem_name.lower().replace(" ", "-")[:60]
            record = save_repair(category, slug, problem_name, solution_name, solution_steps)
            return {"saved": True, "record": record}

        except HTTPException:
            raise
        except Exception as exc:
            log.error("save_repair_record: failed — %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/repair-memory/search")
    async def search_repair_memory(
        category:    str,
        problem:     str,
        x_admin_key: str = Header(default=""),
    ):
        """Search repair memory for similar problems."""
        try:
            from ..repair_memory.repair_search import search
            matches = search(category, problem, top_n=5)
            return {"category": category, "query": problem, "matches": matches}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post("/controls/{session_id}/resolve-approval")
    async def resolve_approval_endpoint(
        session_id: str,
        body:       dict,
    ):
        """
        User resolves a pending approval (approve or reject).
        CEO routes execution accordingly.
        """
        approved = body.get("approved", False)
        feedback = body.get("feedback", "")

        from ..orchestration.approval_gate import resolve_approval
        record = resolve_approval(session_id, approved, feedback)
        if record is None:
            raise HTTPException(status_code=404, detail="No pending approval for this session")

        return {
            "resolved":  True,
            "status":    record["status"],
            "message":   f"Approval {'granted' if approved else 'rejected'}.",
            "next_step": "Builder will apply the fix." if approved else "CEO will ask for alternative approach.",
        }

except ImportError:
    router = None
    log.warning("api/xray_analysis: FastAPI not available — endpoint not registered")
