"""
security_brain.py – Security Brain (tool guardrail)
────────────────────────────────────────────────────
Validates shell commands and tool actions before execution.
All decisions are recorded in the task's debug_log.

Levels:
  BLOCKED  → command matches a dangerous pattern, execution denied
  WARNING  → command is potentially destructive, allowed with a warning entry
  APPROVED → command is safe
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger("swarm.security_brain")

# ── Dangerous patterns that are always blocked ─────────────────────────────────
_BLOCKED_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\s+-[rf]{1,2}\b",          "Recursive remove"),
    (r"\bdd\s+if=",                    "Low-level disk write (dd)"),
    (r":\(\)\{.*:\|:&\};:",            "Fork bomb"),
    (r"\bmkfs\b",                      "Filesystem format"),
    (r"\bformat\s+[a-zA-Z]:",         "Windows drive format"),
    (r"\bdrop\s+database\b",           "DROP DATABASE"),
    (r"\btruncate\s+table\b",          "TRUNCATE TABLE"),
    (r"\bdrop\s+table\b",              "DROP TABLE"),
    (r">\s*/dev/[sh]d[a-z]",          "Overwrite raw disk device"),
    (r"\b(shutdown|reboot|halt)\b",    "System shutdown/reboot"),
    (r"\bchmod\s+[0-7]*7\s+/\b",      "chmod 777 on root path"),
    (r"\bsudo\s+rm\b",                 "sudo rm"),
    (r"\bkill\s+-9\s+1\b",            "Kill PID 1 (init)"),
    (r"\bwipe\s+/",                    "Wipe root path"),
    (r"\bnpx\s+--yes\s+create-react-app\s+--scripts-version\s+dangerous", "Malicious npm package"),
]

# ── Warning patterns (allowed but logged) ─────────────────────────────────────
_WARNING_PATTERNS: list[tuple[str, str]] = [
    (r"\bdrop\b",     "DROP keyword"),
    (r"\bdelete\b",   "DELETE keyword"),
    (r"\bpurge\b",    "PURGE keyword"),
    (r"\btruncate\b", "TRUNCATE keyword"),
    (r"\bnuke\b",     "NUKE keyword"),
    (r"\bwipe\b",     "WIPE keyword"),
    (r"\bforce\b",    "FORCE keyword"),
    (r"\bgit\s+push\s+.*--force\b", "git push --force"),
    (r"\breset\s+--hard\b", "git reset --hard"),
]

_COMPILED_BLOCKED  = [(re.compile(p, re.IGNORECASE | re.DOTALL), desc) for p, desc in _BLOCKED_PATTERNS]
_COMPILED_WARNINGS = [(re.compile(p, re.IGNORECASE), desc)             for p, desc in _WARNING_PATTERNS]


class SecurityBrain:
    """
    Validates commands before ToolBrain executes them.
    Returns (approved: bool, level: str, reason: str).
    """

    def validate(self, command: str, task_id: str = "") -> tuple[bool, str, str]:
        """
        Returns:
          (False, "blocked",   reason) – command is dangerous, must not run
          (True,  "warning",   reason) – command is risky, allowed with log entry
          (True,  "approved",  "")     – command is safe
        """
        cmd_lower = command.strip()

        for pattern, desc in _COMPILED_BLOCKED:
            if pattern.search(cmd_lower):
                reason = f"BLOCKED [{desc}]: command matches dangerous pattern"
                logger.warning("[SecurityBrain][%s] %s | cmd=%.200s", task_id[:8], reason, command)
                return False, "blocked", reason

        for pattern, desc in _COMPILED_WARNINGS:
            if pattern.search(cmd_lower):
                reason = f"WARNING [{desc}]: potentially destructive keyword detected"
                logger.warning("[SecurityBrain][%s] %s | cmd=%.200s", task_id[:8], reason, command)
                return True, "warning", reason

        logger.debug("[SecurityBrain][%s] APPROVED | cmd=%.80s", task_id[:8], command)
        return True, "approved", ""

    def audit_entry(
        self,
        task_id:  str,
        command:  str,
        approved: bool,
        level:    str,
        reason:   str,
    ) -> dict:
        """Build a structured audit entry for the task's debug_log."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type":      "security_check",
            "brain":     "security_brain",
            "task_id":   task_id,
            "command":   command[:300],
            "approved":  approved,
            "level":     level,   # "approved" | "warning" | "blocked"
            "reason":    reason,
        }
