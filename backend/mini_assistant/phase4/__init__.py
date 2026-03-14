"""
mini_assistant/phase4 — Phase 4: Parallel Optimization + Mission Persistence
─────────────────────────────────────────────────────────────────────────────
Full request flow after Phase 4:

    Command Parser   (Phase 1)
    → Planner        intent + task list  (Phase 1)
    → CEO            posture             (Phase 2)
    → Manager        session context     (Phase 2)
    → Skill Selector match known skill   (Phase 3)
    → ParallelSupervisor ← NEW: wave-based async task execution
    → Brain          (image_system execution layer)
    → Critic         (Phase 1)
    → Reflection     log outcome         (Phase 3)
    → Composer       (Phase 1)
    → MissionManager ← NEW: update/create multi-turn mission

Public surface:

    from mini_assistant.phase4 import (
        ParallelSupervisor, run_plan,
        MissionManager, get_mission_manager,
        MissionStore, Mission,
    )
"""

from .parallel_supervisor import ParallelSupervisor, run_plan, WaveResult
from .mission_store      import MissionStore, Mission
from .mission_manager    import MissionManager, get_mission_manager

__all__ = [
    "ParallelSupervisor", "run_plan", "WaveResult",
    "MissionStore", "Mission",
    "MissionManager", "get_mission_manager",
]
