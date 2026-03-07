"""
base.py – BaseBrain
────────────────────
All brains inherit from this. Handles:
  - Ollama API calls (with automatic model fallback)
  - Conversation history management
  - Tool result injection into context
  - Streaming support
"""

import logging
from typing import Generator, Optional

try:
    import ollama
except ImportError as _e:
    import logging as _log
    _log.getLogger(__name__).error(
        "DEPENDENCY ERROR: 'ollama' is not installed – all brains will be unavailable. "
        "Run: pip install ollama  (%s)", _e,
    )
    ollama = None  # type: ignore[assignment]

from ..config import OLLAMA_HOST, MODELS

logger = logging.getLogger(__name__)


class BaseBrain:
    name: str = "base"
    system_prompt: str = "You are a helpful AI assistant."

    def __init__(self, model: str):
        if ollama is None:
            raise ImportError(
                "DEPENDENCY ERROR: 'ollama' is not installed. "
                "Run: pip install ollama"
            )
        self.model = model
        self._client = ollama.Client(host=OLLAMA_HOST)
        self._history: list[dict] = []

    # ── Internal: call Ollama with fallback ───────────────────────────────────

    def _call(
        self,
        messages: list[dict],
        stream: bool = False,
        options: Optional[dict] = None,
    ) -> str | Generator:
        opts = options or {"temperature": 0.7}

        def _try(model: str):
            return self._client.chat(
                model=model,
                messages=messages,
                stream=stream,
                options=opts,
            )

        try:
            response = _try(self.model)
        except Exception as primary_err:
            logger.warning(
                "%s brain: model %s unavailable (%s). Falling back to %s.",
                self.name, self.model, primary_err, MODELS["fallback"],
            )
            try:
                response = _try(MODELS["fallback"])
            except Exception as fallback_err:
                raise RuntimeError(
                    f"Both {self.model} and fallback {MODELS['fallback']} failed: {fallback_err}"
                ) from fallback_err

        if stream:
            return self._stream_generator(response)

        return response["message"]["content"]

    @staticmethod
    def _stream_generator(response) -> Generator[str, None, None]:
        for chunk in response:
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content

    # ── Public API ────────────────────────────────────────────────────────────

    def respond(
        self,
        user_message: str,
        tool_results: Optional[list[dict]] = None,
        images: Optional[list[str]] = None,
        stream: bool = False,
    ) -> str | Generator:
        """
        Generate a response for a user message.

        Args:
            user_message:  The user's text.
            tool_results:  Optional list of {"tool": name, "result": data} from pre-executed tools.
            images:        Optional list of base64-encoded images.
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

        # Build user message (with optional images)
        user_msg: dict = {"role": "user", "content": user_message}
        if images:
            user_msg["images"] = images

        self._history.append(user_msg)

        messages = [sys_msg] + self._history

        result = self._call(messages, stream=stream)

        if not stream:
            self._history.append({"role": "assistant", "content": result})

        return result

    def clear_history(self) -> None:
        self._history = []
