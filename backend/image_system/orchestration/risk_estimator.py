"""
Risk Estimator — Task Risk Classification

Evaluates the potential damage, scope, and reversibility of a task.
Works in concert with the decision engine but produces a richer risk profile
for display in the Task Summary Card.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class RiskProfile:
    level:            str            # "low" | "medium" | "high"
    score:            int            # 0–10
    factors:          List[str]      # human-readable risk drivers
    mitigations:      List[str]      # what we do to reduce this risk
    requires_checkpoint: bool
    requires_approval:   bool


# ---------------------------------------------------------------------------
# Signal patterns
# ---------------------------------------------------------------------------

_DESTRUCTIVE = re.compile(
    r"\b(delete|remove\s+all|drop|wipe|clear\s+all|reset\s+all|"
    r"truncate|destroy|overwrite|purge)\b", re.I
)
_DEPLOY = re.compile(
    r"\b(deploy|publish|push\s+to\s+prod|release|ship|go\s+live|send\s+to)\b", re.I
)
_SCHEMA = re.compile(
    r"\b(schema|migration|database|db|table|column|index|foreign\s+key)\b", re.I
)
_AUTH = re.compile(
    r"\b(auth|login|password|token|secret|credential|api\s+key|oauth|jwt)\b", re.I
)
_FULL_REWRITE = re.compile(
    r"\b(rewrite|rebuild|from\s+scratch|start\s+over|redesign|overhaul|"
    r"redo\s+everything|replace\s+everything)\b", re.I
)
_EXTERNAL_API = re.compile(
    r"\b(api|webhook|http|fetch|axios|rest|graphql|endpoint|integration|"
    r"third[\s\-]party|stripe|paypal|twilio|sendgrid|firebase)\b", re.I
)
_FILE_OPS = re.compile(
    r"\b(file|upload|download|read\s+file|write\s+file|save\s+to|"
    r"export|import|csv|json\s+file|xml)\b", re.I
)


def estimate(
    message: str,
    intent_type: str,
    mode: str,
    has_existing_code: bool = False,
    ambiguity_score: float = 0.0,
) -> RiskProfile:
    """
    Produce a RiskProfile for a task.

    Args:
        message:           Raw or normalized request.
        intent_type:       "build" | "patch" | "query" | "image" | "chat"
        mode:              "builder" | "chat" | "image"
        has_existing_code: Whether an existing built app is present.
        ambiguity_score:   From IntentLock.
    """
    msg = message
    score = 0
    factors: List[str] = []
    mitigations: List[str] = []

    # Destructive operations
    if _DESTRUCTIVE.search(msg):
        score += 4
        factors.append("Destructive operation — data may be permanently removed")
        mitigations.append("Checkpoint created before execution")

    # Deploy / publish
    if _DEPLOY.search(msg):
        score += 4
        factors.append("Deployment action — affects live environment")
        mitigations.append("Approval required before deploy step")

    # Schema / database changes
    if _SCHEMA.search(msg):
        score += 3
        factors.append("Database schema change — migration required")
        mitigations.append("Dry-run schema diff shown before applying")

    # Auth-related changes
    if _AUTH.search(msg):
        score += 2
        factors.append("Authentication/security code change")
        mitigations.append("Security review step added before completion")

    # Full rewrite of existing code
    if _FULL_REWRITE.search(msg) and has_existing_code:
        score += 3
        factors.append("Full rewrite of existing code — previous version will be replaced")
        mitigations.append("Snapshot of current version saved to checkpoint")

    # External API integrations
    if _EXTERNAL_API.search(msg):
        score += 2
        factors.append("External API integration — depends on third-party service availability")
        mitigations.append("Graceful error handling required for API failures")

    # File I/O operations
    if _FILE_OPS.search(msg):
        score += 1
        factors.append("File operation — disk writes involved")
        mitigations.append("File changes logged for rollback")

    # Ambiguity adds risk
    if ambiguity_score > 0.4:
        score += 2
        factors.append("Ambiguous request — higher chance of building the wrong thing")
        mitigations.append("Intent confirmed before execution")
    elif ambiguity_score > 0.2:
        score += 1

    # Builder mode is higher stakes than chat
    if mode == "builder":
        score += 1

    # Complex build tasks
    if intent_type == "build" and len(msg.split()) > 30:
        score += 1
        factors.append("Large build scope")
        mitigations.append("Task decomposed into checkpointed steps")

    # Clamp
    score = min(score, 10)

    # Determine level
    if score >= 6:
        level = "high"
    elif score >= 3:
        level = "medium"
    else:
        level = "low"

    # Add default mitigations for any non-trivial task
    if score >= 3 and "Checkpoint created before execution" not in mitigations:
        mitigations.append("Checkpoint created before execution")

    # Fallbacks for low-risk
    if not factors:
        factors.append("Standard operation — no elevated risk signals detected")
    if not mitigations:
        mitigations.append("Reversible — can be undone if needed")

    requires_checkpoint = score >= 3
    requires_approval = score >= 6

    return RiskProfile(
        level=level,
        score=score,
        factors=factors,
        mitigations=mitigations,
        requires_checkpoint=requires_checkpoint,
        requires_approval=requires_approval,
    )
