"""
Async Ollama API client for the Mini Assistant image system.

Handles all communication with the local Ollama server, including text
generation, chat, embeddings, and model management.
"""

import asyncio
import json
import logging
from typing import Any, AsyncIterator, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# Load model registry once at module level so all helpers can reference it
_MODEL_REGISTRY: dict = {}

def _load_registry() -> dict:
    """Load the model registry JSON lazily."""
    global _MODEL_REGISTRY
    if _MODEL_REGISTRY:
        return _MODEL_REGISTRY
    from pathlib import Path
    registry_path = Path(__file__).parent.parent / "config" / "model_registry.json"
    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            _MODEL_REGISTRY = json.load(f)
    except FileNotFoundError:
        logger.warning("model_registry.json not found, using defaults")
        _MODEL_REGISTRY = {
            "ollama_models": {
                "router": {"model": "qwen3:14b"},
                "router_fallback": {"model": "qwen2.5:7b"},
                "coder": {"model": "qwen2.5-coder:14b"},
                "vision": {"model": "qwen2.5vl:7b"},
                "embeddings": {"model": "nomic-embed-text"},
            }
        }
    return _MODEL_REGISTRY


def _model_name(role: str) -> str:
    """Return the Ollama model name for a given registry role key."""
    registry = _load_registry()
    return registry["ollama_models"][role]["model"]


