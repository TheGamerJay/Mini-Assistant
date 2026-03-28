"""
base.py – BaseBrain
────────────────────
All brains inherit from this. Handles:
  - Claude/OpenAI API calls (with fallback)
  - Conversation history management
  - Tool result injection into context
  - Streaming support
"""

import logging
import os
from typing import Generator, Iterator, Optional

from ..config import MODELS

logger = logging.getLogger(__name__)


def _sync_ai_call(messages: list, system: str | None = None) -> str:
    """Synchronous Claude (primary) / OpenAI (fallback) call."""
    ant_key = os.getenv("ANTHROPIC_API_KEY")
    oai_key = os.getenv("OPENAI_API_KEY")

    # Filter out system messages from messages list; pass as system param for Claude
    user_messages = [m for m in messages if m.get("role") != "system"]
    # If no explicit system arg, extract from messages
    if system is None:
        for m in messages:
            if m.get("role") == "system":
                system = m["content"]
                break

    if ant_key:
        import anthropic
        client = anthropic.Anthropic(api_key=ant_key)
        kw = {"system": system} if system else {}
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            messages=user_messages,
            **kw,
        )
        return msg.content[0].text

    if oai_key:
        import openai
        client = openai.OpenAI(api_key=oai_key)
        oms = ([{"role": "system", "content": system}] if system else []) + user_messages
        resp = client.chat.completions.create(model="gpt-4o", max_tokens=8192, messages=oms)
        return resp.choices[0].message.content or ""

    raise RuntimeError("No AI API key configured (ANTHROPIC_API_KEY or OPENAI_API_KEY required)")


def _sync_ai_stream(messages: list, system: str | None = None) -> Iterator[str]:
    """Synchronous streaming Claude (primary) / OpenAI (fallback) call."""
    ant_key = os.getenv("ANTHROPIC_API_KEY")
    oai_key = os.getenv("OPENAI_API_KEY")

    user_messages = [m for m in messages if m.get("role") != "system"]
    if system is None:
        for m in messages:
            if m.get("role") == "system":
                system = m["content"]
                break

    if ant_key:
        import anthropic
        client = anthropic.Anthropic(api_key=ant_key)
        kw = {"system": system} if system else {}
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            messages=user_messages,
            **kw,
        ) as stream:
            yield from stream.text_stream
        return

    if oai_key:
        import openai
        client = openai.OpenAI(api_key=oai_key)
        oms = ([{"role": "system", "content": system}] if system else []) + user_messages
        for chunk in client.chat.completions.create(
            model="gpt-4o", max_tokens=8192, messages=oms, stream=True
        ):
            content = chunk.choices[0].delta.content
            if content:
                yield content
        return

    raise RuntimeError("No AI API key configured (ANTHROPIC_API_KEY or OPENAI_API_KEY required)")


class BaseBrain:
    name: str = "base"
    system_prompt: str = "You are a helpful AI assistant."

    def __init__(self, model: str):
        self.model = model
        self._history: list[dict] = []

    # ── Internal: call AI with fallback ───────────────────────────────────────

    def _call(
        self,
        messages: list[dict],
        stream: bool = False,
        options: Optional[dict] = None,
    ) -> str | Iterator:
        try:
            if stream:
                return _sync_ai_stream(messages)
            return _sync_ai_call(messages)
        except Exception as exc:
            logger.warning(
                "%s brain: AI call failed (%s).",
                self.name, exc,
            )
            raise RuntimeError(f"AI call failed: {exc}") from exc

    @staticmethod
    def _stream_generator(response) -> Generator[str, None, None]:
        """Compatibility shim — response is already a generator."""
        yield from response

    # ── Public API ────────────────────────────────────────────────────────────

    def respond(
        self,
        user_message: str,
        tool_results: Optional[list[dict]] = None,
        images: Optional[list[str]] = None,
        stream: bool = False,
    ) -> str | Iterator:
        """
        Generate a response for a user message.

        Args:
            user_message:  The user's text.
            tool_results:  Optional list of {"tool": name, "result": data} from pre-executed tools.
            images:        Optional list of base64-encoded images (passed as text description for Claude).
            stream:        If True, returns a token generator instead of a full string.
        """
        # Build system message
        sys_msg = {"role": "system", "content": self.system_prompt}

        # Inject tool results into user message if present
        if tool_results:
            tool_block = "\n\n".join(
                f"[{r['tool']} result]\n{r['result']}" for r in tool_results
            )
            user_message = f"{user_message}\n\n{tool_block}"

        # Build user message
        user_msg: dict = {"role": "user", "content": user_message}

        self._history.append(user_msg)

        messages = [sys_msg] + self._history

        result = self._call(messages, stream=stream)

        if not stream:
            self._history.append({"role": "assistant", "content": result})

        return result

    def clear_history(self) -> None:
        self._history = []
