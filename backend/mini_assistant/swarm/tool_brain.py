"""
tool_brain.py – Tool Brain (safe shell / git / file execution)
──────────────────────────────────────────────────────────────
Phase 9.5 hardening:

Execution model
───────────────
  SAFE_ARGV_ONLY  – shlex.split + shell=False. Default for allowlisted commands.
  LIMITED_SHELL   – shell=True allowed only when ShellClassifier confirms the
                    command genuinely requires shell parsing (pipes, redirects,
                    chaining, subshells, glob). Requires a shell_reason string.
  BLOCK_UNKNOWN   – unknown (non-allowlisted) commands are BLOCKED by default.
                    They cannot fall through to shell=True silently.

Command allowlist (CommandPolicy)
──────────────────────────────────
  Per-command policies define:
    • allowed_subcommands   – frozenset; empty = no sub restriction
    • blocked_arg_patterns  – compiled regexes that block even allowlisted cmds
    • requires_subcommand   – True = must have a subcommand
    • shell_allowed         – True = this command may run in LIMITED_SHELL if
                              the classifier also confirms shell is needed

ToolResult
──────────
  Extended with: execution_mode, used_shell, shell_reason, env_keys_used,
  intent_source, matched_security_patterns, shell_audit_warnings.
  Secrets are NEVER stored: env values are not logged, only keys.

Unknown command policy
──────────────────────
  If base command is not in _COMMAND_POLICIES, the command is BLOCKED.
  Caller must either: add it to _COMMAND_POLICIES, or use force_shell=True
  with an explicit shell_reason (for one-off approved commands).

Usage (from OrchestratorEngine):
    result = self._tool_brain.run(command, task_id=task.task_id,
                                   intent_source="structured_intent")
    result.success, result.stdout, result.to_dict()
"""

from __future__ import annotations

import logging
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import time
from typing import Optional

from .security_brain import (
    SecurityBrain, SecurityDecision, SecurityLevel, ShellSafetyAudit,
)

logger = logging.getLogger("swarm.tool_brain")

_DEFAULT_TIMEOUT = 60   # seconds


# ── Execution modes ────────────────────────────────────────────────────────────

class ExecutionMode:
    SAFE_ARGV_ONLY = "safe_argv_only"   # shlex.split + shell=False
    LIMITED_SHELL  = "limited_shell"    # shell=True, classifier confirmed need
    BLOCK_UNKNOWN  = "block_unknown"    # unknown command → blocked


# ── Intent sources ─────────────────────────────────────────────────────────────

class IntentSource:
    STRUCTURED_INTENT  = "structured_intent"    # from ExecutionIntent JSON block
    LEGACY_FALLBACK    = "legacy_dollar_fallback"  # from $ line extraction (warn)
    DIRECT             = "direct"                # direct ToolBrain API call


# ── CommandPolicy ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CommandPolicy:
    """
    Per-command execution policy.

    Fields
    ------
    allowed_subcommands   Permitted subcommands. Empty frozenset = no restriction.
    blocked_arg_patterns  Regex patterns that block even allowed commands.
    requires_subcommand   Must supply a subcommand (e.g. git, npm).
    shell_allowed         Command may use LIMITED_SHELL if classifier confirms need.
    """
    allowed_subcommands:  frozenset[str]
    blocked_arg_patterns: tuple         = ()   # tuple of compiled re.Pattern
    requires_subcommand:  bool          = False
    shell_allowed:        bool          = False


# ── Command allowlist ──────────────────────────────────────────────────────────

def _bp(*patterns: str) -> tuple:
    """Compile blocked arg patterns for a CommandPolicy."""
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


