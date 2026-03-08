"""
orchestrator_task.py – Top-Level Orchestrator Task Models
──────────────────────────────────────────────────────────
Defines the *macro-level* task that tracks a complete user request through
the multi-agent workflow state machine.

Relationship to existing SwarmTask
-----------------------------------
  SwarmTask        = one unit of work for ONE agent (micro-level, already exists)
  OrchestratorTask = the full user request tracked across ALL states (macro-level, this file)

The OrchestratorTask owns a list of WorkflowSteps; each step corresponds to
one workflow state and internally triggers one or more SwarmTask executions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ─── Enumerations ─────────────────────────────────────────────────────────────

class WorkflowState(str, Enum):
    """Top-level states for the orchestrator state machine."""
    CREATED           = "created"
    LOADING_CONTEXT   = "loading_context"
    PLANNING          = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    CODING            = "coding"
    REVIEWING         = "reviewing"
    TESTING           = "testing"
    FIXING            = "fixing"
    DEPLOYING         = "deploying"
    DOCUMENTING       = "documenting"
    COMPLETED         = "completed"
    FAILED            = "failed"
    CANCELLED         = "cancelled"


class StepStatus(str, Enum):
    """Per-step execution status."""
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    DONE        = "done"
    FAILED      = "failed"
    SKIPPED     = "skipped"


class OrchTaskType(str, Enum):
    """High-level task classification (drives blueprint selection)."""
    BUILD   = "build"
    FIX     = "fix"
    TEST    = "test"
    REVIEW  = "review"
    DEPLOY  = "deploy"
    GENERIC = "generic"


# ─── State machine rules ───────────────────────────────────────────────────────

# Legal transitions: state → list of states it may move to
VALID_TRANSITIONS: dict[WorkflowState, list[WorkflowState]] = {
    WorkflowState.CREATED: [
        WorkflowState.LOADING_CONTEXT,
        WorkflowState.FAILED,
        WorkflowState.CANCELLED,
    ],
    WorkflowState.LOADING_CONTEXT: [
        WorkflowState.PLANNING,
        WorkflowState.FAILED,
    ],
    WorkflowState.PLANNING: [
        WorkflowState.AWAITING_APPROVAL,
        WorkflowState.CODING,
        WorkflowState.TESTING,
        WorkflowState.REVIEWING,
        WorkflowState.FAILED,
    ],
    WorkflowState.AWAITING_APPROVAL: [
        WorkflowState.CODING,
        WorkflowState.TESTING,
        WorkflowState.REVIEWING,
        WorkflowState.CANCELLED,
    ],
    WorkflowState.CODING: [
        WorkflowState.REVIEWING,
        WorkflowState.TESTING,
        WorkflowState.FAILED,
    ],
    WorkflowState.REVIEWING: [
        WorkflowState.TESTING,
        WorkflowState.CODING,  # loop back if review requests changes
        WorkflowState.FAILED,
    ],
    WorkflowState.TESTING: [
        WorkflowState.FIXING,
        WorkflowState.DEPLOYING,
        WorkflowState.DOCUMENTING,
        WorkflowState.COMPLETED,
        WorkflowState.FAILED,
    ],
    WorkflowState.FIXING: [
        WorkflowState.TESTING,  # loop back to re-test after fix
        WorkflowState.CODING,
        WorkflowState.FAILED,
    ],
    WorkflowState.DEPLOYING: [
        WorkflowState.DOCUMENTING,
        WorkflowState.COMPLETED,
        WorkflowState.FAILED,
    ],
    WorkflowState.DOCUMENTING: [
        WorkflowState.COMPLETED,
        WorkflowState.FAILED,
    ],
    WorkflowState.COMPLETED:  [],
    WorkflowState.FAILED:     [],
    WorkflowState.CANCELLED:  [],
}

# Terminal states where no further transitions are expected
TERMINAL_STATES = {WorkflowState.COMPLETED, WorkflowState.FAILED, WorkflowState.CANCELLED}

# Which agents are permitted to execute in each state.
# Enforced by OrchestratorEngine before dispatching to SwarmManager.
# Unknown agents (future ones) get a warning but are not blocked.
AGENT_ALLOWED_STATES: dict[str, list[WorkflowState]] = {
    "planner_agent":      [WorkflowState.PLANNING],
    "research_agent":     [WorkflowState.LOADING_CONTEXT, WorkflowState.PLANNING],
    "coding_agent":       [WorkflowState.CODING],
    "debug_agent":        [WorkflowState.FIXING],
    "tester_agent":       [WorkflowState.TESTING],
    "file_analyst_agent": [WorkflowState.LOADING_CONTEXT, WorkflowState.PLANNING, WorkflowState.REVIEWING],
    "vision_agent":       [WorkflowState.CODING, WorkflowState.REVIEWING],
    # Future agents (stubs – allowed states defined in advance)
    "tool_agent":         [WorkflowState.DEPLOYING],
    "security_agent":     [WorkflowState.CODING, WorkflowState.DEPLOYING, WorkflowState.FIXING],
    "doc_agent":          [WorkflowState.DOCUMENTING],
    "memory_agent":       [WorkflowState.LOADING_CONTEXT, WorkflowState.PLANNING,
                           WorkflowState.COMPLETED, WorkflowState.FAILED],
    "learning_agent":     [WorkflowState.COMPLETED, WorkflowState.FAILED],
    "ui_agent":           [WorkflowState.CODING, WorkflowState.REVIEWING],
}


# ─── Data models ──────────────────────────────────────────────────────────────

@dataclass
class StateTransition:
    """Immutable audit record of one state change."""
    from_state: str
    to_state:   str
    reason:     str = ""
    timestamp:  str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "from":      self.from_state,
            "to":        self.to_state,
            "reason":    self.reason,
            "timestamp": self.timestamp,
        }


@dataclass
class WorkflowStep:
    """
    One logical step in the orchestrator workflow.

    A step corresponds to one WorkflowState execution. It tracks which agent
    ran, what swarm tasks were spawned, and the outcome.
    """
    step_id:        str        = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:           str        = ""
    state:          str        = ""
    agent_name:     str        = ""
    status:         StepStatus = StepStatus.PENDING
    output:         str        = ""
    error:          str        = ""
    swarm_task_ids: list[str]  = field(default_factory=list)
    started_at:     Optional[str] = None
    completed_at:   Optional[str] = None

    def start(self) -> None:
        self.status     = StepStatus.IN_PROGRESS
        self.started_at = datetime.now(timezone.utc).isoformat()

    def complete(self, output: str = "") -> None:
        self.status       = StepStatus.DONE
        self.output       = output
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def fail(self, error: str) -> None:
        self.status       = StepStatus.FAILED
        self.error        = error
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def skip(self, reason: str = "") -> None:
        self.status       = StepStatus.SKIPPED
        self.error        = reason
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "step_id":        self.step_id,
            "name":           self.name,
            "state":          self.state,
            "agent_name":     self.agent_name,
            "status":         str(self.status),
            "output":         self.output[:500] if self.output else "",
            "error":          self.error,
            "swarm_task_ids": self.swarm_task_ids,
            "started_at":     self.started_at,
            "completed_at":   self.completed_at,
        }


@dataclass
class OrchestratorTask:
    """
    Top-level task that tracks a complete user request through the
    multi-agent workflow state machine.

    Lifecycle
    ---------
    created
      → loading_context  (memory retrieval)
      → planning         (planner agent)
      → [awaiting_approval]  (optional human gate)
      → coding           (coding agent)
      → reviewing        (code reviewer)
      → testing          (tester agent)
      ↕  fixing          (debug agent, looped with testing)
      → deploying        (tool agent)
      → documenting      (doc agent)
      → completed

    Any state → failed | cancelled
    """
    goal:            str
    task_id:         str               = field(default_factory=lambda: str(uuid.uuid4()))
    task_type:       str               = OrchTaskType.GENERIC
    current_state:   WorkflowState     = WorkflowState.CREATED
    steps:           list[WorkflowStep]     = field(default_factory=list)
    assigned_agents: list[str]         = field(default_factory=list)
    retry_count:     int               = 0
    max_retries:     int               = 3
    created_at:      str               = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at:      str               = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at:    Optional[str]     = None
    result:          Optional[str]     = None
    failure_reason:  Optional[str]     = None
    state_history:   list[StateTransition] = field(default_factory=list)
    metadata:        dict[str, Any]    = field(default_factory=dict)

    # ── State machine ──────────────────────────────────────────────────────────

    def transition(self, new_state: WorkflowState, reason: str = "") -> None:
        """
        Advance to new_state, recording the transition in state_history.
        Raises ValueError if the transition is not permitted.
        """
        allowed = VALID_TRANSITIONS.get(self.current_state, [])
        if new_state not in allowed:
            raise ValueError(
                f"Invalid state transition: {self.current_state} → {new_state}. "
                f"Permitted: {[s.value for s in allowed]}"
            )
        self.state_history.append(StateTransition(
            from_state=str(self.current_state),
            to_state=str(new_state),
            reason=reason,
        ))
        self.current_state = new_state
        self.updated_at    = datetime.now(timezone.utc).isoformat()
        if new_state in TERMINAL_STATES:
            self.completed_at = self.updated_at

    def force_state(self, new_state: WorkflowState, reason: str = "forced") -> None:
        """
        Bypass transition validation – used ONLY by resume logic to reset
        a failed task to a safe checkpoint state.
        """
        self.state_history.append(StateTransition(
            from_state=str(self.current_state),
            to_state=str(new_state),
            reason=reason,
        ))
        self.current_state = new_state
        self.updated_at    = datetime.now(timezone.utc).isoformat()

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        self.retry_count += 1
        self.updated_at   = datetime.now(timezone.utc).isoformat()

    # ── Step helpers ───────────────────────────────────────────────────────────

    def add_step(self, name: str, state: str, agent_name: str) -> WorkflowStep:
        step = WorkflowStep(name=name, state=state, agent_name=agent_name)
        self.steps.append(step)
        return step

    def current_step(self) -> Optional[WorkflowStep]:
        """Return the most recent IN_PROGRESS step, or None."""
        for step in reversed(self.steps):
            if step.status == StepStatus.IN_PROGRESS:
                return step
        return None

    def last_completed_state(self) -> Optional[WorkflowState]:
        """Return the WorkflowState of the last successfully DONE step (for resume)."""
        for step in reversed(self.steps):
            if step.status == StepStatus.DONE and step.state:
                try:
                    return WorkflowState(step.state)
                except ValueError:
                    continue
        return None

    # ── Serialization ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "task_id":         self.task_id,
            "task_type":       self.task_type,
            "goal":            self.goal[:1000],
            "current_state":   str(self.current_state),
            "steps":           [s.to_dict() for s in self.steps],
            "assigned_agents": self.assigned_agents,
            "retry_count":     self.retry_count,
            "max_retries":     self.max_retries,
            "created_at":      self.created_at,
            "updated_at":      self.updated_at,
            "completed_at":    self.completed_at,
            "result":          self.result[:2000] if self.result else None,
            "failure_reason":  self.failure_reason,
            "state_history":   [t.to_dict() for t in self.state_history],
            "metadata":        self.metadata,
        }

    @staticmethod
    def from_dict(d: dict) -> "OrchestratorTask":
        steps = [
            WorkflowStep(
                step_id       = s.get("step_id", str(uuid.uuid4())[:8]),
                name          = s.get("name", ""),
                state         = s.get("state", ""),
                agent_name    = s.get("agent_name", ""),
                status        = StepStatus(s.get("status", "pending")),
                output        = s.get("output", ""),
                error         = s.get("error", ""),
                swarm_task_ids= s.get("swarm_task_ids", []),
                started_at    = s.get("started_at"),
                completed_at  = s.get("completed_at"),
            )
            for s in d.get("steps", [])
        ]
        history = [
            StateTransition(
                from_state=t.get("from", ""),
                to_state  =t.get("to", ""),
                reason    =t.get("reason", ""),
                timestamp =t.get("timestamp", ""),
            )
            for t in d.get("state_history", [])
        ]
        return OrchestratorTask(
            goal            = d["goal"],
            task_id         = d["task_id"],
            task_type       = d.get("task_type", OrchTaskType.GENERIC),
            current_state   = WorkflowState(d.get("current_state", "created")),
            steps           = steps,
            assigned_agents = d.get("assigned_agents", []),
            retry_count     = d.get("retry_count", 0),
            max_retries     = d.get("max_retries", 3),
            created_at      = d.get("created_at", ""),
            updated_at      = d.get("updated_at", ""),
            completed_at    = d.get("completed_at"),
            result          = d.get("result"),
            failure_reason  = d.get("failure_reason"),
            state_history   = history,
            metadata        = d.get("metadata", {}),
        )
