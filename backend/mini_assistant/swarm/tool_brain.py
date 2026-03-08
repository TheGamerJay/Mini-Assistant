"""
tool_brain.py – Tool Brain (safe shell / git / file execution)
──────────────────────────────────────────────────────────────
All tool actions (shell commands, git ops, file writes) route through here.
Every command is validated by SecurityBrain before execution.
Outputs are captured and returned as structured ToolResult objects.

Phase 9 hardening:
  - ToolResult dataclass (command, args, cwd, exit_code, stdout, stderr,
    success, blocked_by_security, warning_flags, security_level, duration_ms)
  - Command allowlist: safe commands use shlex.split + subprocess.run(shell=False)
  - shell=True only for complex pipelines (explicitly opted-in per call)
  - Structured SecurityDecision wired through

Usage (from OrchestratorEngine):
    result = self._tool_brain.run(command, task_id=task.task_id)
    result.success, result.stdout, result.to_dict()
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import time
from typing import Optional

from .security_brain import SecurityBrain, SecurityDecision, SecurityLevel

logger = logging.getLogger("swarm.tool_brain")

_DEFAULT_TIMEOUT = 60   # seconds


# ── Command allowlist (safe to run without shell=True) ─────────────────────────

_SAFE_BASE_COMMANDS: frozenset[str] = frozenset({
    # Version control
    "git",
    # Package managers
    "npm", "npx", "yarn", "pnpm",
    "pip", "pip3",
    # Runtimes
    "python", "python3", "node",
    # Build/test
    "pytest", "jest", "mocha", "vitest",
    "make", "cargo", "go",
    # Docker (allowed but requires security check)
    "docker", "docker-compose",
    # Unix basics
    "ls", "cat", "cp", "mv", "mkdir", "touch", "echo",
    "head", "tail", "grep", "find", "wc", "sort", "uniq",
    # Network (read-only)
    "curl", "wget", "ping",
})

# Subcommand allowlists for specific base commands
_GIT_ALLOWED_SUBCOMMANDS: frozenset[str] = frozenset({
    "clone", "pull", "fetch", "status", "log", "diff", "show",
    "add", "commit", "push", "checkout", "branch", "merge", "rebase",
    "stash", "tag", "remote", "init", "describe",
})

_NPM_ALLOWED_SUBCOMMANDS: frozenset[str] = frozenset({
    "install", "ci", "run", "test", "build", "start", "lint",
    "audit", "outdated", "list", "pack",
})

_DOCKER_ALLOWED_SUBCOMMANDS: frozenset[str] = frozenset({
    "build", "run", "ps", "images", "logs", "stop", "start",
    "pull", "push", "tag", "inspect", "exec",
})


# ── ToolResult dataclass ───────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """
    Structured result from a ToolBrain execution.

    Fields
    ------
    command          The full original command string
    args             Parsed argument list (if shell=False was used)
    cwd              Working directory used
    exit_code        Process exit code (-1 blocked, -2 timeout, -3 error)
    stdout           Captured standard output (trimmed to 4000 chars)
    stderr           Captured standard error (trimmed to 2000 chars)
    success          True if exit_code == 0
    blocked_by_security  True if SecurityBrain blocked the command
    warning_flags    List of security warning descriptions (if any)
    security_level   "approved" | "warning" | "blocked"
    security_decision  Full SecurityDecision for audit trail
    duration_ms      Execution time in milliseconds
    task_id          Task context reference
    timestamp        UTC ISO timestamp of execution
    """
    command:             str
    args:                list[str]
    cwd:                 Optional[str]
    exit_code:           int
    stdout:              str
    stderr:              str
    success:             bool
    blocked_by_security: bool
    warning_flags:       list[str]
    security_level:      str
    security_decision:   SecurityDecision
    duration_ms:         int
    task_id:             str
    timestamp:           str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "timestamp":            self.timestamp,
            "type":                 "tool_result",
            "brain":                "tool_brain",
            "task_id":              self.task_id,
            "command":              self.command[:200],
            "args":                 self.args,
            "cwd":                  self.cwd,
            "exit_code":            self.exit_code,
            "stdout_snippet":       self.stdout[:300],
            "stderr_snippet":       self.stderr[:300],
            "success":              self.success,
            "blocked_by_security":  self.blocked_by_security,
            "warning_flags":        self.warning_flags,
            "security_level":       self.security_level,
            "duration_ms":          self.duration_ms,
        }

    # Legacy compat: unpack as (success, output, audit_dict)
    def as_legacy_tuple(self) -> tuple[bool, str, dict]:
        combined_output = (self.stdout + ("\n" + self.stderr if self.stderr else "")).strip()
        return self.success, combined_output, self.to_dict()


# ── ToolBrain ──────────────────────────────────────────────────────────────────

class ToolBrain:
    """
    Executes shell commands safely.
    SecurityBrain runs first — BLOCKED commands never reach subprocess.
    All actions produce a structured ToolResult for full audit traceability.
    """

    def __init__(self):
        self._security = SecurityBrain()

    # ── Core executor ──────────────────────────────────────────────────────────

    def run(
        self,
        command:    str,
        task_id:    str           = "",
        cwd:        Optional[str] = None,
        timeout:    int           = _DEFAULT_TIMEOUT,
        env:        Optional[dict] = None,
        force_shell: bool         = False,
    ) -> ToolResult:
        """
        Validate + execute a shell command.

        Parameters
        ----------
        command      Full command string to execute.
        task_id      Task ID for audit trail.
        cwd          Working directory.
        timeout      Execution timeout in seconds.
        env          Optional environment dict.
        force_shell  If True, force shell=True (only for complex pipelines).

        Returns
        -------
        ToolResult  Structured result with all execution metadata.
        """
        decision: SecurityDecision = self._security.validate(command, task_id)

        if decision.is_blocked:
            logger.warning("[ToolBrain][%s] Blocked: %s", task_id[:8], decision.reason)
            return ToolResult(
                command             = command,
                args                = [],
                cwd                 = cwd,
                exit_code           = -1,
                stdout              = "",
                stderr              = f"BLOCKED by SecurityBrain: {decision.reason}",
                success             = False,
                blocked_by_security = True,
                warning_flags       = [],
                security_level      = SecurityLevel.BLOCKED,
                security_decision   = decision,
                duration_ms         = 0,
                task_id             = task_id,
            )

        if decision.is_warning:
            logger.warning(
                "[ToolBrain][%s] Running with security warning: %s | cmd=%.120s",
                task_id[:8], decision.reason, command,
            )

        # Determine execution mode: safe list → shell=False; else shell=True
        use_shell, args = self._resolve_exec_mode(command, force_shell)

        start_ms = _now_ms()
        try:
            if use_shell:
                result = subprocess.run(
                    command,
                    shell          = True,
                    capture_output = True,
                    text           = True,
                    timeout        = timeout,
                    cwd            = cwd,
                    env            = env,
                )
            else:
                result = subprocess.run(
                    args,
                    shell          = False,
                    capture_output = True,
                    text           = True,
                    timeout        = timeout,
                    cwd            = cwd,
                    env            = env,
                )

            duration = _now_ms() - start_ms
            success  = result.returncode == 0
            stdout   = result.stdout.strip()[:4000]
            stderr   = result.stderr.strip()[:2000]

            logger.info(
                "[ToolBrain][%s] rc=%d dur=%dms shell=%s cmd=%.80s",
                task_id[:8], result.returncode, duration, use_shell, command,
            )

            return ToolResult(
                command             = command,
                args                = args,
                cwd                 = cwd,
                exit_code           = result.returncode,
                stdout              = stdout,
                stderr              = stderr,
                success             = success,
                blocked_by_security = False,
                warning_flags       = ([decision.matched_pattern] if decision.is_warning else []),
                security_level      = decision.level,
                security_decision   = decision,
                duration_ms         = duration,
                task_id             = task_id,
            )

        except subprocess.TimeoutExpired:
            duration = _now_ms() - start_ms
            msg = f"TIMEOUT: command exceeded {timeout}s"
            logger.warning("[ToolBrain][%s] %s | cmd=%.80s", task_id[:8], msg, command)
            return ToolResult(
                command             = command,
                args                = args,
                cwd                 = cwd,
                exit_code           = -2,
                stdout              = "",
                stderr              = msg,
                success             = False,
                blocked_by_security = False,
                warning_flags       = [],
                security_level      = decision.level,
                security_decision   = decision,
                duration_ms         = duration,
                task_id             = task_id,
            )

        except Exception as exc:
            duration = _now_ms() - start_ms
            msg = f"ERROR: {exc}"
            logger.exception("[ToolBrain][%s] Unexpected error running command.", task_id[:8])
            return ToolResult(
                command             = command,
                args                = args,
                cwd                 = cwd,
                exit_code           = -3,
                stdout              = "",
                stderr              = msg,
                success             = False,
                blocked_by_security = False,
                warning_flags       = [],
                security_level      = decision.level,
                security_decision   = decision,
                duration_ms         = duration,
                task_id             = task_id,
            )

    # ── Execution mode resolver ────────────────────────────────────────────────

    def _resolve_exec_mode(
        self,
        command: str,
        force_shell: bool,
    ) -> tuple[bool, list[str]]:
        """
        Determine whether to use shell=True or shell=False.

        Returns (use_shell: bool, args: list[str]).
        - If force_shell=True → shell=True, args=[]
        - If command contains shell metacharacters (|, &&, ;, >, <) → shell=True
        - If base command is in safe allowlist → shell=False, args=shlex.split(command)
        - Otherwise → shell=True (fallback for unknown commands)
        """
        if force_shell:
            return True, []

        # Contains shell metacharacters → must use shell=True
        shell_meta = ('|', '&&', '||', ';', '>', '<', '`', '$(',)
        if any(m in command for m in shell_meta):
            return True, []

        try:
            args = shlex.split(command)
        except ValueError:
            return True, []

        if not args:
            return True, []

        base = args[0].lower().split("/")[-1].split("\\")[-1]  # handle full paths

        if base in _SAFE_BASE_COMMANDS:
            # Subcommand allowlist checks
            if base == "git" and len(args) > 1:
                sub = args[1].lower()
                if sub not in _GIT_ALLOWED_SUBCOMMANDS:
                    logger.warning(
                        "[ToolBrain] git subcommand '%s' not in allowlist – using shell=True", sub
                    )
                    return True, []
            elif base == "npm" and len(args) > 1:
                sub = args[1].lower()
                if sub not in _NPM_ALLOWED_SUBCOMMANDS:
                    logger.warning(
                        "[ToolBrain] npm subcommand '%s' not in allowlist – using shell=True", sub
                    )
                    return True, []
            elif base == "docker" and len(args) > 1:
                sub = args[1].lower()
                if sub not in _DOCKER_ALLOWED_SUBCOMMANDS:
                    logger.warning(
                        "[ToolBrain] docker subcommand '%s' not in allowlist – using shell=True", sub
                    )
                    return True, []
            return False, args

        # Unknown base command – fall back to shell=True
        return True, []

    # ── Convenience wrappers ───────────────────────────────────────────────────

    def git(
        self,
        args:    str,
        task_id: str           = "",
        cwd:     Optional[str] = None,
    ) -> ToolResult:
        """Run a git command."""
        return self.run(f"git {args}", task_id=task_id, cwd=cwd)

    def pip_install(
        self,
        packages: str,
        task_id:  str = "",
    ) -> ToolResult:
        """pip install one or more packages."""
        return self.run(f"pip install {packages}", task_id=task_id)

    def npm_install(
        self,
        packages: str,
        cwd:      Optional[str] = None,
        task_id:  str           = "",
    ) -> ToolResult:
        """npm install one or more packages."""
        return self.run(f"npm install {packages}", task_id=task_id, cwd=cwd)

    def npm_run(
        self,
        script:  str,
        cwd:     Optional[str] = None,
        task_id: str           = "",
    ) -> ToolResult:
        """npm run <script>."""
        return self.run(f"npm run {script}", task_id=task_id, cwd=cwd)

    def python_run(
        self,
        script:  str,
        cwd:     Optional[str] = None,
        task_id: str           = "",
    ) -> ToolResult:
        """python <script>."""
        return self.run(f"python {script}", task_id=task_id, cwd=cwd)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_ms() -> int:
    return int(time() * 1000)
