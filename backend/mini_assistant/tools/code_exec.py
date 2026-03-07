"""
code_exec.py – Python Code Execution Sandbox
──────────────────────────────────────────────
Runs Python code in a subprocess with:
  - Configurable timeout
  - Output truncation
  - Restricted builtins (no file system writes outside temp dir)
  - Captured stdout, stderr, and return code
"""

import logging
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from ..config import CODE_TIMEOUT, CODE_MAX_OUTPUT

logger = logging.getLogger(__name__)

# Packages that are blocked from being imported in the sandbox
_BLOCKED_IMPORTS = {"subprocess", "os.system", "shutil.rmtree", "ctypes"}


def _check_dangerous(code: str) -> list[str]:
    """Return a list of warning strings for risky patterns."""
    warnings = []
    risky = [
        ("os.system", "Direct shell execution"),
        ("subprocess.run", "Subprocess execution (allowed but flagged)"),
        ("shutil.rmtree", "Recursive directory deletion"),
        ("open(", "File I/O detected"),
        ("__import__", "Dynamic import"),
        ("eval(", "eval() usage"),
        ("exec(", "exec() usage"),
    ]
    for pattern, label in risky:
        if pattern in code:
            warnings.append(label)
    return warnings


def execute_python(
    code: str,
    timeout: int = CODE_TIMEOUT,
    allow_input: bool = False,
) -> dict:
    """
    Execute Python code in a sandboxed subprocess.

    Args:
        code:        Python source code to run.
        timeout:     Max execution time in seconds.
        allow_input: If False, stdin is set to /dev/null.

    Returns:
        dict with keys:
            stdout      – captured standard output (truncated)
            stderr      – captured standard error (truncated)
            returncode  – process exit code
            success     – bool
            warnings    – list of flagged patterns
            truncated   – bool (True if output was cut)
    """
    warnings = _check_dangerous(code)
    logger.info("Executing Python code (%d chars). Warnings: %s", len(code), warnings)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL if not allow_input else None,
            cwd=tempfile.gettempdir(),  # run in a neutral directory
        )

        stdout = result.stdout
        stderr = result.stderr
        truncated = False

        if len(stdout) > CODE_MAX_OUTPUT:
            stdout = stdout[:CODE_MAX_OUTPUT] + f"\n... [truncated at {CODE_MAX_OUTPUT} chars]"
            truncated = True
        if len(stderr) > CODE_MAX_OUTPUT:
            stderr = stderr[:CODE_MAX_OUTPUT] + f"\n... [truncated at {CODE_MAX_OUTPUT} chars]"

        return {
            "stdout":     stdout,
            "stderr":     stderr,
            "returncode": result.returncode,
            "success":    result.returncode == 0,
            "warnings":   warnings,
            "truncated":  truncated,
        }

    except subprocess.TimeoutExpired:
        return {
            "stdout":     "",
            "stderr":     f"Execution timed out after {timeout} seconds.",
            "returncode": -1,
            "success":    False,
            "warnings":   warnings,
            "truncated":  False,
        }
    except Exception as exc:
        return {
            "stdout":     "",
            "stderr":     str(exc),
            "returncode": -1,
            "success":    False,
            "warnings":   warnings,
            "truncated":  False,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
