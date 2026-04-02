"""
router_types.py — Shared data contracts for the CEO Router.

RouterRequest  : normalized input from any caller
RouterDecision : structured decision returned by CEO — source of truth for execution
ExecutionStep  : single step inside the execution plan

Rules:
- No business logic here — types only
- All fields must remain JSON-serialisable
- mode_hint is informational only; CEO may ignore it
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Input contract
# ---------------------------------------------------------------------------

@dataclass
class RouterRequest:
    """
    Normalized request object passed to route_request().

    message          : required — the user's raw text
    user_id          : optional — for TR memory scoping
    session_id       : optional — for conversation continuity
    attachments      : list of base64 strings or file metadata dicts
    mode_hint        : optional UI hint — NEVER authoritative
    user_tier        : "free" | "paid" — controls depth and visibility
    context_available: which modules are available this session
    """
    message:            str
    user_id:            Optional[str]  = None
    session_id:         Optional[str]  = None
    attachments:        list           = field(default_factory=list)
    mode_hint:          Optional[str]  = None
    user_tier:          str            = "free"
    authorization:      Optional[str]  = None   # Bearer token — for billing deduction
    context_available:  dict           = field(default_factory=lambda: {
        "task_assist":      True,
        "campaign_lab":     True,
        "web_intelligence": True,
    })

    def to_dict(self) -> dict:
        return {
            "user_id":           self.user_id,
            "session_id":        self.session_id,
            "message":           self.message,
            "attachments":       self.attachments,
            "mode_hint":         self.mode_hint,
            "user_tier":         self.user_tier,
            "context_available": self.context_available,
        }


# ---------------------------------------------------------------------------
# Execution plan step
# ---------------------------------------------------------------------------

@dataclass
class ExecutionStep:
    step:   int
    type:   str            # "module_call" | "memory_load" | "web_call" | "clarify"
    target: str            # module name or tool name
    reason: str

    def to_dict(self) -> dict:
        return {
            "step":   self.step,
            "type":   self.type,
            "target": self.target,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Output contract
# ---------------------------------------------------------------------------

@dataclass
class RouterDecision:
    """
    Structured decision object returned by CEO Router.

    This is the ONLY source of truth for the execution layer.
    No module may deviate from this decision.
    """
    intent:               str
    complexity:           str            # "simple" | "multi_step" | "full_system"
    selected_module:      str            # see MODULE_NAMES in module_selector.py
    requires_memory:      bool
    memory_scope:         Optional[str]
    requires_web:         bool
    web_mode:             Optional[str]  # "search" | "scraper" | "crawler"
    requires_backend:     bool
    needs_user_input:     bool
    clarification_question: Optional[str]
    execution_plan:       list[ExecutionStep] = field(default_factory=list)
    validation_required:  bool           = True
    tier_visibility:      str            = "free"  # "free" | "paid"
    # Original request fields — threaded through so modules don't need RouterRequest
    message:              Optional[str]  = None
    attachments:          list           = field(default_factory=list)

    # Truth classification (Phase 67)
    truth_type:           str            = "stable_knowledge"
    truth_can_answer:     bool           = True
    cannot_verify_reason: Optional[str]  = None
    injected_tool_result: Optional[dict] = None   # pre-fetched tool result (e.g. clock)

    # Billing (this bracket)
    billing_status:       str            = "approved"   # "approved" | "blocked" | "grace"
    billing_warning:      Optional[dict] = None         # low-credit warning to surface to user

    # Session context (Phase 62)
    session_context:      Optional[dict] = None   # loaded from context_store

    def to_dict(self) -> dict:
        return {
            "intent":                self.intent,
            "complexity":            self.complexity,
            "selected_module":       self.selected_module,
            "requires_memory":       self.requires_memory,
            "memory_scope":          self.memory_scope,
            "requires_web":          self.requires_web,
            "web_mode":              self.web_mode,
            "requires_backend":      self.requires_backend,
            "needs_user_input":      self.needs_user_input,
            "clarification_question": self.clarification_question,
            "execution_plan":        [s.to_dict() for s in self.execution_plan],
            "validation_required":   self.validation_required,
            "tier_visibility":       self.tier_visibility,
            "message":               self.message,
            "attachments":           self.attachments,
            "truth_type":            self.truth_type,
            "truth_can_answer":      self.truth_can_answer,
            "cannot_verify_reason":  self.cannot_verify_reason,
        }