_COMMAND_POLICIES: dict[str, CommandPolicy] = {
    # Version control
    "git": CommandPolicy(
        allowed_subcommands = frozenset({
            "clone", "pull", "fetch", "status", "log", "diff", "show",
            "add", "commit", "push", "checkout", "branch", "merge",
            "rebase", "stash", "tag", "remote", "init", "describe",
            "config", "rev-parse", "ls-files", "restore", "switch",
            "cherry-pick", "bisect",
        }),
        blocked_arg_patterns = _bp(
            r"--upload-pack",
            r"--receive-pack",
            r"--exec=",
        ),
        requires_subcommand = True,
    ),

    # Node package managers
    "npm": CommandPolicy(
        allowed_subcommands = frozenset({
            "install", "ci", "run", "test", "build", "start", "lint",
            "audit", "outdated", "list", "pack", "publish",
        }),
        requires_subcommand = True,
    ),
    "npx": CommandPolicy(
        allowed_subcommands = frozenset(),
        blocked_arg_patterns = _bp(
            r"--yes\s+.*dangerous",   # known malicious pattern
        ),
    ),
    "yarn": CommandPolicy(
        allowed_subcommands = frozenset({
            "install", "add", "remove", "run", "build", "test", "lint",
        }),
    ),
    "pnpm": CommandPolicy(
        allowed_subcommands = frozenset({
            "install", "add", "remove", "run", "build", "test",
        }),
    ),

    # Python package managers / runtimes
    "pip": CommandPolicy(
        allowed_subcommands = frozenset({
            "install", "uninstall", "list", "show", "freeze", "download",
            "check",
        }),
        requires_subcommand = True,
    ),
    "pip3": CommandPolicy(
        allowed_subcommands = frozenset({
            "install", "uninstall", "list", "show", "freeze", "download",
            "check",
        }),
        requires_subcommand = True,
    ),
    "python": CommandPolicy(
        allowed_subcommands = frozenset(),
        blocked_arg_patterns = _bp(r"-c\s+"),   # python -c "..." is dangerous
    ),
    "python3": CommandPolicy(
        allowed_subcommands = frozenset(),
        blocked_arg_patterns = _bp(r"-c\s+"),
    ),

    # JavaScript runtime
    "node": CommandPolicy(
        allowed_subcommands = frozenset(),
        blocked_arg_patterns = _bp(r"-e\s+"),   # node -e "..." is dangerous
    ),

    # Test runners
    "pytest":  CommandPolicy(allowed_subcommands=frozenset()),
    "jest":    CommandPolicy(allowed_subcommands=frozenset()),
    "mocha":   CommandPolicy(allowed_subcommands=frozenset()),
    "vitest":  CommandPolicy(allowed_subcommands=frozenset()),

    # Build tools
    "make":  CommandPolicy(allowed_subcommands=frozenset()),
    "cargo": CommandPolicy(
        allowed_subcommands = frozenset({
            "build", "test", "run", "check", "clean", "doc", "fmt",
        }),
        requires_subcommand = True,
    ),
    "go": CommandPolicy(
        allowed_subcommands = frozenset({
            "build", "test", "run", "fmt", "vet", "get", "mod", "clean",
        }),
        requires_subcommand = True,
    ),

    # Docker (requires security check)
    "docker": CommandPolicy(
        allowed_subcommands = frozenset({
            "build", "run", "ps", "images", "logs", "stop", "start",
            "pull", "push", "tag", "inspect", "exec",
        }),
        requires_subcommand = True,
    ),
    "docker-compose": CommandPolicy(
        allowed_subcommands = frozenset({
            "up", "down", "build", "logs", "ps", "restart", "pull",
        }),
        requires_subcommand = True,
    ),

    # Unix read-only basics
    "ls":    CommandPolicy(allowed_subcommands=frozenset()),
    "cat":   CommandPolicy(allowed_subcommands=frozenset()),
    "head":  CommandPolicy(allowed_subcommands=frozenset()),
    "tail":  CommandPolicy(allowed_subcommands=frozenset()),
    "grep":  CommandPolicy(allowed_subcommands=frozenset()),
    "find":  CommandPolicy(allowed_subcommands=frozenset()),
    "wc":    CommandPolicy(allowed_subcommands=frozenset()),
    "sort":  CommandPolicy(allowed_subcommands=frozenset()),
    "uniq":  CommandPolicy(allowed_subcommands=frozenset()),
    "echo":  CommandPolicy(allowed_subcommands=frozenset()),

    # File ops (write — allowed but monitored)
    "cp":    CommandPolicy(allowed_subcommands=frozenset()),
    "mv":    CommandPolicy(allowed_subcommands=frozenset()),
    "mkdir": CommandPolicy(allowed_subcommands=frozenset()),
    "touch": CommandPolicy(allowed_subcommands=frozenset()),

    # Network read-only
    "curl": CommandPolicy(
        allowed_subcommands = frozenset(),
        blocked_arg_patterns = _bp(
            r"\|\s*(bash|sh|zsh|fish|python3?|node)\b",
        ),
    ),
    "wget": CommandPolicy(
        allowed_subcommands = frozenset(),
        blocked_arg_patterns = _bp(
            r"-O-\s*\|\s*(bash|sh)",
            r"\|\s*(bash|sh)\b",
        ),
    ),
    "ping": CommandPolicy(allowed_subcommands=frozenset()),
}

