"""
vision_agent.py – Vision Agent
────────────────────────────────
Analyses screenshots, UI images, diagrams, and other visual inputs.
Also handles image generation requests (routes to the image_gen tool).

Input (task.args):
  images  – list of image file paths or base64 strings
  prompt  – specific question about the images (optional)
  mode    – "analyse" (default) | "generate"
"""

from __future__ import annotations

from typing import Optional

from .base_agent       import BaseAgent
from .task_models      import SwarmTask, TaskResult, TaskType
from ..tools.image_gen import generate_image


_VISION_SYSTEM = """\
You are an expert visual analyst and UI/UX specialist.

When analysing images:
- Describe what you see clearly and thoroughly.
- Identify UI components, layouts, charts, code, or diagrams.
- Note any issues, errors, or areas that need attention.
- If it's a screenshot with code or errors, read and explain them precisely.
- If it's a UI design, comment on usability and layout.
- If asked a specific question, answer it directly.
"""


class VisionAgent(BaseAgent):
    """
    Vision agent: image analysis (VisionBrain) + image generation (tool).
    """

    agent_name = "vision_agent"
    agent_type = "vision"

    def run(self, task: SwarmTask, context: dict[str, TaskResult]) -> TaskResult:
        self._logger.info("Vision task: %s", task.description[:80])

        mode = task.args.get("mode", "analyse")

        # ── Image generation mode ─────────────────────────────────────────────
        if mode == "generate" or task.type == TaskType.IMAGE_GEN:
            return self._generate(task)

        # ── Image analysis mode ───────────────────────────────────────────────
        return self._analyse(task, context)

    def _analyse(self, task: SwarmTask, context: dict[str, TaskResult]) -> TaskResult:
        """Analyse images using the vision LLM."""
        images: list[str] = task.args.get("images", [])

        if not images:
            # No images provided – fall back to text-only response
            self._logger.warning("VisionAgent called with no images – using text-only response.")
            prompt = self._inject_context(task, context)
            response = self._call_llm(
                user_prompt   = prompt,
                system_prompt = _VISION_SYSTEM,
            )
            return self._make_result(task=task, output=response)

        prompt_text = task.args.get("prompt") or task.description
        dep_context = self._inject_context(task, context)
        if dep_context != task.description:
            prompt_text += f"\n\nContext:\n{dep_context[:500]}"

        self._logger.info("Analysing %d image(s).", len(images))
        response = self._call_llm(
            user_prompt   = prompt_text,
            system_prompt = _VISION_SYSTEM,
            images        = images,
            temperature   = 0.1,
        )

        return self._make_result(
            task   = task,
            output = response,
            data   = {"images_analysed": len(images)},
        )

    def _generate(self, task: SwarmTask) -> TaskResult:
        """Generate an image using the SD/ComfyUI tool."""
        prompt = task.args.get("prompt") or task.description
        self._logger.info("Generating image: %s", prompt[:60])

        result = generate_image(prompt)

        if result.get("success"):
            output = f"Image generated successfully for prompt: {prompt}"
            return self._make_result(
                task   = task,
                output = output,
                data   = {"image_b64": result.get("image_b64", ""), "success": True},
            )
        else:
            error = result.get("error", "Unknown error")
            return self._make_result(
                task    = task,
                output  = f"Image generation failed: {error}",
                success = False,
                error   = error,
            )
