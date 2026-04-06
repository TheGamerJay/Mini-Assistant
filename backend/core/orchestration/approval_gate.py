"""
orchestration/approval_gate.py — CEO approval gating system.

ANY risky action — not only Doctor repair — must go through this gate
before execution. CEO calls assert_approved() at the point of execution;
it raises ApprovalRequiredError if no approval exists for that action.

RISKY ACTION CATALOG:
  "file_delete"         — deleting or permanently removing a file
  "file_overwrite"      — overwriting an existing file that was not just created
  "shell_command"       — running arbitrary shell/subprocess commands
  "deploy"              — deploying to Vercel, Railway, Heroku, or any cloud
  "git_destructive"     — git reset --hard, force push, rebase, branch -D
  "db_destructive"      — DROP TABLE, DELETE without WHERE, TRUNCATE
  "service_restart"     — restarting a running service or process
  "doctor_fix"          — any code fix proposed by Doctor module

Approval flow:
  1. CEO detects or is told a risky action is needed
  2. CEO calls request_approval() — stores the pending proposal
  3. CEO returns "needs_approval" response to user (via chat_endpoint)
  4. User sends "approve" or "reject" in next message
  5. chat_endpoint calls resolve_approval()
  6. CEO calls assert_approved(session_id, action_type) before executing
     → if approved: proceeds
     → if not approved: raises ApprovalRequiredError (hard-fail, not swallowed)

Rules:
  - assert_approved() NEVER returns silently on a risky action without a record
  - Blanket approval is NOT allowed — approval is per-proposal
  - Doctor NEVER applies fixes — it proposes them
  - Builder NEVER applies unapproved destructive changes
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

log = logging.getLogger("ceo_router.approval_gate")


# ---------------------------------------------------------------------------
# Risky action catalog
# ---------------------------------------------------------------------------

# Complete set of action types that require explicit user approval.
# CEO must classify any execution step against this set before proceeding.
RISKY_ACTION_TYPES: frozenset[str] = frozenset({
    "file_delete",        # rm / unlink / shutil.rmtree
    "file_overwrite",     # writing to a pre-existing file
    "shell_command",      # subprocess, os.system, Popen
    "deploy",             # Vercel, Railway, Heroku, any cloud push
    "git_destructive",    # reset --hard, force push, rebase, branch -D
    "db_destructive",     # DROP TABLE, DELETE no WHERE, TRUNCATE
    "service_restart",    # restarting a running process
    "doctor_fix",         # any Doctor-proposed code fix
})

# Human-readable labels for the approval UI
ACTION_LABELS: dict[str, str] = {
    "file_delete":     "Delete a file permanently",
    "file_overwrite":  "Overwrite an existing file",
    "shell_command":   "Run a shell command",
    "deploy":          "Deploy to a cloud provider",
    "git_destructive": "Destructive git operation",
    "db_destructive":  "Destructive database operation",
    "service_restart": "Restart a running service",
    "doctor_fix":      "Apply a code fix proposed by Doctor",
}


def is_risky(action_type: str) -> bool:
    """Return True if action_type requires approval before execution."""
    return action_type in RISKY_ACTION_TYPES


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ApprovalRequiredError(Exception):
    """
    Raised by assert_approved() when a risky action is attempted without
    a valid approved proposal.

    This is a HARD_FAIL — CEO must NOT swallow it with try/except.
    Pipeline must pause and surface this to the user.

    Attributes:
        session_id:  the session that triggered the violation
        action_type: which risky action was attempted without approval
        proposal_id: the proposal that needs approval (or None if none exists)
    """
    def __init__(
        self,
        session_id:  str,
        action_type: str,
        proposal_id: Optional[str] = None,
    ):
        label = ACTION_LABELS.get(action_type, action_type)
        super().__init__(
            f"Approval required: '{label}' cannot proceed without user approval. "
            f"session={session_id!r} proposal={proposal_id!r}"
        )
        self.session_id  = session_id
        self.action_type = action_type
        self.proposal_id = proposal_id


# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

# Per-session pending approval: { session_id: approval_record }
_PENDING: dict[str, dict[str, Any]] = {}
# Resolved approvals history: { session_id: [resolved_records] }
_HISTORY: dict[str, list[dict[str, Any]]] = {}


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def request_approval(
    session_id:     str,
    action_type:    str,
    module:         str,
    issue:          str,
    proposed_fix:   str,
    fix_steps:      list[str],
    affected_files: list[str],
    severity:       str = "medium",
) -> dict[str, Any]:
    """
    Create and store a pending approval request.

    action_type MUST be one of RISKY_ACTION_TYPES. If it isn't, this call
    logs a warning and still creates the record — CEO must validate the
    action_type before calling this.

    Returns the approval record — CEO embeds this in the API response so
    the frontend can render an approval card.
    """
    if action_type not in RISKY_ACTION_TYPES:
        log.warning(
            "approval_gate: unknown action_type=%r for session=%s — "
            "defaulting to 'doctor_fix'. Add to RISKY_ACTION_TYPES if intentional.",
            action_type, session_id,
        )
        action_type = "doctor_fix"

    proposal_id = f"approval_{uuid.uuid4().hex[:10]}"
    record: dict[str, Any] = {
        "session_id":     session_id,
        "proposal_id":    proposal_id,
        "action_type":    action_type,
        "action_label":   ACTION_LABELS.get(action_type, action_type),
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
        "approval_gate: pending session=%s proposal=%s action=%s severity=%s",
        session_id, proposal_id, action_type, severity,
    )
    return record


def resolve_approval(
    session_id: str,
    approved:   bool,
    feedback:   str = "",
) -> Optional[dict[str, Any]]:
    """
    Resolve a pending approval (approved or rejected).

    Returns the resolved record, or None if no pending approval exists.

    CEO uses the returned record to decide next action:
      approved=True  → proceed with execution
      approved=False → surface to user or stop
    """
    record = _PENDING.pop(session_id, None)
    if record is None:
        log.warning("approval_gate: no pending approval for session=%s", session_id)
        return None

    record["status"]   = "approved" if approved else "rejected"
    record["feedback"] = feedback

    _HISTORY.setdefault(session_id, []).append(record)

    log.info(
        "approval_gate: resolved session=%s proposal=%s status=%s",
        session_id, record["proposal_id"], record["status"],
    )
    return record


def assert_approved(session_id: str, action_type: str) -> dict[str, Any]:
    """
    Hard gate: raises ApprovalRequiredError unless the most recent resolved
    approval for this session covers the requested action_type and is approved.

    CEO calls this immediately before executing ANY risky action.
    This MUST NOT be wrapped in a try/except that swallows the error.

    Returns the approved record on success so CEO can include it in logs.

    Raises:
        ApprovalRequiredError — if no approved record exists for this action.
    """
    if action_type not in RISKY_ACTION_TYPES:
        # Not risky — no approval needed
        return {}

    # Check if there is a currently-pending approval (user hasn't responded yet)
    pending = _PENDING.get(session_id)
    if pending and pending["action_type"] == action_type:
        raise ApprovalRequiredError(
            session_id  = session_id,
            action_type = action_type,
            proposal_id = pending["proposal_id"],
        )

    # Check history for an approved record matching this action type
    history = _HISTORY.get(session_id, [])
    for rec in reversed(history):
        if rec.get("action_type") == action_type and rec.get("status") == "approved":
            log.info(
                "approval_gate: assert_approved OK session=%s action=%s proposal=%s",
                session_id, action_type, rec["proposal_id"],
            )
            return rec

    # No approved record found
    raise ApprovalRequiredError(
        session_id  = session_id,
        action_type = action_type,
        proposal_id = None,
    )


# ---------------------------------------------------------------------------
# Inspection helpers
# ---------------------------------------------------------------------------

def get_pending(session_id: str) -> Optional[dict[str, Any]]:
    """Return the pending approval for a session, or None."""
    return _PENDING.get(session_id)


def has_pending(session_id: str) -> bool:
    return session_id in _PENDING


def get_history(session_id: str) -> list[dict[str, Any]]:
    """Return all resolved approvals for a session (for X-Ray)."""
    return list(_HISTORY.get(session_id, []))


def clear_session(session_id: str) -> None:
    _PENDING.pop(session_id, None)
    _HISTORY.pop(session_id, None)


# ---------------------------------------------------------------------------
# UI message builder
# ---------------------------------------------------------------------------

def build_approval_message(record: dict[str, Any]) -> str:
    """
    Build a human-readable approval request message for the user.
    CEO presents this string — never the raw dict.
    """
    label = record.get("action_label") or ACTION_LABELS.get(
        record.get("action_type", ""), record.get("action_type", "action")
    )
    lines = [
        f"**Action requiring approval:** {label}",
        f"**Issue:** {record['issue']}",
        f"**Proposed fix:** {record['proposed_fix']}",
    ]
    if record.get("affected_files"):
        lines.append(f"**Files affected:** {', '.join(record['affected_files'])}")
    if record.get("fix_steps"):
        lines.append("**Steps:**")
        for i, step in enumerate(record["fix_steps"], 1):
            lines.append(f"  {i}. {step}")
    lines.append("\n**Do you approve?** Reply **approve** to proceed or **reject** to cancel.")
    return "\n".join(lines)
