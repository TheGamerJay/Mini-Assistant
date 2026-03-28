"""
Decision Engine — Ask vs Act

Evaluates whether Mini Assistant should:
  - ACT immediately (low risk, reversible, cosmetic)
  - ACT + SHOW (uncertain but safe progress possible)
  - ASK FIRST (high impact, hard to reverse, multiple valid interpretations)

This is the first gate in the orchestration pipeline. It must be fast and
deterministic — no LLM calls here, pure rule evaluation + lightweight scoring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Decision(str, Enum):
    ACT        = "act"         # proceed immediately
    ACT_SHOW   = "act_show"    # proceed, but surface result for approval before finalising
    ASK        = "ask"         # pause and clarify before doing anything


@dataclass
class DecisionResult:
    decision:         Decision
    confidence:       float          # 0.0 – 1.0, how confident we are in the decision itself
    reason:           str
    reversible:       bool
    risk_level:       str            # "low" | "medium" | "high"
    interpretations:  List[str] = field(default_factory=list)
    clarification_q:  Optional[str] = None   # set when decision == ASK


# ---------------------------------------------------------------------------
# Signals used for scoring
# ---------------------------------------------------------------------------

_HIGH_IMPACT_PATTERNS = re.compile(
    r"\b(delete|remove|drop|wipe|clear|reset|rebuild|replace|rewrite|"
    r"migrate|rename|overwrite|destroy|purge|truncate)\b",
    re.I,
)

_IRREVERSIBLE_PATTERNS = re.compile(
    r"\b(deploy|publish|send|submit|upload|push|release|ship|"
    r"delete\s+all|remove\s+all|drop\s+table|wipe\s+data)\b",
    re.I,
)

_AMBIGUITY_MARKERS = re.compile(
    r"\b(maybe|might|or|either|not sure|don't know|whatever|anything|"
    r"something like|kind of|sort of|i guess|perhaps|ideally)\b",
    re.I,
)

_BUILD_INTENT_PATTERNS = re.compile(
    r"\b(build|create|make|generate|add|implement|develop|write|code|design|set\s*up)\b",
    re.I,
)

_PATCH_INTENT_PATTERNS = re.compile(
    r"\b(fix|patch|update|change|tweak|adjust|slow|faster|bigger|smaller|"
    r"move|align|color|style|font|size|spacing|dark|light)\b",
    re.I,
)

_COSMETIC_PATTERNS = re.compile(
    r"\b(color|colour|font|size|spacing|margin|padding|border|shadow|"
    r"opacity|darker|lighter|bigger|smaller|wider|narrower|align|center|"
    r"layout|style|theme|icon|label|text|wording|rename|move)\b",
    re.I,
)

_SCOPE_CREEP_PATTERNS = re.compile(
    r"\b(everything|entire|whole|all\s+of|complete\s+rewrite|from\s+scratch|"
    r"start\s+over|redesign|overhaul|revamp|rethink)\b",
    re.I,
)


def evaluate(
    message: str,
    has_existing_code: bool = False,
    history_length: int = 0,
    mode: str = "chat",          # "chat" | "builder" | "image"
    vibe_mode: bool = False,
) -> DecisionResult:
    """
    Core decision gate. Runs synchronously — no I/O.

    Args:
        message:          Raw user message.
        has_existing_code: Whether a built app / codebase already exists.
        history_length:   Number of prior messages in session.
        mode:             Current operating mode.
        vibe_mode:        If True, lean toward ACT (fewer confirmations).

    Returns:
        DecisionResult
    """
    msg = message.strip()

    # --- Score individual signals ---
    is_high_impact    = bool(_HIGH_IMPACT_PATTERNS.search(msg))
    is_irreversible   = bool(_IRREVERSIBLE_PATTERNS.search(msg))
    is_ambiguous      = bool(_AMBIGUITY_MARKERS.search(msg))
    is_build          = bool(_BUILD_INTENT_PATTERNS.search(msg))
    is_patch          = bool(_PATCH_INTENT_PATTERNS.search(msg))
    is_cosmetic       = bool(_COSMETIC_PATTERNS.search(msg))
    is_scope_creep    = bool(_SCOPE_CREEP_PATTERNS.search(msg))
    is_short          = len(msg.split()) < 8

    # Multi-interpretation check: does the message contain "or" between distinct ideas?
    has_or_branch = bool(re.search(r"\bor\b", msg, re.I)) and len(msg.split()) > 6

    # Risk score: 0 (none) → 10 (maximum)
    risk_score = 0
    if is_high_impact:    risk_score += 3
    if is_irreversible:   risk_score += 4
    if is_scope_creep:    risk_score += 3
    if is_ambiguous:      risk_score += 2
    if has_or_branch:     risk_score += 2
    if mode == "builder" and is_high_impact: risk_score += 1

    # Reversibility: cosmetic/patch changes are easily undone
    reversible = not is_irreversible and (is_cosmetic or is_patch or is_short)

    # Risk level bucketing
    if risk_score >= 6:
        risk_level = "high"
    elif risk_score >= 3:
        risk_level = "medium"
    else:
        risk_level = "low"

    # --- Collect candidate interpretations when ambiguous ---
    interpretations: List[str] = []
    clarification_q: Optional[str] = None

    # --- Decision rules ---

    # Rule 1: Destructive + irreversible → always ask
    if is_irreversible and is_high_impact and not vibe_mode:
        return DecisionResult(
            decision=Decision.ASK,
            confidence=0.95,
            reason="Action is destructive and hard to reverse.",
            reversible=False,
            risk_level="high",
            clarification_q=_destructive_clarification(msg),
        )

    # Rule 2: Vibe mode → always act (user wants zero friction)
    if vibe_mode:
        return DecisionResult(
            decision=Decision.ACT,
            confidence=0.9,
            reason="Vibe mode active — proceeding immediately.",
            reversible=reversible,
            risk_level=risk_level,
        )

    # Rule 3: Pure cosmetic patch on existing code → act
    if is_cosmetic and has_existing_code and not is_scope_creep:
        return DecisionResult(
            decision=Decision.ACT,
            confidence=0.88,
            reason="Cosmetic change on existing code — safe to apply directly.",
            reversible=True,
            risk_level="low",
        )

    # Rule 4: Simple patch with clear intent → act
    if is_patch and not is_ambiguous and not is_scope_creep and has_existing_code:
        return DecisionResult(
            decision=Decision.ACT,
            confidence=0.85,
            reason="Clear targeted patch — proceeding.",
            reversible=True,
            risk_level="low",
        )

    # Rule 5: Ambiguous with scope creep risk → ask
    if (is_ambiguous or has_or_branch) and (is_build or is_scope_creep):
        interpretations = _extract_interpretations(msg)
        clarification_q = _ambiguity_clarification(msg, interpretations)
        return DecisionResult(
            decision=Decision.ASK,
            confidence=0.82,
            reason="Multiple valid interpretations — clarifying before building.",
            reversible=reversible,
            risk_level=risk_level,
            interpretations=interpretations,
            clarification_q=clarification_q,
        )

    # Rule 6: First message in builder, building something new → act + show plan
    if mode == "builder" and is_build and history_length < 3:
        return DecisionResult(
            decision=Decision.ACT_SHOW,
            confidence=0.80,
            reason="New build request — will plan steps and show summary before executing.",
            reversible=True,
            risk_level="low",
        )

    # Rule 7: High risk in builder mode → act + show for approval
    if mode == "builder" and risk_level in ("medium", "high"):
        return DecisionResult(
            decision=Decision.ACT_SHOW,
            confidence=0.78,
            reason="Medium/high risk action — showing plan for confirmation.",
            reversible=reversible,
            risk_level=risk_level,
        )

    # Rule 8: Short conversational → act immediately
    if is_short and not is_build and not is_high_impact:
        return DecisionResult(
            decision=Decision.ACT,
            confidence=0.92,
            reason="Short conversational message — responding directly.",
            reversible=True,
            risk_level="low",
        )

    # Default: act
    return DecisionResult(
        decision=Decision.ACT,
        confidence=0.75,
        reason="Low risk, proceeding with task.",
        reversible=reversible,
        risk_level=risk_level,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _destructive_clarification(msg: str) -> str:
    if re.search(r"\b(delete|wipe|remove)\b", msg, re.I):
        return "This will permanently remove data. Are you sure you want to proceed? I can't undo this."
    if re.search(r"\b(rebuild|rewrite|from scratch|start over)\b", msg, re.I):
        return "This will replace the entire existing app. Should I save a checkpoint of the current version first?"
    return "This action may be hard to reverse. Can you confirm you want to proceed?"


def _ambiguity_clarification(msg: str, interpretations: List[str]) -> str:
    if not interpretations:
        return "I want to make sure I build exactly what you need. Could you clarify what you have in mind?"
    opts = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(interpretations))
    return f"I see a few ways to interpret this:\n{opts}\n\nWhich direction do you want?"


def _extract_interpretations(msg: str) -> List[str]:
    """Lightweight interpretation extractor — finds 'or'-branched options."""
    parts = re.split(r"\bor\b", msg, flags=re.I)
    clean = [p.strip().capitalize() for p in parts if len(p.strip()) > 4]
    return clean[:3]  # max 3 interpretations
