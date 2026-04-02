"""
modules/doctor.py — Doctor module: debugging, error tracing, and code repair.

Receives broken code + error context, identifies root cause, returns a fix.
Never guesses without evidence — root_cause must be traceable to provided input.

Output format:
  {
      "type":          "repair_output",
      "issue":         str,     # one-line description of the symptom
      "root_cause":    str,     # specific diagnosed root cause (not vague)
      "fix":           str,     # concrete fix description
      "files_updated": [        # files that were changed
          {"path": str, "description": str, "code": str}
      ],
      "confidence":    "high" | "medium" | "low",
  }

Rules:
- must identify root cause — no vague answers
- root_cause must NOT contain "unknown", "unclear", "might be", "possibly"
  unless that IS the confidence level (in which case confidence = "low")
- fix must be actionable — specific code change or command
- modules NEVER call each other — Doctor does not call Builder
- if logs/traces are not provided, confidence is capped at "medium"
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

log = logging.getLogger("ceo_router.modules.doctor")

_ANTHROPIC_MODEL = "claude-sonnet-4-6"


async def execute(
    decision:    dict[str, Any],
    memory:      dict[str, Any],
    web_results: dict[str, Any],
) -> dict[str, Any]:
    """
    Diagnose and fix the reported issue.
    Returns a structured repair_output dict.
    """
    message = decision.get("message", "")

    # ── Extract error evidence from message and memory ─────────────────────────
    evidence = _collect_evidence(message, memory, web_results)
    log.info("doctor: evidence_types=%s", list(evidence.keys()))

    # ── Search Repair Memory for similar past problems ─────────────────────────
    repair_matches = _search_repair_memory(message)
    if repair_matches:
        log.info("doctor: repair memory matches=%d top_confidence=%s",
                 len(repair_matches), repair_matches[0].get("confidence_level"))
        # Inject top match as supporting context (reference only — not auto-applied)
        top = repair_matches[0]
        evidence["repair_memory_reference"] = (
            f"Similar past problem: {top['problem_name']} "
            f"(confidence={top['confidence_level']}, success_count={top['success_count']}). "
            f"Past solution: {top['solution_name']}. "
            f"Steps: {'; '.join(top['solution_steps'][:3])}"
        )

    # ── Determine confidence ceiling ───────────────────────────────────────────
    has_logs      = bool(evidence.get("logs"))
    has_traceback = bool(evidence.get("traceback"))
    has_code      = bool(evidence.get("code_snippet"))
    if has_logs or has_traceback:
        max_confidence = "high"
    elif has_code:
        max_confidence = "medium"
    else:
        max_confidence = "medium"

    system_prompt = _build_system_prompt(max_confidence)
    user_prompt   = _build_user_prompt(message, evidence)

    raw = await _call_llm(system_prompt, user_prompt)
    if raw is None:
        return _error("LLM call failed — no response returned")

    return _structure_output(raw, max_confidence)


# ---------------------------------------------------------------------------
# Evidence extraction
# ---------------------------------------------------------------------------

_TRACEBACK_PAT = re.compile(
    r"(Traceback \(most recent call last\).*?(?=\n\n|\Z)|"
    r"Error: .+|Exception: .+|TypeError: .+|ValueError: .+|"
    r"AttributeError: .+|KeyError: .+|ImportError: .+)",
    re.DOTALL | re.MULTILINE,
)
_CODE_FENCE_PAT = re.compile(r"```[\w]*\n?(.*?)```", re.DOTALL)


def _search_repair_memory(issue_description: str) -> list[dict]:
    """
    Search repair memory for similar past diagnoses.
    Returns matches with confidence — reference only, never auto-applied.
    """
    try:
        from core.repair_memory.repair_search import search_all_categories
        return search_all_categories(issue_description, top_n=3)
    except Exception as exc:
        log.debug("doctor: repair memory search unavailable — %s", exc)
        return []


def _collect_evidence(message: str, memory: dict, web_results: dict) -> dict[str, str]:
    evidence: dict[str, str] = {}

    # Traceback in message
    tb = _TRACEBACK_PAT.search(message)
    if tb:
        evidence["traceback"] = tb.group()[:2000]

    # Code fence in message
    code = _CODE_FENCE_PAT.search(message)
    if code:
        evidence["code_snippet"] = code.group(1)[:3000]

    # Repair memory (past fix patterns)
    if memory.get("repair_memory"):
        evidence["repair_patterns"] = str(memory["repair_memory"])[:1000]

    # Logs from memory or web (unlikely but possible)
    if memory.get("logs"):
        evidence["logs"] = str(memory["logs"])[:2000]

    # Raw message as fallback context
    evidence["user_description"] = message[:1000]

    return evidence


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_system_prompt(max_confidence: str) -> str:
    return f"""You are a senior debugging engineer. Your job is to diagnose and fix issues.

