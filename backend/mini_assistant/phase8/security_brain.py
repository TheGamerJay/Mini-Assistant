"""
backend/mini_assistant/phase8/security_brain.py

Security / Guardrail Brain — intercepts every tool call before execution.

Decision flow:
  1. Look up the ToolDef from tool_registry (sets baseline risk).
  2. Scan the command string for danger patterns (escalated risk).
  3. Check blocked patterns (always refuse).
  4. Return a SecurityDecision with final risk level + reasoning.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .tool_registry import ToolDef, get_tool


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# These patterns ALWAYS result in "blocked" regardless of tool category.
_BLOCKED_PATTERNS: List[re.Pattern] = [re.compile(p, re.IGNORECASE) for p in [
    r"rm\s+-rf\s+/",            # wipe root filesystem
    r"dd\s+if=",                # disk-wipe via dd
    r"mkfs\.",                  # format filesystem
    r":\(\)\{.*\};:",            # fork bomb
    r"curl\s+.*\|\s*sh",        # curl-pipe-sh
    r"wget\s+.*\|\s*sh",        # wget-pipe-sh
    r"chmod\s+777\s+/",         # open-up root
    r"sudo\s+rm",               # sudo delete
    r">\s*/dev/sda",            # overwrite block device
    r"shutdown\s",              # system shutdown
    r"halt\b",                  # system halt
    r"reboot\b",                # reboot
    r"poweroff\b",              # power off
]]

# These patterns escalate risk from "caution" → "danger" or confirm "danger".
_DANGER_PATTERNS: List[re.Pattern] = [re.compile(p, re.IGNORECASE) for p in [
    r"--force",
    r"-f\b",
    r"--hard",
    r"reset\s+head",
    r"push\s+.*--force",
    r"push\s+-f\b",
    r"drop\s+table",
    r"truncate\s+table",
    r"delete\s+from",
    r"rm\s+-r",
    r"rmdir",
    r"shutil\.rmtree",
    r"os\.remove",
    r"unlink\(",
    r"format\s+[a-z]:",          # Windows format drive
]]

# Path traversal / injection guards for file operations.
_INJECTION_PATTERNS: List[re.Pattern] = [re.compile(p, re.IGNORECASE) for p in [
    r"\.\./\.\.",               # deep path traversal
    r";\s*[a-z]",               # command chaining via ;
    r"\|\|",                    # OR chaining
    r"&&",                      # AND chaining (flag — may be legit in shell_exec)
    r"`[^`]+`",                 # backtick substitution
    r"\$\([^)]+\)",             # $() substitution
]]


# ---------------------------------------------------------------------------
# SecurityDecision
# ---------------------------------------------------------------------------

@dataclass
class SecurityDecision:
    tool_name: str
    command: str
    risk_level: str                   # safe | caution | danger | blocked
    requires_approval: bool
    blocked: bool
    reasons: List[str] = field(default_factory=list)
    tool_def: Optional[ToolDef] = None

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "command": self.command,
            "risk_level": self.risk_level,
            "requires_approval": self.requires_approval,
            "blocked": self.blocked,
            "reasons": self.reasons,
        }


# ---------------------------------------------------------------------------
# SecurityBrain
# ---------------------------------------------------------------------------

class SecurityBrain:
    """
    Stateless guardrail classifier.  Call `evaluate(tool_name, command)` before
    every tool execution.  The result tells ToolBrain whether to run, queue for
    approval, or hard-block the request.
    """

    # Risk level ordering (higher index = more severe)
    _RISK_ORDER = ["safe", "caution", "danger", "blocked"]

    @classmethod
    def _max_risk(cls, a: str, b: str) -> str:
        ia = cls._RISK_ORDER.index(a) if a in cls._RISK_ORDER else 0
        ib = cls._RISK_ORDER.index(b) if b in cls._RISK_ORDER else 0
        return cls._RISK_ORDER[max(ia, ib)]

    def evaluate(self, tool_name: str, command: str) -> SecurityDecision:
        reasons: List[str] = []
        tool_def = get_tool(tool_name)

        # --- Baseline risk from tool registry ---
        if tool_def:
            risk = tool_def.default_risk
            needs_approval = tool_def.requires_approval
        else:
            # Unknown tool → treat as danger
            risk = "danger"
            needs_approval = True
            reasons.append(f"Unknown tool '{tool_name}' — defaulting to danger")

        # --- Hard-blocked patterns ---
        for pattern in _BLOCKED_PATTERNS:
            if pattern.search(command):
                return SecurityDecision(
                    tool_name=tool_name,
                    command=command,
                    risk_level="blocked",
                    requires_approval=False,
                    blocked=True,
                    reasons=[f"Blocked pattern matched: {pattern.pattern}"],
                    tool_def=tool_def,
                )

        # --- Danger escalation patterns ---
        for pattern in _DANGER_PATTERNS:
            if pattern.search(command):
                risk = self._max_risk(risk, "danger")
                needs_approval = True
                reasons.append(f"Danger pattern detected: {pattern.pattern}")
                break  # one match is enough to escalate

        # --- Injection / traversal patterns (for non-shell_exec tools) ---
        if tool_name != "shell_exec":
            for pattern in _INJECTION_PATTERNS:
                if pattern.search(command):
                    risk = self._max_risk(risk, "danger")
                    needs_approval = True
                    reasons.append(f"Potential injection detected: {pattern.pattern}")
                    break

        if not reasons:
            reasons.append(f"Risk based on tool category: {risk}")

        return SecurityDecision(
            tool_name=tool_name,
            command=command,
            risk_level=risk,
            requires_approval=needs_approval,
            blocked=False,
            reasons=reasons,
            tool_def=tool_def,
        )


# Singleton
security_brain = SecurityBrain()


def evaluate_tool(tool_name: str, command: str) -> SecurityDecision:
    """Convenience wrapper around the singleton."""
    return security_brain.evaluate(tool_name, command)
