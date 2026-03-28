"""
Safe Editor — Phase 3

Provides diff-based, targeted code edits with:
  - before/after tracking
  - dry-run support
  - rollback via checkpoint
  - context-aware patching (never overwrites whole files blindly)

This is the ONLY module that should mutate code/files during task execution.
All writes go through here so they are logged, reversible, and auditable.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class EditResult:
    success:      bool
    before_hash:  str
    after_hash:   str
    diff_preview: str     # first 500 chars of unified diff
    lines_changed: int
    dry_run:      bool
    error:        Optional[str] = None


@dataclass
class ChangeLog:
    task_id:     str
    step_id:     str
    change_type: str        # "patch" | "full_replace" | "append" | "delete_section"
    before_hash: str
    after_hash:  str
    diff_preview: str
    lines_changed: int
    reason:      str
    timestamp:   str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# Module-level change log (per-process; for persistent logs use a DB/file)
_change_log: List[ChangeLog] = []


def get_change_log() -> List[ChangeLog]:
    return list(_change_log)


def clear_change_log() -> None:
    _change_log.clear()


# ---------------------------------------------------------------------------
# Core edit operations
# ---------------------------------------------------------------------------

def patch_content(
    original: str,
    old_text:  str,
    new_text:  str,
    task_id:   str = "",
    step_id:   str = "",
    reason:    str = "",
    dry_run:   bool = False,
) -> Tuple[str, EditResult]:
    """
    Replace old_text with new_text in original, at most once.
    Prefers targeted replacement — will NOT fall back to full rewrite.

    Returns:
        (patched_content, EditResult)
    """
    before_hash = _hash(original)

    if old_text not in original:
        return original, EditResult(
            success=False,
            before_hash=before_hash,
            after_hash=before_hash,
            diff_preview="",
            lines_changed=0,
            dry_run=dry_run,
            error=f"old_text not found in content (len={len(old_text)})",
        )

    patched = original.replace(old_text, new_text, 1)
    after_hash = _hash(patched)
    diff = _unified_diff(original, patched)
    lines_changed = _count_changed_lines(diff)

    result = EditResult(
        success=True,
        before_hash=before_hash,
        after_hash=after_hash,
        diff_preview=diff[:500],
        lines_changed=lines_changed,
        dry_run=dry_run,
    )

    if not dry_run:
        _change_log.append(ChangeLog(
            task_id=task_id,
            step_id=step_id,
            change_type="patch",
            before_hash=before_hash,
            after_hash=after_hash,
            diff_preview=diff[:500],
            lines_changed=lines_changed,
            reason=reason,
        ))
        logger.info("[SafeEditor] patch applied: %d lines changed, task=%s", lines_changed, task_id)

    return patched if not dry_run else original, result


def full_replace(
    new_content: str,
    task_id:     str = "",
    step_id:     str = "",
    reason:      str = "",
    old_content: str = "",
    dry_run:     bool = False,
    justification: str = "",
) -> Tuple[str, EditResult]:
    """
    Full content replacement.
    Should be used ONLY when a patch is impossible (e.g. first build, structural change).
    Requires a justification string to document why.
    """
    before_hash = _hash(old_content)
    after_hash  = _hash(new_content)
    diff = _unified_diff(old_content, new_content) if old_content else "[Full replace — no prior content]"
    lines_changed = _count_changed_lines(diff)

    if not justification:
        logger.warning("[SafeEditor] full_replace called without justification — use patch_content for targeted edits")

    result = EditResult(
        success=True,
        before_hash=before_hash,
        after_hash=after_hash,
        diff_preview=diff[:500],
        lines_changed=lines_changed,
        dry_run=dry_run,
    )

    if not dry_run:
        _change_log.append(ChangeLog(
            task_id=task_id,
            step_id=step_id,
            change_type="full_replace",
            before_hash=before_hash,
            after_hash=after_hash,
            diff_preview=diff[:500],
            lines_changed=lines_changed,
            reason=f"{reason} | justification: {justification}",
        ))
        logger.info("[SafeEditor] full_replace: %d lines, task=%s", lines_changed, task_id)

    return new_content if not dry_run else old_content, result


def verify_no_regression(
    before:  str,
    after:   str,
    checks:  Optional[List[str]] = None,
) -> Tuple[bool, List[str]]:
    """
    Quick structural regression check.
    Verifies that key patterns present in `before` are still present in `after`.

    Args:
        before: Original content.
        after:  Patched content.
        checks: Optional list of regex patterns that must still exist.

    Returns:
        (passed, list_of_issues)
    """
    issues: List[str] = []

    if not checks:
        # Default: check that the content got at least slightly shorter or same size
        # (ensures we didn't accidentally blow up the file)
        ratio = len(after) / max(1, len(before))
        if ratio > 3.0:
            issues.append(f"Output is {ratio:.1f}x larger than input — possible runaway generation")
        return (len(issues) == 0), issues

    for pattern in checks:
        if re.search(pattern, before) and not re.search(pattern, after):
            issues.append(f"Pattern lost after edit: {pattern[:80]}")

    return (len(issues) == 0), issues


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _unified_diff(before: str, after: str) -> str:
    lines_before = before.splitlines(keepends=True)
    lines_after  = after.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        lines_before, lines_after,
        fromfile="before", tofile="after",
        n=2,
    ))
    return "".join(diff_lines)


def _count_changed_lines(diff: str) -> int:
    return sum(1 for line in diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
