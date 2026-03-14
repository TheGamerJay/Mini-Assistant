"""
command_parser.py — Slash Command Parser
─────────────────────────────────────────
Detects /command prefixes and returns structured command info.

Slash commands provide forced-intent routing — they override the
Planner's keyword detection when present.

Supported commands:
  /chat    <message>  — normal conversation
  /search  <query>    — web search
  /image   <prompt>   — image generation
  /analyze            — image/screenshot analysis (expects attachment)
  /code    <request>  — code generation or explanation
  /fix     <error>    — debug an error or issue
  /plan    <goal>     — plan a multi-step task
  /build   <brief>    — build a web app via App Builder
  /files              — inspect project file structure
  /context            — show project context scan
  /help               — show available commands

Commands are case-insensitive.  Unknown commands fall through as normal chat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ── Command registry ──────────────────────────────────────────────────────────

SLASH_COMMANDS: dict[str, dict] = {
    "chat": {
        "intent":      "normal_chat",
        "description": "Start a normal conversation",
        "example":     "/chat what is a transformer?",
    },
    "search": {
        "intent":      "web_search",
        "description": "Search the web for current information",
        "example":     "/search latest GPT news",
    },
    "image": {
        "intent":      "image_generate",
        "description": "Generate an image with ComfyUI",
        "example":     "/image cyberpunk city at night, neon lights",
    },
    "analyze": {
        "intent":      "image_analysis",
        "description": "Analyze an attached image or screenshot",
        "example":     "/analyze  (attach an image first)",
    },
    "code": {
        "intent":      "code_runner",
        "description": "Write, explain, or refactor code",
        "example":     "/code write a Python FastAPI health-check endpoint",
    },
    "fix": {
        "intent":      "debugging",
        "description": "Debug an error, bug, or broken route",
        "example":     "/fix ModuleNotFoundError: No module named 'requests'",
    },
    "plan": {
        "intent":      "planning",
        "description": "Break a goal into an ordered execution plan",
        "example":     "/plan add a login system to my app",
    },
    "build": {
        "intent":      "app_builder",
        "description": "Build a full web app via the App Builder",
        "example":     "/build a portfolio website with dark theme",
    },
    "files": {
        "intent":      "file_analysis",
        "description": "Inspect the project file structure",
        "example":     "/files",
    },
    "context": {
        "intent":      "file_analysis",
        "description": "Run the project context scanner and show a summary",
        "example":     "/context",
    },
    "help": {
        "intent":      "normal_chat",
        "description": "Show all available slash commands",
        "example":     "/help",
    },
}

_SLASH_RE = re.compile(r"^/(\w+)\s*(.*)", re.DOTALL | re.IGNORECASE)


# ── Data type ─────────────────────────────────────────────────────────────────

@dataclass
class ParsedCommand:
    """Result of parsing a user message for a slash prefix."""
    raw: str                         # original message as typed
    command: Optional[str]           # e.g. "fix" — None if not a slash command
    args: str                        # everything after the command, stripped
    intent_override: Optional[str]   # maps to blueprint intent or None
    is_slash: bool                   # True if a / prefix was detected
    is_known: bool                   # True if command is in SLASH_COMMANDS
    help_requested: bool             # True if /help was typed


# ── Parser ────────────────────────────────────────────────────────────────────

def parse(message: str) -> ParsedCommand:
    """
    Parse a raw user message for slash commands.

    Returns:
        ParsedCommand — always succeeds; is_slash=False when no command found.

    Examples:
        parse("/fix ImportError: No module named 'requests'")
        # → ParsedCommand(command="fix", intent_override="debugging", ...)

        parse("What is Python?")
        # → ParsedCommand(command=None, is_slash=False, ...)
    """
    stripped = message.strip()

    if not stripped.startswith("/"):
        return ParsedCommand(
            raw=message,
            command=None,
            args=message,
            intent_override=None,
            is_slash=False,
            is_known=False,
            help_requested=False,
        )

    m = _SLASH_RE.match(stripped)
    if not m:
        # Lone "/" or malformed — treat as chat
        return ParsedCommand(
            raw=message,
            command=None,
            args=stripped,
            intent_override=None,
            is_slash=False,
            is_known=False,
            help_requested=False,
        )

    command = m.group(1).lower()
    args    = m.group(2).strip()

    cmd_info       = SLASH_COMMANDS.get(command)
    intent_override = cmd_info["intent"] if cmd_info else None
    is_known        = cmd_info is not None
    help_requested  = command == "help"

    # If the command gives no args, substitute the command name as minimal context
    # (avoids sending an empty string to brains)
    if not args:
        if command == "help":
            args = "Show all available slash commands with descriptions and examples."
        elif command == "context":
            args = "Show the project context scan summary."
        elif command == "files":
            args = "List the project files and structure."
        else:
            args = command   # minimal — brain will ask for more detail if needed

    return ParsedCommand(
        raw=message,
        command=command,
        args=args,
        intent_override=intent_override,
        is_slash=True,
        is_known=is_known,
        help_requested=help_requested,
    )


def help_text() -> str:
    """Return a formatted help string listing all commands."""
    lines = ["**Available slash commands:**\n"]
    for cmd, info in SLASH_COMMANDS.items():
        lines.append(f"  `/{cmd}` — {info['description']}")
        lines.append(f"           e.g. `{info['example']}`")
    lines.append("\nCommands override intent detection. Use natural language for everything else.")
    return "\n".join(lines)
