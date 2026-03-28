"""
Mode Guard — Phase 4

Enforces strict isolation between Mini Assistant's three operating modes:
  - chat:    conversational only — no builder execution, no image gen tools
  - image:   image generation/editing only — own state, no builder logic
  - builder: full orchestration, file editing, checkpoints, execution plans

Rules:
  - Each mode has its own allowed tool set
  - Cross-mode actions are blocked
  - Mode switches require explicit confirmation (no silent auto-switch)
  - Shared: only high-level user preferences

Called before every tool invocation in the orchestration pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import FrozenSet, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mode → allowed tool categories
# ---------------------------------------------------------------------------

_MODE_TOOLS: dict[str, FrozenSet[str]] = {
    "chat": frozenset({
        "respond", "search", "fetch_memory", "code_review",
        "explain", "analyze_text", "voice_transcribe",
    }),
    "image": frozenset({
        "generate_image", "edit_image", "analyze_image",
        "fetch_memory", "respond",
    }),
    "builder": frozenset({
        "respond", "build_code", "patch_code", "analyze_code",
        "execute_code", "checkpoint", "rollback", "deploy",
        "generate_image", "analyze_image",
        "fetch_memory", "search", "code_review", "explain",
        "run_tests", "visual_review",
    }),
}

# Which modes require explicit user confirmation to enter
_CONFIRMATION_REQUIRED = {"builder", "deploy"}


@dataclass
class ModeCheckResult:
    allowed:      bool
    mode:         str
    tool:         str
    reason:       str
    switch_needed: Optional[str] = None   # set if tool requires a different mode


def check(tool_name: str, current_mode: str) -> ModeCheckResult:
    """
    Verify that `tool_name` is allowed in `current_mode`.

    Args:
        tool_name:    Internal tool category name.
        current_mode: "chat" | "image" | "builder"

    Returns:
        ModeCheckResult — check .allowed before proceeding.
    """
    allowed_tools = _MODE_TOOLS.get(current_mode, frozenset())

    if tool_name in allowed_tools:
        return ModeCheckResult(
            allowed=True,
            mode=current_mode,
            tool=tool_name,
            reason="Tool is allowed in current mode.",
        )

    # Find which mode does allow this tool
    correct_mode = None
    for mode, tools in _MODE_TOOLS.items():
        if tool_name in tools:
            correct_mode = mode
            break

    if correct_mode:
        reason = (
            f"Tool '{tool_name}' is not available in {current_mode} mode. "
            f"Switch to {correct_mode} mode to use it."
        )
        logger.warning("[ModeGuard] BLOCKED tool=%s mode=%s → requires mode=%s", tool_name, current_mode, correct_mode)
        return ModeCheckResult(
            allowed=False,
            mode=current_mode,
            tool=tool_name,
            reason=reason,
            switch_needed=correct_mode,
        )

    # Unknown tool
    reason = f"Unknown tool '{tool_name}' — not registered in any mode."
    logger.warning("[ModeGuard] UNKNOWN tool=%s", tool_name)
    return ModeCheckResult(
        allowed=False,
        mode=current_mode,
        tool=tool_name,
        reason=reason,
    )


def validate_mode_switch(from_mode: str, to_mode: str) -> tuple[bool, str]:
    """
    Check whether a mode switch is allowed and what confirmation is needed.

    Returns:
        (allowed: bool, message: str)
    """
    if from_mode == to_mode:
        return True, "Already in this mode."

    if to_mode not in _MODE_TOOLS:
        return False, f"Unknown mode: {to_mode}"

    if to_mode in _CONFIRMATION_REQUIRED:
        return True, (
            f"Switching to {to_mode.title()} mode. "
            f"This will pause {from_mode.title()} mode state. Continue?"
        )

    return True, f"Switching from {from_mode} to {to_mode} mode."
