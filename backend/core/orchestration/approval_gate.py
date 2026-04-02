"""
orchestration/approval_gate.py — CEO approval gating system.

ALL fixes proposed by Doctor MUST go through this gate before execution.
NO fix is applied without explicit user approval routed through CEO.

Approval flow:
  1. CEO calls request_approval() with the proposed fix
  2. CEO returns "needs_approval" response to user (via chat_endpoint)
  3. User sees the proposal and responds (approve / reject / modify)
  4. Next user message calls resolve_approval()
  5. CEO routes: approved → Builder executes, rejected → ask_user or stop

Approval record:
  {
      "session_id":   str,
      "proposal_id":  str,
      "module":       str,       # which module will execute if approved
      "issue":        str,       # what problem was found
      "proposed_fix": str,       # what Doctor proposes
      "fix_steps":    list[str], # exact steps to apply
      "affected_files": list[str],
      "severity":     str,       # "low" | "medium" | "high"
      "status":       str,       # "pending" | "approved" | "rejected"
      "feedback":     str,       # user feedback on rejection
  }

Rules:
  - Doctor NEVER applies fixes — it proposes them
  - Builder NEVER applies unapproved fixes
  - NO execution happens without CEO approval
  - Approval is per-proposal — blanket approval is NOT allowed
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

log = logging.getLogger("ceo_router.approval_gate")

# Per-session pending approvals: { session_id: approval_record }
_PENDING: dict[str, dict[str, Any]] = {}
# History: { session_id: [resolved_records, ...] }
_HISTORY: dict[str, list[dict[str, Any]]] = {}


def request_approval(
    session_id:    str,
    module:        str,
    issue:         str,
    proposed_fix:  str,
    fix_steps:     list[str],
    affected_files: list[str],
    severity:      str = "medium",
) -> dict[str, Any]:
    """
    Create and store a pending approval request.
    CEO must present this to the user before any fix is executed.

    Returns the approval record — include in API response for UI display.
    """
    proposal_id = f"approval_{uuid.uuid4().hex[:10]}"
    record = {
        "session_id":     session_id,
        "proposal_id":    proposal_id,
        "module":         module,
        "issue":          issue,
        "proposed_fix":   proposed_fix,
        "fix_steps":      fix_steps,
        "affected_files": affected_files,
        "severity":       severity,
        "status":         "pending",
        "feedback":       "",
    }
    _PENDING[session_id] = record
    log.info(
        "approval_gate: pending session=%s proposal=%s severity=%s",
        session_id, proposal_id, severity,
    )
    return record


def resolve_approval(
    session_id: str,
    approved:   bool,
    feedback:   str = "",
) -> Optional[dict[str, Any]]:
    """
    Resolve a pending approval.
    Returns the resolved record, or None if no pending approval exists.

    CEO uses the resolved record to decide next action:
      approved=True  → route to Builder with fix_steps
      approved=False → surface to user or stop
    """
    record = _PENDING.pop(session_id, None)
    if record is None:
        log.warning("approval_gate: no pending approval for session=%s", session_id)
        return None

    record["status"]   = "approved" if approved else "rejected"
    record["feedback"] = feedback

    if session_id not in _HISTORY:
        _HISTORY[session_id] = []
    _HISTORY[session_id].append(record)

    log.info(
        "approval_gate: resolved session=%s proposal=%s status=%s",
        session_id, record["proposal_id"], record["status"],
    )
    return record


def get_pending(session_id: str) -> Optional[dict[str, Any]]:
    """Return the pending approval for a session, or None."""
    return _PENDING.get(session_id)


def get_history(session_id: str) -> list[dict[str, Any]]:
    """Return all resolved approvals for a session (for X-Ray)."""
    return list(_HISTORY.get(session_id, []))


def has_pending(session_id: str) -> bool:
    return session_id in _PENDING


def clear_session(session_id: str) -> None:
    _PENDING.pop(session_id, None)
    _HISTORY.pop(session_id, None)


def build_approval_message(record: dict[str, Any]) -> str:
    """
    Build a human-readable approval request message for the user.
    CEO presents this — never raw dict.
    """
    lines = [
        f"**Issue found:** {record['issue']}",
        f"**Proposed fix:** {record['proposed_fix']}",
    ]
    if record.get("affected_files"):
        lines.append(f"**Files affected:** {', '.join(record['affected_files'])}")
    if record.get("fix_steps"):
        lines.append("**Steps:**")
        for i, step in enumerate(record["fix_steps"], 1):
            lines.append(f"  {i}. {step}")
    lines.append("\n**Do you approve this fix?** Reply 'approve' or 'reject'.")
    return "\n".join(lines)
