"""
Verification Engine — Phase 5

Multi-layer verification before a task is declared complete:
  1. Structural — syntax, balanced tags, required elements
  2. Visual     — screenshot analysis (uses existing /api/visual_review logic)
  3. Runtime    — console error detection from DOM report
  4. Interaction — button/form/modal presence checks

A task is ONLY marked complete when all required checks pass.
Failures feed back into the rollback/retry pipeline.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class VerificationIssue:
    layer:    str     # "structural" | "visual" | "runtime" | "interaction"
    severity: str     # "error" | "warning" | "info"
    message:  str
    fix_hint: str = ""


@dataclass
class VerificationResult:
    passed:   bool
    issues:   List[VerificationIssue] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    summary:  str = ""


# ---------------------------------------------------------------------------
# Structural Verification
# ---------------------------------------------------------------------------

_REQUIRED_HTML_ELEMENTS = [
    (re.compile(r"<!DOCTYPE\s+html", re.I),    "Missing DOCTYPE declaration"),
    (re.compile(r"<html",            re.I),    "Missing <html> tag"),
    (re.compile(r"<head",            re.I),    "Missing <head> tag"),
    (re.compile(r"<body",            re.I),    "Missing <body> tag"),
]

_PLACEHOLDER_PATTERNS = [
    (re.compile(r"lorem ipsum",           re.I),  "Lorem ipsum placeholder text found"),
    (re.compile(r"via\.placeholder\.com", re.I),  "Placeholder image URL found"),
    (re.compile(r"example\.com",          re.I),  "example.com URL found"),
    (re.compile(r"coming soon",           re.I),  "Coming soon placeholder found"),
    (re.compile(r"TODO(?!\s*:?\s*\w)",    re.I),  "TODO placeholder found"),
]

_BALANCED_TAG_RE = re.compile(r"<(/?)(\w+)[^>]*>")


def verify_structural(html: str) -> VerificationResult:
    """
    Check HTML structure: required elements, balanced tags, no placeholders.
    """
    issues: List[VerificationIssue] = []
    warnings: List[str] = []

    # Required elements
    for pattern, msg in _REQUIRED_HTML_ELEMENTS:
        if not pattern.search(html):
            issues.append(VerificationIssue(
                layer="structural", severity="error", message=msg,
                fix_hint="Add the missing HTML structure element.",
            ))

    # Placeholder content
    for pattern, msg in _PLACEHOLDER_PATTERNS:
        if pattern.search(html):
            issues.append(VerificationIssue(
                layer="structural", severity="error", message=msg,
                fix_hint="Replace placeholder with real content.",
            ))

    # Balanced tags (simplified — checks open vs close counts for common tags)
    void_tags = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "param", "source", "track", "wbr"}
    tag_counts: Dict[str, int] = {}
    for m in _BALANCED_TAG_RE.finditer(html):
        is_close = bool(m.group(1))
        tag = m.group(2).lower()
        if tag in void_tags:
            continue
        tag_counts[tag] = tag_counts.get(tag, 0) + (-1 if is_close else 1)

    for tag, delta in tag_counts.items():
        if abs(delta) > 0 and tag in ("div", "script", "style", "section", "main", "nav"):
            issues.append(VerificationIssue(
                layer="structural", severity="warning",
                message=f"Possibly unbalanced <{tag}> tags (delta={delta:+d})",
                fix_hint=f"Check opening/closing <{tag}> pairs.",
            ))

    # File size sanity
    if len(html) < 200:
        issues.append(VerificationIssue(
            layer="structural", severity="error",
            message="Output is suspiciously short — possible truncation",
            fix_hint="Regenerate the full file.",
        ))

    passed = not any(i.severity == "error" for i in issues)
    summary = (
        f"Structural: {'PASS' if passed else 'FAIL'} "
        f"({len([i for i in issues if i.severity == 'error'])} errors, "
        f"{len([i for i in issues if i.severity == 'warning'])} warnings)"
    )

    return VerificationResult(passed=passed, issues=issues, warnings=warnings, summary=summary)


# ---------------------------------------------------------------------------
# Runtime Verification (from DOM/console error report)
# ---------------------------------------------------------------------------

_RUNTIME_ERROR_RE = re.compile(
    r"(ReferenceError|TypeError|SyntaxError|Uncaught|Cannot\s+read\s+propert|"
    r"is\s+not\s+defined|is\s+not\s+a\s+function|Failed\s+to\s+load|"
    r"net::ERR_|404\s+Not\s+Found|CORS\s+error)",
    re.I,
)

_RUNTIME_WARNING_RE = re.compile(
    r"(console\.error|console\.warn|DeprecationWarning|"
    r"\[Violation\]|Performance\s+warning)",
    re.I,
)


def verify_runtime(console_log: str, dom_report: str = "") -> VerificationResult:
    """
    Verify runtime health from console output and DOM snapshot.
    """
    issues: List[VerificationIssue] = []
    warnings: List[str] = []
    combined = f"{console_log}\n{dom_report}"

    for m in _RUNTIME_ERROR_RE.finditer(combined):
        line = _extract_line_context(combined, m.start())
        issues.append(VerificationIssue(
            layer="runtime", severity="error",
            message=f"Runtime error: {line[:120]}",
            fix_hint="Debug the JavaScript error before marking complete.",
        ))

    for m in _RUNTIME_WARNING_RE.finditer(combined):
        line = _extract_line_context(combined, m.start())
        warnings.append(f"Warning: {line[:80]}")

    # Deduplicate issues
    seen = set()
    unique_issues = []
    for issue in issues:
        key = issue.message[:60]
        if key not in seen:
            seen.add(key)
            unique_issues.append(issue)
    issues = unique_issues[:10]  # cap at 10 to avoid noise

    passed = not any(i.severity == "error" for i in issues)
    return VerificationResult(
        passed=passed, issues=issues, warnings=warnings,
        summary=f"Runtime: {'PASS' if passed else 'FAIL'} ({len(issues)} errors)",
    )


# ---------------------------------------------------------------------------
# Interaction Verification
# ---------------------------------------------------------------------------

_INTERACTIVE_ELEMENT_PATTERNS = [
    (re.compile(r"<button",          re.I), "button"),
    (re.compile(r"<input",           re.I), "input"),
    (re.compile(r"<form",            re.I), "form"),
    (re.compile(r"<select",          re.I), "select"),
    (re.compile(r"addEventListener", re.I), "event listener"),
]

_DEAD_BUTTON_RE = re.compile(r"<button[^>]*>\s*(?:TODO|Coming Soon|Not Implemented)\s*</button>", re.I)
_ALERT_TODO_RE  = re.compile(r"alert\(['\"](?:TODO|coming soon|not implemented)", re.I)


def verify_interaction(html: str, user_request: str = "") -> VerificationResult:
    """
    Check that interactive elements exist and aren't dead stubs.
    """
    issues: List[VerificationIssue] = []
    warnings: List[str] = []

    # Dead buttons / alert TODOs
    if _DEAD_BUTTON_RE.search(html):
        issues.append(VerificationIssue(
            layer="interaction", severity="error",
            message="Dead button with TODO/Coming Soon label found",
            fix_hint="Implement the button's actual functionality.",
        ))

    if _ALERT_TODO_RE.search(html):
        issues.append(VerificationIssue(
            layer="interaction", severity="error",
            message="Button fires alert('TODO') — not implemented",
            fix_hint="Replace alert stub with real functionality.",
        ))

    # If request mentions specific interactions, verify they exist
    request_lower = user_request.lower()
    if "button" in request_lower and not re.search(r"<button", html, re.I):
        warnings.append("Request mentions buttons but none found in output")

    if "form" in request_lower and not re.search(r"<form", html, re.I):
        warnings.append("Request mentions form but no <form> element found")

    if "modal" in request_lower and not re.search(r"modal|dialog|overlay", html, re.I):
        warnings.append("Request mentions modal but no modal pattern found")

    passed = not any(i.severity == "error" for i in issues)
    return VerificationResult(
        passed=passed, issues=issues, warnings=warnings,
        summary=f"Interaction: {'PASS' if passed else 'FAIL'}",
    )


# ---------------------------------------------------------------------------
# Combined verification pipeline
# ---------------------------------------------------------------------------

def run_full_verification(
    html:          str,
    user_request:  str = "",
    console_log:   str = "",
    dom_report:    str = "",
    skip_layers:   Optional[List[str]] = None,
) -> VerificationResult:
    """
    Run all verification layers and combine results.

    Args:
        html:          Full HTML output.
        user_request:  Original normalized goal.
        console_log:   Browser console output (if available).
        dom_report:    DOM inspector snapshot (if available).
        skip_layers:   List of layer names to skip ("structural", "runtime", "interaction").

    Returns:
        Combined VerificationResult.
    """
    skip = set(skip_layers or [])
    all_issues: List[VerificationIssue] = []
    all_warnings: List[str] = []
    layer_summaries: List[str] = []

    if "structural" not in skip:
        r = verify_structural(html)
        all_issues.extend(r.issues)
        all_warnings.extend(r.warnings)
        layer_summaries.append(r.summary)

    if "runtime" not in skip and (console_log or dom_report):
        r = verify_runtime(console_log, dom_report)
        all_issues.extend(r.issues)
        all_warnings.extend(r.warnings)
        layer_summaries.append(r.summary)

    if "interaction" not in skip:
        r = verify_interaction(html, user_request)
        all_issues.extend(r.issues)
        all_warnings.extend(r.warnings)
        layer_summaries.append(r.summary)

    passed = not any(i.severity == "error" for i in all_issues)
    summary = " | ".join(layer_summaries) if layer_summaries else "No layers run"

    return VerificationResult(
        passed=passed,
        issues=all_issues,
        warnings=all_warnings,
        summary=summary,
    )


def _extract_line_context(text: str, pos: int, window: int = 80) -> str:
    start = max(0, pos - 20)
    end   = min(len(text), pos + window)
    return text[start:end].replace("\n", " ").strip()
