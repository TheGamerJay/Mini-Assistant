"""
modules/builder.py — Builder module.

Handles backend, frontend, and full-system builds.
Returns structured build_output — never plain text.

Flow:
  1. Classify task (backend / frontend / full_system)
  2. Decompose into components
  3. Generate files with real code
  4. Return structured output

Output format:
  {
      "type":       "build_output",
      "category":   "backend" | "frontend" | "full_system",
      "summary":    str,
      "components": [...],
      "files":      [ {"path": str, "type": str, "description": str, "code": str} ],
      "notes":      [...],
      "confidence": "high" | "medium" | "low",
  }

Rules:
- must return structured output — plain text is a validation failure
- components must be listed explicitly for full_system
- files must have real code (not pseudo-code)
- paths must be realistic
- no missing dependencies
- modules NEVER call each other — Builder does not call Doctor or Vision
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("ceo_router.modules.builder")

_ANTHROPIC_MODEL = "claude-opus-4-6"


async def execute(
    decision:    dict[str, Any],
    memory:      dict[str, Any],
    web_results: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a system based on the CEO decision.

    For multi_step and full_system complexity, delegates to the CEO Orchestrator
    which manages the multi-brain loop (Builder → Hands → Vision → Doctor).

    For simple tasks, uses a single LLM call and returns structured build_output.
    """
    message    = decision.get("message", "")
    complexity = decision.get("complexity", "simple")

    # ── Multi-brain orchestration for complex tasks ────────────────────────────
    if complexity in ("multi_step", "full_system"):
        session_id = decision.get("session_id")
        if session_id:
            try:
                from core.orchestration.ceo_orchestrator import execute_builder_task
                log.info("builder: delegating to CEO orchestrator session=%s", session_id)
                return await execute_builder_task(session_id, decision, memory, web_results)
            except Exception as exc:
                log.error("builder: orchestrator failed, falling back to direct — %s", exc, exc_info=True)
        # No session_id or orchestrator failed — fall through to direct build

    # ── Step 1: Classify task ──────────────────────────────────────────────────
    category = _classify_task(message, complexity)
    log.info("builder: category=%s complexity=%s", category, complexity)

    # ── Step 2: Decompose into components ─────────────────────────────────────
    components = _decompose(message, category, complexity)

    # ── Step 3: Build via LLM ─────────────────────────────────────────────────
    system_prompt = _build_system_prompt(category, components, memory)
    user_prompt   = _build_user_prompt(message, category, components, memory, web_results)

    raw = await _call_llm(system_prompt, user_prompt)

    if raw is None:
        return _error("LLM call failed — no response returned")

    # ── Step 4: Parse and structure output ────────────────────────────────────
    return _structure_output(raw, category, components, message)


# ---------------------------------------------------------------------------
# Task classification (Phase 32)
# ---------------------------------------------------------------------------

import re as _re

_BACKEND_KW = _re.compile(
    r"\b(api|endpoint|route|server|backend|database|schema|auth|jwt|"
    r"middleware|service|model|migration|sql|crud|rest|graphql|"
    r"business logic|lambda|function|microservice)\b",
    _re.IGNORECASE,
)
_FRONTEND_KW = _re.compile(
    r"\b(ui|component|page|view|react|vue|angular|tailwind|css|html|"
    r"button|form|input|modal|sidebar|navbar|dashboard|table|chart|"
    r"frontend|client.?side|spa|next\.?js|responsive|layout)\b",
    _re.IGNORECASE,
)


def _classify_task(message: str, complexity: str) -> str:
    if complexity == "full_system":
        return "full_system"
    backend_score  = len(_BACKEND_KW.findall(message))
    frontend_score = len(_FRONTEND_KW.findall(message))
    if backend_score > 0 and frontend_score > 0:
        return "full_system"
    if backend_score >= frontend_score:
        return "backend"
    return "frontend"


# ---------------------------------------------------------------------------
# Decomposition (Phase 33)
# ---------------------------------------------------------------------------

_COMPONENT_TEMPLATES: dict[str, list[str]] = {
    "backend": [
        "API endpoint definitions",
        "Request/response schema",
        "Business logic layer",
        "Data model / database schema",
        "Error handling",
    ],
    "frontend": [
        "Component structure",
        "State management",
        "UI layout",
        "User interactions / event handlers",
        "Styling",
    ],
    "full_system": [
        "Database schema",
        "API endpoints",
        "Business logic",
        "Authentication / authorization",
        "Frontend components",
        "State management",
        "Data flow between layers",
        "Error handling",
    ],
}

# Feature-specific component additions
_FEATURE_COMPONENTS: list[tuple[_re.Pattern, list[str]]] = [
    (_re.compile(r"\bleaderboard\b", _re.IGNORECASE),
     ["Scoring logic", "Sorting / ranking", "Pagination", "Caching layer"]),
    (_re.compile(r"\b(login|auth|sign.?in|sign.?up)\b", _re.IGNORECASE),
     ["Session management", "Token handling (JWT)", "Password hashing"]),
    (_re.compile(r"\b(upload|file upload|image upload)\b", _re.IGNORECASE),
     ["File validation", "Storage integration", "Upload progress handling"]),
    (_re.compile(r"\b(real.?time|websocket|live update)\b", _re.IGNORECASE),
     ["WebSocket connection", "Event broadcasting", "Reconnection logic"]),
    (_re.compile(r"\b(search|filter|sort)\b", _re.IGNORECASE),
     ["Search query logic", "Filter/sort parameters", "Index optimization"]),
]


