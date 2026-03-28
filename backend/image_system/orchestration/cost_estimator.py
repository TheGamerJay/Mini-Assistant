"""
Cost Estimator — Credit Cost Range Estimation

Estimates min/max credit cost before execution so users can make informed decisions.
Credits represent delivered value. This estimator is deliberately conservative
(overestimate slightly) to avoid surprise charges.

Actual credits are charged per-step on delivery, not on estimate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class CostEstimate:
    min_credits:  int
    max_credits:  int
    label:        str    # "Free" | "Low" | "Moderate" | "High"
    breakdown:    str    # human-readable summary


# Per-step base costs (in credits)
_STEP_COSTS = {
    "analyze":     0,    # read-only, free
    "plan":        1,
    "edit":        2,
    "build":       3,
    "verify":      1,
    "checkpoint":  0,
    "deploy":      5,
    "image":       4,
}

# Multipliers by mode
_MODE_MULT = {
    "chat":    1.0,
    "builder": 1.2,
    "image":   1.5,
}

# Multipliers by risk level
_RISK_MULT = {
    "low":    1.0,
    "medium": 1.3,
    "high":   1.6,
}


def estimate(
    intent_type: str,
    mode: str,
    risk_level: str,
    step_count: int = 1,
    message_word_count: int = 10,
    has_verification: bool = False,
    has_checkpoint: bool = False,
) -> CostEstimate:
    """
    Estimate credit cost range before execution.

    Args:
        intent_type:        "build" | "patch" | "query" | "image" | "chat"
        mode:               "builder" | "chat" | "image"
        risk_level:         "low" | "medium" | "high"
        step_count:         Number of execution steps planned.
        message_word_count: Rough complexity proxy.
        has_verification:   Whether verification pass is included.
        has_checkpoint:     Whether checkpointing is included.
    """
    # Base cost by intent type
    base_type_cost = {
        "chat":     0,
        "query":    0,
        "analysis": 1,
        "patch":    2,
        "build":    4,
        "image":    4,
    }.get(intent_type, 2)

    # Step cost accumulation
    step_cost = step_count * 1  # 1 credit per execution step

    # Complexity modifier from word count
    if message_word_count > 50:
        complexity = 2
    elif message_word_count > 20:
        complexity = 1
    else:
        complexity = 0

    # Verification and checkpoint overhead
    overhead = 0
    if has_verification:
        overhead += 1
    if has_checkpoint:
        overhead += 0  # checkpoints are free

    raw = base_type_cost + step_cost + complexity + overhead

    # Apply mode and risk multipliers
    mode_mult = _MODE_MULT.get(mode, 1.0)
    risk_mult = _RISK_MULT.get(risk_level, 1.0)

    min_credits = max(0, int(raw * mode_mult * 0.8))
    max_credits = max(0, int(raw * mode_mult * risk_mult * 1.2))

    # Ensure at least a small range
    if max_credits <= min_credits:
        max_credits = min_credits + 1

    # Label
    if max_credits == 0:
        label = "Free"
    elif max_credits <= 3:
        label = "Low"
    elif max_credits <= 8:
        label = "Moderate"
    else:
        label = "High"

    # Breakdown text
    parts = []
    if base_type_cost > 0:
        parts.append(f"{intent_type.title()} task base")
    if step_cost > 0:
        parts.append(f"{step_count} execution step{'s' if step_count != 1 else ''}")
    if complexity > 0:
        parts.append("complexity modifier")
    if overhead > 0:
        parts.append("verification pass")
    breakdown = (", ".join(parts) if parts else "Conversational — no charge") + "."

    return CostEstimate(
        min_credits=min_credits,
        max_credits=max_credits,
        label=label,
        breakdown=breakdown,
    )
