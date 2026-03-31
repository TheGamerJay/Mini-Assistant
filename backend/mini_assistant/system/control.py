"""
Mini Assistant — Backend Control Layer
Intent detection, mode routing, act/ask gating, tool safety, orchestration.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import time

from .telemetry import log_request, log_tool, debug_view, log_event, new_request_id

MODES = ["chat", "build", "image", "edit"]
ACTIVE_MODE = None

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(mode: str) -> str:
    path = PROMPTS_DIR / f"{mode}_mode.txt"
    if path.exists():
        return path.read_text()
    core = PROMPTS_DIR / "core.txt"
    return core.read_text() if core.exists() else ""


# ─── INTENT DETECTION ────────────────────────────────────────

@dataclass
class IntentResult:
    intent: str
    confidence: float
    matched_signals: list[str]
    ambiguous: bool = False
    multiple: list[str] = field(default_factory=list)


INTENT_SIGNALS = {
    "chat":    ["explain", "what is", "how does", "tell me", "why", "discuss",
                "summarize", "help me understand", "can you", "what are"],
    "build":   ["create", "build", "write", "scaffold", "design", "make",
                "generate code", "set up", "implement", "add feature", "new"],
    "image":   ["generate image", "create image", "draw", "visualize",
                "show me", "make an image", "image of", "picture of"],
    "edit":    ["edit", "fix", "modify", "update", "change", "refactor",
                "improve", "adjust", "rename", "replace", "rewrite"],
    "search":  ["search", "find", "look up", "latest", "current", "check"],
    "analyze": ["analyze", "review", "compare", "evaluate", "audit", "assess"],
    "execute": ["run", "execute", "deploy", "start", "launch", "trigger"],
    "delete":  ["delete", "remove", "drop", "destroy", "wipe", "reset"],
}

CONFIDENCE_THRESHOLDS = {
    "act": 0.70,
    "ask": 0.40,
}


def detect_intent(message: str) -> IntentResult:
    msg = message.lower()
    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}

    for intent, signals in INTENT_SIGNALS.items():
        hits = [s for s in signals if s in msg]
        if hits:
            score = min(sum(len(s.split()) * 0.15 for s in hits), 1.0)
            scores[intent] = score
            matched[intent] = hits

    if not scores:
        return IntentResult(intent="ambiguous", confidence=0.0,
                            matched_signals=[], ambiguous=True)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_intent, top_score = ranked[0]

    multi = [i for i, s in ranked if s >= CONFIDENCE_THRESHOLDS["ask"]]
    if len(multi) >= 2 and (ranked[0][1] - ranked[1][1]) < 0.20:
        return IntentResult(
            intent="ambiguous",
            confidence=top_score,
            matched_signals=matched.get(top_intent, []),
            ambiguous=True,
            multiple=multi[:3],
        )

    return IntentResult(
        intent=top_intent,
        confidence=top_score,
        matched_signals=matched.get(top_intent, []),
        ambiguous=top_score < CONFIDENCE_THRESHOLDS["ask"],
    )


# ─── CONTEXT EXTRACTION ──────────────────────────────────────

CONTEXT_PATTERNS = {
    "language":    r"\b(python|javascript|typescript|go|rust|java|c\+\+|ruby|swift)\b",
    "framework":   r"\b(react|vue|angular|flask|fastapi|django|express|nextjs|rails)\b",
    "target":      r"\bfor\s+([\w\s]+?)(?:\.|,|$)",
    "subject":     r"\b(?:the|a|an)\s+([\w\s]{2,30}?)(?:\s+(?:that|which|to|for|in|with))",
    "destructive": r"\b(delete|drop|remove|destroy|wipe|reset|overwrite|truncate)\b",
    "scope":       r"\b(all|every|entire|whole|everything|completely)\b",
}


def extract_context(message: str) -> dict:
    ctx: dict = {"missing_critical_info": False, "is_destructive": False}
    msg_lower = message.lower()

    for key, pattern in CONTEXT_PATTERNS.items():
        match = re.search(pattern, msg_lower)
        if match:
            ctx[key] = match.group(1).strip() if match.lastindex else True

    if ctx.get("destructive") and ctx.get("scope"):
        ctx["is_destructive"] = True
        ctx["risk_level"] = "high"
    elif ctx.get("destructive"):
        ctx["is_destructive"] = True
        ctx["risk_level"] = "medium"

    return ctx


# ─── MULTI-INTENT HANDLING ────────────────────────────────────

def handle_multi_intent(result: IntentResult) -> dict:
    options = " | ".join(result.multiple)
    return {
        "action": "ask",
        "reason": "multi_intent",
        "question": f"I detected multiple things you might want: {options}. Which should I focus on first?",
    }


# ─── ACT vs ASK GATE ─────────────────────────────────────────

HIGH_COST_INTENTS = {"image", "build", "execute"}
HIGH_COST_TOKEN_THRESHOLD = 3000


def should_act(intent_result: IntentResult, context: dict, token_estimate: int = 0) -> tuple[bool, str]:
    intent = intent_result.intent

    if intent_result.ambiguous:
        return False, "ambiguous_intent"

    if intent_result.confidence < CONFIDENCE_THRESHOLDS["act"]:
        return False, f"low_confidence ({intent_result.confidence:.2f})"

    if context.get("is_destructive"):
        risk = context.get("risk_level", "medium")
        if risk == "high":
            return False, "destructive_high_risk"
        if risk == "medium" and not context.get("user_confirmed"):
            return False, "destructive_needs_confirmation"

    if intent in HIGH_COST_INTENTS and not context.get("user_confirmed"):
        if token_estimate > HIGH_COST_TOKEN_THRESHOLD:
            return False, "high_cost_unconfirmed"

    if context.get("missing_critical_info"):
        return False, f"missing: {context.get('missing_field', 'required info')}"

    return True, "ok"


# ─── MODE ROUTING ────────────────────────────────────────────

def route_to_mode(intent: str) -> str | None:
    routing = {
        "chat":    "chat",
        "build":   "build",
        "image":   "image",
        "edit":    "edit",
        "search":  "chat",
        "analyze": "chat",
    }
    return routing.get(intent)


# ─── TOOL SAFETY ─────────────────────────────────────────────

TOOL_SCHEMAS = {
    "web_search":     {"required": ["query"],          "types": {"query": str}},
    "code_runner":    {"required": ["code", "language"], "types": {"code": str, "language": str}},
    "file_write":     {"required": ["path", "content"], "types": {"path": str, "content": str}},
    "file_read":      {"required": ["path"],            "types": {"path": str}},
    "image_generate": {"required": ["prompt", "canvas"], "types": {"prompt": str, "canvas": str}},
}

TOOL_TIMEOUTS_MS = {
    "web_search":     8_000,
    "code_runner":   15_000,
    "file_write":     3_000,
    "file_read":      3_000,
    "image_generate": 30_000,
}


def get_tools_for_mode(mode: str) -> list[str]:
    tool_map = {
        "chat":  ["web_search"],
        "build": ["code_runner", "file_write", "web_search"],
        "image": ["image_generate"],
        "edit":  ["file_read", "file_write", "code_runner"],
    }
    return tool_map.get(mode, [])


def validate_tool_call(tool: str, params: dict, mode: str) -> tuple[bool, str]:
    if tool not in get_tools_for_mode(mode):
        return False, f"tool '{tool}' not permitted in {mode} mode"

    schema = TOOL_SCHEMAS.get(tool)
    if not schema:
        return False, f"unknown tool '{tool}'"

    for f in schema["required"]:
        if f not in params or params[f] is None:
            return False, f"missing required param '{f}' for {tool}"
        expected_type = schema["types"].get(f)
        if expected_type and not isinstance(params[f], expected_type):
            return False, f"param '{f}' must be {expected_type.__name__}"

    return True, "ok"


def call_tool_with_timeout(tool: str, params: dict, timeout_ms: int):
    """Stub — replace with real tool dispatcher."""
    raise NotImplementedError(f"Dispatcher not wired for tool: {tool}")


def handle_failure(tool: str, result: dict) -> dict:
    return {
        "ok": False,
        "failed_tool": tool,
        "reason": result.get("error", "unknown"),
        "next_step": "surface_to_user",
    }


def execute_tool(tool: str, params: dict, mode: str) -> dict:
    valid, reason = validate_tool_call(tool, params, mode)
    if not valid:
        return {"ok": False, "error": reason, "action": "abort"}

    timeout = TOOL_TIMEOUTS_MS.get(tool, 10_000)
    t_tool = time.perf_counter()

    try:
        result = call_tool_with_timeout(tool, params, timeout_ms=timeout)
    except TimeoutError:
        log_tool(tool=tool, success=False, reason=f"timed out after {timeout}ms", timed_out=True, start=t_tool)
        return handle_failure(tool, {"error": f"timed out after {timeout}ms"})
    except Exception as e:
        log_tool(tool=tool, success=False, reason=str(e), start=t_tool)
        return handle_failure(tool, {"error": str(e)})

    if not result or result.get("error"):
        log_tool(tool=tool, success=False, reason=result.get("error", "empty result") if result else "empty result", start=t_tool)
        return handle_failure(tool, result or {})

    log_tool(tool=tool, success=True, start=t_tool)
    return {"ok": True, "result": result}


# ─── MODE ISOLATION ──────────────────────────────────────────

def set_mode(mode: str) -> dict:
    global ACTIVE_MODE
    if mode not in MODES:
        raise ValueError(f"Invalid mode: {mode}")
    ACTIVE_MODE = mode
    return {
        "active_mode": mode,
        "system_prompt": load_prompt(mode),
        "tools_allowed": get_tools_for_mode(mode),
    }


# ─── COST CONTROL ────────────────────────────────────────────

def cost_check(intent: str, token_estimate: int, prior_calls: int) -> bool:
    if intent == "image" and prior_calls >= 1:
        return False
    if token_estimate > 4000 and intent == "chat":
        return False
    return True


# ─── MAIN ORCHESTRATOR ───────────────────────────────────────

ASK_PROMPTS = {
    "destructive_high_risk":         "This will affect everything — are you sure? Please confirm.",
    "destructive_needs_confirmation": "This is a destructive action. Confirm before I proceed.",
    "ambiguous_intent":               "I'm not sure what you'd like me to do — can you clarify?",
    "high_cost_unconfirmed":          "This will use significant resources. Confirm to proceed.",
}


def handle_request(user_message: str, user: dict, token_estimate: int = 0) -> dict:
    t_start = time.perf_counter()
    rid = new_request_id()
    intent_result = detect_intent(user_message)
    context = extract_context(user_message)

    if intent_result.multiple:
        log_event("request", {"detected_intent": "multi", "multiple": intent_result.multiple,
                               "act": False, "act_reason": "multi_intent",
                               "duration_ms": round((time.perf_counter() - t_start) * 1000)})
        return handle_multi_intent(intent_result)

    if intent_result.ambiguous:
        log_request(detected_intent="ambiguous", confidence=intent_result.confidence,
                    mode_selected=None, multi_intent=False, context_summary=context,
                    act_decision=False, act_reason="ambiguous_intent", start=t_start)
        return {"action": "ask", "reason": "ambiguous_intent",
                "question": ASK_PROMPTS["ambiguous_intent"]}

    mode = route_to_mode(intent_result.intent)
    if not mode:
        log_request(detected_intent=intent_result.intent, confidence=intent_result.confidence,
                    mode_selected=None, multi_intent=False, context_summary=context,
                    act_decision=False, act_reason="no_route", start=t_start)
        return {"action": "ask", "question": "Can you clarify what you'd like me to do?"}

    act, reason = should_act(intent_result, context, token_estimate)

    log_request(detected_intent=intent_result.intent, confidence=intent_result.confidence,
                mode_selected=mode, multi_intent=bool(intent_result.multiple),
                context_summary=context, act_decision=act, act_reason=reason, start=t_start)

    if not act:
        question = ASK_PROMPTS.get(reason, f"I need more info before proceeding ({reason}).")
        if "low_confidence" in reason:
            question = f"I think you want [{intent_result.intent}] but I'm not certain — is that right?"
        return {"action": "ask", "reason": reason, "question": question}

    session = set_mode(mode)

    response = {
        "action":        "execute",
        "request_id":    rid,
        "mode":          mode,
        "intent":        intent_result.intent,
        "confidence":    intent_result.confidence,
        "system_prompt": session["system_prompt"],
        "tools":         session["tools_allowed"],
        "context":       context,
        "watermark":     (user.get("plan", "free") == "free") if mode == "image" else False,
    }

    dbg = debug_view(intent_result=intent_result, context=context,
                     act_decision=act, act_reason=reason)
    if dbg:
        response["_debug"] = dbg["debug"]

    return response