def _decompose(message: str, category: str, complexity: str) -> list[str]:
    """Return ordered component list for the task."""
    base = list(_COMPONENT_TEMPLATES.get(category, _COMPONENT_TEMPLATES["backend"]))
    for pattern, extras in _FEATURE_COMPONENTS:
        if pattern.search(message):
            for extra in extras:
                if extra not in base:
                    base.append(extra)
    return base


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_system_prompt(category: str, components: list[str], memory: dict) -> str:
    project_ctx = memory.get("project_context", {})
    stack_hint  = ""
    if project_ctx:
        stack_hint = f"\nProject context: {project_ctx}"

    return f"""You are a senior software engineer generating a structured build output.

Category: {category}
Components to address: {', '.join(components)}{stack_hint}

RULES:
1. Return ONLY valid JSON matching the build_output schema below — no markdown wrapper, no extra text.
2. All code must be real and runnable — no pseudo-code, no placeholders.
3. File paths must be realistic for the chosen stack.
4. Every component in the list must appear in at least one file.
5. No broken imports or missing dependencies.

OUTPUT SCHEMA:
{{
  "type": "build_output",
  "category": "{category}",
  "summary": "<one sentence describing what was built>",
  "components": ["<component1>", ...],
  "files": [
    {{
      "path": "<realistic/file/path.ext>",
      "type": "backend | frontend | config",
      "description": "<what this file does>",
      "code": "<full working code>"
    }}
  ],
  "notes": ["<dependency note or usage instruction>", ...],
  "confidence": "high | medium | low"
}}"""


def _build_user_prompt(
    message:     str,
    category:    str,
    components:  list[str],
    memory:      dict,
    web_results: dict,
) -> str:
    parts = [f"Build request: {message}"]

    if memory.get("project_context"):
        parts.append(f"Existing project context: {memory['project_context']}")

    if memory.get("prior_code"):
        parts.append(f"Prior code to build on:\n{memory['prior_code']}")

    if web_results.get("ok") and web_results.get("results"):
        snippets = web_results["results"][:2]
        refs = "\n".join(f"- {r.get('title','')}: {r.get('snippet','')}" for r in snippets)
        parts.append(f"Relevant web context:\n{refs}")

    parts.append(f"Required components: {', '.join(components)}")
    parts.append("Return the JSON build_output now.")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

async def _call_llm(system_prompt: str, user_prompt: str) -> str | None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("builder: ANTHROPIC_API_KEY not set")
        return None
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model      = _ANTHROPIC_MODEL,
            max_tokens = 8192,
            system     = system_prompt,
            messages   = [{"role": "user", "content": user_prompt}],
        )
        return resp.content[0].text if resp.content else None
    except Exception as exc:
        log.error("builder: LLM call failed — %s", exc, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Output structuring (Phase 34)
# ---------------------------------------------------------------------------

def _structure_output(
    raw:        str,
    category:   str,
    components: list[str],
    message:    str,
) -> dict[str, Any]:
    """Parse LLM JSON output and enforce build_output structure."""
    import json

    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("builder: JSON parse failed — %s", exc)
        # Return a degraded but structured output rather than plain text
        return {
            "type":       "build_output",
            "category":   category,
            "summary":    f"Build output for: {message[:100]}",
            "components": components,
            "files":      [],
            "notes":      ["JSON parse error — raw output could not be structured", raw[:500]],
            "confidence": "low",
            "status":     "parse_error",
        }

    # Enforce required fields
    data["type"]       = "build_output"
    data["category"]   = data.get("category", category)
    data["components"] = data.get("components", components)
    data["files"]      = data.get("files", [])
    data["notes"]      = data.get("notes", [])
    data["confidence"] = data.get("confidence", "medium")
    data.setdefault("summary", f"Build output for: {message[:100]}")

    # Validate files have required fields (Phase 34 rules)
    cleaned_files = []
    for f in data["files"]:
        if not isinstance(f, dict):
            continue
        if not f.get("path") or not f.get("code"):
            continue
        f.setdefault("type", "backend")
        f.setdefault("description", f.get("path", ""))
        cleaned_files.append(f)
    data["files"] = cleaned_files

    log.info(
        "builder: built category=%s files=%d components=%d confidence=%s",
        data["category"], len(data["files"]), len(data["components"]), data["confidence"],
    )
    return data


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------

def _error(reason: str) -> dict[str, Any]:
    return {
        "type":       "build_output",
        "status":     "error",
        "error":      reason,
        "category":   "unknown",
        "summary":    reason,
        "components": [],
        "files":      [],
        "notes":      [],
        "confidence": "low",
    }