# ── Shell classification ───────────────────────────────────────────────────────

_SHELL_REQUIRED_RE: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?<!\|)\|(?!\|)"), "pipe (|)"),
    (re.compile(r"\|\|"),           "OR chain (||)"),
    (re.compile(r"&&"),             "AND chain (&&)"),
    (re.compile(r"(?<!>)>(?!>)"),   "output redirect (>)"),
    (re.compile(r">>"),             "append redirect (>>)"),
    (re.compile(r"(?<!<)<(?!<)"),   "input redirect (<)"),
    (re.compile(r";\s*\S"),         "command separator (;)"),
    (re.compile(r"\$\("),          "command substitution ($(...))"),
    (re.compile(r"`"),             "backtick subshell"),
    (re.compile(r"[\*\?\[]"),      "glob pattern (*/?/[)"),
]


def _classify_shell_need(command: str) -> tuple[bool, str]:
    """
    Return (needs_shell: bool, reason: str).
    Checks for shell metacharacters that cannot be handled by shlex + argv.
    If shlex.split() itself fails, that also indicates shell mode is needed.
    """
    for pattern, reason in _SHELL_REQUIRED_RE:
        if pattern.search(command):
            return True, reason
    try:
        shlex.split(command)
        return False, ""
    except ValueError as exc:
        return True, f"shlex parse failed: {exc}"


