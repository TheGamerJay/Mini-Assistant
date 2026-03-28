"""
Anti-Overbuild Guard — Scope Enforcement

Prevents the system from:
  - Adding features the user didn't request
  - Refactoring unrelated code
  - Redesigning product direction
  - Silently expanding requirements

After a task is planned, this guard classifies each planned change as:
  - in_scope:           explicitly requested or required for correctness
  - supporting:         technically necessary to support the request
  - out_of_scope:       not requested — BLOCKED by default
  - optional_suggest:   improvement the system COULD make — surfaced, not auto-applied

This is applied during the planning phase before execution begins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PlannedChange:
    """A single change the system is considering making."""
    id:          str
    description: str
    file_path:   Optional[str] = None
    reason:      str = ""
    tags:        List[str] = field(default_factory=list)


@dataclass
class ScopeGuardResult:
    in_scope:             List[PlannedChange]
    supporting:           List[PlannedChange]
    blocked_out_of_scope: List[PlannedChange]
    optional_suggestions: List[PlannedChange]
    verdict:              str    # "clean" | "trimmed" | "blocked"
    summary:              str


# ---------------------------------------------------------------------------
# Heuristic patterns — what counts as out-of-scope expansion
# ---------------------------------------------------------------------------

_REFACTOR_TAGS = {
    "refactor", "cleanup", "reorganize", "restructure", "reformat",
    "rename_all", "add_types", "add_comments", "optimize", "performance",
    "accessibility_audit", "seo_audit", "add_tests",
}

_COSMETIC_IMPROVEMENT_TAGS = {
    "add_animation", "add_hover_effect", "add_gradient", "add_shadow",
    "add_icon", "improve_spacing", "add_dark_mode", "improve_typography",
}

_SCOPE_EXPANSION_PHRASES = re.compile(
    r"\b(while\s+(we're|we\s+are|i'm)\s+(at\s+it|here)|"
    r"also\s+(could|should|would|might)|"
    r"while\s+i\s+have\s+it|"
    r"i\s+(noticed|also\s+noticed|saw)|"
    r"bonus|extra|as\s+a\s+bonus|"
    r"improve\s+(?!the\s+requested|the\s+fix)|"
    r"better\s+(?!the\s+requested)|"
    r"upgrade|enhance\s+(?!the\s+requested))\b",
    re.I,
)


def evaluate(
    planned_changes: List[PlannedChange],
    user_request: str,
    intent_type: str,
    vibe_mode: bool = False,
) -> ScopeGuardResult:
    """
    Classify planned changes and block out-of-scope ones.

    Args:
        planned_changes: List of changes the system is planning.
        user_request:    The original normalized user request.
        intent_type:     "build" | "patch" | "query" | "chat"
        vibe_mode:       If True, relax scope enforcement (still blocks destructive).

    Returns:
        ScopeGuardResult with classified change lists.
    """
    in_scope: List[PlannedChange] = []
    supporting: List[PlannedChange] = []
    blocked: List[PlannedChange] = []
    optional: List[PlannedChange] = []

    for change in planned_changes:
        classification = _classify(change, user_request, intent_type, vibe_mode)
        if classification == "in_scope":
            in_scope.append(change)
        elif classification == "supporting":
            supporting.append(change)
        elif classification == "out_of_scope":
            blocked.append(change)
        elif classification == "optional":
            optional.append(change)

    # Verdict
    if blocked:
        verdict = "trimmed"
    elif optional:
        verdict = "clean"
    else:
        verdict = "clean"

    # Summary
    summary_parts = [f"{len(in_scope)} in-scope"]
    if supporting:
        summary_parts.append(f"{len(supporting)} supporting")
    if blocked:
        summary_parts.append(f"{len(blocked)} blocked (out of scope)")
    if optional:
        summary_parts.append(f"{len(optional)} optional suggestions available")
    summary = ", ".join(summary_parts) + "."

    return ScopeGuardResult(
        in_scope=in_scope,
        supporting=supporting,
        blocked_out_of_scope=blocked,
        optional_suggestions=optional,
        verdict=verdict,
        summary=summary,
    )


def _classify(
    change: PlannedChange,
    user_request: str,
    intent_type: str,
    vibe_mode: bool,
) -> str:
    """Classify a single planned change."""
    tags = set(change.tags)
    desc = change.description.lower()
    reason = change.reason.lower()

    # Supporting changes are always allowed (bug fixes needed for correctness)
    if "required_for_correctness" in tags or "fix_dependency" in tags:
        return "supporting"

    # Refactors on a patch task → out of scope
    if intent_type == "patch" and (tags & _REFACTOR_TAGS):
        if not vibe_mode:
            return "out_of_scope"
        return "optional"

    # Cosmetic improvements not asked for → optional
    if tags & _COSMETIC_IMPROVEMENT_TAGS:
        # Only block if not related to the request
        if not _is_related_to_request(desc, user_request):
            return "optional"

    # Scope expansion language in the reason → out of scope
    if _SCOPE_EXPANSION_PHRASES.search(reason):
        if not vibe_mode:
            return "out_of_scope"
        return "optional"

    # "Add tests" when not asked → optional
    if "add_tests" in tags and "test" not in user_request.lower():
        return "optional"

    # Refactor unrelated file → out of scope
    if "refactor_unrelated" in tags:
        return "out_of_scope"

    return "in_scope"


def _is_related_to_request(description: str, request: str) -> bool:
    """Check if a change description shares significant keywords with the request."""
    req_words = set(re.findall(r"\b\w{4,}\b", request.lower()))
    desc_words = set(re.findall(r"\b\w{4,}\b", description.lower()))
    # 25%+ overlap = related
    if not req_words:
        return False
    overlap = len(req_words & desc_words) / len(req_words)
    return overlap >= 0.25


# ---------------------------------------------------------------------------
# Convenience: build planned changes from a simple list of descriptions
# ---------------------------------------------------------------------------

def from_descriptions(descriptions: List[str], tags_per_change: Optional[List[List[str]]] = None) -> List[PlannedChange]:
    """
    Build a list of PlannedChange objects from plain description strings.
    Useful for quick testing or simple planners that output text steps.
    """
    from typing import Optional as Opt
    result = []
    for i, desc in enumerate(descriptions):
        tags = (tags_per_change[i] if tags_per_change and i < len(tags_per_change) else [])
        result.append(PlannedChange(
            id=f"change_{i+1}",
            description=desc,
            tags=tags,
            reason="",
        ))
    return result


# Type re-export for convenience
from typing import Optional
