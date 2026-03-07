"""
task_models.py – Swarm Task Data Models
─────────────────────────────────────────
Defines the core data structures shared by every component of the swarm.

  SwarmTask   – a single unit of work assigned to one agent
  TaskResult  – the output of an executed task
  SwarmResult – the final combined output of an entire swarm run
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ─── Enumerations ─────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING  = "pending"    # waiting to be picked up
    RUNNING  = "running"    # currently executing
    COMPLETE = "complete"   # finished successfully
    FAILED   = "failed"     # failed and retries exhausted
    BLOCKED  = "blocked"    # dependencies not yet met (informational)


class TaskType(str, Enum):
    RESEARCH      = "research"
    CODING        = "coding"
    DEBUG         = "debug"
    TESTING       = "testing"
    FILE_ANALYSIS = "file_analysis"
    VISION        = "vision"
    PLANNING      = "planning"
    IMAGE_GEN     = "image_gen"
    GENERIC       = "generic"


# Maps task type → default agent name
TASK_AGENT_MAP: dict[str, str] = {
    TaskType.RESEARCH:      "research_agent",
    TaskType.CODING:        "coding_agent",
    TaskType.DEBUG:         "debug_agent",
    TaskType.TESTING:       "tester_agent",
    TaskType.FILE_ANALYSIS: "file_analyst_agent",
    TaskType.VISION:        "vision_agent",
    TaskType.PLANNING:      "planner_agent",
    TaskType.IMAGE_GEN:     "vision_agent",
    TaskType.GENERIC:       "research_agent",
}


# ─── Task ─────────────────────────────────────────────────────────────────────

@dataclass
class SwarmTask:
    """
    A single unit of work within a swarm run.

    Fields
    ------
    id             Auto-generated short UUID (8 chars).
    type           One of TaskType values – drives agent assignment.
    description    Human-readable task description fed to the agent.
    assigned_agent The agent that will execute this task.
    depends_on     List of task ids that must complete before this one starts.
    priority       1 = highest priority, 10 = lowest.
    args           Arbitrary key-value args passed to the agent at runtime.
                   Common keys: query, path, images, code, error, language.
    status         Mutable lifecycle field updated by the TaskQueue.
    result         Set to TaskResult after execution.
    error          Error message if status == FAILED.
    retries        How many times this task has been retried.
    max_retries    Max retries before marking as FAILED (default 2).
    """
    description:    str
    type:           str                  = TaskType.GENERIC
    id:             str                  = field(default_factory=lambda: str(uuid.uuid4())[:8])
    assigned_agent: str                  = ""
    depends_on:     list[str]            = field(default_factory=list)
    priority:       int                  = 5
    args:           dict[str, Any]       = field(default_factory=dict)
    status:         TaskStatus           = TaskStatus.PENDING
    result:         Optional[Any]        = field(default=None, repr=False)
    error:          Optional[str]        = None
    retries:        int                  = 0
    max_retries:    int                  = 2
    created_at:     str                  = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    started_at:     Optional[str]        = None
    completed_at:   Optional[str]        = None

    def __post_init__(self):
        # Auto-assign agent based on type if not provided
        if not self.assigned_agent:
            self.assigned_agent = TASK_AGENT_MAP.get(self.type, "research_agent")

    def mark_started(self) -> None:
        self.status     = TaskStatus.RUNNING
        self.started_at = datetime.now(timezone.utc).isoformat()

    def mark_complete(self, result: "TaskResult") -> None:
        self.status       = TaskStatus.COMPLETE
        self.result       = result
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def mark_failed(self, error: str) -> None:
        self.status       = TaskStatus.FAILED
        self.error        = error
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def can_retry(self) -> bool:
        return self.retries < self.max_retries

    def to_dict(self) -> dict:
        return {
            "id":             self.id,
            "type":           self.type,
            "description":    self.description,
            "assigned_agent": self.assigned_agent,
            "depends_on":     self.depends_on,
            "status":         str(self.status),
            "priority":       self.priority,
            "args":           self.args,
            "retries":        self.retries,
            "error":          self.error,
            "created_at":     self.created_at,
            "started_at":     self.started_at,
            "completed_at":   self.completed_at,
        }


# ─── Task result ──────────────────────────────────────────────────────────────

@dataclass
class TaskResult:
    """Output from a single agent execution."""
    task_id:  str
    agent:    str
    success:  bool
    output:   str                 = ""     # primary text output
    data:     dict[str, Any]      = field(default_factory=dict)   # structured extras
    error:    Optional[str]       = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "agent":   self.agent,
            "success": self.success,
            "output":  self.output[:4000],
            "error":   self.error,
        }


# ─── Swarm run result ─────────────────────────────────────────────────────────

@dataclass
class SwarmResult:
    """Combined output of an entire swarm execution."""
    run_id:          str
    request:         str
    success:         bool
    final_output:    str
    tasks:           list[SwarmTask]            = field(default_factory=list)
    task_results:    dict[str, TaskResult]      = field(default_factory=dict)
    summary:         str                        = ""
    errors:          list[str]                  = field(default_factory=list)
    duration_seconds: float                     = 0.0

    def to_dict(self) -> dict:
        return {
            "run_id":           self.run_id,
            "request":          self.request[:200],
            "success":          self.success,
            "final_output":     self.final_output,
            "summary":          self.summary,
            "task_count":       len(self.tasks),
            "tasks":            [t.to_dict() for t in self.tasks],
            "errors":           self.errors,
            "duration_seconds": round(self.duration_seconds, 2),
        }