Confidence ceiling for this request: {max_confidence}
(If evidence is insufficient for full diagnosis, confidence must NOT exceed {max_confidence}.)

RULES:
1. Return ONLY valid JSON — no markdown wrapper, no extra text.
2. root_cause must be specific and traceable to the evidence provided.
3. Do NOT use "unknown", "unclear", "might be", or "possibly" in root_cause
   unless you also set confidence to "low".
4. fix must be actionable — a specific code change, command, or configuration fix.
5. files_updated may be an empty list if the fix is configuration or explanation only.

OUTPUT SCHEMA:
{{
  "type": "repair_output",
  "issue": "<one-line symptom description>",
  "root_cause": "<specific diagnosed root cause>",
  "fix": "<concrete actionable fix>",
  "files_updated": [
    {{
      "path": "<file/path.ext>",
      "description": "<what changed and why>",
      "code": "<fixed code>"
    }}
  ],
  "confidence": "high | medium | low"
}}"""


def _build_user_prompt(message: str, evidence: dict) -> str:
    parts = [f"Debug request: {message}"]

    if evidence.get("traceback"):
        parts.append(f"Error traceback:\n{evidence['traceback']}")
    if evidence.get("code_snippet"):
        parts.append(f"Code with issue:\n{evidence['code_snippet']}")
    if evidence.get("logs"):
        parts.append(f"Relevant logs:\n{evidence['logs']}")
    if evidence.get("repair_patterns"):
        parts.append(f"Similar past fixes:\n{evidence['repair_patterns']}")

    parts.append("Diagnose and return the repair_output JSON now.")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

async def _call_llm(system_prompt: str, user_prompt: str) -> str | None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("doctor: ANTHROPIC_API_KEY not set")
        return None
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model      = _ANTHROPIC_MODEL,
            max_tokens = 4096,
            system     = system_prompt,
            messages   = [{"role": "user", "content": user_prompt}],
        )
        return resp.content[0].text if resp.content else None
    except Exception as exc:
        log.error("doctor: LLM call failed — %s", exc, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Output structuring
# ---------------------------------------------------------------------------

def _structure_output(raw: str, max_confidence: str) -> dict[str, Any]:
    import json

    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("doctor: JSON parse failed — %s", exc)
        return {
            "type":          "repair_output",
            "issue":         "Unable to parse LLM output",
            "root_cause":    "JSON parse error in Doctor module output",
            "fix":           raw[:500],
            "files_updated": [],
            "confidence":    "low",
            "status":        "parse_error",
        }

    data["type"] = "repair_output"
    data.setdefault("issue", "")
    data.setdefault("root_cause", "")
    data.setdefault("fix", "")
    data.setdefault("files_updated", [])

    # Cap confidence at max_confidence
    conf_order = {"high": 2, "medium": 1, "low": 0}
    actual_conf = data.get("confidence", "medium")
    if conf_order.get(actual_conf, 1) > conf_order.get(max_confidence, 1):
        data["confidence"] = max_confidence
        log.debug("doctor: confidence capped from %s → %s", actual_conf, max_confidence)

    log.info(
        "doctor: issue=%r confidence=%s files=%d",
        data["issue"][:60], data["confidence"], len(data["files_updated"]),
    )
    return data


def _error(reason: str) -> dict[str, Any]:
    return {
        "type":          "repair_output",
        "status":        "error",
        "error":         reason,
        "issue":         reason,
        "root_cause":    "Doctor module execution failed",
        "fix":           "Retry with more error context",
        "files_updated": [],
        "confidence":    "low",
    }
