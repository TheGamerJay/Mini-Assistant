"""
modules/core_chat.py — Core chat module stub.

Receives a RouterDecision and executes general conversation.
Routes to the existing image_system streaming endpoint internally.

Rules:
- does NOT decide routing — reads decision from RouterDecision
- does NOT load memory — memory is pre-loaded by module_executor
- does NOT call other modules directly
"""

from __future__ import annotations

from typing import Any


async def execute(decision: dict, memory: dict, web_results: dict) -> dict[str, Any]:
    """
    Stub — wired to image_system streaming in module_executor.
    """
    return {
        "module":  "core_chat",
        "status":  "routed_to_streaming",
        "decision": decision,
    }
