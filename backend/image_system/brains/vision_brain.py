"""
Vision Brain for the Mini Assistant image system.

Wraps qwen2.5vl:7b for image understanding, style comparison, and issue detection.
"""

import base64
import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class VisionBrain:
    """
    Provides image-understanding capabilities via qwen2.5vl:7b.

    Images are sent as base64-encoded strings inside Ollama's message format.
    """

    _ANALYSIS_SYSTEM = (
        "You are an expert image analyst. Describe images in precise, detailed terms. "
        "Focus on composition, subject, style, lighting, colour palette, and mood."
    )

    _COMPARE_SYSTEM = (
        "You are an expert art style comparator. "
        "Given two images (reference first, then generated), evaluate how closely "
        "the generated image matches the reference in terms of: art style, colour palette, "
        "mood, line quality, and overall aesthetic. "
        "Return JSON: {\"similarity_score\": 0.0-1.0, \"style_match\": \"...\", "
        "\"differences\": [\"...\"], \"recommendations\": [\"...\"]}"
    )

    _ISSUES_SYSTEM = (
        "You are an expert at detecting defects in AI-generated images. "
        "Look for: anatomical errors (extra fingers, deformed hands, wrong proportions), "
        "composition issues (bad framing, cluttered, off-balance), "
        "technical issues (blurriness, noise, artifacts, colour banding). "
        "Return JSON: {\"anatomy_issues\": [\"...\"], \"composition_issues\": [\"...\"], "
        "\"technical_issues\": [\"...\"], \"severity\": \"none|minor|moderate|severe\"}"
    )

    def __init__(self) -> None:
        from ..services.ollama_client import OllamaClient
        self._ollama = OllamaClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(
        self,
        image_bytes: bytes,
        question: str,
        detail_level: str = "standard",
    ) -> str:
        """
        Answer a question about an image.

        Args:
            image_bytes: Raw image bytes (PNG/JPEG).
            question: Question or instruction about the image.
            detail_level: "brief", "standard", or "detailed".

        Returns:
            Text answer from the vision model.
        """
        system = self._analysis_system_for_detail(detail_level)
        image_b64 = self._encode_image(image_bytes)

        logger.info("VisionBrain.analyze detail=%s question='%s...'", detail_level, question[:60])
        return await self._ollama.run_vision(
            prompt=question, system=system, images=[image_b64]
        )

    async def compare_style(
        self, reference_bytes: bytes, generated_bytes: bytes
    ) -> dict:
        """
        Compare a reference image against a generated image for style similarity.

        Args:
            reference_bytes: Raw bytes of the reference image.
            generated_bytes: Raw bytes of the generated image.

        Returns:
            Dict with similarity_score, style_match, differences, recommendations.
        """
        ref_b64 = self._encode_image(reference_bytes)
        gen_b64 = self._encode_image(generated_bytes)

        prompt = (
            "Compare these two images. The first is the reference; the second is the generated result. "
            "Return your JSON evaluation."
        )

        logger.info("VisionBrain.compare_style")
        raw = await self._ollama.run_vision(
            prompt=prompt,
            system=self._COMPARE_SYSTEM,
            images=[ref_b64, gen_b64],
        )

        parsed = self._parse_json_safe(raw)
        if parsed:
            return parsed

        # Graceful degradation
        return {
            "similarity_score": 0.5,
            "style_match": "Comparison unavailable",
            "differences": [],
            "recommendations": [],
        }

    async def detect_issues(self, image_bytes: bytes) -> dict:
        """
        Detect anatomy, composition, and technical issues in an image.

        Args:
            image_bytes: Raw image bytes.

        Returns:
            Dict with anatomy_issues, composition_issues, technical_issues, severity.
        """
        image_b64 = self._encode_image(image_bytes)
        prompt = "Analyse this image for defects and issues. Return your JSON report."

        logger.info("VisionBrain.detect_issues")
        raw = await self._ollama.run_vision(
            prompt=prompt,
            system=self._ISSUES_SYSTEM,
            images=[image_b64],
        )

        parsed = self._parse_json_safe(raw)
        if parsed:
            return parsed

        return {
            "anatomy_issues": [],
            "composition_issues": [],
            "technical_issues": ["Issue detection unavailable"],
            "severity": "none",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_image(image_bytes: bytes) -> str:
        """Return the base64-encoded string representation of image bytes."""
        return base64.b64encode(image_bytes).decode("utf-8")

    @staticmethod
    def _analysis_system_for_detail(detail_level: str) -> str:
        """Return a system prompt adjusted for the requested detail level."""
        if detail_level == "brief":
            return (
                "You are an image analyst. Give a concise 1-2 sentence description. "
                "Be direct and factual."
            )
        if detail_level == "detailed":
            return (
                "You are an expert image analyst. Provide an exhaustive analysis covering: "
                "subject matter, composition, lighting, colour palette, mood, artistic style, "
                "technical quality, and notable details. Be thorough."
            )
        # standard
        return VisionBrain._ANALYSIS_SYSTEM

    @staticmethod
    def _parse_json_safe(text: str) -> Optional[dict]:
        """Strip markdown fences and parse JSON, returning None on failure."""
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
