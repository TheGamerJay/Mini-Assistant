"""
mini_assistant/phase2 — Phase 2: Executive Hierarchy Foundation
────────────────────────────────────────────────────────────────
Full request flow after Phase 2:

    Command Parser  (Phase 1)
    → CEO           sets posture: mode, risk, priority
    → Manager       normalizes message, injects session context
    → Planner       ALWAYS FIRST — intent + task list  (Phase 1)
    → Supervisor    task state tracking + execution coordination
    → Brain         (existing image_system execution layer)
    → Critic        (Phase 1)
    → Composer      (Phase 1)

Public surface:

    from mini_assistant.phase2 import run_executive

    ceo_posture, manager_packet, supervisor = run_executive(
        message, session_id, plan, history
    )
"""

from .ceo        import assess as ceo_assess,  CEOPosture
from .manager    import prepare as mgr_prepare, ManagerPacket, get_session_summary
from .supervisor import Supervisor, SupervisorResult
from .models     import MODEL_CONFIG, get_model
from .router     import call_model
from .qa         import review as qa_review, should_run_qa

__all__ = [
    # Phase 2 core
    "ceo_assess",
    "CEOPosture",
    "mgr_prepare",
    "ManagerPacket",
    "get_session_summary",
    "Supervisor",
    "SupervisorResult",
    # Multi-model routing
    "MODEL_CONFIG",
    "get_model",
    "call_model",
    # QA feedback loop
    "qa_review",
    "should_run_qa",
]
