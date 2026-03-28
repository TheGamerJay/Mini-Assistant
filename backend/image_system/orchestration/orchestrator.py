"""
Orchestrator — Phase 1 Coordinator

Entry point for the orchestration system.
Called before any chat/builder execution to:
  1. Evaluate ask vs act (decision_engine)
  2. Parse and lock intent (intent_lock)
  3. Estimate risk, cost, confidence
  4. Return a structured AnalysisResult for the frontend

The frontend renders the ThinkingSequence + TaskSummaryCard from this result.
If decision == ASK, the clarification question is surfaced directly.
If decision == ACT or ACT_SHOW, the task proceeds (with or without plan display).

This module is NON-BLOCKING for simple/chat requests — it returns quickly
for conversational messages so they don't feel delayed.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .decision_engine import evaluate as de_evaluate, Decision, DecisionResult
from .intent_lock     import parse as il_parse, IntentLock
from .confidence_engine import estimate as conf_estimate, ConfidenceResult
from .risk_estimator    import estimate as risk_estimate, RiskProfile
from .cost_estimator    import estimate as cost_estimate, CostEstimate

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """
    Complete pre-execution analysis package.
    Serializes to JSON for the `/api/orchestrate/analyze` endpoint.
    """
    # Core decision
    decision:             str          # "act" | "act_show" | "ask"
    proceed_immediately:  bool         # True when no UI confirmation needed

    # Intent
    intent_type:          str
    normalized_goal:      str
    mode:                 str

    # Scores
    confidence:           float
    confidence_label:     str
    risk_level:           str
    risk_score:           int

    # Cost
    cost_min:             int
    cost_max:             int
    cost_label:           str

    # Human-readable breakdowns
    confidence_factors:   List[str]
    confidence_deductions: List[str]
    risk_factors:         List[str]
    risk_mitigations:     List[str]

    # Clarification (set when decision == "ask")
    clarification_q:      Optional[str]
    interpretations:      List[str]

    # Flags
    requires_checkpoint:  bool
    requires_approval:    bool
    contradiction_found:  bool
    ambiguity_score:      float

    # Constraints / assumptions
    constraints:          List[str]
    assumptions:          List[str]

    # Recommendation
    recommendation:       Optional[str]

    # Meta
    elapsed_ms:           int
    session_id:           str


def analyze(
    message: str,
    session_id: str,
    mode: str = "chat",
    history: Optional[List[Dict[str, Any]]] = None,
    has_existing_code: bool = False,
    vibe_mode: bool = False,
) -> AnalysisResult:
    """
    Run the full Phase 1 analysis pipeline.

    Fast path: conversational/query messages skip expensive sub-steps.
    """
    t0 = time.monotonic()
    history = history or []
    history_length = len(history)

    # ── Step 1: Decision Engine ──────────────────────────────────────────────
    decision_result: DecisionResult = de_evaluate(
        message=message,
        has_existing_code=has_existing_code,
        history_length=history_length,
        mode=mode,
        vibe_mode=vibe_mode,
    )

    # Fast path for simple conversational messages
    if decision_result.decision == Decision.ACT and decision_result.risk_level == "low":
        elapsed = int((time.monotonic() - t0) * 1000)
        # Still parse intent for logging, but don't block
        intent = il_parse(message, session_id, mode, history)
        return AnalysisResult(
            decision="act",
            proceed_immediately=True,
            intent_type=intent.intent_type,
            normalized_goal=intent.normalized_goal,
            mode=mode,
            confidence=decision_result.confidence,
            confidence_label="High",
            risk_level="low",
            risk_score=0,
            cost_min=0,
            cost_max=0,
            cost_label="Free" if intent.intent_type in ("chat", "query") else "Low",
            confidence_factors=["Low-risk action — proceeding directly"],
            confidence_deductions=[],
            risk_factors=["No elevated risk signals"],
            risk_mitigations=[],
            clarification_q=None,
            interpretations=[],
            requires_checkpoint=False,
            requires_approval=False,
            contradiction_found=False,
            ambiguity_score=0.0,
            constraints=intent.constraints,
            assumptions=intent.assumptions_accepted,
            recommendation=None,
            elapsed_ms=elapsed,
            session_id=session_id,
        )

    # ── Step 2: Intent Lock ──────────────────────────────────────────────────
    intent: IntentLock = il_parse(message, session_id, mode, history)

    # ── Step 3: Risk Profile ─────────────────────────────────────────────────
    risk: RiskProfile = risk_estimate(
        message=intent.normalized_goal,
        intent_type=intent.intent_type,
        mode=mode,
        has_existing_code=has_existing_code,
        ambiguity_score=intent.ambiguity_score,
    )

    # ── Step 4: Confidence ───────────────────────────────────────────────────
    # Check if a similar pattern exists in the build patterns library
    similar_pattern_found = _check_pattern_library(intent.normalized_goal)

    conf: ConfidenceResult = conf_estimate(
        intent_type=intent.intent_type,
        normalized_goal=intent.normalized_goal,
        ambiguity_score=intent.ambiguity_score,
        risk_level=risk.level,
        mode=mode,
        has_existing_code=has_existing_code,
        history_length=history_length,
        similar_pattern_found=similar_pattern_found,
    )

    # ── Step 5: Cost Estimate ────────────────────────────────────────────────
    # Estimate step count based on intent type
    step_count = _estimate_step_count(intent.intent_type, message)

    cost: CostEstimate = cost_estimate(
        intent_type=intent.intent_type,
        mode=mode,
        risk_level=risk.level,
        step_count=step_count,
        message_word_count=len(message.split()),
        has_verification=(mode == "builder"),
        has_checkpoint=risk.requires_checkpoint,
    )

    # ── Assemble result ──────────────────────────────────────────────────────
    elapsed = int((time.monotonic() - t0) * 1000)

    proceed_immediately = (
        decision_result.decision == Decision.ACT
        and not risk.requires_approval
    )

    logger.info(
        "[Orchestrator] session=%s intent=%s decision=%s risk=%s confidence=%.2f cost=%d-%d elapsed=%dms",
        session_id[:8],
        intent.intent_type,
        decision_result.decision,
        risk.level,
        conf.score,
        cost.min_credits,
        cost.max_credits,
        elapsed,
    )

    return AnalysisResult(
        decision=decision_result.decision.value,
        proceed_immediately=proceed_immediately,
        intent_type=intent.intent_type,
        normalized_goal=intent.normalized_goal,
        mode=mode,
        confidence=conf.score,
        confidence_label=conf.label,
        risk_level=risk.level,
        risk_score=risk.score,
        cost_min=cost.min_credits,
        cost_max=cost.max_credits,
        cost_label=cost.label,
        confidence_factors=conf.factors,
        confidence_deductions=conf.deductions,
        risk_factors=risk.factors,
        risk_mitigations=risk.mitigations,
        clarification_q=decision_result.clarification_q,
        interpretations=decision_result.interpretations,
        requires_checkpoint=risk.requires_checkpoint,
        requires_approval=risk.requires_approval,
        contradiction_found=intent.contradiction_found,
        ambiguity_score=intent.ambiguity_score,
        constraints=intent.constraints,
        assumptions=intent.assumptions_accepted,
        recommendation=conf.recommendation,
        elapsed_ms=elapsed,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def to_dict(result: AnalysisResult) -> Dict[str, Any]:
    """Convert AnalysisResult to a JSON-serializable dict."""
    from dataclasses import asdict
    return asdict(result)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_pattern_library(goal: str) -> bool:
    """Non-fatal check for similar build patterns."""
    try:
        from ..brains.build_patterns import search_patterns
        patterns = search_patterns(goal, top_n=1)
        return len(patterns) > 0
    except Exception:
        return False


def _estimate_step_count(intent_type: str, message: str) -> int:
    """Rough step count estimate based on intent."""
    words = len(message.split())
    base = {
        "chat":     1,
        "query":    1,
        "analysis": 2,
        "patch":    3,
        "image":    2,
        "build":    5,
    }.get(intent_type, 3)

    # Large requests need more steps
    if words > 50:
        base += 2
    elif words > 25:
        base += 1

    return base
