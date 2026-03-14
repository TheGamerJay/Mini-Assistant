"""
mini_assistant/phase6 — Phase 6: Session Memory + Engineering Assistant + Model Selector
──────────────────────────────────────────────────────────────────────────────────────────
Full request flow after Phase 6:

    Command Parser      (Phase 1)
    → Planner           intent + task list  (Phase 1)
    → CEO               posture             (Phase 2)
    → Manager           session context     (Phase 2)  ← now injects session memory
    → Skill Selector    match known skill   (Phase 3)
    → ParallelSupervisor wave execution     (Phase 4)
    → MissionManager    multi-turn objective(Phase 4)
    → EngineeringAsst   ← NEW: context inject for code/debug intents
    → Brain             (image_system execution layer)
    → Critic            (Phase 1)
    → Reflection        log outcome         (Phase 3)
    → SessionMemory     ← NEW: extract + store facts from this turn
    → Composer          (Phase 1)

Public surface:

    from mini_assistant.phase6 import (
        SessionMemory, get_memory,
        EngineeringAssistant, get_engineering_assistant,
    )
"""

from .session_memory        import SessionMemory, get_memory, MemoryFact
from .engineering_assistant import EngineeringAssistant, get_engineering_assistant

__all__ = [
    "SessionMemory", "get_memory", "MemoryFact",
    "EngineeringAssistant", "get_engineering_assistant",
]
