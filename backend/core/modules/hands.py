"""
modules/hands.py — Hands module: controlled execution of approved actions.

Applies changes, writes files, and runs commands — but ONLY when CEO has
explicitly approved and routed the action here.

Current state: limited — file write + command output acknowledgement only.
Future: actual file writes, deployments, shell command execution.

Output format:
  {
      "type":    "hands_output",
      "actions": [ {"action": str, "target": str, "status": str, "result": str} ],
      "summary": str,
  }

Rules:
- only runs when CEO explicitly routes execution here
- no autonomous action — every action must be traceable to the CEO decision
- all actions are logged before execution
- currently in limited mode — actions are acknowledged but not executed
- modules NEVER call each other — Hands does not call Builder or Doctor
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("ceo_router.modules.hands")


async def execute(
    decision:    dict[str, Any],
    memory:      dict[str, Any],
    web_results: dict[str, Any],
) -> dict[str, Any]:
    """
    Acknowledge and record the execution request.
    Currently in limited mode — actions are planned but not applied.
    """
    message = decision.get("message", "")
    actions = _parse_requested_actions(message)

    log.info("hands: %d action(s) requested (limited mode)", len(actions))

    acknowledged = []
    for action in actions:
        log.info("hands: action_type=%s target=%s", action["action"], action.get("target", ""))
        acknowledged.append({
            "action":  action["action"],
            "target":  action.get("target", ""),
            "status":  "acknowledged",
            "result":  _limited_mode_message(action),
        })

    summary = (
        f"{len(acknowledged)} action(s) acknowledged. "
        "Hands module is in limited mode — actions are recorded but not applied."
    )

    return {
        "type":    "hands_output",
        "actions": acknowledged,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Action parser
# ---------------------------------------------------------------------------

_WRITE_PAT = re.compile(
    r"\b(write|save|create|generate) (to |the )?(file|disk|path|directory)\b",
    re.IGNORECASE,
)
_APPLY_PAT = re.compile(
    r"\b(apply|apply (the )?changes|apply (the )?fix|apply (the )?patch)\b",
    re.IGNORECASE,
)
_DEPLOY_PAT = re.compile(
    r"\b(deploy|push to|release|publish|go live|ship)\b",
    re.IGNORECASE,
)
_RUN_PAT = re.compile(
    r"\b(run|execute|start|launch|trigger) (the |this )?(script|command|code|test|pipeline)\b",
    re.IGNORECASE,
)

_FILE_PATH_PAT = re.compile(r"[\w./\\-]+\.\w{1,10}")


def _parse_requested_actions(message: str) -> list[dict[str, str]]:
    """Extract what actions the user is requesting."""
    actions = []

    if _APPLY_PAT.search(message):
        actions.append({"action": "apply_changes", "target": "pending changes"})

    if _WRITE_PAT.search(message):
        path_match = _FILE_PATH_PAT.search(message)
        target = path_match.group() if path_match else "unspecified file"
        actions.append({"action": "write_file", "target": target})

    if _DEPLOY_PAT.search(message):
        actions.append({"action": "deploy", "target": "production"})

    if _RUN_PAT.search(message):
        actions.append({"action": "run_command", "target": "unspecified command"})

    if not actions:
        actions.append({"action": "general_execution", "target": message[:80]})

    return actions


def _limited_mode_message(action: dict) -> str:
    return (
        f"Action '{action['action']}' on '{action.get('target', '')}' received. "
        "Full execution (file writes, deployments, shell commands) is pending "
        "in a future Hands upgrade. No changes were applied."
    )
