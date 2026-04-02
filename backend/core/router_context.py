"""
router_context.py — Request-scoped context object passed through the CEO pipeline.

RouterContext carries intermediate state between each CEO decision step.
It is NOT the final output (that is RouterDecision).
It is NOT the input (that is RouterRequest).

It exists so each sub-step (intent, complexity, module, memory, web, etc.)
can read prior decisions without coupling to each other directly.

Rules:
- only CEO Router and its sub-steps write to this
- modules never receive or modify RouterContext
- all fields are optional — steps fill them in as they run
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RouterContext:
    # From request
    message:        str         = ""
    user_tier:      str         = "free"
    has_attachments: bool       = False
    mode_hint:      Optional[str] = None
    session_id:     Optional[str] = None
    user_id:        Optional[str] = None

    # Filled by intent_classifier
    primary_intent:   str   = "general_chat"
    secondary_intent: Optional[str] = None
    intent_confidence: float = 0.0

    # Filled by complexity_detector
    complexity:       str   = "simple"   # simple | multi_step | full_system
    is_underspecified: bool = False       # full_system but missing key details

    # Filled by module_selector
    selected_module:  str   = "core_chat"

    # Filled by memory_decider
    requires_memory:  bool  = False
    memory_scope:     Optional[str] = None

    # Filled by web_decider
    requires_web:     bool  = False
    web_mode:         Optional[str] = None  # search | scraper | crawler

    # Filled by clarification_engine
    needs_user_input: bool  = False
    clarification_question: Optional[str] = None

    # Filled by tier_controller
    tier_visibility:  str   = "free"

    # Filled by truth_classifier (Phase 67)
    truth_type:           str            = "stable_knowledge"
    tool_required:        bool           = False
    truth_can_answer:     bool           = True
    cannot_verify_reason: Optional[str]  = None
    injected_tool_result: Optional[dict] = None   # e.g. system_clock result

    # Filled by retrieval_engine (Phase 64)
    retrieval_result:     Optional[dict] = None

    # Meta
    events_emitted:   list  = field(default_factory=list)
