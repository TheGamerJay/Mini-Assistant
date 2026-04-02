"""
execution/error_handler.py — Structured error handling and recovery for the CEO pipeline.

Every error surfaces with:
  - clear description of what failed
  - recovery options the user can choose from
  - recommended next step

Error types:
  module_failure      — module.execute() returned status=error or threw
  validation_failure  — output_validator returned ok=False
  web_failure         — web fetch returned ok=False
  memory_missing      — required memory not found, no clarification asked
  execution_interrupt — unexpected exception during plan execution
  clarification_timeout — clarification was required but not resolved

Output format:
  {
      "type":             "error",
      "error_type":       str,
      "issue":            str,       # plain language description
      "recovery_options": list[str], # what the user can do
      "next_step":        str,       # single recommended action
      "detail":           dict,      # technical detail (X-Ray only)
  }

Rules:
- never silently fail — every error must surface
- recovery_options must be actionable
- next_step must be a single clear recommendation
- detail is for X-Ray mode only — not shown to user by default
"""

from __future__ import annotations

from typing import Any


def module_failure(
    module: str,
    error:  str,
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type":       "error",
        "error_type": "module_failure",
        "issue":      f"The {module} module encountered an error and could not complete.",
        "recovery_options": [
            "Try again — transient errors often resolve on retry",
            "Simplify your request — break it into smaller steps",
            "Switch to a different approach or module",
        ],
        "next_step": "Retry the request. If the error persists, simplify the task.",
        "detail":    {"module": module, "error": error, "result_keys": list(result.keys())},
    }


def validation_failure(
    module:          str,
    validation_type: str,
    issues:          list[str],
    result:          dict[str, Any],
) -> dict[str, Any]:
    return {
        "type":       "error",
        "error_type": "validation_failure",
        "issue":      f"The output from {module} did not pass validation ({validation_type}).",
        "recovery_options": [
            "Request regeneration — ask the system to try again",
            "Provide more specific instructions to guide the output",
            "Accept the output as-is if the issues are minor",
        ],
        "next_step": f"Issues found: {'; '.join(issues[:3])}. Request regeneration or refine your prompt.",
        "detail":    {
            "module":          module,
            "validation_type": validation_type,
            "issues":          issues,
            "output_keys":     list(result.keys()),
        },
    }


def web_failure(mode: str, error: str) -> dict[str, Any]:
    return {
        "type":       "error",
        "error_type": "web_failure",
        "issue":      f"Web {mode} could not retrieve the requested data.",
        "recovery_options": [
            "Retry — the target site may have been temporarily unavailable",
            "Provide the information directly instead of fetching it",
            "Try a different search query or URL",
        ],
        "next_step": "Retry the request or provide the data directly.",
        "detail":    {"mode": mode, "error": error},
    }


def memory_missing(module: str, scope: str) -> dict[str, Any]:
    return {
        "type":       "error",
        "error_type": "memory_missing",
        "issue":      f"Required memory for {module} ({scope}) was not found.",
        "recovery_options": [
            "Provide the required information in your message",
            "Upload or paste the relevant document",
        ],
        "next_step": "Share the required information directly in your message.",
        "detail":    {"module": module, "scope": scope},
    }


def execution_interrupt(step: str, error: str) -> dict[str, Any]:
    return {
        "type":       "error",
        "error_type": "execution_interrupt",
        "issue":      f"Execution was interrupted at step '{step}'.",
        "recovery_options": [
            "Retry the full request",
            "Report the error if it repeats",
        ],
        "next_step": "Retry the request. If it fails again, report the step and error.",
        "detail":    {"step": step, "error": error},
    }


def from_result(
    module: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Build an error response from a module result dict that has status=error.
    Convenience wrapper for the most common case.
    """
    return module_failure(
        module = module,
        error  = result.get("error", "unknown error"),
        result = result,
    )