# ── ToolResult ─────────────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """
    Structured result from a ToolBrain execution.

    Fields
    ------
    command                  Full original command string
    args                     Parsed argument list (when shell=False)
    cwd                      Working directory used
    exit_code                Process exit code (-1 blocked, -2 timeout, -3 error)
    stdout                   Captured stdout (trimmed to 4000 chars)
    stderr                   Captured stderr (trimmed to 2000 chars)
    success                  True if exit_code == 0
    blocked_by_security      True if SecurityBrain blocked the command
    warning_flags            Security warning descriptions
    security_level           "approved" | "warning" | "blocked"
    security_decision        Full SecurityDecision object
    duration_ms              Execution time in milliseconds
    task_id                  Task context reference
    timestamp                UTC ISO timestamp

    Phase 9.5 additions
    ───────────────────
    execution_mode           ExecutionMode value used
    used_shell               True if subprocess ran with shell=True
    shell_reason             Why shell was used (empty if shell=False)
    env_keys_used            Keys of env vars passed (NEVER values)
    intent_source            IntentSource value (how command was submitted)
    matched_security_patterns All security pattern descriptions that triggered
    shell_audit_warnings     Metachar warnings from shell safety audit
    """
    command:                  str
    args:                     list[str]
    cwd:                      Optional[str]
    exit_code:                int
    stdout:                   str
    stderr:                   str
    success:                  bool
    blocked_by_security:      bool
    warning_flags:            list[str]
    security_level:           str
    security_decision:        SecurityDecision
    duration_ms:              int
    task_id:                  str
    # Phase 9.5
    execution_mode:           str
    used_shell:               bool
    shell_reason:             str
    env_keys_used:            list[str]
    intent_source:            str
    matched_security_patterns: list[str]
    shell_audit_warnings:     list[str]
    timestamp:                str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "timestamp":                  self.timestamp,
            "type":                       "tool_result",
            "brain":                      "tool_brain",
            "task_id":                    self.task_id,
            "command":                    self.command[:200],
            "args":                       self.args,
            "cwd":                        self.cwd,
            "exit_code":                  self.exit_code,
            "stdout_snippet":             self.stdout[:300],
            "stderr_snippet":             self.stderr[:300],
            "success":                    self.success,
            "blocked_by_security":        self.blocked_by_security,
            "warning_flags":              self.warning_flags,
            "security_level":             self.security_level,
            "duration_ms":                self.duration_ms,
            # Phase 9.5
            "execution_mode":             self.execution_mode,
            "used_shell":                 self.used_shell,
            "shell_reason":               self.shell_reason,
            "env_keys_used":              self.env_keys_used,
            "intent_source":              self.intent_source,
            "matched_security_patterns":  self.matched_security_patterns,
            "shell_audit_warnings":       self.shell_audit_warnings,
        }

    def as_legacy_tuple(self) -> tuple[bool, str, dict]:
        """Backward-compat: unpack as (success, combined_output, audit_dict)."""
        combined = (self.stdout + ("\n" + self.stderr if self.stderr else "")).strip()
        return self.success, combined, self.to_dict()


# ── ToolBrain ──────────────────────────────────────────────────────────────────

class ToolBrain:
    """
    Executes shell commands safely.

    Default policy: BLOCK_UNKNOWN — commands not in _COMMAND_POLICIES are
    blocked and never reach subprocess. SecurityBrain runs first for all
    commands; BLOCKED commands never reach subprocess regardless.
    shell=True is only used when ShellClassifier confirms it is genuinely
    required AND the secondary metacharacter audit passes.
    """

    def __init__(self):
        self._security = SecurityBrain()

    # ── Core executor ──────────────────────────────────────────────────────────

    def run(
        self,
        command:      str,
        task_id:      str           = "",
        cwd:          Optional[str] = None,
        timeout:      int           = _DEFAULT_TIMEOUT,
        env:          Optional[dict] = None,
        force_shell:  bool          = False,
        shell_reason: str           = "",
        intent_source: str          = IntentSource.DIRECT,
    ) -> ToolResult:
        """
        Validate + execute a shell command.

        Parameters
        ----------
        command       Full command string.
        task_id       Task ID for audit trail.
        cwd           Working directory.
        timeout       Execution timeout in seconds.
        env           Optional environment dict. Keys are logged; values are NOT.
        force_shell   Bypass ARGV-only policy. Requires shell_reason.
        shell_reason  Mandatory human-readable explanation when force_shell=True.
        intent_source How the command originated (structured / fallback / direct).

        Returns ToolResult. Secrets are never stored (env keys only).
        """
        env_keys = list(env.keys()) if env else []

        # ── Phase 9.5: warn on legacy fallback source ─────────────────────────
        if intent_source == IntentSource.LEGACY_FALLBACK:
            logger.warning(
                "[ToolBrain][%s] Legacy $ fallback source — prefer structured ExecutionIntent | cmd=%.80s",
                task_id[:8], command,
            )

        # ── Step 1: Primary SecurityBrain validation ──────────────────────────
        decision: SecurityDecision = self._security.validate(command, task_id)

        if decision.is_blocked:
            logger.warning("[ToolBrain][%s] Blocked by SecurityBrain: %s", task_id[:8], decision.reason)
            return self._blocked_result(
                command, task_id, cwd, env_keys, decision, intent_source,
                reason=f"BLOCKED by SecurityBrain: {decision.reason}",
                exec_mode=ExecutionMode.BLOCK_UNKNOWN,
            )

        # ── Step 2: Resolve execution mode ────────────────────────────────────
        exec_mode, use_shell, resolved_shell_reason, args, block_reason = \
            self._resolve_command(command, force_shell, shell_reason)

        if block_reason:
            logger.warning("[ToolBrain][%s] Command blocked at allowlist: %s", task_id[:8], block_reason)
            block_decision = SecurityDecision(
                approved         = False,
                level            = SecurityLevel.BLOCKED,
                reason           = block_reason,
                matched_pattern  = block_reason,
                matched_patterns = [block_reason],
                command          = command[:300],
                task_id          = task_id,
            )
            return self._blocked_result(
                command, task_id, cwd, env_keys, block_decision, intent_source,
                reason=block_reason,
                exec_mode=exec_mode,
            )

        # ── Step 3: Shell metachar safety audit (only if shell=True) ──────────
        shell_audit_warnings: list[str] = []
        if use_shell:
            audit: ShellSafetyAudit = self._security.audit_shell_safety(command, task_id)
            if not audit.safe:
                reason = f"Shell metachar audit BLOCKED: {audit.reason}"
                logger.warning("[ToolBrain][%s] %s | cmd=%.120s", task_id[:8], reason, command)
                block_decision = SecurityDecision(
                    approved         = False,
                    level            = SecurityLevel.BLOCKED,
                    reason           = reason,
                    matched_pattern  = audit.blocked_patterns[0] if audit.blocked_patterns else "",
                    matched_patterns = audit.blocked_patterns,
                    command          = command[:300],
                    task_id          = task_id,
                )
                return self._blocked_result(
                    command, task_id, cwd, env_keys, block_decision, intent_source,
                    reason=reason,
                    exec_mode=exec_mode,
                )
            shell_audit_warnings = audit.warning_patterns
            if shell_audit_warnings:
                logger.warning(
                    "[ToolBrain][%s] Shell metachar warnings: %s | cmd=%.120s",
                    task_id[:8], shell_audit_warnings, command,
                )

        if decision.is_warning:
            logger.warning(
                "[ToolBrain][%s] Running with security warning: %s | cmd=%.120s",
                task_id[:8], decision.reason, command,
            )

        # ── Step 4: Execute ───────────────────────────────────────────────────
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
                "[ToolBrain][%s] rc=%d dur=%dms mode=%s shell=%s cmd=%.80s",
                task_id[:8], result.returncode, duration, exec_mode, use_shell, command,
            )

            return ToolResult(
                command                  = command,
                args                     = args,
                cwd                      = cwd,
                exit_code                = result.returncode,
                stdout                   = stdout,
                stderr                   = stderr,
                success                  = success,
                blocked_by_security      = False,
                warning_flags            = decision.matched_patterns if decision.is_warning else [],
                security_level           = decision.level,
                security_decision        = decision,
                duration_ms              = duration,
                task_id                  = task_id,
                execution_mode           = exec_mode,
                used_shell               = use_shell,
                shell_reason             = resolved_shell_reason,
                env_keys_used            = env_keys,
                intent_source            = intent_source,
                matched_security_patterns = decision.matched_patterns,
                shell_audit_warnings     = shell_audit_warnings,
            )

        except subprocess.TimeoutExpired:
            duration = _now_ms() - start_ms
            msg = f"TIMEOUT: command exceeded {timeout}s"
            logger.warning("[ToolBrain][%s] %s | cmd=%.80s", task_id[:8], msg, command)
            return self._error_result(
                command, args, task_id, cwd, env_keys, decision, intent_source,
                exit_code=-2, stderr=msg, duration=duration,
                exec_mode=exec_mode, used_shell=use_shell,
                shell_reason=resolved_shell_reason,
                shell_audit_warnings=shell_audit_warnings,
            )

        except Exception as exc:
            duration = _now_ms() - start_ms
            msg = f"ERROR: {exc}"
            logger.exception("[ToolBrain][%s] Unexpected error.", task_id[:8])
            return self._error_result(
                command, args, task_id, cwd, env_keys, decision, intent_source,
                exit_code=-3, stderr=msg, duration=duration,
                exec_mode=exec_mode, used_shell=use_shell,
                shell_reason=resolved_shell_reason,
                shell_audit_warnings=shell_audit_warnings,
            )

    # ── Command resolution ─────────────────────────────────────────────────────

    def _resolve_command(
        self,
        command:      str,
        force_shell:  bool,
        shell_reason: str,
    ) -> tuple[str, bool, str, list[str], str]:
        """
        Determine execution mode, whether to use shell, and parse argv.

        Returns (exec_mode, use_shell, shell_reason, args, block_reason).
        block_reason non-empty means the command must be blocked.
        """
        # force_shell is an explicit opt-in override (requires reason)
        if force_shell:
            if not shell_reason:
                return (
                    ExecutionMode.LIMITED_SHELL, True,
                    "force_shell=True (no reason provided — use shell_reason param)",
                    [], "",
                )
            return ExecutionMode.LIMITED_SHELL, True, shell_reason, [], ""

        # Check if command genuinely needs shell
        needs_shell, auto_reason = _classify_shell_need(command)
        if needs_shell:
            # Parse base command to check allowlist policy
            try:
                tokens = shlex.split(command)
            except ValueError:
                tokens = command.split()

            base = _extract_base(tokens[0] if tokens else command)
            policy = _COMMAND_POLICIES.get(base)

            # For shell-required commands: only allow if command is in allowlist
            # AND that command's policy permits shell mode
            if policy is None:
                block_reason = (
                    f"Unknown command '{base}' requires shell mode "
                    f"({auto_reason}) but is not in allowlist — BLOCKED. "
                    f"Add to _COMMAND_POLICIES or use force_shell=True with shell_reason."
                )
                return ExecutionMode.BLOCK_UNKNOWN, False, "", [], block_reason

            # Known command in shell-required context: allow LIMITED_SHELL
            return (
                ExecutionMode.LIMITED_SHELL, True,
                f"shell required: {auto_reason}", [], "",
            )

        # No shell metacharacters → attempt SAFE_ARGV_ONLY
        try:
            args = shlex.split(command)
        except ValueError as exc:
            return ExecutionMode.BLOCK_UNKNOWN, False, "", [], f"shlex parse error: {exc}"

        if not args:
            return ExecutionMode.BLOCK_UNKNOWN, False, "", [], "Empty command"

        base = _extract_base(args[0])
        policy = _COMMAND_POLICIES.get(base)

        if policy is None:
            block_reason = (
                f"Unknown command '{base}' — BLOCKED by BLOCK_UNKNOWN policy. "
                f"Not in allowlist. Add to _COMMAND_POLICIES or use force_shell=True."
            )
            return ExecutionMode.BLOCK_UNKNOWN, False, "", [], block_reason

        # Validate subcommand if required
        if policy.requires_subcommand:
            if len(args) < 2:
                return (
                    ExecutionMode.BLOCK_UNKNOWN, False, "", [],
                    f"Command '{base}' requires a subcommand but none provided",
                )
            sub = args[1].lower()
            if policy.allowed_subcommands and sub not in policy.allowed_subcommands:
                return (
                    ExecutionMode.BLOCK_UNKNOWN, False, "", [],
                    f"Subcommand '{sub}' not in allowlist for '{base}'. "
                    f"Allowed: {sorted(policy.allowed_subcommands)}",
                )
        elif policy.allowed_subcommands and len(args) > 1:
            sub = args[1].lower()
            if sub not in policy.allowed_subcommands:
                logger.warning(
                    "[ToolBrain] Subcommand '%s' not in allowlist for '%s' — proceeding",
                    sub, base,
                )

        # Check blocked arg patterns
        full_cmd = " ".join(args[1:])
        for pat in policy.blocked_arg_patterns:
            if pat.search(full_cmd):
                return (
                    ExecutionMode.BLOCK_UNKNOWN, False, "", [],
                    f"Blocked argument pattern matched for '{base}': {pat.pattern}",
                )

        return ExecutionMode.SAFE_ARGV_ONLY, False, "", args, ""

    # ── Result factories ───────────────────────────────────────────────────────

    def _blocked_result(
        self,
        command:       str,
        task_id:       str,
        cwd:           Optional[str],
        env_keys:      list[str],
        decision:      SecurityDecision,
        intent_source: str,
        reason:        str,
        exec_mode:     str,
    ) -> ToolResult:
        return ToolResult(
            command                  = command,
            args                     = [],
            cwd                      = cwd,
            exit_code                = -1,
            stdout                   = "",
            stderr                   = reason,
            success                  = False,
            blocked_by_security      = True,
            warning_flags            = [],
            security_level           = SecurityLevel.BLOCKED,
            security_decision        = decision,
            duration_ms              = 0,
            task_id                  = task_id,
            execution_mode           = exec_mode,
            used_shell               = False,
            shell_reason             = "",
            env_keys_used            = env_keys,
            intent_source            = intent_source,
            matched_security_patterns = decision.matched_patterns,
            shell_audit_warnings     = [],
        )

    def _error_result(
        self,
        command:             str,
        args:                list[str],
        task_id:             str,
        cwd:                 Optional[str],
        env_keys:            list[str],
        decision:            SecurityDecision,
        intent_source:       str,
        exit_code:           int,
        stderr:              str,
        duration:            int,
        exec_mode:           str,
        used_shell:          bool,
        shell_reason:        str,
        shell_audit_warnings: list[str],
    ) -> ToolResult:
        return ToolResult(
            command                  = command,
            args                     = args,
            cwd                      = cwd,
            exit_code                = exit_code,
            stdout                   = "",
            stderr                   = stderr,
            success                  = False,
            blocked_by_security      = False,
            warning_flags            = decision.matched_patterns if decision.is_warning else [],
            security_level           = decision.level,
            security_decision        = decision,
            duration_ms              = duration,
            task_id                  = task_id,
            execution_mode           = exec_mode,
            used_shell               = used_shell,
            shell_reason             = shell_reason,
            env_keys_used            = env_keys,
            intent_source            = intent_source,
            matched_security_patterns = decision.matched_patterns,
            shell_audit_warnings     = shell_audit_warnings,
        )

    # ── Convenience wrappers ───────────────────────────────────────────────────

    def git(
        self,
        args:    str,
        task_id: str           = "",
        cwd:     Optional[str] = None,
        intent_source: str     = IntentSource.DIRECT,
    ) -> ToolResult:
        return self.run(f"git {args}", task_id=task_id, cwd=cwd,
                        intent_source=intent_source)

    def pip_install(
        self,
        packages:      str,
        task_id:       str = "",
        intent_source: str = IntentSource.DIRECT,
    ) -> ToolResult:
        return self.run(f"pip install {packages}", task_id=task_id,
                        intent_source=intent_source)

    def npm_install(
        self,
        packages:      str,
        cwd:           Optional[str] = None,
        task_id:       str           = "",
        intent_source: str           = IntentSource.DIRECT,
    ) -> ToolResult:
        return self.run(f"npm install {packages}", task_id=task_id, cwd=cwd,
                        intent_source=intent_source)

    def npm_run(
        self,
        script:        str,
        cwd:           Optional[str] = None,
        task_id:       str           = "",
        intent_source: str           = IntentSource.DIRECT,
    ) -> ToolResult:
        return self.run(f"npm run {script}", task_id=task_id, cwd=cwd,
                        intent_source=intent_source)

    def python_run(
        self,
        script:        str,
        cwd:           Optional[str] = None,
        task_id:       str           = "",
        intent_source: str           = IntentSource.DIRECT,
    ) -> ToolResult:
        return self.run(f"python {script}", task_id=task_id, cwd=cwd,
                        intent_source=intent_source)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_base(cmd_token: str) -> str:
    """Extract the base command name from a full path (handles / and \\)."""
    return cmd_token.replace("\\", "/").split("/")[-1].lower()


def _now_ms() -> int:
    return int(time() * 1000)
