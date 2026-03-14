"""
mini_assistant/phase1 — Phase 1: Planner-First Core Routing
────────────────────────────────────────────────────────────
Public surface:

    from mini_assistant.phase1 import run_phase1

    result = await run_phase1(message, history=[])
    # result is a dict with: intent, plan, critic, reply_hint, slash_command

Components:
  command_parser.py  — slash command detector
  intent_planner.py  — blueprint Planner Brain (11 intents)
  critic.py          — basic response quality validator
  composer.py        — final response assembler
"""

from .command_parser import parse as parse_command, SLASH_COMMANDS
from .intent_planner import plan as make_plan, PlannerOutput
from .critic import critique, CriticResult
from .composer import compose

__all__ = [
    "parse_command",
    "SLASH_COMMANDS",
    "make_plan",
    "PlannerOutput",
    "critique",
    "CriticResult",
    "compose",
]
