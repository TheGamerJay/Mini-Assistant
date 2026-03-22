"""
Coding Brain for the Mini Assistant image system.

Uses Claude claude-sonnet-4-6 for coding tasks, ComfyUI workflow generation,
workflow debugging, and prompt improvement suggestions.

[MODEL ROUTER] coding → Claude claude-sonnet-4-6
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_CODING_MODEL = "claude-sonnet-4-6"


class CodingBrain:
    """
    Specialised brain for code-related tasks using Claude claude-sonnet-4-6.

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
        self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    def _get_client(self):
        import anthropic
        return anthropic.AsyncAnthropic(api_key=self._api_key)

    # ------------------------------------------------------------------
    # General coding
    # ------------------------------------------------------------------

    async def run(self, task: str, context: Optional[str] = None) -> str:
        """
        Run a general coding task through Claude claude-sonnet-4-6.

        Args:
            task: Description of the coding task or question.
            context: Optional additional context (e.g. existing code).

        Returns:
            The model's text response.
        """
        prompt = task
        if context:
            prompt = f"Context:\n{context}\n\nTask:\n{task}"

        logger.info(
            "[MODEL ROUTER] coding → Claude %s | task='%s...'",
            _CODING_MODEL, task[:60],
        )

        client = self._get_client()
        response = await client.messages.create(
            model=_CODING_MODEL,
            max_tokens=4096,
            system=self._GENERAL_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    # ------------------------------------------------------------------
    # ComfyUI workflow generation
    # ------------------------------------------------------------------

    async def generate_comfyui_workflow(self, description: str) -> dict:
        """
        Generate a ComfyUI API-format workflow JSON for the given description.
        """
        prompt = (
            f"Generate a ComfyUI API-format workflow JSON for:\n{description}\n\n"
            "Return ONLY the JSON object, no explanations."
        )
        logger.info(
            "[MODEL ROUTER] workflow_gen → Claude %s | desc='%s...'",
            _CODING_MODEL, description[:80],
        )

        client = self._get_client()
        response = await client.messages.create(
            model=_CODING_MODEL,
            max_tokens=2048,
            system=self._WORKFLOW_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        return self._parse_json_safe(raw) or {}

    # ------------------------------------------------------------------
    # Workflow debugging
    # ------------------------------------------------------------------

    async def debug_workflow(self, workflow_dict: dict, error_message: str) -> dict:
        """
        Diagnose and fix a broken ComfyUI workflow.
        """
        prompt = (
            f"Error message:\n{error_message}\n\n"
            f"Broken workflow:\n{json.dumps(workflow_dict, indent=2)}\n\n"
            "Diagnose the issue and return a fixed workflow."
        )
        logger.info(
            "[MODEL ROUTER] workflow_debug → Claude %s | error='%s...'",
            _CODING_MODEL, error_message[:120],
        )

        client = self._get_client()
        response = await client.messages.create(
            model=_CODING_MODEL,
            max_tokens=2048,
            system=self._DEBUG_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        parsed = self._parse_json_safe(raw)
        if parsed and "fixed_workflow" in parsed:
            return parsed
        return {"analysis": raw, "fixed_workflow": {}}

    # ------------------------------------------------------------------
    # Prompt improvement
    # ------------------------------------------------------------------

    async def suggest_prompt_improvements(self, prompt: str, issues: list) -> dict:
        """
        Suggest prompt improvements based on image review issues.
        """
        issues_text = "\n".join(f"- {i}" for i in issues) if issues else "No specific issues listed."
        user_prompt = (
            f"Original prompt:\n{prompt}\n\n"
            f"Issues detected:\n{issues_text}\n\n"
            "Suggest an improved prompt that addresses these issues."
        )
        logger.info(
            "[MODEL ROUTER] prompt_improve → Claude %s | issues=%d",
            _CODING_MODEL, len(issues),
        )

        client = self._get_client()
        response = await client.messages.create(
            model=_CODING_MODEL,
            max_tokens=512,
            system=self._PROMPT_IMPROVE_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = response.content[0].text
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
