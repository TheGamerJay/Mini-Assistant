"""
base_agent.py – Abstract Base Agent
──────────────────────────────────────
Every swarm agent inherits from BaseAgent.

Subclasses must define:
  agent_name  – display name used in logs
  agent_type  – key into config.AGENT_MODELS (e.g. "coding", "research")
  run()       – execute a SwarmTask and return a TaskResult
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

try:
    import ollama
except ImportError as _e:
    import logging as _log
    _log.getLogger(__name__).error(
        "DEPENDENCY ERROR: 'ollama' is not installed – swarm agents will be unavailable. "
        "Run: pip install ollama  (%s)", _e,
    )
    ollama = None  # type: ignore[assignment]

from ..config import AGENT_MODELS, MODELS, OLLAMA_HOST
from .task_models import SwarmTask, TaskResult


class BaseAgent(ABC):
    """
    Abstract base for all swarm agents.

    Provides:
      _call_llm()          – call the agent's assigned Ollama model
      _inject_context()    – build a prompt that includes dependency outputs
      _make_result()       – convenient TaskResult factory
    """

    agent_name: str = "base_agent"
    agent_type: str = "fast"   # override to pick the right model

    def __init__(self):
        self._model  = AGENT_MODELS.get(self.agent_type, MODELS["fallback"])
        self._client = ollama.Client(host=OLLAMA_HOST)
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
        """
        Call the agent's assigned Ollama model and return the response text.
        Falls back to MODELS["fallback"] on any error.
        """
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        user_msg: dict[str, Any] = {"role": "user", "content": user_prompt}
        if images:
            user_msg["images"] = images
        messages.append(user_msg)

        def _chat(model: str) -> str:
            resp = self._client.chat(
                model=model,
                messages=messages,
                options={"temperature": temperature},
            )
            return resp["message"]["content"].strip()

        try:
            return _chat(self._model)
        except Exception as exc:
            self._logger.warning(
                "Primary model %s failed (%s) – falling back to %s.",
                self._model, exc, MODELS["fallback"],
            )
            try:
                return _chat(MODELS["fallback"])
            except Exception as exc2:
                self._logger.error("Fallback model also failed: %s", exc2)
                return f"[{self.agent_name}] LLM unavailable: {exc2}"

    # ── Context injection ─────────────────────────────────────────────────────

    def _inject_context(self, task: SwarmTask, context: dict[str, TaskResult]) -> str:
        """
        Build the user prompt by appending outputs from dependency tasks.
        """
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
        """
        Execute the task and return a TaskResult.

        Args:
            task:    The task to execute.
            context: Map of task_id → TaskResult for completed dependency tasks.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self._model})"
