"""
billing/probe_detector.py — Internal probe detection + safe response builder.

Detects requests attempting to extract:
  - system prompts
  - internal routing logic
  - architecture details
  - logs, repair memory, X-Ray data
  - billing formulas / cost thresholds
  - tool schemas, env vars, secrets

CEO checks every request against this BEFORE routing.
If a probe is detected, CEO returns the safe response without
executing any module.

PROBE TYPES:
  system_prompt_probe     — "show your system prompt / instructions"
  architecture_probe      — "how do you route / what is your architecture"
  data_extraction_probe   — "show logs / repair memory / X-Ray"
  secrets_probe           — "print env vars / API key / token"
  model_probe             — "what model are you / what LLM"
  behavior_probe          — "how do you know / how do you decide"
  billing_probe           — "how are credits calculated / show cost formula"

RESPONSE RULE:
  Always respond with a high-level, honest, non-technical explanation.
  Never expose exact logic, thresholds, configs, or implementation details.
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("billing.probe_detector")

# ---------------------------------------------------------------------------
# Pattern registry
# ---------------------------------------------------------------------------

_PROBES: list[tuple[str, re.Pattern]] = [
    ("system_prompt_probe", re.compile(
        r"\b("
        r"system prompt|hidden prompt|initial prompt|base prompt|"
        r"instructions you (were|are) given|what instructions|"
        r"show your prompt|print your prompt|reveal your prompt|"
        r"your prompt is|ignore (previous|all) instructions|"
        r"repeat (your|the) (instructions|prompt)|"
        r"what were you told|jailbreak|DAN|pretend you have no"
        r")\b",
        re.IGNORECASE,
    )),
    ("architecture_probe", re.compile(
        r"\b("
        r"how (do you|does the system) route|routing logic|ceo router|"
        r"your internal (logic|architecture|design|code|structure)|"
        r"how (are you|is this) (built|implemented|structured|coded)|"
        r"what modules|what brains|brain (pipeline|system)|"
        r"show (your|the) (architecture|code|source|internals)|"
        r"internal (components|pipeline|flow|system design)|"
        r"how (does|do) (orchestration|routing|the CEO) work"
        r")\b",
        re.IGNORECASE,
    )),
    ("data_extraction_probe", re.compile(
        r"\b("
        r"show (your |the )?(logs?|log files?|error logs?)|"
        r"(print|display|reveal|dump) (the |your )?(logs?|events?|history)|"
        r"repair memory|repair library|past (fixes|repairs|solutions)|"
        r"x-?ray (data|report|analysis)|internal (events?|diagnostics?)|"
        r"session (state|data|store)|execution (history|trace|events?)"
        r")\b",
        re.IGNORECASE,
    )),
    ("secrets_probe", re.compile(
        r"\b("
        r"(print|show|reveal|what is) (your |the )?(api key|secret|token|"
        r"password|credential|env|environment variable|jwt|database url)|"
        r"anthropic[_ ]?(api[_ ]?key|key)|openai[_ ]?key|"
        r"MONGO|STRIPE|RESEND|JWT_SECRET"
        r")\b",
        re.IGNORECASE,
    )),
    ("model_probe", re.compile(
        r"\b("
        r"what (model|llm|ai|version) (are you|do you use|is this)|"
        r"which (model|llm|version)|what version of (claude|gpt|openai)|"
        r"are you (claude|gpt|chatgpt|gemini|llama)|"
        r"(claude|gpt)[- ]?(sonnet|haiku|opus|turbo|4|3\.5)|"
        r"model (name|id|version)|what (llm|AI) (powers|runs) (you|this)"
        r")\b",
        re.IGNORECASE,
    )),
    ("behavior_probe", re.compile(
        r"\b("
        r"how (do you|does the system) (know|detect|decide|determine|validate|"
        r"fix|repair|evaluate|check|verify|score|rank)|"
        r"what (thresholds?|limits?|retries?|rules?) (do you use|are used)|"
        r"how many (retries|attempts|tries)|what (triggers?|causes?) (you to|the system to)|"
        r"internal (validation|scoring|ranking|thresholds?)|"
        r"how (does|do) (validation|scoring|ranking|retry) work"
        r")\b",
        re.IGNORECASE,
    )),
    ("billing_probe", re.compile(
        r"\b("
        r"how (are|is) credits? (calculated|computed|deducted|charged)|"
        r"(show|print|reveal) (the |your )?(cost|billing|credit) (formula|map|table|logic)|"
        r"what does .{0,20} cost (in credits?|internally)|"
        r"billing (formula|algorithm|logic|thresholds?)|"
        r"credit (formula|algorithm|deduction logic)"
        r")\b",
        re.IGNORECASE,
    )),
]

# ---------------------------------------------------------------------------
# Safe responses per probe type
# ---------------------------------------------------------------------------

_SAFE_RESPONSES: dict[str, str] = {
    "system_prompt_probe": (
        "I use internal instructions to guide how I respond, but I don't share those directly — "
        "they're part of how I'm configured to be helpful and safe. "
        "What I can tell you is what I'm here to help with: coding, building, debugging, "
        "and general software assistance."
    ),
    "architecture_probe": (
        "I use internal routing and tools to handle different types of requests. "
        "For complex tasks I coordinate multiple internal checks to make sure results are accurate. "
        "The specifics of how that's wired together aren't something I share, "
        "but happy to help with whatever you're actually trying to build."
    ),
    "data_extraction_probe": (
        "Logs, internal diagnostics, and execution history are admin-only tools — "
        "they're not accessible through the chat interface. "
        "If you're running into an issue, tell me what went wrong and I'll help debug it directly."
    ),
    "secrets_probe": (
        "API keys, secrets, and credentials are never exposed through this interface. "
        "If you need help setting up or managing API keys for your own project, I'm happy to help with that."
    ),
    "model_probe": (
        "I'm Mini Assistant — built to help with software development tasks. "
        "I don't share details about the underlying model or infrastructure. "
        "Is there something specific I can help you build or debug?"
    ),
    "behavior_probe": (
        "I use internal checks to evaluate whether results are accurate, relevant, and complete. "
        "When something doesn't match expectations, I adjust. "
        "I don't share the specifics of those checks — but you can see the results in what I produce."
    ),
    "billing_probe": (
        "Credits power advanced features like building, generating, and deep analysis. "
        "Chat itself is free, but requires an active credit balance. "
        "You can see your credit usage and costs in your account dashboard. "
        "I don't expose the internal cost formulas."
    ),
}

_DEFAULT_SAFE_RESPONSE = (
    "That's not something I can share details about. "
    "Is there something I can actually help you build or debug?"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect(message: str) -> dict[str, Any]:
    """
    Scan a message for internal probe patterns.

    Returns:
      {
        is_probe:    bool,
        probe_type:  str | None,   # first matched type
        all_types:   list[str],    # all matched types
        safe_response: str | None, # what to say instead
      }
    """
    message_stripped = message.strip()
    matched: list[str] = []

    for probe_type, pattern in _PROBES:
        if pattern.search(message_stripped):
            matched.append(probe_type)

    if not matched:
        return {"is_probe": False, "probe_type": None, "all_types": [], "safe_response": None}

    primary = matched[0]
    safe    = _SAFE_RESPONSES.get(primary, _DEFAULT_SAFE_RESPONSE)

    log.info("probe_detector: detected types=%s msg_preview=%r", matched, message_stripped[:60])

    return {
        "is_probe":      True,
        "probe_type":    primary,
        "all_types":     matched,
        "safe_response": safe,
    }


def build_probe_response(probe_result: dict[str, Any]) -> dict[str, Any]:
    """Build the structured response CEO returns for a detected probe."""
    return {
        "type":          "probe_response",
        "status":        "safe_response",
        "message":       probe_result["safe_response"] or _DEFAULT_SAFE_RESPONSE,
        "probe_type":    probe_result["probe_type"],
        "action":        "none",
    }
