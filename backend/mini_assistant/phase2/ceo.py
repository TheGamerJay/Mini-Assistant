"""
ceo.py — CEO Layer
──────────────────
Sets system posture and high-level policy before any work begins.

The CEO does NOT execute work.
The CEO does NOT do deep task reasoning.
The CEO sets posture only — mode, risk, priority, policy notes.

Downstream consumers (Manager, Supervisor) read the posture and adjust
their behaviour accordingly.

Posture modes:
  fast        — short conversational replies, skip heavy brains
  builder     — app/image/code generation, quality over speed
  debug       — error analysis, minimal fix, step-by-step trace
  research    — deep analysis, web search, long-form synthesis
  creative    — image generation with imaginative latitude
  architect   — planning, file analysis, structural thinking
  cautious    — potentially sensitive/complex request, double-check outputs

Risk postures:
  safe        — prefer minimal changes, don't overwrite, confirm on ambiguity
  aggressive  — proceed with best guess, optimise for speed

Priorities:
  speed       — single fast brain, minimal steps
  quality     — multi-step planning, critic pass, retry on failure
  balanced    — one-step unless complexity detected
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

from ..phase1.intent_planner import PlannerOutput


# ── Output type ───────────────────────────────────────────────────────────────

@dataclass
class CEOPosture:
    mode:         str                      # fast|builder|debug|research|creative|architect|cautious
    risk_posture: str                      # safe|aggressive
    priority:     str                      # speed|quality|balanced
    notes:        list[str] = field(default_factory=list)
    ceo_ms:       float     = 0.0

    def to_dict(self) -> dict:
        return {
            "mode":         self.mode,
            "risk_posture": self.risk_posture,
            "priority":     self.priority,
            "notes":        self.notes,
            "ceo_ms":       self.ceo_ms,
        }


# ── Mode selector ─────────────────────────────────────────────────────────────

# Intent → default mode mapping
_INTENT_MODE: dict[str, str] = {
    "normal_chat":            "fast",
    "web_search":             "research",
    "image_generate":         "builder",
    "image_analysis":         "debug",
    "code_runner":            "builder",
    "debugging":              "debug",
    "planning":               "architect",
    "file_analysis":          "architect",
    "app_builder":            "builder",
    "3d_asset_generation":    "builder",
    "3d_character_generation":"builder",
}

# Creative override — image requests with these words get creative mode
_CREATIVE_RE = re.compile(
    r"\b(imaginative|surreal|fantasy|dream|artistic|painterly|abstract|"
    r"unique|original|creative|concept art|illustration|stylised|stylized)\b",
    re.IGNORECASE,
)

# Cautious trigger — requests that warrant extra care
_CAUTIOUS_RE = re.compile(
    r"\b(delete|remove|drop|wipe|overwrite|destroy|replace all|"
    r"production|live site|database|credentials|password|secret|api key|"
    r"git push|force push|rm -rf|sudo|chmod|chown)\b",
    re.IGNORECASE,
)

# Research upgrade — even if base intent is chat, go research mode for these
_RESEARCH_RE = re.compile(
    r"\b(explain in depth|comprehensive|detailed|compare|evaluate|"
    r"pros and cons|deep dive|thorough|full analysis|research)\b",
    re.IGNORECASE,
)


def _select_mode(intent: str, message: str) -> str:
    base_mode = _INTENT_MODE.get(intent, "fast")

    # Cautious overrides everything
    if _CAUTIOUS_RE.search(message):
        return "cautious"

    # Creative upgrade for image generation
    if intent == "image_generate" and _CREATIVE_RE.search(message):
        return "creative"

    # Research upgrade for deep analysis requests
    if base_mode in ("fast", "balanced") and _RESEARCH_RE.search(message):
        return "research"

    return base_mode


# ── Risk posture selector ─────────────────────────────────────────────────────

def _select_risk(mode: str, intent: str) -> str:
    # Cautious mode always means safe posture
    if mode == "cautious":
        return "safe"
    # Destructive intents → safe
    if intent in ("debugging", "file_analysis"):
        return "safe"
    # Fast chat → can be a bit more aggressive (less validation overhead)
    if mode == "fast" and intent == "normal_chat":
        return "aggressive"
    return "safe"


# ── Priority selector ─────────────────────────────────────────────────────────

def _select_priority(mode: str, message: str) -> str:
    # Short messages → optimise for speed
    if len(message.strip()) < 50 and mode == "fast":
        return "speed"
    # Builder / architect / research → quality matters
    if mode in ("builder", "architect", "research", "debug"):
        return "quality"
    return "balanced"


# ── Policy notes ──────────────────────────────────────────────────────────────

def _build_notes(mode: str, risk: str, intent: str, message: str) -> list[str]:
    notes: list[str] = []

    if mode == "cautious":
        notes.append("Destructive or sensitive keywords detected — apply extra validation.")

    if mode == "builder" and intent in ("app_builder", "code_runner"):
        notes.append("Project modification likely — prefer patching existing files over creating new ones.")

    if mode == "debug":
        notes.append("Error context expected — focus on minimal root-cause fix.")

    if mode == "research":
        notes.append("Deep analysis requested — prefer research brain with multi-step synthesis.")

    if mode == "creative":
        notes.append("Creative latitude granted — enhance prompt, explore style variants.")

    if mode == "architect":
        notes.append("Structural thinking mode — surface dependencies and risks in plan.")

    if intent in ("3d_character_generation", "3d_asset_generation"):
        notes.append("3D pipeline (Phase 9) not yet active — return planning response.")

    return notes


# ── Public API ────────────────────────────────────────────────────────────────

def assess(plan: PlannerOutput, message: str) -> CEOPosture:
    """
    CEO assessment: derive posture from the Planner's output.

    Always called AFTER the Planner has determined intent.
    CEO never overrides intent — it only influences how execution is run.

    Args:
        plan:    PlannerOutput from Phase 1.
        message: Effective user message (args, not slash prefix).

    Returns:
        CEOPosture — always succeeds.
    """
    t0 = time.perf_counter()

    mode     = _select_mode(plan.intent, message)
    risk     = _select_risk(mode, plan.intent)
    priority = _select_priority(mode, message)
    notes    = _build_notes(mode, risk, plan.intent, message)

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    return CEOPosture(
        mode         = mode,
        risk_posture = risk,
        priority     = priority,
        notes        = notes,
        ceo_ms       = elapsed_ms,
    )
