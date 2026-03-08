"""
execution_intent.py – Structured Planner-to-Tool Contract
──────────────────────────────────────────────────────────
Defines the ExecutionIntent dataclass that the Planner brain outputs
when tool execution is required, and a parser to extract intents from
raw planner text.

The Planner is instructed to embed a JSON block in its output:

    ```json
    {
      "execution_intents": [
        {
          "action_type": "shell",
          "command": "git",
          "args": ["push", "origin", "main"],
          "cwd": "/app",
          "reason": "Deploy latest build to production branch",
          "risk_level": "medium"
        }
      ]
    }
    ```

ToolBrain executes ONLY these structured intents after SecurityBrain approval.
If no intents are present the deploying step returns the plan text as-is.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("swarm.execution_intent")

# ── Constants ──────────────────────────────────────────────────────────────────

VALID_ACTION_TYPES = frozenset({
    "shell",       # arbitrary safe shell command
    "git",         # git sub-command
    "npm",         # npm sub-command
    "pip",         # pip sub-command
    "python",      # run a python script
    "node",        # run a node script
    "file_write",  # write content to a file path
    "file_read",   # read a file path
    "mkdir",       # create directory
    "docker",      # docker sub-command (requires approval_required=True)
})

VALID_RISK_LEVELS = frozenset({"low", "medium", "high"})

# JSON block regex: captures ```json ... ``` blocks
_JSON_BLOCK_RE = re.compile(
    r"```json\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class ExecutionIntent:
    """
    A single structured tool-execution request from the Planner brain.
    ToolBrain executes these (after SecurityBrain approval) instead of
    extracting raw shell commands from planner free-text.
    """
    action_type: str                    # one of VALID_ACTION_TYPES
    command:     str                    # base command (e.g. "git", "npm")
    args:        list[str]              # positional args (e.g. ["push", "origin", "main"])
    cwd:         Optional[str]  = None  # working directory
    reason:      str            = ""    # human-readable justification
    risk_level:  str            = "low" # "low" | "medium" | "high"
    intent_id:   str            = field(
        default_factory=lambda: str(uuid.uuid4())[:8]
    )
    created_at:  str            = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def full_command(self) -> str:
        """Reconstruct the full command string for display/logging."""
        parts = [self.command] + self.args
        return " ".join(parts)

    def to_dict(self) -> dict:
        return {
            "intent_id":   self.intent_id,
            "action_type": self.action_type,
            "command":     self.command,
            "args":        self.args,
            "cwd":         self.cwd,
            "reason":      self.reason,
            "risk_level":  self.risk_level,
            "created_at":  self.created_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "ExecutionIntent":
        return ExecutionIntent(
            action_type = d.get("action_type", "shell"),
            command     = d.get("command", ""),
            args        = d.get("args", []),
            cwd         = d.get("cwd"),
            reason      = d.get("reason", ""),
            risk_level  = d.get("risk_level", "low"),
            intent_id   = d.get("intent_id", str(uuid.uuid4())[:8]),
            created_at  = d.get("created_at", datetime.now(timezone.utc).isoformat()),
        )

    def validate(self) -> tuple[bool, str]:
        """Return (valid, error_message). Empty error_message means valid."""
        if self.action_type not in VALID_ACTION_TYPES:
            return False, f"Unknown action_type '{self.action_type}'"
        if not self.command.strip():
            return False, "command is empty"
        if self.risk_level not in VALID_RISK_LEVELS:
            return False, f"Unknown risk_level '{self.risk_level}'"
        # High-risk intents must have a non-empty reason
        if self.risk_level == "high" and not self.reason.strip():
            return False, "high-risk intent requires a non-empty reason"
        return True, ""


# ── Parser ─────────────────────────────────────────────────────────────────────

def parse_execution_intents(planner_output: str) -> list[ExecutionIntent]:
    """
    Extract ExecutionIntent objects from a planner output string.

    The planner is expected to embed a JSON block:
        ```json
        {"execution_intents": [...]}
        ```

    Returns an empty list if no valid intents are found.
    Silently skips malformed intent entries and logs a warning.
    """
    intents: list[ExecutionIntent] = []

    for match in _JSON_BLOCK_RE.finditer(planner_output):
        raw_json = match.group(1)
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            logger.warning("[ExecutionIntent] JSON parse error: %s", exc)
            continue

        raw_list = data.get("execution_intents", [])
        if not isinstance(raw_list, list):
            continue

        for item in raw_list:
            if not isinstance(item, dict):
                continue
            try:
                intent = ExecutionIntent.from_dict(item)
                valid, err = intent.validate()
                if not valid:
                    logger.warning("[ExecutionIntent] Skipping invalid intent: %s | %s", err, item)
                    continue
                intents.append(intent)
                logger.debug("[ExecutionIntent] Parsed: %s %s (risk=%s)",
                             intent.action_type, intent.full_command, intent.risk_level)
            except Exception as exc:
                logger.warning("[ExecutionIntent] Failed to parse intent entry: %s", exc)

    return intents


def planner_tool_prompt_suffix() -> str:
    """
    Return the suffix to append to the planner's prompt when tool execution
    is expected (i.e. during DEPLOYING state or when tools are needed).
    The planner should embed a JSON block with structured execution intents.
    """
    return """
When tool execution is required, include a structured JSON block at the end of your response:

```json
{
  "execution_intents": [
    {
      "action_type": "git",
      "command": "git",
      "args": ["push", "origin", "main"],
      "cwd": "/app",
      "reason": "Push latest commits to production branch",
      "risk_level": "medium"
    }
  ]
}
```

action_type must be one of: shell, git, npm, pip, python, node, file_write, file_read, mkdir, docker
risk_level must be: low | medium | high
Include a clear reason for every intent. High-risk intents require explicit justification.
Do NOT include credentials, secrets, or passwords in any intent.
"""
