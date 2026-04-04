"""
AI client for the Mini Assistant image system.

Replaces Ollama with Claude claude-sonnet-4-6 (primary) and OpenAI GPT-4o (fallback).
The class interface is kept identical so all callers continue to work unchanged.
"""

import asyncio
import logging
import os
from typing import Any, AsyncIterator, List, Optional

logger = logging.getLogger(__name__)

# Kept for compatibility – callers that reference _model_name will get this
_model_name = "claude-sonnet-4-6"

# Stub for legacy callers that imported _load_registry
def _load_registry() -> dict:
    """Compatibility stub — returns a minimal registry indicating Claude/OpenAI."""
    return {
        "ollama_models": {
            "router":          {"model": "claude-sonnet-4-6"},
            "router_fallback": {"model": "gpt-4o"},
            "coder":           {"model": "claude-sonnet-4-6"},
            "vision":          {"model": "gpt-4o"},
            "embeddings":      {"model": "text-embedding-3-small"},
        }
    }


# ---------------------------------------------------------------------------
# Low-level async helpers
# ---------------------------------------------------------------------------

async def _async_ai_chat(
    prompt: str,
    system: Optional[str] = None,
    images: Optional[List[str]] = None,
    ant_key: Optional[str] = None,
    oai_key: Optional[str] = None,
) -> str:
    """
    Async Claude (primary) / OpenAI (fallback) call.

    ant_key / oai_key: injected keys from the routing layer.
    Falls back to env vars if not provided (platform fallback path).
    """
    ant_key = ant_key or os.getenv("ANTHROPIC_API_KEY")
    oai_key = oai_key or os.getenv("OPENAI_API_KEY")

    if ant_key:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=ant_key)
        kw: dict = {}
        if system:
            kw["system"] = system

        if images:
            # Claude multi-modal content
            content: Any = [{"type": "text", "text": prompt}]
            for img_b64 in images:
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
                })
            msgs = [{"role": "user", "content": content}]
        else:
            msgs = [{"role": "user", "content": prompt}]

        msg = await client.messages.create(
            model="claude-sonnet-4-6", max_tokens=8192, messages=msgs, **kw
        )
        return msg.content[0].text

    if oai_key:
        import openai
        client = openai.AsyncOpenAI(api_key=oai_key)
        if images:
            oai_content: Any = [{"type": "text", "text": prompt}]
            for img_b64 in images:
                oai_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                })
            user_msg: Any = {"role": "user", "content": oai_content}
        else:
            user_msg = {"role": "user", "content": prompt}
        oms = ([{"role": "system", "content": system}] if system else []) + [user_msg]
        resp = await client.chat.completions.create(model="gpt-4o", max_tokens=8192, messages=oms)
        return resp.choices[0].message.content or ""

    raise RuntimeError("No AI API key configured (ANTHROPIC_API_KEY or OPENAI_API_KEY required)")


async def _async_ai_embed(text: str) -> List[float]:
    """Async OpenAI text-embedding-3-small."""
    oai_key = os.getenv("OPENAI_API_KEY")
    if oai_key:
        import openai
        client = openai.AsyncOpenAI(api_key=oai_key)
        resp = await client.embeddings.create(model="text-embedding-3-small", input=text)
        return resp.data[0].embedding
    # Fallback: return a zero vector (384 dims to match common expectations)
    logger.warning("No OPENAI_API_KEY for embeddings — returning zero vector")
    return [0.0] * 384


