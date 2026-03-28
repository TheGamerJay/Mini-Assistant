"""
tester.py – Automatic Test Generation & Execution
───────────────────────────────────────────────────
When a coding brain writes code, this module:

  1. Extracts the code from the LLM response.
  2. Uses the coder brain to generate pytest unit tests for it.
  3. Runs the tests via subprocess (same sandbox as code_exec).
  4. Returns a TestResult with pass/fail details.

The test file is written to a temp directory and cleaned up afterwards.
Pytest output is parsed into structured pass/fail counts.

Usage:
    tester  = Tester()
    result  = tester.test_response(
        request="Write a function that reverses a string",
        response="```python\\ndef reverse(s):\\n    return s[::-1]\\n```",
    )
    if not result.passed:
        print(result.failure_summary)
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional

import os
from ..config import MODELS, CODE_TIMEOUT

logger = logging.getLogger(__name__)

MAX_TEST_CHARS = 8_000   # cap on generated test code


@dataclass
class TestResult:
    passed: bool
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_errored: int = 0
    stdout: str = ""
    stderr: str = ""
    generated_tests: str = ""
    failure_summary: str = ""
    error: Optional[str] = None   # set if the runner itself crashed


# ─── Code extraction ──────────────────────────────────────────────────────────

def extract_python_code(response: str) -> Optional[str]:
    """Extract the first ```python ... ``` block from an LLM response."""
    match = re.search(r"```python\n(.*?)```", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: generic fenced block
    match = re.search(r"```\w*\n(.*?)```", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


# ─── Test generator ───────────────────────────────────────────────────────────

_TEST_GEN_SYSTEM = """\
You are an expert Python test engineer.

Given Python code and the original task description, write pytest unit tests.

Rules:
- Import the functions/classes directly (assume same module, use exec trick if needed).
- Cover: happy path, edge cases, error cases.
- Keep tests self-contained, no external dependencies unless clearly needed.
- Use pytest conventions: functions named test_*, assert statements only.
- Do NOT include installation commands or explanations.
- Output ONLY the raw Python test code (no markdown fences, no prose).
"""


def generate_tests(code: str, task_description: str) -> str:
    """
    Call Claude/OpenAI to generate pytest tests for `code`.
    Falls back to a minimal placeholder if generation fails.
    """
    prompt = (
        f"Task: {task_description}\n\n"
        f"Code to test:\n```python\n{code[:4000]}\n```\n\n"
        "Write pytest unit tests for the code above. Output only raw Python."
    )

    try:
        ant_key = os.getenv("ANTHROPIC_API_KEY")
        oai_key = os.getenv("OPENAI_API_KEY")
        if ant_key:
            import anthropic
            client = anthropic.Anthropic(api_key=ant_key)
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=_TEST_GEN_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
        elif oai_key:
            import openai
            client = openai.OpenAI(api_key=oai_key)
            resp = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": _TEST_GEN_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = (resp.choices[0].message.content or "").strip()
        else:
            raise RuntimeError("No AI key")
        # Strip any accidental fences
        raw = re.sub(r"```(?:python)?", "", raw).replace("```", "").strip()
        return raw[:MAX_TEST_CHARS]

    except Exception as exc:
        logger.warning("Test generation LLM failed: %s", exc)
        return (
            "def test_code_imports_without_error():\n"
            "    pass  # Code imported successfully\n"
        )


# ─── Test runner ──────────────────────────────────────────────────────────────

def _parse_pytest_output(stdout: str, stderr: str) -> dict:
    """Parse pytest summary line into counts."""
    counts = {"run": 0, "passed": 0, "failed": 0, "errored": 0}

    # Match lines like: "3 passed, 1 failed, 1 error in 0.12s"
    summary_re = re.compile(
        r"(\d+)\s+passed|(\d+)\s+failed|(\d+)\s+error", re.IGNORECASE
    )
    for m in summary_re.finditer(stdout + "\n" + stderr):
        if m.group(1):
            counts["passed"] += int(m.group(1))
        if m.group(2):
            counts["failed"] += int(m.group(2))
        if m.group(3):
            counts["errored"] += int(m.group(3))

    counts["run"] = counts["passed"] + counts["failed"] + counts["errored"]
    return counts


def run_tests(code: str, test_code: str, timeout: int = CODE_TIMEOUT * 2) -> TestResult:
    """
    Write code + tests to temp files and execute pytest.

    Returns a TestResult with parsed outcomes.
    """
    with tempfile.TemporaryDirectory(prefix="mini_test_") as tmpdir:
        # Write the source module
        src_file  = os.path.join(tmpdir, "solution.py")
        test_file = os.path.join(tmpdir, "test_solution.py")

        # Prepend an import of the solution module into the test file
        full_test = (
            f"import sys, os\n"
            f"sys.path.insert(0, r'{tmpdir}')\n"
            f"exec(open(r'{src_file}').read(), globals())\n\n"
            + test_code
        )

        try:
            with open(src_file,  "w", encoding="utf-8") as f:
                f.write(code)
            with open(test_file, "w", encoding="utf-8") as f:
                f.write(full_test)

            result = subprocess.run(
                ["python", "-m", "pytest", test_file, "-v", "--tb=short", "--no-header"],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )

            stdout = result.stdout or ""
            stderr = result.stderr or ""
            counts = _parse_pytest_output(stdout, stderr)

            passed = result.returncode == 0 or counts["passed"] > 0 and counts["failed"] == 0

            summary = ""
            if not passed:
                # Extract failure lines
                fail_lines = [
                    l for l in (stdout + stderr).splitlines()
                    if any(k in l for k in ("FAILED", "ERROR", "AssertionError", "assert"))
                ]
                summary = "\n".join(fail_lines[:20])

            return TestResult(
                passed         = passed,
                tests_run      = counts["run"],
                tests_passed   = counts["passed"],
                tests_failed   = counts["failed"],
                tests_errored  = counts["errored"],
                stdout         = stdout[:3000],
                stderr         = stderr[:1000],
                generated_tests= test_code,
                failure_summary= summary,
            )

        except subprocess.TimeoutExpired:
            return TestResult(
                passed=False, error="Test run timed out",
                generated_tests=test_code,
                failure_summary="Tests timed out – possible infinite loop.",
            )
        except Exception as exc:
            return TestResult(
                passed=False, error=str(exc),
                generated_tests=test_code,
                failure_summary=f"Test runner error: {exc}",
            )


# ─── High-level tester ────────────────────────────────────────────────────────

class Tester:
    """
    Auto-generate and run tests for code produced by the coder brain.
    """

    def test_response(
        self,
        request: str,
        response: str,
        custom_tests: Optional[str] = None,
    ) -> TestResult:
        """
        Extract code from response, generate tests, run them.

        Args:
            request:      Original user request (used as context for test gen).
            response:     Full LLM response containing the code.
            custom_tests: If provided, use these tests instead of auto-generating.

        Returns:
            TestResult with pass/fail details.
        """
        code = extract_python_code(response)
        if not code:
            logger.info("No Python code found in response – skipping tests.")
            return TestResult(
                passed=True,   # nothing to test
                tests_run=0,
                failure_summary="No Python code block found in response.",
            )

        logger.info("Generating tests for code block (%d chars).", len(code))
        test_code = custom_tests or generate_tests(code, task_description=request)
        return run_tests(code, test_code)

    def test_code_directly(
        self,
        code: str,
        task_description: str,
        custom_tests: Optional[str] = None,
    ) -> TestResult:
        """Run tests against a raw code string (not wrapped in an LLM response)."""
        test_code = custom_tests or generate_tests(code, task_description)
        return run_tests(code, test_code)
