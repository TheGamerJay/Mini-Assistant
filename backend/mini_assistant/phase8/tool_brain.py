"""
backend/mini_assistant/phase8/tool_brain.py

Tool Brain — executes shell / git / file tools after security clearance.

Flow:
  1. Receive tool_name + command from orchestrator.
  2. Call SecurityBrain.evaluate() — block or queue for approval if needed.
  3. If approved/safe: run the tool and return ToolResult.
  4. If needs_approval: persist to ApprovalStore and return pending status.
  5. If blocked: return error immediately.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .approval_store import ApprovalStore, approval_store
from .security_brain import SecurityDecision, evaluate_tool
from .tool_registry import get_tool


# ---------------------------------------------------------------------------
# ToolResult
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    tool_name: str
    command: str
    status: str           # success | error | pending | blocked
    output: str = ""
    error: str = ""
    exit_code: int = 0
    approval_id: Optional[str] = None
    security: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        d = {
            "tool_name": self.tool_name,
            "command": self.command,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
        }
        if self.approval_id:
            d["approval_id"] = self.approval_id
        if self.security:
            d["security"] = self.security
        return d


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------

def _run_shell(command: str, cwd: Optional[str] = None, timeout: int = 30) -> tuple[int, str, str]:
    """Run a shell command synchronously, return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout}s"
    except Exception as exc:
        return 1, "", str(exc)


# ---------------------------------------------------------------------------
# Tool executors  (one per category)
# ---------------------------------------------------------------------------

def _exec_git(command: str, cwd: Optional[str]) -> tuple[int, str, str]:
    return _run_shell(command, cwd=cwd, timeout=30)


def _exec_shell(command: str, cwd: Optional[str]) -> tuple[int, str, str]:
    return _run_shell(command, cwd=cwd, timeout=60)


def _exec_file_read(tool_name: str, command: str, cwd: Optional[str]) -> tuple[int, str, str]:
    """Execute file read operations (cat / ls / grep wrappers)."""
    if tool_name == "file_read":
        # command is expected to be a file path
        path = Path(command.strip())
        if not path.is_absolute() and cwd:
            path = Path(cwd) / path
        if not path.exists():
            return 1, "", f"File not found: {path}"
        if not path.is_file():
            return 1, "", f"Not a file: {path}"
        try:
            return 0, path.read_text(errors="replace"), ""
        except Exception as exc:
            return 1, "", str(exc)
    # file_list, file_search — fall back to shell
    return _run_shell(command, cwd=cwd, timeout=15)


def _exec_file_write(tool_name: str, command: str, cwd: Optional[str]) -> tuple[int, str, str]:
    """Execute file write operations."""
    return _run_shell(command, cwd=cwd, timeout=15)


def _exec_deploy(command: str, cwd: Optional[str]) -> tuple[int, str, str]:
    return _run_shell(command, cwd=cwd, timeout=300)


# ---------------------------------------------------------------------------
# ToolBrain
# ---------------------------------------------------------------------------

class ToolBrain:
    def __init__(self, store: ApprovalStore):
        self._store = store

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def execute(
        self,
        tool_name: str,
        command: str,
        session_id: str = "default",
        cwd: Optional[str] = None,
        auto_approve_safe: bool = True,
    ) -> ToolResult:
        """
        Main entry point.
        - Evaluates security.
        - Blocks, queues for approval, or runs immediately.
        """
        sec: SecurityDecision = evaluate_tool(tool_name, command)

        # --- Hard block ---
        if sec.blocked or sec.risk_level == "blocked":
            return ToolResult(
                tool_name=tool_name,
                command=command,
                status="blocked",
                error=f"Blocked by security guardrail: {'; '.join(sec.reasons)}",
                exit_code=-1,
                security=sec.to_dict(),
            )

        # --- Needs approval ---
        if sec.requires_approval and not auto_approve_safe:
            approval_id = self._store.add_pending(
                tool_name=tool_name,
                command=command,
                session_id=session_id,
                risk_level=sec.risk_level,
                reasons=sec.reasons,
            )
            return ToolResult(
                tool_name=tool_name,
                command=command,
                status="pending",
                output="Awaiting user approval before execution.",
                approval_id=approval_id,
                security=sec.to_dict(),
            )

        # --- Execute ---
        return await self._run(tool_name, command, cwd, sec)

    async def execute_approved(self, approval_id: str, cwd: Optional[str] = None) -> ToolResult:
        """Run a previously queued tool after the user approves it."""
        pending = self._store.get_pending(approval_id)
        if not pending:
            return ToolResult(
                tool_name="unknown",
                command="",
                status="error",
                error=f"Approval ID not found: {approval_id}",
                exit_code=1,
            )

        self._store.mark_approved(approval_id)
        sec = evaluate_tool(pending["tool_name"], pending["command"])

        # Re-evaluate — should still be danger but not blocked
        if sec.blocked:
            self._store.mark_denied(approval_id)
            return ToolResult(
                tool_name=pending["tool_name"],
                command=pending["command"],
                status="blocked",
                error="Blocked after re-evaluation.",
                exit_code=-1,
                security=sec.to_dict(),
            )

        return await self._run(pending["tool_name"], pending["command"], cwd, sec)

    # ------------------------------------------------------------------
    # Internal execution dispatcher
    # ------------------------------------------------------------------

    async def _run(
        self,
        tool_name: str,
        command: str,
        cwd: Optional[str],
        sec: SecurityDecision,
    ) -> ToolResult:
        loop = asyncio.get_event_loop()
        tool_def = get_tool(tool_name)
        category = tool_def.category if tool_def else "shell"

        def _sync_run():
            if category == "git":
                return _exec_git(command, cwd)
            elif category in ("shell",):
                return _exec_shell(command, cwd)
            elif category == "file_read":
                return _exec_file_read(tool_name, command, cwd)
            elif category == "file_write":
                return _exec_file_write(tool_name, command, cwd)
            elif category == "deploy":
                return _exec_deploy(command, cwd)
            else:
                return _exec_shell(command, cwd)

        exit_code, stdout, stderr = await loop.run_in_executor(None, _sync_run)

        status = "success" if exit_code == 0 else "error"
        return ToolResult(
            tool_name=tool_name,
            command=command,
            status=status,
            output=stdout[:8000],    # cap output
            error=stderr[:2000],
            exit_code=exit_code,
            security=sec.to_dict(),
        )


# ---------------------------------------------------------------------------
# Module-level singleton (initialised after approval_store import)
# ---------------------------------------------------------------------------
tool_brain = ToolBrain(store=approval_store)
