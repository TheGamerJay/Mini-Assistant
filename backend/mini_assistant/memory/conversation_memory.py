"""
conversation_memory.py – Short-Term Conversation Memory
─────────────────────────────────────────────────────────
Maintains a bounded ring-buffer of recent messages for a session.

Usage:
    mem = ConversationMemory(max_turns=20)
    mem.add("user", "Hello, how are you?")
    mem.add("assistant", "I'm great, how can I help?")
    context = mem.format_for_llm()  # inject into next LLM call
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator


@dataclass
class Turn:
    role: str       # "user" | "assistant" | "system" | "tool"
    content: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict = field(default_factory=dict)


class ConversationMemory:
    """
    Fixed-size ring buffer of conversation turns.

    When max_turns is reached, the oldest turn is dropped automatically.
    The system prompt (if set) is always prepended and never dropped.
    """

    def __init__(self, max_turns: int = 30, system_prompt: str = ""):
        self._max_turns     = max_turns
        self._system_prompt = system_prompt
        self._turns: deque[Turn] = deque(maxlen=max_turns)

    # ── Mutation ──────────────────────────────────────────────────────────────

    def add(self, role: str, content: str, metadata: dict | None = None) -> None:
        """Append a new turn. Oldest turn is auto-dropped when full."""
        self._turns.append(Turn(role=role, content=content, metadata=metadata or {}))

    def add_user(self, content: str) -> None:
        self.add("user", content)

    def add_assistant(self, content: str) -> None:
        self.add("assistant", content)

    def add_tool_result(self, tool_name: str, result: str) -> None:
        self.add("tool", f"[{tool_name}] {result}")

    def clear(self) -> None:
        """Reset all turns (keeps system prompt)."""
        self._turns.clear()

    def set_system_prompt(self, prompt: str) -> None:
        self._system_prompt = prompt

    # ── Access ────────────────────────────────────────────────────────────────

    @property
    def turns(self) -> list[Turn]:
        return list(self._turns)

    @property
    def length(self) -> int:
        return len(self._turns)

    def __iter__(self) -> Iterator[Turn]:
        return iter(self._turns)

    def last_user_message(self) -> str | None:
        for turn in reversed(self._turns):
            if turn.role == "user":
                return turn.content
        return None

    def last_assistant_message(self) -> str | None:
        for turn in reversed(self._turns):
            if turn.role == "assistant":
                return turn.content
        return None

    # ── Formatting for LLM injection ──────────────────────────────────────────

    def to_ollama_messages(self) -> list[dict]:
        """
        Return the conversation as a list of Ollama-compatible message dicts.

        Format: [{"role": "user"|"assistant"|"system", "content": "..."}]
        """
        messages: list[dict] = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        for turn in self._turns:
            role = turn.role if turn.role in ("user", "assistant", "system") else "user"
            messages.append({"role": role, "content": turn.content})
        return messages

    def format_for_llm(self, max_chars: int = 6000) -> str:
        """
        Return a plain-text summary of recent turns for injection into a prompt.
        Truncates from the oldest end if total length exceeds max_chars.
        """
        lines: list[str] = []
        for turn in self._turns:
            prefix = turn.role.upper()
            lines.append(f"{prefix}: {turn.content}")

        text = "\n".join(lines)
        if len(text) > max_chars:
            # Keep the most recent portion
            text = "...[earlier context truncated]...\n" + text[-max_chars:]
        return text

    def __repr__(self) -> str:
        return f"ConversationMemory(turns={len(self._turns)}/{self._max_turns})"
