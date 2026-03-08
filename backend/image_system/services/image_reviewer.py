"""
Vision-based image review service for the Mini Assistant image system.

Uses qwen2.5vl:7b via OllamaClient to score generated images and decide
whether a retry is warranted.
"""

import base64
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Default review result returned when vision analysis fails
_DEFAULT_REVIEW: dict = {
    "quality_score": 0.5,
    "style_match": 0.5,
    "anatomy_score": 0.5,
    "composition_score": 0.5,
    "issues": ["vision review unavailable"],
    "retry_recommended": False,
    "retry_reason": None,
    "alt_checkpoint": None,
    "alt_workflow": None,
    "confidence": 0.0,
}

_REVIEWER_SYSTEM_PROMPT = """\
You are an expert AI image quality reviewer specialising in Stable Diffusion outputs.
Your role is to objectively evaluate generated images and return a structured JSON report.

Evaluation criteria:
- quality_score (0.0-1.0): Overall technical quality (sharpness, detail, noise level).
- style_match (0.0-1.0): How well the image matches the intended style (anime/realistic/fantasy).
- anatomy_score (0.0-1.0): Correctness of human/character anatomy (hands, faces, proportions).
- composition_score (0.0-1.0): Balance, framing, focal point quality.
- issues (list of strings): Specific problems observed (e.g. "malformed hand", "blurry background").
- retry_recommended (bool): True only if quality_score < 0.6 OR anatomy_score < 0.5.
- retry_reason (string or null): Brief explanation if retry is recommended.
- alt_checkpoint (string or null): Suggest a different checkpoint key only if style is fundamentally wrong.
- alt_workflow (string or null): Suggest a different workflow key only if framing is badly wrong.
- confidence (0.0-1.0): Your confidence in this evaluation.

Respond with ONLY valid JSON matching the schema above. No markdown, no explanation."""


class ImageReviewer:
    """
    Evaluates generated images using the vision brain (qwen2.5vl:7b).

    Methods are async coroutines. Construct one instance and reuse it.
    """

    def __init__(self) -> None:
        from .ollama_client import OllamaClient
        self._ollama = OllamaClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def review_image(
        self,
        image_bytes: bytes,
        original_request: str,
        route_result: dict,
    ) -> dict:
        """
        Score a generated image against the original request and routing context.

        Args:
            image_bytes: Raw PNG/JPEG bytes of the generated image.
            original_request: The user's original text request.
            route_result: The RouteResult dict so we know the intended style.

        Returns:
            Review dict with quality_score, style_match, anatomy_score,
            composition_score, issues, retry_recommended, retry_reason,
            alt_checkpoint, alt_workflow, confidence.
        """
        style_family = route_result.get("style_family", "anime")
        checkpoint = route_result.get("selected_checkpoint", "anime_general")

        image_b64 = self._encode_image(image_bytes)

        prompt = (
            f"Original request: \"{original_request}\"\n"
            f"Intended style family: {style_family}\n"
            f"Checkpoint used: {checkpoint}\n\n"
            "Please review the attached image and return your JSON evaluation."
        )

        try:
            raw_response = await self._ollama.run_vision(
                prompt=prompt,
                system=_REVIEWER_SYSTEM_PROMPT,
                images=[image_b64],
            )
            review = self._parse_review(raw_response)
        except Exception as exc:
            logger.warning("Image review failed: %s. Returning default.", exc)
            review = dict(_DEFAULT_REVIEW)

        logger.info(
            "Review complete: quality=%.2f style=%.2f anatomy=%.2f retry=%s",
            review.get("quality_score", 0),
            review.get("style_match", 0),
            review.get("anatomy_score", 0),
            review.get("retry_recommended", False),
        )
        return review

    async def analyze_reference(self, image_bytes: bytes) -> dict:
        """
        Analyse a reference image to extract style characteristics.

        Useful for img2img style-matching workflows.

        Args:
            image_bytes: Raw bytes of the reference image.

        Returns:
            Dict with keys: art_style, dominant_colors, mood, composition,
            suggested_checkpoint, suggested_workflow, description.
        """
        image_b64 = self._encode_image(image_bytes)
        system = (
            "You are an expert art style analyst. Examine the provided image and "
            "return a JSON object describing its visual characteristics. "
            "Keys: art_style (string), dominant_colors (list of strings), "
            "mood (string), composition (string), "
            "suggested_checkpoint (one of: anime_general, anime_shonen, anime_seinen, "
            "anime_shojo, anime_slice_of_life, realistic, fantasy, flux_premium), "
            "suggested_workflow (string), description (one-sentence summary). "
            "Return ONLY valid JSON."
        )
        prompt = "Analyse the style of this reference image."

        default_analysis = {
            "art_style": "unknown",
            "dominant_colors": [],
            "mood": "neutral",
            "composition": "unknown",
            "suggested_checkpoint": "anime_general",
            "suggested_workflow": "anime_general",
            "description": "Reference image analysis unavailable.",
        }

        try:
            raw = await self._ollama.run_vision(prompt=prompt, system=system, images=[image_b64])
            analysis = self._parse_json_safe(raw)
            if not analysis:
                return default_analysis
            return {**default_analysis, **analysis}
        except Exception as exc:
            logger.warning("Reference analysis failed: %s", exc)
            return default_analysis

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_image(image_bytes: bytes) -> str:
        """Return a base64-encoded string of the image bytes."""
        return base64.b64encode(image_bytes).decode("utf-8")

    def _parse_review(self, raw: str) -> dict:
        """
        Parse the vision model's JSON response into a validated review dict.

        Falls back to the default review on any parse error.
        """
        parsed = self._parse_json_safe(raw)
        if not parsed:
            logger.warning("Could not parse review JSON, using default. Raw: %s", raw[:200])
            return dict(_DEFAULT_REVIEW)

        # Clamp scores to [0, 1]
        for key in ("quality_score", "style_match", "anatomy_score", "composition_score", "confidence"):
            if key in parsed:
                try:
                    parsed[key] = max(0.0, min(1.0, float(parsed[key])))
                except (TypeError, ValueError):
                    parsed[key] = _DEFAULT_REVIEW[key]

        # Ensure lists
        if not isinstance(parsed.get("issues"), list):
            parsed["issues"] = []

        # Ensure bool
        if "retry_recommended" in parsed:
            parsed["retry_recommended"] = bool(parsed["retry_recommended"])

        # Auto-set retry if scores are critically low
        if (
            parsed.get("quality_score", 1.0) < 0.6
            or parsed.get("anatomy_score", 1.0) < 0.5
        ):
            parsed["retry_recommended"] = True
            if not parsed.get("retry_reason"):
                parsed["retry_reason"] = "Low quality or anatomy score detected automatically."

        return {**_DEFAULT_REVIEW, **parsed}

    @staticmethod
    def _parse_json_safe(text: str) -> Optional[dict]:
        """Attempt to parse JSON from text, stripping markdown fences if present."""
        text = text.strip()
        # Strip ```json ... ``` fences
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON object from surrounding text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
        return None
