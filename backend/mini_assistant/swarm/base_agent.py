"""
base_agent.py – Abstract Base Agent
──────────────────────────────────────
Every swarm agent inherits from BaseAgent.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Optional

from ..config import AGENT_MODELS, MODELS
from .task_models import SwarmTask, TaskResult


def _sync_ai_call(
    user_prompt: str,
    system_prompt: str = "",
    images: Optional[list[str]] = None,
) -> str:
    """Synchronous Claude/OpenAI call for swarm agents."""
    ant_key = os.getenv("ANTHROPIC_API_KEY")
    oai_key = os.getenv("OPENAI_API_KEY")

    user_content: Any = user_prompt
    if images:
        # Build multi-modal content for vision (Claude supports this)
        user_content = [{"type": "text", "text": user_prompt}]
        for img_b64 in images:
            user_content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
            })

    if ant_key:
        import anthropic
        client = anthropic.Anthropic(api_key=ant_key)
        kw = {"system": system_prompt} if system_prompt else {}
        msgs = [{"role": "user", "content": user_content}]
        msg = client.messages.create(model="claude-opus-4-6", max_tokens=8192, messages=msgs, **kw)
        return msg.content[0].text

    if oai_key:
        import openai
        client = openai.OpenAI(api_key=oai_key)
        if images:
            # OpenAI vision format
            oai_content = [{"type": "text", "text": user_prompt}]
            for img_b64 in images:
                oai_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                })
            user_msg: Any = {"role": "user", "content": oai_content}
        else:
            user_msg = {"role": "user", "content": user_prompt}
        oms = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + [user_msg]
        resp = client.chat.completions.create(model="gpt-4o", max_tokens=4096, messages=oms)
        return resp.choices[0].message.content or ""

    raise RuntimeError("No AI API key configured (ANTHROPIC_API_KEY or OPENAI_API_KEY required)")


class BaseAgent(ABC):
    """
    Abstract base for all swarm agents.

    Provides:
      _call_llm()          – call the agent's assigned AI model
      _inject_context()    – build a prompt that includes dependency outputs
      _make_result()       – convenient TaskResult factory
    """

    agent_name: str = "base_agent"
    agent_type: str = "fast"

    def __init__(self):
        self._model  = AGENT_MODELS.get(self.agent_type, MODELS["fallback"])
        self._logger = logging.getLogger(f"swarm.{self.agent_name}")
        self._logger.debug("Initialised %s → model=%s", self.agent_name, self._model)

    # ── LLM helper ────────────────────────────────────────────────────────────

    def _call_llm(
        self,
        user_prompt: str,
        system_prompt: str = "",
        temperature: float = 0.1,
        images: Optional[list[str]] = None,
    ) -> str:
        """Call Claude/OpenAI and return the response text."""
        try:
            return _sync_ai_call(user_prompt, system_prompt=system_prompt, images=images)
        except Exception as exc:
            self._logger.error("AI call failed: %s", exc)
            return f"[{self.agent_name}] AI unavailable: {exc}"

    # ── Context injection ─────────────────────────────────────────────────────

    def _inject_context(self, task: SwarmTask, context: dict[str, TaskResult]) -> str:
        parts: list[str] = [task.description]
        for dep_id in task.depends_on:
            dep_result = context.get(dep_id)
            if dep_result and dep_result.output:
                parts.append(
                    f"\n\n--- Context from task [{dep_id}] ---\n{dep_result.output[:2000]}"
                )
        return "\n".join(parts)

    # ── Result factory ────────────────────────────────────────────────────────

    def _make_result(
        self,
        task: SwarmTask,
        output: str,
        success: bool = True,
        data: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> TaskResult:
        return TaskResult(
            task_id = task.id,
            agent   = self.agent_name,
            success = success,
            output  = output,
            data    = data or {},
            error   = error,
        )

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def run(self, task: SwarmTask, context: dict[str, TaskResult]) -> TaskResult:
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self._model})"
