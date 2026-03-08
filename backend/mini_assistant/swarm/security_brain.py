"""
security_brain.py – Security Brain (tool guardrail)
────────────────────────────────────────────────────
Validates shell commands and tool actions before execution.
Returns structured SecurityDecision objects with full audit metadata.

Decision levels:
  BLOCKED  → command matches a dangerous pattern, execution denied
  WARNING  → command is potentially destructive, allowed with log entry
  APPROVED → command is safe

Phase 9.5 hardening:
  - matched_patterns: list (all triggered patterns, not just first)
  - audit_shell_safety(): secondary metachar audit before any shell=True
    checks: null bytes, eval, IFS manipulation, backtick subshells,
    env variable expansion, source, newline injection, PID leak
  - expanded blocked/warning pattern sets
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


# ── Primary blocked patterns (never executed) ──────────────────────────────────

_BLOCKED_PATTERNS: list[tuple[str, str]] = [
    # Destructive file ops
    (r"\brm\s+-[rf]{1,2}\b",                         "Recursive remove"),
    (r"\brm\s+.*--recursive\b",                      "Recursive remove (--recursive)"),
    (r"\bsudo\s+rm\b",                               "sudo rm"),
    (r"\bwipe\s+/",                                  "Wipe root path"),

    # Low-level / disk
    (r"\bdd\s+if=",                                  "Low-level disk write (dd)"),
    (r"\bmkfs\b",                                    "Filesystem format"),
    (r"\bformat\s+[a-zA-Z]:",                        "Windows drive format"),
    (r">\s*/dev/[sh]d[a-z]",                         "Overwrite raw disk device"),

    # Fork bomb / system
    (r":\(\)\{.*?:\|:&\s*\};",                        "Fork bomb"),
    (r"\b(shutdown|reboot|halt)\b",                  "System shutdown/reboot"),
    (r"\bkill\s+-9\s+1\b",                           "Kill PID 1 (init)"),

    # Database destructive
    (r"\bdrop\s+database\b",                         "DROP DATABASE"),
    (r"\btruncate\s+table\b",                        "TRUNCATE TABLE"),
    (r"\bdrop\s+table\b",                            "DROP TABLE"),

    # Permission escalation
    (r"\bchmod\s+[0-7]*7\s+/\b",                    "chmod 777 on root path"),
    (r"\bchown\s+.*\s+/\b",                          "chown on root"),

    # Path traversal
    (r"\.\./\.\./\.\./",                             "Deep path traversal (../../..)"),
    (r"~root/",                                      "Root home access attempt"),
    (r"/etc/shadow",                                 "Shadow password file access"),
    (r"/etc/passwd",                                 "Passwd file access"),
    (r"/proc/.*mem",                                 "Process memory access"),

    # Secret / private key leakage
    (r"\bcat\s+.*\.pem\b",                           "Private key read (PEM)"),
    (r"\bcat\s+.*\.key\b",                           "Private key read (.key)"),
    (r"\bcat\s+.*id_rsa\b",                          "SSH private key read"),
    (r"\bcp\s+.*\.env\s+/",                          "Copy .env to root path"),
    (r"\bcurl\b.*\bpassword\b",                      "Password in curl command"),
    (r"\bwget\b.*\bpassword\b",                      "Password in wget command"),

    # Malicious npm
    (r"\bnpx\s+--yes\s+create-react-app\s+--scripts-version\s+dangerous",
                                                     "Malicious npm package"),

    # Exfiltration
    (r"\bbase64\b.*\|\s*curl\b",                     "Base64 + curl (exfil)"),
    (r"\bbase64\b.*\|\s*wget\b",                     "Base64 + wget (exfil)"),

    # Crontab injection
    (r"\bcrontab\s+-r\b",                            "Remove all crontabs"),
    (r"\becho\b.*>>\s*/etc/cron",                    "Crontab injection via echo"),

    # Shell metachar injection (blocked always)
    (r"\x00",                                        "Null byte injection"),
    (r"\beval\b",                                    "eval command (code injection)"),
    (r"\$IFS\b",                                     "IFS variable manipulation"),

    # Curl/wget piped to shell
    (r"\bcurl\b[^|]*\|\s*(bash|sh|zsh|fish|python3?|node)\b",
                                                     "curl piped to shell/interpreter"),
    (r"\bwget\b[^|]*\|\s*(bash|sh|zsh|fish|python3?|node)\b",
                                                     "wget piped to shell/interpreter"),
]


# ── Primary warning patterns (allowed but logged) ─────────────────────────────

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

    # Environment exposure
    (r"\benv\b\s*$",                      "env dump"),
    (r"\bprintenv\b",                     "printenv dump"),
    (r"\bset\b\s*$",                      "set dump (may expose secrets)"),

    # Suspicious piping (non-blocked variants)
    (r"\|\s*python3?\b",                  "Pipe to python"),

    # Deployment credential patterns
    (r"--token\s+\S+",                    "Token in command args"),
    (r"--password\s+\S+",                 "Password in command args"),
    (r"API_KEY=\S+",                      "Hardcoded API key"),
    (r"SECRET=\S+",                       "Hardcoded secret"),
    (r"PASSWORD=\S+",                     "Hardcoded password"),

    # Source / dot-source
    (r"\bsource\s+",                      "source command"),
    (r"\.\s+[~/]",                        "dot-source from path"),

    # Shell var expansion / metachar (warning in shell context)
    (r"`[^`]*`",                          "Backtick command substitution"),
    (r"\$\$\b",                           "PID variable ($$)"),
    (r"\$0\b",                            "Shell self-reference ($0)"),
    (r"\$\{[^}]+\}",                      "Shell variable expansion (${...})"),
    (r"\\n|\\r",                          "Newline escape sequence"),

    # Env manipulation
    (r"\bexport\s+",                      "export statement"),
    (r"\bunset\s+",                       "unset statement"),

    # npm/pip flags
    (r"\bnpm\s+install\b.*--no-save",     "npm install --no-save"),
    (r"\bpip\s+install\b.*--user",        "pip install --user"),
]


_COMPILED_BLOCKED  = [(re.compile(p, re.IGNORECASE | re.DOTALL), d) for p, d in _BLOCKED_PATTERNS]
_COMPILED_WARNINGS = [(re.compile(p, re.IGNORECASE), d)             for p, d in _WARNING_PATTERNS]


# ── Shell metachar audit patterns (checked before shell=True) ─────────────────

_SHELL_METACHAR_BLOCKED: list[tuple[str, str]] = [
    (r"\x00",                   "Null byte injection"),
    (r"\beval\b",               "eval keyword (code injection)"),
    (r"\$IFS\b",                "IFS manipulation (bypass attempt)"),
]

_SHELL_METACHAR_WARNINGS: list[tuple[str, str]] = [
    (r"`[^`]*`",                "Backtick subshell in shell command"),
    (r"\$\$\b",                 "PID variable ($$) in shell command"),
    (r"\$0\b",                  "Shell self-reference ($0)"),
    (r"\bsource\s+",            "source command in shell context"),
    (r"\.\s+[~/]",              "dot-source from path"),
    (r"\$\{[^}]+\}",            "Shell variable expansion (${...})"),
    (r"\\n|\\r",                "Newline escape sequence (injection risk)"),
    (r"\bexport\s+[A-Z_]+=",   "Environment export with value"),
    (r"\bunset\s+",             "unset in shell command"),
]

_COMPILED_SHELL_METACHAR_BLOCKED  = [(re.compile(p, re.IGNORECASE | re.DOTALL), d) for p, d in _SHELL_METACHAR_BLOCKED]
_COMPILED_SHELL_METACHAR_WARNINGS = [(re.compile(p, re.IGNORECASE), d)             for p, d in _SHELL_METACHAR_WARNINGS]


# ── SecurityDecision dataclass ─────────────────────────────────────────────────

@dataclass
class SecurityDecision:
    """
    Structured result from SecurityBrain.validate().

    Fields
    ------
    approved         True if execution is permitted (approved | warning)
    level            "approved" | "warning" | "blocked"
    reason           Human-readable explanation (empty for approved)
    matched_pattern  Primary pattern description that triggered (first match)
    matched_patterns All pattern descriptions that triggered (comprehensive)
    command          The evaluated command (truncated to 300 chars)
    task_id          Task context for audit trail
    timestamp        UTC ISO timestamp
    """
    approved:         bool
    level:            str
    reason:           str
    matched_pattern:  str          # primary (backward compat)
    matched_patterns: list[str]    # all matches
    command:          str
    task_id:          str
    timestamp:        str = field(
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
            "timestamp":        self.timestamp,
            "type":             "security_check",
            "brain":            "security_brain",
            "task_id":          self.task_id,
            "command":          self.command,
            "approved":         self.approved,
            "level":            self.level,
            "reason":           self.reason,
            "matched_pattern":  self.matched_pattern,
            "matched_patterns": self.matched_patterns,
        }


# ── ShellSafetyAudit result ────────────────────────────────────────────────────

@dataclass
class ShellSafetyAudit:
    """
    Result of audit_shell_safety() — secondary metachar check for shell=True.

    Fields
    ------
    safe              True if shell execution is permitted
    blocked_patterns  Descriptions of blocked metachar patterns found
    warning_patterns  Descriptions of warning metachar patterns found
    reason            Combined reason string (empty if safe + no warnings)
    """
    safe:             bool
    blocked_patterns: list[str]
    warning_patterns: list[str]
    reason:           str

    def to_dict(self) -> dict:
        return {
            "safe":             self.safe,
            "blocked_patterns": self.blocked_patterns,
            "warning_patterns": self.warning_patterns,
            "reason":           self.reason,
        }


# ── SecurityBrain ──────────────────────────────────────────────────────────────

class SecurityBrain:
    """
    Validates commands before ToolBrain executes them.
    Returns structured SecurityDecision and ShellSafetyAudit objects.
    """

    def validate(
        self,
        command: str,
        task_id: str = "",
    ) -> SecurityDecision:
        """
        Primary validation: check against blocked/warning pattern lists.

        Returns SecurityDecision with:
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
                    approved         = False,
                    level            = SecurityLevel.BLOCKED,
                    reason           = reason,
                    matched_pattern  = desc,
                    matched_patterns = [desc],
                    command          = truncated,
                    task_id          = task_id,
                )

        # Collect all warning matches (not just first)
        warning_matches: list[str] = []
        for pattern, desc in _COMPILED_WARNINGS:
            if pattern.search(command.strip()):
                warning_matches.append(desc)

        if warning_matches:
            reason = f"WARNING [{warning_matches[0]}]: potentially destructive"
            if len(warning_matches) > 1:
                reason += f" (also: {', '.join(warning_matches[1:])})"
            logger.warning(
                "[SecurityBrain][%s] %s | cmd=%.200s",
                task_id[:8], reason, command,
            )
            return SecurityDecision(
                approved         = True,
                level            = SecurityLevel.WARNING,
                reason           = reason,
                matched_pattern  = warning_matches[0],
                matched_patterns = warning_matches,
                command          = truncated,
                task_id          = task_id,
            )

        logger.debug("[SecurityBrain][%s] APPROVED | cmd=%.80s", task_id[:8], command)
        return SecurityDecision(
            approved         = True,
            level            = SecurityLevel.APPROVED,
            reason           = "",
            matched_pattern  = "",
            matched_patterns = [],
            command          = truncated,
            task_id          = task_id,
        )

    def audit_shell_safety(
        self,
        command: str,
        task_id: str = "",
    ) -> ShellSafetyAudit:
        """
        Secondary metacharacter/quoting audit — called by ToolBrain before
        any shell=True execution. Checks for injection risks that only matter
        in a shell context (backticks, eval, IFS, variable expansion, etc.).

        Returns ShellSafetyAudit with safe=False if any blocked metachar is found.
        """
        blocked: list[str] = []
        warnings: list[str] = []

        for pattern, desc in _COMPILED_SHELL_METACHAR_BLOCKED:
            if pattern.search(command):
                blocked.append(desc)
                logger.warning(
                    "[SecurityBrain][%s] SHELL_BLOCKED [%s] | cmd=%.200s",
                    task_id[:8], desc, command,
                )

        for pattern, desc in _COMPILED_SHELL_METACHAR_WARNINGS:
            if pattern.search(command):
                warnings.append(desc)
                logger.debug(
                    "[SecurityBrain][%s] SHELL_WARNING [%s] | cmd=%.200s",
                    task_id[:8], desc, command,
                )

        safe   = len(blocked) == 0
        parts: list[str] = []
        if blocked:
            parts.append(f"Blocked metacharacters: {', '.join(blocked)}")
        if warnings:
            parts.append(f"Warning metacharacters: {', '.join(warnings)}")

        return ShellSafetyAudit(
            safe             = safe,
            blocked_patterns = blocked,
            warning_patterns = warnings,
            reason           = "; ".join(parts),
        )

    # ── Legacy compatibility ───────────────────────────────────────────────────

    def validate_legacy(
        self,
        command: str,
        task_id: str = "",
    ) -> tuple[bool, str, str]:
        """Legacy tuple API. Returns (approved, level, reason)."""
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
        """Legacy structured audit entry (backward compatibility)."""
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
