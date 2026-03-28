"""
Confidence Engine — Success Probability Estimation

Estimates likelihood of task success before execution based on:
  - clarity of the request
  - task complexity
  - dependency uncertainty
  - similarity to past successful patterns
  - mode constraints

Returns a float 0.0–1.0 and a structured breakdown.
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class ConfidenceResult:
    score:           float          # 0.0 – 1.0
    label:           str            # "Very High" | "High" | "Medium" | "Low" | "Very Low"
    factors:         List[str]      # human-readable factor list
    deductions:      List[str]      # what lowered confidence
    recommendation:  Optional[str]  # if low, suggested mitigations


def estimate(
    intent_type: str,
    normalized_goal: str,
    ambiguity_score: float,
    risk_level: str,
    mode: str,
    has_existing_code: bool = False,
    history_length: int = 0,
    similar_pattern_found: bool = False,
) -> ConfidenceResult:
    """
    Estimate task success probability.

    Args:
        intent_type:           "build" | "patch" | "query" | "image" | "analysis" | "chat"
        normalized_goal:       Clean goal string.
        ambiguity_score:       0.0 (clear) – 1.0 (very ambiguous).
        risk_level:            "low" | "medium" | "high"
        mode:                  "chat" | "builder" | "image"
        has_existing_code:     Whether an existing codebase/app is present.
        history_length:        Number of prior conversation turns.
        similar_pattern_found: Whether build_patterns library has a matching template.
    """
    base = 0.90
    factors: List[str] = []
    deductions: List[str] = []

    # --- Clarity boost ---
    if ambiguity_score < 0.1:
        base += 0.05
        factors.append("Request is clear and specific")
    elif ambiguity_score < 0.3:
        factors.append("Request is mostly clear")
    else:
        penalty = min(0.25, ambiguity_score * 0.35)
        base -= penalty
        deductions.append(f"Ambiguous phrasing (score {ambiguity_score:.2f}) — harder to match intent exactly")

    # --- Intent type baseline ---
    type_adj = {
        "chat":     +0.05,   # conversational, very high success
        "query":    +0.05,
        "patch":    +0.02,   # patches are targeted
        "image":    -0.03,   # image quality is subjective
        "build":    -0.05,   # builds are complex
        "analysis": 0.00,
    }
    adj = type_adj.get(intent_type, 0.0)
    base += adj
    if adj < 0:
        deductions.append(f"{intent_type.title()} tasks are inherently more complex")
    else:
        factors.append(f"{intent_type.title()} task type has high baseline success")

    # --- Risk level ---
    if risk_level == "high":
        base -= 0.15
        deductions.append("High risk action — more failure points")
    elif risk_level == "medium":
        base -= 0.07
        deductions.append("Medium risk — some uncertainty in execution")
    else:
        factors.append("Low risk action")

    # --- Context continuity ---
    if has_existing_code and intent_type == "patch":
        base += 0.04
        factors.append("Patching existing code with full context available")
    elif not has_existing_code and intent_type == "patch":
        base -= 0.10
        deductions.append("Patch requested but no existing code found in context")

    # --- Session warmth ---
    if history_length > 5:
        base += 0.03
        factors.append("Rich conversation history — better context available")
    elif history_length == 0:
        base -= 0.02
        deductions.append("First message — no project context yet")

    # --- Pattern library boost ---
    if similar_pattern_found:
        base += 0.06
        factors.append("Similar successful build pattern found in library")

    # --- Goal length heuristic ---
    words = len(normalized_goal.split())
    if words < 4:
        base -= 0.08
        deductions.append("Very short request — may lack enough detail")
    elif words > 60:
        base -= 0.05
        deductions.append("Very long request — higher risk of scope creep")

    # Clamp
    score = max(0.30, min(0.99, base))

    # Label
    if score >= 0.90:
        label = "Very High"
    elif score >= 0.78:
        label = "High"
    elif score >= 0.62:
        label = "Medium"
    elif score >= 0.45:
        label = "Low"
    else:
        label = "Very Low"

    # Recommendation
    recommendation = None
    if score < 0.65:
        recommendation = "Consider splitting this into smaller steps to improve reliability."
    elif ambiguity_score > 0.4:
        recommendation = "Clarifying the request before building will increase precision."

    return ConfidenceResult(
        score=round(score, 2),
        label=label,
        factors=factors,
        deductions=deductions,
        recommendation=recommendation,
    )
