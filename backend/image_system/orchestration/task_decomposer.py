"""
Task Decomposer — Phase 2

Breaks a user's request into a sequenced list of TaskStep objects.
Each step is:
  - independently executable
  - checkpointed
  - reversible
  - status-tracked

This module uses lightweight heuristics + template matching (no LLM).
For LLM-assisted decomposition, the orchestrator calls this and then
optionally refines with the manager brain.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class StepType(str, Enum):
    ANALYZE    = "analyze"
    PLAN       = "plan"
    EDIT       = "edit"
    BUILD      = "build"
    TEST       = "test"
    VERIFY     = "verify"
    CHECKPOINT = "checkpoint"
    SUMMARY    = "summary"
    DEPLOY     = "deploy"


class StepStatus(str, Enum):
    PENDING    = "pending"
    RUNNING    = "running"
    DONE       = "done"
    FAILED     = "failed"
    SKIPPED    = "skipped"
    ROLLED_BACK = "rolled_back"


@dataclass
class TaskStep:
    step_id:          str
    order_index:      int
    title:            str
    description:      str
    type:             StepType
    dependencies:     List[str] = field(default_factory=list)   # step_ids this depends on
    estimated_cost:   int = 0
    estimated_risk:   str = "low"
    status:           StepStatus = StepStatus.PENDING
    output_summary:   str = ""
    error_summary:    str = ""
    requires_approval: bool = False
    started_at:       Optional[str] = None
    completed_at:     Optional[str] = None
    checkpoint_id:    Optional[str] = None
    rollback_available: bool = False


@dataclass
class DecomposedTask:
    task_id:      str
    title:        str
    intent_type:  str
    mode:         str
    steps:        List[TaskStep]
    total_estimated_cost: int = 0
    created_at:   str = ""

    def current_step(self) -> Optional[TaskStep]:
        for s in self.steps:
            if s.status in (StepStatus.PENDING, StepStatus.RUNNING):
                return s
        return None

    def completed_count(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.DONE)

    def is_complete(self) -> bool:
        return all(s.status in (StepStatus.DONE, StepStatus.SKIPPED) for s in self.steps)

    def has_failures(self) -> bool:
        return any(s.status == StepStatus.FAILED for s in self.steps)


# ---------------------------------------------------------------------------
# Templates — standard step sequences by intent type
# ---------------------------------------------------------------------------

def _build_template(goal: str, has_existing_code: bool, risk_level: str) -> List[dict]:
    """Steps for a fresh build."""
    steps = [
        {"title": "Analyze request", "type": StepType.ANALYZE, "desc": "Read project context and understand what to build.", "cost": 0},
        {"title": "Build execution plan", "type": StepType.PLAN,    "desc": "Decompose the request into implementation steps.", "cost": 1},
        {"title": "Generate application", "type": StepType.BUILD,   "desc": "Write the complete working code.", "cost": 3},
        {"title": "Self-review",          "type": StepType.VERIFY,  "desc": "Check for bugs, missing features, and quality issues.", "cost": 1},
        {"title": "Checkpoint",           "type": StepType.CHECKPOINT, "desc": "Save current state for rollback.", "cost": 0},
        {"title": "Deliver",              "type": StepType.SUMMARY, "desc": "Present the result and offer next steps.", "cost": 0},
    ]
    return steps


def _patch_template(goal: str, has_existing_code: bool, risk_level: str) -> List[dict]:
    """Steps for patching existing code."""
    steps = [
        {"title": "Read current code",    "type": StepType.ANALYZE, "desc": "Load and understand the existing code.", "cost": 0},
        {"title": "Identify change scope","type": StepType.PLAN,    "desc": "Determine minimum required changes.", "cost": 0},
    ]
    if risk_level in ("medium", "high"):
        steps.append({"title": "Checkpoint", "type": StepType.CHECKPOINT, "desc": "Save current state before modifications.", "cost": 0, "req_approval": False})
    steps += [
        {"title": "Apply patch",          "type": StepType.EDIT,   "desc": "Make targeted changes only.", "cost": 2},
        {"title": "Verify correctness",   "type": StepType.VERIFY, "desc": "Confirm changes work as expected.", "cost": 1},
        {"title": "Deliver",              "type": StepType.SUMMARY,"desc": "Show what changed.", "cost": 0},
    ]
    return steps


def _image_template(goal: str, **_) -> List[dict]:
    return [
        {"title": "Parse image request",  "type": StepType.ANALYZE, "desc": "Extract style, subject, and quality parameters.", "cost": 0},
        {"title": "Generate image",       "type": StepType.BUILD,   "desc": "Run image generation pipeline.", "cost": 4},
        {"title": "Review quality",       "type": StepType.VERIFY,  "desc": "Check output quality and retry if needed.", "cost": 1},
        {"title": "Deliver",              "type": StepType.SUMMARY, "desc": "Present image with description.", "cost": 0},
    ]


def _analysis_template(goal: str, **_) -> List[dict]:
    return [
        {"title": "Load context",         "type": StepType.ANALYZE, "desc": "Read relevant files and state.", "cost": 0},
        {"title": "Perform analysis",     "type": StepType.ANALYZE, "desc": "Evaluate the subject systematically.", "cost": 1},
        {"title": "Report findings",      "type": StepType.SUMMARY, "desc": "Present findings with recommendations.", "cost": 0},
    ]


def _chat_template(goal: str, **_) -> List[dict]:
    return [
        {"title": "Respond",              "type": StepType.BUILD,   "desc": "Generate conversational response.", "cost": 0},
    ]


_TEMPLATES = {
    "build":    _build_template,
    "patch":    _patch_template,
    "image":    _image_template,
    "analysis": _analysis_template,
    "chat":     _chat_template,
    "query":    _chat_template,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decompose(
    intent_type: str,
    normalized_goal: str,
    mode: str,
    risk_level: str = "low",
    has_existing_code: bool = False,
    requires_approval_threshold: str = "high",
) -> DecomposedTask:
    """
    Decompose a task into ordered, checkpointed steps.

    Args:
        intent_type:     "build" | "patch" | "image" | "analysis" | "chat" | "query"
        normalized_goal: Clean user request string.
        mode:            "builder" | "chat" | "image"
        risk_level:      "low" | "medium" | "high"
        has_existing_code: Whether existing code is present.
        requires_approval_threshold: "medium" | "high" — below which level to skip approval gates.
    """
    template_fn = _TEMPLATES.get(intent_type, _chat_template)
    raw_steps = template_fn(normalized_goal, has_existing_code=has_existing_code, risk_level=risk_level)

    steps: List[TaskStep] = []
    prev_id = None

    for i, raw in enumerate(raw_steps):
        step_id = str(uuid.uuid4())[:8]
        req_approval = raw.get("req_approval", False)

        # Escalate approval for high-risk actions
        if risk_level == "high" and raw["type"] in (StepType.EDIT, StepType.BUILD, StepType.DEPLOY):
            req_approval = True
        elif risk_level == "medium" and requires_approval_threshold == "medium" and raw["type"] == StepType.DEPLOY:
            req_approval = True

        step = TaskStep(
            step_id=step_id,
            order_index=i,
            title=raw["title"],
            description=raw["desc"],
            type=raw["type"],
            dependencies=[prev_id] if prev_id else [],
            estimated_cost=raw.get("cost", 0),
            estimated_risk=risk_level if raw["type"] in (StepType.EDIT, StepType.BUILD) else "low",
            requires_approval=req_approval,
            rollback_available=(raw["type"] == StepType.CHECKPOINT),
        )
        steps.append(step)
        prev_id = step_id

    total_cost = sum(s.estimated_cost for s in steps)
    task_id = str(uuid.uuid4())[:12]

    return DecomposedTask(
        task_id=task_id,
        title=_shorten(normalized_goal),
        intent_type=intent_type,
        mode=mode,
        steps=steps,
        total_estimated_cost=total_cost,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _shorten(text: str, max_len: int = 60) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"
