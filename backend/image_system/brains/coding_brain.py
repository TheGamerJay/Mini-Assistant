"""
Coding Brain for the Mini Assistant image system.

Wraps qwen2.5-coder:14b for general coding tasks, ComfyUI workflow generation,
workflow debugging, and prompt improvement suggestions.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CodingBrain:
    """
    Specialised brain for code-related tasks using qwen2.5-coder:14b.

    Methods are async coroutines.
    """

    _GENERAL_SYSTEM = (
        "You are an expert software engineer. Provide clear, correct, well-commented code. "
        "Use Python 3.11+ idioms. Prefer standard library when possible. "
        "Always include type hints and docstrings."
    )

    _WORKFLOW_SYSTEM = (
        "You are an expert ComfyUI workflow engineer. "
        "You write ComfyUI API-format workflow JSON objects. "
        "The format uses node IDs as keys. Each node has: class_type, inputs, _meta.title. "
        "Node connections use [node_id, output_index] tuples. "
        "Always include: CheckpointLoaderSimple, CLIPTextEncode x2, EmptyLatentImage, "
        "KSampler, VAEDecode, SaveImage. Return ONLY valid JSON, no markdown."
    )

    _DEBUG_SYSTEM = (
        "You are a ComfyUI workflow debugger. "
        "Given a broken workflow and an error message, explain the issue and provide a fixed workflow. "
        "Return JSON: {\"analysis\": \"...\", \"fixed_workflow\": {...}}"
    )

    _PROMPT_IMPROVE_SYSTEM = (
        "You are a Stable Diffusion prompt engineer. "
        "Given an image prompt and a list of issues from a quality review, "
        "suggest improvements. Return JSON: {\"improved_prompt\": \"...\", \"changes\": [\"...\"]}"
    )

    def __init__(self) -> None:
        from ..services.ollama_client import OllamaClient
        self._ollama = OllamaClient()

    # ------------------------------------------------------------------
    # General coding
    # ------------------------------------------------------------------

    async def run(self, task: str, context: Optional[str] = None) -> str:
        """
        Run a general coding task through qwen2.5-coder:14b.

        Args:
            task: Description of the coding task or question.
            context: Optional additional context (e.g. existing code).

        Returns:
            The model's text response.
        """
        prompt = task
        if context:
            prompt = f"Context:\n{context}\n\nTask:\n{task}"

        logger.info("CodingBrain.run task='%s...'", task[:60])
        return await self._ollama.run_coder(prompt=prompt, system=self._GENERAL_SYSTEM)

    # ------------------------------------------------------------------
    # ComfyUI workflow generation
    # ------------------------------------------------------------------

    async def generate_comfyui_workflow(self, description: str) -> dict:
        """
        Generate a ComfyUI API-format workflow JSON for the given description.

        Args:
            description: Natural-language description of the desired workflow
                         (e.g. "txt2img with DreamShaper for fantasy art, 768x512").

        Returns:
            Parsed workflow dict, or an empty dict on failure.
        """
        prompt = (
            f"Generate a ComfyUI API-format workflow JSON for:\n{description}\n\n"
            "Return ONLY the JSON object, no explanations."
        )
        logger.info("Generating ComfyUI workflow for: %s", description[:80])

        raw = await self._ollama.run_coder(prompt=prompt, system=self._WORKFLOW_SYSTEM)
        return self._parse_json_safe(raw) or {}

    # ------------------------------------------------------------------
    # Workflow debugging
    # ------------------------------------------------------------------

    async def debug_workflow(self, workflow_dict: dict, error_message: str) -> dict:
        """
        Diagnose and fix a broken ComfyUI workflow.

        Args:
            workflow_dict: The workflow that produced an error.
            error_message: The error string from ComfyUI.

        Returns:
            Dict with keys ``analysis`` (str) and ``fixed_workflow`` (dict).
            On failure returns ``{"analysis": "<error>", "fixed_workflow": {}}``.
        """
        prompt = (
            f"Error message:\n{error_message}\n\n"
            f"Broken workflow:\n{json.dumps(workflow_dict, indent=2)}\n\n"
            "Diagnose the issue and return a fixed workflow."
        )
        logger.info("Debugging workflow, error: %s", error_message[:120])

        raw = await self._ollama.run_coder(prompt=prompt, system=self._DEBUG_SYSTEM)
        parsed = self._parse_json_safe(raw)
        if parsed and "fixed_workflow" in parsed:
            return parsed
        # If we couldn't parse structured output, return analysis as text
        return {"analysis": raw, "fixed_workflow": {}}

    # ------------------------------------------------------------------
    # Prompt improvement
    # ------------------------------------------------------------------

    async def suggest_prompt_improvements(self, prompt: str, issues: list) -> dict:
        """
        Suggest prompt improvements based on image review issues.

        Args:
            prompt: The original positive prompt used for generation.
            issues: List of issue strings from the ImageReviewer.

        Returns:
            Dict with keys ``improved_prompt`` (str) and ``changes`` (list of str).
        """
        issues_text = "\n".join(f"- {i}" for i in issues) if issues else "No specific issues listed."
        user_prompt = (
            f"Original prompt:\n{prompt}\n\n"
            f"Issues detected:\n{issues_text}\n\n"
            "Suggest an improved prompt that addresses these issues."
        )
        logger.info("Suggesting prompt improvements for %d issues", len(issues))

        raw = await self._ollama.run_coder(prompt=user_prompt, system=self._PROMPT_IMPROVE_SYSTEM)
        parsed = self._parse_json_safe(raw)
        if parsed and "improved_prompt" in parsed:
            return parsed
        return {"improved_prompt": prompt, "changes": ["Improvement suggestion unavailable."]}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json_safe(text: str) -> Optional[dict]:
        """Strip markdown fences and parse JSON, returning None on failure."""
        import re
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return None
