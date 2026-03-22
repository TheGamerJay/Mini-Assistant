"""
intent_planner.py — Phase 1 Blueprint Planner Brain
────────────────────────────────────────────────────
The Planner is the MANDATORY first step for every user request.
No specialist brain or tool should execute before the Planner produces a plan.

Responsibilities:
  1. Accept the user message + optional ParsedCommand
  2. Detect the primary intent (one of 11 blueprint intents)
  3. Build an ordered task list (sequential_tasks) and optional parallel list
  4. Select the appropriate response_mode
  5. Emit warnings for known risks

This implementation is purely keyword-based — no LLM calls.
Fast (~1 ms), always available, deterministic.

The LLM-based planner (mini_assistant/planner.py) handles deeper
multi-step planning for complex requests and is called by the Supervisor
in Phase 4+.  Phase 1 focuses on intent routing.

Blueprint intents:
  normal_chat           — general conversation
  web_search            — look up current information
  image_generate        — create an image via ComfyUI
  image_analysis        — analyze an attached image / screenshot
  code_runner           — write, explain, refactor code
  debugging             — fix errors, bugs, broken routes
  planning              — break a goal into ordered steps
  file_analysis         — inspect project files / structure
  app_builder           — build a full web app
  3d_asset_generation   — generate a 3D prop / object
  3d_character_generation — generate a 3D character / rig
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

from .command_parser import ParsedCommand


# ── Intent constants ─────────────────────────────────────────────────────────

INTENTS = [
    "normal_chat",
    "web_search",
    "image_generate",
    "image_analysis",
    "image_reference_generate",   # analyze reference image → generate new via DALL-E
    "code_runner",
    "debugging",
    "planning",
    "file_analysis",
    "app_builder",
    "3d_asset_generation",
    "3d_character_generation",
]

# Map each intent to the image_system execution intent it translates to.
# This lets the existing image_system router remain the execution layer.
INTENT_TO_EXECUTION: dict[str, str] = {
    "normal_chat":              "chat",
    "web_search":               "chat",                    # handled via search tool
    "image_generate":           "image_generation",
    "image_analysis":           "image_analysis",
    "image_reference_generate": "image_reference_generate",# GPT-4o analyze → DALL-E generate
    "code_runner":              "coding",
    "debugging":                "coding",
    "planning":                 "chat",                    # research brain in chat mode
    "file_analysis":            "chat",                    # scanner + research brain
    "app_builder":              "chat",                    # App Builder UI handles this
    "3d_asset_generation":      "chat",                    # Phase 9 — not yet implemented
    "3d_character_generation":  "chat",                    # Phase 9 — not yet implemented
}

# Response mode per intent
_RESPONSE_MODES: dict[str, str] = {
    "normal_chat":              "chat",
    "web_search":               "research",
    "image_generate":           "builder",
    "image_analysis":           "debug",
    "image_reference_generate": "builder",
    "code_runner":              "builder",
    "debugging":                "debug",
    "planning":                 "architect",
    "file_analysis":            "architect",
    "app_builder":              "builder",
    "3d_asset_generation":      "builder",
    "3d_character_generation":  "builder",
}


# ── Output type ───────────────────────────────────────────────────────────────

@dataclass
class PlannerOutput:
    """Structured plan produced by the Planner Brain."""
    intent: str
    confidence: float
    response_mode: str
    sequential_tasks: list = field(default_factory=list)
    parallel_tasks:   list = field(default_factory=list)
    dependencies:     list = field(default_factory=list)
    files_targeted:   list = field(default_factory=list)
    warnings:         list = field(default_factory=list)
    routing_method:   str  = "keyword"
    planner_ms:       float = 0.0
    slash_command:    Optional[str] = None
    execution_intent: str  = "chat"   # mapped image_system intent

    def to_dict(self) -> dict:
        return {
            "intent":           self.intent,
            "confidence":       self.confidence,
            "response_mode":    self.response_mode,
            "sequential_tasks": self.sequential_tasks,
            "parallel_tasks":   self.parallel_tasks,
            "dependencies":     self.dependencies,
            "files_targeted":   self.files_targeted,
            "warnings":         self.warnings,
            "routing_method":   self.routing_method,
            "planner_ms":       self.planner_ms,
            "slash_command":    self.slash_command,
            "execution_intent": self.execution_intent,
        }


# ── Intent detectors (keyword patterns, priority-ordered) ─────────────────────

# 3D character (highest priority — very specific)
_3D_CHAR = re.compile(
    r"\b(3d|three[- ]?d|three[ -]?dimensional)\b.{0,50}"
    r"\b(character|hero|avatar|player|enemy|npc|humanoid|figure|warrior|rogue|mage|boss)\b",
    re.IGNORECASE,
)
_3D_ASSET = re.compile(
    r"\b(3d|three[- ]?d)\b.{0,50}"
    r"\b(asset|mesh|object|prop|item|weapon|vehicle|building|environment|dungeon)\b",
    re.IGNORECASE,
)

# Image analysis — must precede image_generate to catch "analyze this image"
_IMG_ANALYSIS = re.compile(
    r"("
    r"\b(analyze|analyse|describe|explain|read|ocr|detect|identify|look at)\b.{0,50}"
    r"\b(image|picture|photo|screenshot|attachment|attached|this)\b"
    r"|"
    r"\bwhat('s| is) (in|on|this)\b.{0,30}\b(image|photo|picture|screenshot)\b"
    r")",
    re.IGNORECASE,
)

# Debugging — catch before code_runner to prioritise fix intent
_DEBUGGING = re.compile(
    r"\b("
    r"debug|fix|error|bug|traceback|exception|not working|broken|fails|failing|"
    r"crash|undefined|null pointer|NullPointer|TypeError|ValueError|SyntaxError|"
    r"ImportError|ModuleNotFoundError|AttributeError|KeyError|IndexError|"
    r"404|500|503|cors|cors error|connection refused|can.?t connect|"
    r"why (is|does|doesn.?t|won.?t)|doesn.?t work|isn.?t working"
    r")\b",
    re.IGNORECASE,
)

# Image generation
_IMG_GEN = re.compile(
    r"\b(generate|create|draw|make|paint|render|produce|design|sketch|illustrate)\b"
    r".{0,50}"
    r"\b(image|picture|photo|artwork|art|illustration|logo|icon|wallpaper|poster|"
    r"banner|thumbnail|hero image|splash|background|portrait|landscape|concept art)\b",
    re.IGNORECASE,
)

# App builder — catch before code_runner (building an app > writing a function)
_APP_BUILDER = re.compile(
    r"\b(build|generate|create|make|scaffold|bootstrap)\b.{0,50}"
    r"\b(app|website|web app|web application|landing page|dashboard|tool|"
    r"form|portfolio|store|shop|game|saas|crud|admin panel|blog|e.?commerce)\b",
    re.IGNORECASE,
)

# Code — write / explain / refactor
_CODE = re.compile(
    r"\b("
    r"write|create|implement|code|program|function|class|script|algorithm|"
    r"refactor|optimise|optimize|explain (this )?code|how does (this|the) (code|function)|"
    r"walk me through|snippet|component|hook|endpoint|route|api|regex|query|"
    r"sql|python|javascript|typescript|react|flask|fastapi|django|node"
    r")\b",
    re.IGNORECASE,
)

# Web search
_SEARCH = re.compile(
    r"\b("
    r"search|look up|look up|find online|google|bing|latest|current news|"
    r"today.?s|right now|as of|recent|up to date|what.?s the|"
    r"stock price|weather|currency|exchange rate|news about|"
    r"who is|when did|how many|what year"
    r")\b",
    re.IGNORECASE,
)

# File / project analysis
_FILES = re.compile(
    r"\b("
    r"files?|project files?|codebase|file structure|directory|folder|"
    r"what files?|which files?|show me the|list files?|"
    r"project context|context scan|scanner|what.?s in the project|"
    r"read the file|open the file|inspect|explore"
    r")\b",
    re.IGNORECASE,
)

# Planning / architecture
_PLANNING = re.compile(
    r"\b("
    r"plan|roadmap|steps|how should I|strategy|approach|breakdown|"
    r"architecture|design|blueprint|phases?|milestones?|spec|"
    r"how do I (build|create|implement|design|approach)|"
    r"what.?s the best way|where do I start"
    r")\b",
    re.IGNORECASE,
)


def _detect_intent(message: str) -> tuple[str, float]:
    """
    Detect primary intent from message text.

    Returns:
        (intent, confidence)
    """
    # Priority order matches duplicate-check risk — more specific first
    checks = [
        (_3D_CHAR,     "3d_character_generation", 0.93),
        (_3D_ASSET,    "3d_asset_generation",     0.90),
        (_IMG_ANALYSIS,"image_analysis",           0.91),
        (_DEBUGGING,   "debugging",                0.92),
        (_IMG_GEN,     "image_generate",           0.88),
        (_APP_BUILDER, "app_builder",              0.85),
        (_CODE,        "code_runner",              0.82),
        (_SEARCH,      "web_search",               0.84),
        (_FILES,       "file_analysis",            0.78),
        (_PLANNING,    "planning",                 0.78),
    ]
    for pattern, intent, conf in checks:
        if pattern.search(message):
            return intent, conf

    # Short message → confident it's chat
    if len(message.strip()) < 60:
        return "normal_chat", 0.85

    return "normal_chat", 0.70


# ── Task builder ──────────────────────────────────────────────────────────────

def _build_tasks(intent: str) -> tuple[list, list]:
    """
    Build sequential_tasks and parallel_tasks for the given intent.

    Returns:
        (sequential_tasks, parallel_tasks)
        Each task is a dict: {id, task, brain|tool, depends_on}
    """
    seq: list[dict] = []
    par: list[dict] = []

    if intent == "image_generate":
        seq = [
            {"id": "t1", "task": "validate_and_enhance_prompt", "brain": "fast",      "depends_on": []},
            {"id": "t2", "task": "route_to_comfyui_workflow",   "brain": "image_gen", "depends_on": ["t1"]},
            {"id": "t3", "task": "quality_review",              "brain": "critic",    "depends_on": ["t2"]},
        ]

    elif intent == "image_analysis":
        seq = [
            {"id": "t1", "task": "analyse_image_with_vision",   "brain": "vision",    "depends_on": []},
            {"id": "t2", "task": "format_answer",               "brain": "fast",      "depends_on": ["t1"]},
        ]

    elif intent == "image_reference_generate":
        seq = [
            {"id": "t1", "task": "analyse_reference_image",     "brain": "vision",    "depends_on": []},
            {"id": "t2", "task": "build_dalle_prompt",          "brain": "fast",      "depends_on": ["t1"]},
            {"id": "t3", "task": "generate_image_with_dalle",   "brain": "image_gen", "depends_on": ["t2"]},
            {"id": "t4", "task": "quality_review",              "brain": "critic",    "depends_on": ["t3"]},
        ]

    elif intent == "debugging":
        seq = [
            {"id": "t1", "task": "identify_error_type",         "brain": "coding",    "depends_on": []},
            {"id": "t2", "task": "locate_root_cause",           "brain": "coding",    "depends_on": ["t1"]},
            {"id": "t3", "task": "propose_minimal_fix",         "brain": "coding",    "depends_on": ["t2"]},
            {"id": "t4", "task": "critic_validate_fix",         "brain": "critic",    "depends_on": ["t3"]},
        ]
        # identify_error + scan_for_similar_errors run in parallel first
        par = [
            {"id": "p1", "task": "identify_error_type",         "brain": "coding",    "depends_on": []},
            {"id": "p2", "task": "scan_reflection_log",         "tool": "scanner",    "depends_on": []},
        ]

    elif intent == "code_runner":
        seq = [
            {"id": "t1", "task": "understand_coding_request",   "brain": "coding",    "depends_on": []},
            {"id": "t2", "task": "write_code",                  "brain": "coding",    "depends_on": ["t1"]},
            {"id": "t3", "task": "critic_check_code",           "brain": "critic",    "depends_on": ["t2"]},
        ]

    elif intent == "app_builder":
        seq = [
            {"id": "t1", "task": "gather_requirements",         "brain": "research",  "depends_on": []},
            {"id": "t2", "task": "plan_app_structure",          "brain": "research",  "depends_on": ["t1"]},
            {"id": "t3", "task": "generate_app_files",          "brain": "coding",    "depends_on": ["t2"]},
            {"id": "t4", "task": "critic_validate_output",      "brain": "critic",    "depends_on": ["t3"]},
        ]
        # t2 + scanner can run concurrently after t1 (parallel wave)
        par = [
            {"id": "p1", "task": "plan_app_structure",          "brain": "research",  "depends_on": []},
            {"id": "p2", "task": "scan_project_context",        "tool": "scanner",    "depends_on": []},
        ]

    elif intent == "web_search":
        seq = [
            {"id": "t1", "task": "execute_web_search",          "tool": "search",     "depends_on": []},
            {"id": "t2", "task": "synthesise_results",          "brain": "research",  "depends_on": ["t1"]},
        ]

    elif intent == "planning":
        seq = [
            {"id": "t1", "task": "analyse_goal",                "brain": "research",  "depends_on": []},
            {"id": "t2", "task": "break_into_subtasks",         "brain": "research",  "depends_on": ["t1"]},
            {"id": "t3", "task": "format_plan_response",        "brain": "fast",      "depends_on": ["t2"]},
        ]

    elif intent == "file_analysis":
        seq = [
            {"id": "t1", "task": "run_project_context_scanner", "tool": "scanner",    "depends_on": []},
            {"id": "t2", "task": "answer_file_question",        "brain": "research",  "depends_on": ["t1"]},
        ]

    elif intent in ("3d_character_generation", "3d_asset_generation"):
        seq = [
            {"id": "t1", "task": "concept_design",              "brain": "research",  "depends_on": []},
            {"id": "t2", "task": "3d_generation",               "brain": "3d_gen",    "depends_on": ["t1"]},
            {"id": "t3", "task": "mesh_cleanup",                "brain": "3d_cleanup","depends_on": ["t2"]},
            {"id": "t4", "task": "validate_asset",              "brain": "critic",    "depends_on": ["t3"]},
        ]
        # concept_design + ref_image_search run in parallel
        par = [
            {"id": "p1", "task": "concept_design",              "brain": "research",  "depends_on": []},
            {"id": "p2", "task": "reference_image_search",      "tool": "search",     "depends_on": []},
        ]

    else:  # normal_chat
        seq = [
            {"id": "t1", "task": "respond_to_message",          "brain": "fast",      "depends_on": []},
        ]

    return seq, par


# ── Warnings ──────────────────────────────────────────────────────────────────

def _build_warnings(intent: str, message: str, is_slash: bool) -> list[str]:
    warnings: list[str] = []

    if intent in ("3d_character_generation", "3d_asset_generation"):
        warnings.append(
            "3D pipeline (Phase 9) is not yet implemented. "
            "Returning a planning response for now."
        )

    if intent == "image_generate" and len(message.strip()) < 10:
        warnings.append("Image prompt is very short — consider adding style, mood, and detail.")

    if intent == "debugging" and not any(
        kw in message.lower() for kw in ["error", "bug", "fix", "not working", "broken", "crash"]
    ):
        warnings.append(
            "Detected debugging intent but no explicit error keywords found. "
            "Planner may have over-triggered — review intent confidence."
        )

    if is_slash and intent == "normal_chat":
        # Unknown slash command fell through to normal_chat
        warnings.append(
            "Unrecognised slash command — treated as normal chat. "
            "Use /help to see available commands."
        )

    return warnings


# ── Public API ────────────────────────────────────────────────────────────────

def plan(
    message: str,
    parsed_command: Optional[ParsedCommand] = None,
    history: Optional[list] = None,
) -> PlannerOutput:
    """
    Phase 1 Planner Brain entry point.

    Always call this BEFORE any specialist brain or tool.

    Args:
        message:        The user's message (raw or cleaned, NOT the slash prefix line).
        parsed_command: Result of command_parser.parse() — can be None.
        history:        Recent conversation turns (not used for intent detection yet;
                        reserved for Phase 2 Manager context injection).

    Returns:
        PlannerOutput — always succeeds (no LLM required).
    """
    t0 = time.perf_counter()

    # Slash command intent override takes unconditional precedence
    if parsed_command and parsed_command.is_slash and parsed_command.intent_override:
        intent         = parsed_command.intent_override
        confidence     = 1.0
        routing_method = "slash_command"
    else:
        intent, confidence = _detect_intent(message)
        routing_method     = "keyword"

    seq, par      = _build_tasks(intent)
    response_mode = _RESPONSE_MODES.get(intent, "chat")
    exec_intent   = INTENT_TO_EXECUTION.get(intent, "chat")
    warnings      = _build_warnings(
        intent,
        message,
        is_slash=bool(parsed_command and parsed_command.is_slash),
    )

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    return PlannerOutput(
        intent=intent,
        confidence=confidence,
        response_mode=response_mode,
        sequential_tasks=seq,
        parallel_tasks=par,
        dependencies=[],
        files_targeted=[],
        warnings=warnings,
        routing_method=routing_method,
        planner_ms=elapsed_ms,
        slash_command=(parsed_command.command if parsed_command and parsed_command.is_slash else None),
        execution_intent=exec_intent,
    )