class OllamaClient:
    """
    Async client for the Ollama REST API.

    All methods are coroutines. Create one instance and reuse it; the
    underlying aiohttp.ClientSession is created lazily and shared.
    """

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return (or create) the shared aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Core generate / chat
    # ------------------------------------------------------------------

    async def run_prompt(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.1,
        json_mode: bool = False,
        timeout: int = 60,
    ) -> str:
        """
        Call /api/generate (single-turn, non-streaming).

        Args:
            model: Ollama model name (e.g. "qwen3:14b").
            prompt: User prompt text.
            system: Optional system prompt.
            temperature: Sampling temperature.
            json_mode: If True, request JSON-formatted output.
            timeout: Request timeout in seconds.

        Returns:
            The model's response text (stripped).
        """
        truncated = prompt[:80].replace("\n", " ")
        logger.debug("run_prompt model=%s prompt='%s...'", model, truncated)

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        return await self._post_with_retry(
            "/api/generate", payload, response_key="response", timeout=timeout
        )

    async def run_chat(
        self,
        model: str,
        messages: List[dict],
        temperature: float = 0.1,
        json_mode: bool = False,
        timeout: int = 60,
    ) -> str:
        """
        Call /api/chat (multi-turn, non-streaming).

        Args:
            model: Ollama model name.
            messages: List of {"role": ..., "content": ...} dicts.
            temperature: Sampling temperature.
            json_mode: If True, request JSON-formatted output.
            timeout: Request timeout in seconds.

        Returns:
            The assistant message content (stripped).
        """
        logger.debug("run_chat model=%s turns=%d", model, len(messages))

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        raw = await self._post_with_retry(
            "/api/chat", payload, response_key=None, timeout=timeout
        )
        # /api/chat returns {"message": {"role": "assistant", "content": "..."}}
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data.get("message", {}).get("content", "").strip()

    async def embed(self, model: str, text: str) -> List[float]:
        """
        Call /api/embeddings and return the embedding vector.

        Args:
            model: Embedding model name (e.g. "nomic-embed-text").
            text: Text to embed.

        Returns:
            List of floats representing the embedding.
        """
        logger.debug("embed model=%s text_len=%d", model, len(text))
        session = await self._get_session()
        url = f"{self.base_url}/api/embeddings"
        payload = {"model": model, "prompt": text}

        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("embedding", [])

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    async def list_models(self) -> List[str]:
        """
        Call /api/tags and return a list of locally available model names.

        Returns:
            List of model name strings (e.g. ["qwen3:14b", "nomic-embed-text"]).
        """
        session = await self._get_session()
        url = f"{self.base_url}/api/tags"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return [m["name"] for m in data.get("models", [])]

    async def pull_model(self, model: str) -> AsyncIterator[str]:
        """
        Stream-pull a model from the Ollama registry.

        Yields status lines (JSON strings) as they arrive.

        Args:
            model: Model tag to pull (e.g. "qwen3:14b").
        """
        session = await self._get_session()
        url = f"{self.base_url}/api/pull"
        payload = {"name": model, "stream": True}

        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=3600)) as resp:
            resp.raise_for_status()
            async for raw_line in resp.content:
                line = raw_line.decode("utf-8").strip()
                if line:
                    yield line

    async def check_model_available(self, model: str) -> bool:
        """
        Return True if the given model is already pulled locally.

        Args:
            model: Model tag to check.
        """
        try:
            available = await self.list_models()
            # Ollama may include or omit the ":latest" suffix, normalise both
            normalised = {m.split(":")[0] for m in available} | set(available)
            return model in normalised or model.split(":")[0] in normalised
        except Exception as exc:
            logger.warning("check_model_available failed: %s", exc)
            return False

    async def ensure_models(self, model_names: List[str]) -> None:
        """
        Pull any models from *model_names* that are not yet available.

        Prints progress to stdout.

        Args:
            model_names: List of model tags to ensure are present.
        """
        for model in model_names:
            if await self.check_model_available(model):
                print(f"[ensure_models] {model} already available.")
                continue

            print(f"[ensure_models] Pulling {model} ...")
            async for status_line in self.pull_model(model):
                try:
                    status = json.loads(status_line)
                    if "status" in status:
                        print(f"  {status['status']}", end="\r", flush=True)
                except json.JSONDecodeError:
                    pass
            print(f"\n[ensure_models] {model} ready.")

    # ------------------------------------------------------------------
    # Convenience role wrappers
    # ------------------------------------------------------------------

    async def run_router(self, prompt: str, system: Optional[str] = None) -> str:
        """Run a prompt through the router model (qwen3:14b)."""
        return await self.run_prompt(
            model=_model_name("router"),
            prompt=prompt,
            system=system,
            temperature=0.1,
            json_mode=True,
        )

    async def run_router_fallback(self, prompt: str, system: Optional[str] = None) -> str:
        """Run a prompt through the fallback router model (qwen2.5:7b)."""
        return await self.run_prompt(
            model=_model_name("router_fallback"),
            prompt=prompt,
            system=system,
            temperature=0.1,
            json_mode=True,
        )

    async def run_coder(self, prompt: str, system: Optional[str] = None) -> str:
        """Run a prompt through the coder model (qwen2.5-coder:14b)."""
        return await self.run_prompt(
            model=_model_name("coder"),
            prompt=prompt,
            system=system,
            temperature=0.2,
        )

    async def run_vision(
        self, prompt: str, system: Optional[str] = None, images: Optional[List[str]] = None
    ) -> str:
        """
        Run a prompt through the vision model (qwen2.5vl:7b).

        Args:
            prompt: Text prompt.
            system: Optional system prompt.
            images: List of base64-encoded image strings.
        """
        model = _model_name("vision")
        messages: List[dict] = []
        if system:
            messages.append({"role": "system", "content": system})

        content_payload: Any
        if images:
            content_payload = [{"type": "text", "text": prompt}]
            for img_b64 in images:
                content_payload.append(
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                )
        else:
            content_payload = prompt

        messages.append({"role": "user", "content": content_payload})
        return await self.run_chat(model=model, messages=messages, temperature=0.1)

    async def run_embed(self, text: str) -> List[float]:
        """Embed text with the registered embeddings model (nomic-embed-text)."""
        return await self.embed(model=_model_name("embeddings"), text=text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _post_with_retry(
        self,
        path: str,
        payload: dict,
        response_key: Optional[str],
        timeout: int,
        max_retries: int = 2,
    ) -> Any:
        """
        POST *payload* to *self.base_url + path* with up to *max_retries* retries
        on connection errors.

        If *response_key* is set, parses JSON and returns that key's value.
        Otherwise returns the raw JSON string (for /api/chat multi-key response).
        """
        session = await self._get_session()
        url = f"{self.base_url}{path}"
        client_timeout = aiohttp.ClientTimeout(total=timeout)

        last_exc: Exception = RuntimeError("No attempts made")
        for attempt in range(max_retries + 1):
            try:
                async with session.post(url, json=payload, timeout=client_timeout) as resp:
                    resp.raise_for_status()
                    text = await resp.text()

                if response_key:
                    data = json.loads(text)
                    return data.get(response_key, "").strip()
                else:
                    # Return raw text so callers can parse as needed
                    return text

            except aiohttp.ClientConnectionError as exc:
                last_exc = exc
                if attempt < max_retries:
                    wait = 1.5 ** attempt
                    logger.warning(
                        "Connection error on attempt %d/%d, retrying in %.1fs: %s",
                        attempt + 1, max_retries + 1, wait, exc,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error("All %d attempts failed: %s", max_retries + 1, exc)
            except asyncio.TimeoutError as exc:
                last_exc = exc
                logger.error("Request timed out after %ds (attempt %d)", timeout, attempt + 1)
                if attempt >= max_retries:
                    break
            except Exception as exc:
                # Non-retriable errors surface immediately
                logger.error("Unexpected error calling Ollama: %s", exc)
                raise

        raise last_exc
