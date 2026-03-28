"""
planner.py – Task Planner
──────────────────────────
Converts a user request into a structured list of executable steps.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import MODELS

logger = logging.getLogger(__name__)


def _ai_call(system: str, user: str) -> str:
    """Synchronous Claude/OpenAI call."""
    ant_key = os.getenv("ANTHROPIC_API_KEY")
    oai_key = os.getenv("OPENAI_API_KEY")
    if ant_key:
        import anthropic
        client = anthropic.Anthropic(api_key=ant_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text
    if oai_key:
        import openai
        client = openai.OpenAI(api_key=oai_key)
        resp = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=4096,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""
    raise RuntimeError("No AI API key configured")


# ─── Data types ───────────────────────────────────────────────────────────────

@dataclass
class Step:
    """A single executable unit in a plan."""
    id: str
    task: str
    tool: Optional[str] = None
    brain: Optional[str] = None
    args: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class Plan:
    """Ordered sequence of steps to fulfil a user request."""
    goal: str
    steps: list[Step]
    raw: dict = field(default_factory=dict)

    def is_single_step(self) -> bool:
        return len(self.steps) == 1

    def __repr__(self) -> str:
        lines = [f"Plan: {self.goal}"]
        for s in self.steps:
            lines.append(f"  [{s.id}] {s.task} | tool={s.tool} brain={s.brain}")
        return "\n".join(lines)


# ─── Planner system prompt ────────────────────────────────────────────────────

_PLANNER_SYSTEM = """\
You are a task planner for a multi-brain AI assistant.

Break the user request into an ordered list of concrete steps.

Available tools:
  search       – web search (use for current facts, news, prices)
  python       – execute Python code
  file_read    – read a file or folder from disk
  image_gen    – generate an image
  screenshot   – capture current screen
  computer     – click / type / open apps

Available brains:
  coding       – write, debug, explain, refactor code
  vision       – analyse images / screenshots
  research     – deep reasoning, comparisons, long-form analysis
  fast         – short answers, narration, summaries

Rules:
- Use "tool" when an external action is needed BEFORE reasoning.
- Use "brain" when reasoning / generation is the main action.
- A step may use EITHER tool OR brain, never both.
- Keep steps minimal – do not add steps that are not needed.
- Depends_on lists the ids of steps whose output this step must receive.

Respond with ONLY valid JSON (no markdown):
{
  "steps": [
    {
      "id": "s1",
      "task": "Short description of this step",
      "tool": "search",
      "brain": null,
      "args": {"query": "best GPUs for AI 2024"},
      "depends_on": []
    }
  ]
}
"""


# ─── Planner implementation ───────────────────────────────────────────────────

def _fallback_plan(goal: str, brain: str = "fast") -> Plan:
    """Single-step plan used when the LLM planner cannot run."""
    return Plan(
        goal=goal,
        steps=[Step(id="s1", task=goal, brain=brain)],
    )


def plan(
    message: str,
    brain_hint: Optional[str] = None,
    force_simple: bool = False,
) -> Plan:
    if force_simple or len(message) < 30:
        return _fallback_plan(message, brain=brain_hint or "fast")

    try:
        raw_text = _ai_call(_PLANNER_SYSTEM, message).strip()
        raw_text = re.sub(r"```(?:json)?", "", raw_text).replace("```", "").strip()
        data = json.loads(raw_text)
        steps_data = data.get("steps", [])

        if not steps_data:
            raise ValueError("No steps in planner response")

        steps: list[Step] = []
        for s in steps_data:
            steps.append(Step(
                id=s.get("id", f"s{len(steps)+1}"),
                task=s.get("task", ""),
                tool=s.get("tool") or None,
                brain=s.get("brain") or None,
                args=s.get("args", {}),
                depends_on=s.get("depends_on", []),
            ))

        logger.info("Planner produced %d steps for: %s", len(steps), message[:60])
        return Plan(goal=message, steps=steps, raw=data)

    except Exception as exc:
        logger.warning("Planner LLM failed (%s) – using single-step fallback.", exc)
        return _fallback_plan(message, brain=brain_hint or "fast")
