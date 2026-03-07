"""
planner_agent.py – Planner Agent
──────────────────────────────────
Converts a user request into a list of structured SwarmTask objects.

The planner uses the manager-class model (qwen3:30b) to reason about
what work needs to be done and what order/dependencies make sense.

Output is a JSON array of task descriptors that the manager turns into
SwarmTask instances and loads into the TaskQueue.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from .base_agent   import BaseAgent
from .task_models  import SwarmTask, TaskResult, TaskType, TASK_AGENT_MAP

logger = logging.getLogger(__name__)


_PLANNER_SYSTEM = """\
You are a senior task planning agent for a multi-agent AI assistant called Mini Assistant.

Your job is to break a user request into a list of concrete subtasks.
Each subtask must be assigned to exactly one specialist agent.

Available agents and their task types:
  research_agent     → type: "research"     (web search, documentation review, comparisons)
  coding_agent       → type: "coding"       (write code, scaffold apps, implement features)
  debug_agent        → type: "debug"        (analyse failures, fix broken code, trace errors)
  tester_agent       → type: "testing"      (run tests, validate outputs, check correctness)
  file_analyst_agent → type: "file_analysis" (read project files, summarise architecture)
  vision_agent       → type: "vision"       (analyse screenshots, UI images, diagrams)
  vision_agent       → type: "image_gen"    (generate images, logos, illustrations)

Rules:
- Each task must have a unique id: "t1", "t2", … in order.
- depends_on is a list of task ids that MUST complete before this task starts.
- priority: 1 = most urgent, 10 = least urgent.
- Keep descriptions clear and self-contained.
- Only create tasks that are genuinely needed.
- For simple requests (< 3 logical steps) return just 1–2 tasks.

Respond with ONLY valid JSON – no markdown, no prose:
{
  "tasks": [
    {
      "id": "t1",
      "type": "research",
      "description": "Research FastAPI best practices for authentication",
      "depends_on": [],
      "priority": 2,
      "args": {}
    },
    {
      "id": "t2",
      "type": "coding",
      "description": "Build FastAPI JWT authentication routes based on research findings",
      "depends_on": ["t1"],
      "priority": 3,
      "args": {"language": "python"}
    }
  ]
}
"""


class PlannerAgent(BaseAgent):
    """
    Converts a user request string into a list of SwarmTask objects.

    This agent is called first by the SwarmManager; its output seeds
    the TaskQueue for the rest of the run.
    """

    agent_name = "planner_agent"
    agent_type = "planner"

    def run(self, task: SwarmTask, context: dict[str, TaskResult]) -> TaskResult:
        """
        Run the planner on task.description (the user request).
        Returns a TaskResult whose .data["tasks"] holds parsed SwarmTask list.
        """
        user_request = task.description
        self._logger.info("Planning: %s", user_request[:80])

        raw = self._call_llm(
            user_prompt   = user_request,
            system_prompt = _PLANNER_SYSTEM,
            temperature   = 0.0,
        )

        tasks = self._parse_plan(raw, user_request)
        plan_summary = "\n".join(
            f"  [{t.id}] ({t.type}) {t.description[:60]}" for t in tasks
        )
        self._logger.info("Plan produced %d tasks:\n%s", len(tasks), plan_summary)

        return self._make_result(
            task   = task,
            output = plan_summary,
            data   = {"tasks": tasks},
        )

    def _parse_plan(self, raw: str, fallback_request: str) -> list[SwarmTask]:
        """Parse LLM JSON output into SwarmTask list with graceful fallback."""
        try:
            clean = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
            data  = json.loads(clean)
            items = data.get("tasks", [])
            if not items:
                raise ValueError("Empty task list in planner response")

            tasks: list[SwarmTask] = []
            for item in items:
                task_type = item.get("type", TaskType.GENERIC)
                agent     = item.get("assigned_agent") or TASK_AGENT_MAP.get(task_type, "research_agent")
                tasks.append(SwarmTask(
                    id             = item.get("id", f"t{len(tasks)+1}"),
                    type           = task_type,
                    description    = item.get("description", ""),
                    assigned_agent = agent,
                    depends_on     = item.get("depends_on", []),
                    priority       = int(item.get("priority", 5)),
                    args           = item.get("args", {}),
                ))
            return tasks

        except Exception as exc:
            logger.warning("Planner parse failed (%s) – using single-task fallback.", exc)
            return [SwarmTask(
                id          = "t1",
                type        = TaskType.GENERIC,
                description = fallback_request,
                assigned_agent = "research_agent",
            )]

    def plan_direct(self, user_request: str) -> list[SwarmTask]:
        """
        Convenience: call the planner directly without wrapping in a SwarmTask.
        Returns the parsed task list.
        """
        wrapper = SwarmTask(description=user_request, type=TaskType.PLANNING)
        result  = self.run(wrapper, {})
        return result.data.get("tasks", [wrapper])
