"""
tool_brain.py – Tool Brain (safe shell / git / file execution)
──────────────────────────────────────────────────────────────
All tool actions (shell commands, git ops, file writes) route through here.
Every command is validated by SecurityBrain before execution.
Outputs are captured and returned with a full audit trail.

Usage (from OrchestratorEngine):
    ok, output, audit = self._tool_brain.run(command, task_id=task.task_id)
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from datetime import datetime, timezone
from typing import Optional

from .security_brain import SecurityBrain

logger = logging.getLogger("swarm.tool_brain")

_DEFAULT_TIMEOUT = 60   # seconds


class ToolBrain:
    """
    Executes shell commands safely.
    SecurityBrain runs first — BLOCKED commands never reach subprocess.
    All actions produce a structured audit entry for the task debug_log.
    """

    def __init__(self):
        self._security = SecurityBrain()

    def run(
        self,
        command:  str,
        task_id:  str          = "",
        cwd:      Optional[str] = None,
        timeout:  int          = _DEFAULT_TIMEOUT,
        env:      Optional[dict] = None,
    ) -> tuple[bool, str, dict]:
        """
        Validate + execute a shell command.
        Returns (success: bool, output: str, audit_entry: dict).

        audit_entry keys:
          timestamp, type, brain, task_id, command, approved, level, reason,
          exit_code, duration_ms, output_snippet
        """
        approved, level, reason = self._security.validate(command, task_id)
        audit = self._security.audit_entry(task_id, command, approved, level, reason)

        if not approved:
            audit.update({"exit_code": -1, "duration_ms": 0, "output_snippet": ""})
            logger.warning("[ToolBrain][%s] Blocked: %s", task_id[:8], reason)
            return False, f"BLOCKED by SecurityBrain: {reason}", audit

        if level == "warning":
            logger.warning("[ToolBrain][%s] Running with security warning: %s | cmd=%.120s",
                           task_id[:8], reason, command)

        start_ms = _now_ms()
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=env,
            )
            duration = _now_ms() - start_ms
            success  = result.returncode == 0
            output   = (result.stdout + result.stderr).strip()

            audit.update({
                "exit_code":      result.returncode,
                "duration_ms":    duration,
                "output_snippet": output[:300],
            })
            logger.info(
                "[ToolBrain][%s] rc=%d dur=%dms cmd=%.80s",
                task_id[:8], result.returncode, duration, command,
            )
            return success, output[:4000], audit

        except subprocess.TimeoutExpired:
            duration = _now_ms() - start_ms
            msg = f"TIMEOUT: command exceeded {timeout}s"
            audit.update({"exit_code": -2, "duration_ms": duration, "output_snippet": msg})
            logger.warning("[ToolBrain][%s] %s | cmd=%.80s", task_id[:8], msg, command)
            return False, msg, audit

        except Exception as exc:
            duration = _now_ms() - start_ms
            msg = f"ERROR: {exc}"
            audit.update({"exit_code": -3, "duration_ms": duration, "output_snippet": msg})
            logger.exception("[ToolBrain][%s] Unexpected error running command.", task_id[:8])
            return False, msg, audit

    def git(self, args: str, task_id: str = "", cwd: Optional[str] = None) -> tuple[bool, str, dict]:
        """Convenience wrapper: run a git command."""
        return self.run(f"git {args}", task_id=task_id, cwd=cwd)

    def pip_install(self, packages: str, task_id: str = "") -> tuple[bool, str, dict]:
        """Convenience wrapper: pip install."""
        return self.run(f"pip install {packages}", task_id=task_id)

    def npm_install(self, packages: str, cwd: Optional[str] = None, task_id: str = "") -> tuple[bool, str, dict]:
        """Convenience wrapper: npm install."""
        return self.run(f"npm install {packages}", task_id=task_id, cwd=cwd)


def _now_ms() -> int:
    from time import time
    return int(time() * 1000)