async def _async_ai_stream(
    prompt: str,
    system: Optional[str] = None,
    ant_key: Optional[str] = None,
    oai_key: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Async streaming Claude / OpenAI call.

    ant_key / oai_key: injected keys from the routing layer.
    Falls back to env vars if not provided (platform fallback path).
    """
    ant_key = ant_key or os.getenv("ANTHROPIC_API_KEY")
    oai_key = oai_key or os.getenv("OPENAI_API_KEY")

    if ant_key:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=ant_key)
        kw = {"system": system} if system else {}
        async with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
            **kw,
        ) as s:
            async for text in s.text_stream:
                yield text
        return

    if oai_key:
        import openai
        client = openai.AsyncOpenAI(api_key=oai_key)
        oms = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        async with await client.chat.completions.create(
            model="gpt-4o", max_tokens=8192, messages=oms, stream=True
        ) as s:
            async for chunk in s:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        return

    raise RuntimeError("No AI API key configured")


# ---------------------------------------------------------------------------
# OllamaClient — same public interface, now backed by Claude/OpenAI
# ---------------------------------------------------------------------------

class OllamaClient:
    """
    Drop-in replacement for the original Ollama client.

    All callers that used OllamaClient continue to work unchanged.
    Methods that accepted a ``model`` parameter ignore it; all calls
    go to Claude claude-sonnet-4-6 (primary) or GPT-4o (fallback).
    """

    def __init__(self, base_url: str = "") -> None:
        # base_url ignored — kept for signature compatibility
        pass

    async def close(self) -> None:
        """No-op — no persistent session to close."""
        pass

    # ------------------------------------------------------------------
    # Core generate / chat
    # ------------------------------------------------------------------

    async def run_prompt(
        self,
        model: str = "",
        prompt: str = "",
        system: Optional[str] = None,
        temperature: float = 0.1,
        json_mode: bool = False,
        timeout: int = 60,
    ) -> str:
        return await _async_ai_chat(prompt, system=system)

    async def run_chat(
        self,
        model: str = "",
        messages: Optional[List[dict]] = None,
        temperature: float = 0.1,
        json_mode: bool = False,
        timeout: int = 60,
    ) -> str:
        msgs = messages or []
        system = next((m["content"] for m in msgs if m.get("role") == "system"), None)
        user_parts = [m["content"] for m in msgs if m.get("role") != "system"]
        prompt = "\n\n".join(str(p) for p in user_parts)
        return await _async_ai_chat(prompt, system=system)

    async def run_chat_stream(
        self,
        model: str = "",
        messages: Optional[List[dict]] = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        msgs = messages or []
        system = next((m["content"] for m in msgs if m.get("role") == "system"), None)
        user_parts = [m["content"] for m in msgs if m.get("role") != "system"]
        prompt = "\n\n".join(str(p) for p in user_parts)
        async for chunk in _async_ai_stream(prompt, system=system):
            yield chunk

    async def embed(self, model: str = "", text: str = "") -> List[float]:
        return await _async_ai_embed(text)

    # ------------------------------------------------------------------
    # Model management — no-ops / stubs
    # ------------------------------------------------------------------

    async def list_models(self) -> List[str]:
        return ["claude-sonnet-4-6", "gpt-4o"]

    async def pull_model(self, model: str) -> AsyncIterator[str]:
        logger.info("pull_model no-op for %s (using Claude/OpenAI)", model)
        return
        yield  # make it an async generator

    async def check_model_available(self, model: str) -> bool:
        return True

    async def ensure_models(self, model_names: List[str]) -> None:
        logger.info("ensure_models no-op (using Claude/OpenAI)")

    # ------------------------------------------------------------------
    # Convenience role wrappers (kept for callers that use them)
    # ------------------------------------------------------------------

    async def run_router(self, prompt: str, system: Optional[str] = None) -> str:
        return await _async_ai_chat(prompt, system=system)

    async def run_router_fallback(self, prompt: str, system: Optional[str] = None) -> str:
        return await _async_ai_chat(prompt, system=system)

    async def run_coder(self, prompt: str, system: Optional[str] = None) -> str:
        return await _async_ai_chat(prompt, system=system)

    async def run_vision(
        self,
        prompt: str,
        system: Optional[str] = None,
        images: Optional[List[str]] = None,
    ) -> str:
        return await _async_ai_chat(prompt, system=system, images=images)

    async def run_embed(self, text: str) -> List[float]:
        return await _async_ai_embed(text)
