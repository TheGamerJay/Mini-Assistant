"""
security_brain.py – Security Brain (tool guardrail)
────────────────────────────────────────────────────
Validates shell commands and tool actions before execution.
Returns structured SecurityDecision objects.

Decision levels:
  BLOCKED  → command matches a dangerous pattern, execution denied
  WARNING  → command is potentially destructive, allowed with log entry
  APPROVED → command is safe

Phase 9 hardening: expanded patterns covering path traversal, secret
leakage, git destructive ops, suspicious piping, env exposure, and
deployment credential leakage.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("swarm.security_brain")


# ── Security levels ────────────────────────────────────────────────────────────

class SecurityLevel:
    APPROVED = "approved"
    WARNING  = "warning"
    BLOCKED  = "blocked"


# ── Blocked patterns (never executed) ─────────────────────────────────────────

_BLOCKED_PATTERNS: list[tuple[str, str]] = [
    # Destructive file ops
    (r"\brm\s+-[rf]{1,2}\b",                         "Recursive remove"),
    (r"\brm\s+.*--recursive\b",                      "Recursive remove (--recursive flag)"),
    (r"\bsudo\s+rm\b",                               "sudo rm"),
    (r"\bwipe\s+/",                                  "Wipe root path"),

    # Low-level / disk
    (r"\bdd\s+if=",                                  "Low-level disk write (dd)"),
    (r"\bmkfs\b",                                    "Filesystem format"),
    (r"\bformat\s+[a-zA-Z]:",                        "Windows drive format"),
    (r">\s*/dev/[sh]d[a-z]",                         "Overwrite raw disk device"),

    # Fork bomb / system
    (r":\(\)\{.*:\|:&\};:",                          "Fork bomb"),
    (r"\b(shutdown|reboot|halt)\b",                  "System shutdown/reboot"),
    (r"\bkill\s+-9\s+1\b",                           "Kill PID 1 (init)"),

    # Database destructive
    (r"\bdrop\s+database\b",                         "DROP DATABASE"),
    (r"\btruncate\s+table\b",                        "TRUNCATE TABLE"),
    (r"\bdrop\s+table\b",                            "DROP TABLE"),

    # Permission escalation
    (r"\bchmod\s+[0-7]*7\s+/\b",                    "chmod 777 on root path"),
    (r"\bchown\s+.*\s+/\b",                          "chown on root"),

    # Path traversal attempts
    (r"\.\./\.\./\.\./",                             "Deep path traversal (../../..)"),
    (r"~root/",                                      "Root home access attempt"),
    (r"/etc/shadow",                                 "Shadow password file access"),
    (r"/etc/passwd",                                 "Passwd file access"),
    (r"/proc/.*mem",                                 "Process memory access"),

    # Secret leakage / credential exposure
    (r"\bcat\s+.*\.pem\b",                           "Private key file read (PEM)"),
    (r"\bcat\s+.*\.key\b",                           "Private key file read (.key)"),
    (r"\bcat\s+.*id_rsa\b",                          "SSH private key read"),
    (r"\bcp\s+.*\.env\s+/",                          "Copy .env to root path"),
    (r"\bcurl\b.*\bpassword\b",                      "Password in curl command"),
    (r"\bwget\b.*\bpassword\b",                      "Password in wget command"),

    # Malicious npm
    (r"\bnpx\s+--yes\s+create-react-app\s+--scripts-version\s+dangerous",
                                                     "Malicious npm package"),

    # Suspicious exfiltration
    (r"\bbase64\b.*\|\s*curl\b",                     "Base64 encode + curl (exfil)"),
    (r"\bbase64\b.*\|\s*wget\b",                     "Base64 encode + wget (exfil)"),

    # Crontab injection
    (r"\bcrontab\s+-r\b",                            "Remove all crontabs"),
    (r"\becho\b.*>>\s*/etc/cron",                    "Crontab injection via echo"),
]


# ── Warning patterns (allowed but logged) ─────────────────────────────────────

_WARNING_PATTERNS: list[tuple[str, str]] = [
    # SQL keywords
    (r"\bdrop\b",                         "DROP keyword"),
    (r"\bdelete\b",                       "DELETE keyword"),
    (r"\bpurge\b",                        "PURGE keyword"),
    (r"\btruncate\b",                     "TRUNCATE keyword"),
    (r"\bnuke\b",                         "NUKE keyword"),
    (r"\bwipe\b",                         "WIPE keyword"),
    (r"\bforce\b",                        "FORCE keyword"),

    # Git destructive
    (r"\bgit\s+push\s+.*--force\b",       "git push --force"),
    (r"\bgit\s+push\s+-f\b",              "git push -f"),
    (r"\breset\s+--hard\b",               "git reset --hard"),
    (r"\bgit\s+clean\s+-[fd]{1,2}",       "git clean -fd"),
    (r"\bgit\s+branch\s+-[Dd]\b",         "git branch delete"),

    # Environment variable exposure
    (r"\benv\b\s*$",                      "env dump (no args)"),
    (r"\bprintenv\b",                     "printenv dump"),
    (r"\bset\b\s*$",                      "set dump (may show secrets)"),

    # Suspicious piping chains
    (r"\|\s*bash\b",                      "Pipe to bash (code injection risk)"),
    (r"\|\s*sh\b",                        "Pipe to sh (code injection risk)"),
    (r"\|\s*python3?\b",                  "Pipe to python (code injection risk)"),
    (r"\bcurl\b.*\|\s*(bash|sh)\b",       "curl | bash pattern"),
    (r"\bwget\b.*-O-\b.*\|\s*(bash|sh)",  "wget | bash pattern"),

    # Deployment credential leakage
    (r"--token\s+\S+",                    "Token in command args"),
    (r"--password\s+\S+",                 "Password in command args"),
    (r"-p\s+\S+",                         "Password flag with value"),
    (r"API_KEY=\S+",                      "Hardcoded API key in command"),
    (r"SECRET=\S+",                       "Hardcoded secret in command"),

    # npm/pip unsafe
    (r"\bnpm\s+install\b.*--no-save",     "npm install --no-save (audit trail risk)"),
    (r"\bpip\s+install\b.*--user",        "pip install --user (scope concern)"),
]


_COMPILED_BLOCKED  = [(re.compile(p, re.IGNORECASE | re.DOTALL), d) for p, d in _BLOCKED_PATTERNS]
_COMPILED_WARNINGS = [(re.compile(p, re.IGNORECASE), d)             for p, d in _WARNING_PATTERNS]


# ── SecurityDecision dataclass ─────────────────────────────────────────────────

@dataclass
class SecurityDecision:
    """
    Structured result from SecurityBrain.validate().

    Fields
    ------
    approved        True if execution is permitted (level = approved | warning)
    level           "approved" | "warning" | "blocked"
    reason          Human-readable explanation (empty for approved)
    matched_pattern The pattern description that triggered, if any
    command         The command that was evaluated (truncated to 300 chars)
    task_id         Task context for audit trail
    timestamp       UTC ISO timestamp
    """
    approved:        bool
    level:           str
    reason:          str
    matched_pattern: str
    command:         str
    task_id:         str
    timestamp:       str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def is_blocked(self) -> bool:
        return self.level == SecurityLevel.BLOCKED

    @property
    def is_warning(self) -> bool:
        return self.level == SecurityLevel.WARNING

    @property
    def is_approved(self) -> bool:
        return self.level == SecurityLevel.APPROVED

    def to_dict(self) -> dict:
        return {
            "timestamp":       self.timestamp,
            "type":            "security_check",
            "brain":           "security_brain",
            "task_id":         self.task_id,
            "command":         self.command,
            "approved":        self.approved,
            "level":           self.level,
            "reason":          self.reason,
            "matched_pattern": self.matched_pattern,
        }


# ── SecurityBrain ──────────────────────────────────────────────────────────────

class SecurityBrain:
    """
    Validates commands before ToolBrain executes them.
    Returns a structured SecurityDecision for full audit traceability.
    """

    def validate(
        self,
        command: str,
        task_id: str = "",
    ) -> SecurityDecision:
        """
        Validate a shell command against blocked/warning pattern lists.

        Returns a SecurityDecision with:
          level="blocked"  – must not run
          level="warning"  – risky, allowed with log entry
          level="approved" – safe
        """
        truncated = command.strip()[:300]

        for pattern, desc in _COMPILED_BLOCKED:
            if pattern.search(command.strip()):
                reason = f"BLOCKED [{desc}]: command matches dangerous pattern"
                logger.warning(
                    "[SecurityBrain][%s] %s | cmd=%.200s",
                    task_id[:8], reason, command,
                )
                return SecurityDecision(
                    approved        = False,
                    level           = SecurityLevel.BLOCKED,
                    reason          = reason,
                    matched_pattern = desc,
                    command         = truncated,
                    task_id         = task_id,
                )

        for pattern, desc in _COMPILED_WARNINGS:
            if pattern.search(command.strip()):
                reason = f"WARNING [{desc}]: potentially destructive keyword detected"
                logger.warning(
                    "[SecurityBrain][%s] %s | cmd=%.200s",
                    task_id[:8], reason, command,
                )
                return SecurityDecision(
                    approved        = True,
                    level           = SecurityLevel.WARNING,
                    reason          = reason,
                    matched_pattern = desc,
                    command         = truncated,
                    task_id         = task_id,
                )

        logger.debug("[SecurityBrain][%s] APPROVED | cmd=%.80s", task_id[:8], command)
        return SecurityDecision(
            approved        = True,
            level           = SecurityLevel.APPROVED,
            reason          = "",
            matched_pattern = "",
            command         = truncated,
            task_id         = task_id,
        )

    # ── Legacy compatibility ───────────────────────────────────────────────────

    def validate_legacy(
        self,
        command: str,
        task_id: str = "",
    ) -> tuple[bool, str, str]:
        """
        Legacy tuple API for code that hasn't migrated to SecurityDecision yet.
        Returns (approved, level, reason).
        """
        d = self.validate(command, task_id)
        return d.approved, d.level, d.reason

    def audit_entry(
        self,
        task_id:  str,
        command:  str,
        approved: bool,
        level:    str,
        reason:   str,
    ) -> dict:
        """Build a legacy structured audit entry (for backward compatibility)."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type":      "security_check",
            "brain":     "security_brain",
            "task_id":   task_id,
            "command":   command[:300],
            "approved":  approved,
            "level":     level,
            "reason":    reason,
        }
