"""
planner.py – Task Planner
──────────────────────────
Converts a user request into a structured list of executable steps.

Each step specifies:
  - id:         unique step identifier
  - task:       human-readable description
  - tool:       optional tool name ("search", "python", "file_read", "image_gen",
                "screenshot", "computer")
  - brain:      optional brain name to call ("coding", "vision", "research", "fast")
  - depends_on: list of step ids whose outputs this step needs
  - args:       static arguments resolved at plan time

If the LLM planner fails (model not available, parse error) a single-step
fallback plan is returned so the system always has something to execute.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    import ollama
except ImportError as _e:
    import logging as _log
    _log.getLogger(__name__).error(
        "DEPENDENCY ERROR: 'ollama' is not installed – task planner will be unavailable. "
        "Run: pip install ollama  (%s)", _e,
    )
    ollama = None  # type: ignore[assignment]

from .config import MODELS, OLLAMA_HOST

logger = logging.getLogger(__name__)

# ─── Data types ───────────────────────────────────────────────────────────────

@dataclass
class Step:
    """A single executable unit in a plan."""
    id: str
    task: str
    tool: Optional[str] = None        # "search" | "python" | "file_read" | "image_gen" | "screenshot" | "computer"
    brain: Optional[str] = None       # "coding" | "vision" | "research" | "fast"
    args: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class Plan:
    """Ordered sequence of steps to fulfil a user request."""
    goal: str
    steps: list[Step]
    raw: dict = field(default_factory=dict)   # raw LLM JSON for debugging

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
    },
    {
      "id": "s2",
      "task": "Summarise and compare the GPU results",
      "tool": null,
      "brain": "research",
      "args": {},
      "depends_on": ["s1"]
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
    """
    Convert a user message into a structured Plan.

    Args:
        message:      The user's request.
        brain_hint:   Brain suggested by the router (used for fallback).
        force_simple: Skip LLM, return a single-step plan immediately.

    Returns:
        A Plan instance with one or more Steps.
    """
    if force_simple or len(message) < 30:
        return _fallback_plan(message, brain=brain_hint or "fast")

    try:
        client = ollama.Client(host=OLLAMA_HOST)
        resp = client.chat(
            model=MODELS.get("fast", MODELS["fallback"]),   # planner uses fast model
            messages=[
                {"role": "system", "content": _PLANNER_SYSTEM},
                {"role": "user",   "content": message},
            ],
            options={"temperature": 0.0},
        )
        raw_text = resp["message"]["content"].strip()
        # Strip optional markdown fences
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
