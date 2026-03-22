"""
Vision Brain for the Mini Assistant image system.

Uses OpenAI GPT-4o for image understanding, style comparison, and issue detection.

[MODEL ROUTER] image_analysis → OpenAI GPT-4o
"""

import base64
import logging
import os
from typing import Optional

from ..utils.json_validator import extract_json_from_text

logger = logging.getLogger(__name__)

_VISION_MODEL = "gpt-4o"


class VisionBrain:
    """
    Provides image-understanding capabilities via OpenAI GPT-4o.

    Images are sent as base64-encoded data URLs in the OpenAI message format.
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
        self._api_key = os.environ.get("OPENAI_API_KEY", "")

    def _get_client(self):
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=self._api_key)

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
        Answer a question about an image using GPT-4o vision.

        Args:
            image_bytes: Raw image bytes (PNG/JPEG).
            question: Question or instruction about the image.
            detail_level: "brief", "standard", or "detailed".

        Returns:
            Text answer from the vision model.
        """
        system = self._analysis_system_for_detail(detail_level)
        image_b64 = self._encode_image(image_bytes)

        logger.info(
            "[MODEL ROUTER] image_analysis → OpenAI %s | detail=%s question='%s...'",
            _VISION_MODEL, detail_level, question[:60],
        )

        client = self._get_client()
        response = await client.chat.completions.create(
            model=_VISION_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}", "detail": "high"},
                    },
                    {"type": "text", "text": question},
                ]},
            ],
            max_tokens=1500,
        )
        return response.choices[0].message.content or ""

    async def compare_style(
        self, reference_bytes: bytes, generated_bytes: bytes
    ) -> dict:
        """
        Compare a reference image against a generated image for style similarity.

        Returns:
            Dict with similarity_score, style_match, differences, recommendations.
        """
        ref_b64 = self._encode_image(reference_bytes)
        gen_b64 = self._encode_image(generated_bytes)

        logger.info("[MODEL ROUTER] image_compare → OpenAI %s", _VISION_MODEL)

        client = self._get_client()
        response = await client.chat.completions.create(
            model=_VISION_MODEL,
            messages=[
                {"role": "system", "content": self._COMPARE_SYSTEM},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{ref_b64}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{gen_b64}"}},
                    {"type": "text", "text": "Compare these two images. The first is the reference; the second is the generated result. Return your JSON evaluation."},
                ]},
            ],
            max_tokens=800,
        )
        raw = response.choices[0].message.content or ""
        parsed = self._parse_json_safe(raw)
        if parsed:
            return parsed

        return {
            "similarity_score": 0.5,
            "style_match": "Comparison unavailable",
            "differences": [],
            "recommendations": [],
        }

    async def detect_issues(self, image_bytes: bytes) -> dict:
        """
        Detect anatomy, composition, and technical issues in an image.

        Returns:
            Dict with anatomy_issues, composition_issues, technical_issues, severity.
        """
        image_b64 = self._encode_image(image_bytes)

        logger.info("[MODEL ROUTER] image_detect_issues → OpenAI %s", _VISION_MODEL)

        client = self._get_client()
        response = await client.chat.completions.create(
            model=_VISION_MODEL,
            messages=[
                {"role": "system", "content": self._ISSUES_SYSTEM},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    {"type": "text", "text": "Analyse this image for defects and issues. Return your JSON report."},
                ]},
            ],
            max_tokens=600,
        )
        raw = response.choices[0].message.content or ""
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
        return VisionBrain._ANALYSIS_SYSTEM

    @staticmethod
    def _parse_json_safe(text: str) -> Optional[dict]:
        """Extract and parse JSON from model output, returning None on failure."""
        return extract_json_from_text(text)
