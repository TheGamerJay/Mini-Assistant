"""
vision.py – Vision Brain
─────────────────────────
Handles image understanding: screenshots, photos, diagrams, UI analysis.
Accepts images as base64 strings or file paths (auto-converted).
"""

import base64
import logging
from pathlib import Path

from .base import BaseBrain
from ..config import MODELS

logger = logging.getLogger(__name__)


def _load_image(source: str) -> str:
    """Return base64-encoded image. Source can be a file path or existing b64 string."""
    path = Path(source)
    if path.exists():
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    # Assume it's already base64
    return source


class VisionBrain(BaseBrain):
    name = "vision"
    system_prompt = """You are an expert vision AI assistant with deep perceptual abilities.

Your capabilities:
- Describe images in precise, structured detail
- Read and extract text from screenshots (OCR)
- Analyse UI layouts and suggest improvements
- Identify objects, people, scenes, charts, and diagrams
- Compare multiple images and note differences
- Debug visual errors shown in screenshots

When analysing screenshots, always note:
1. What application / website is shown
2. Any error messages or warnings visible
3. The current state of the UI
4. What the user might be trying to do"""

    def __init__(self):
        super().__init__(model=MODELS["vision"])

    def describe(self, image_source: str, question: str = "Describe this image in detail.") -> str:
        img_b64 = _load_image(image_source)
        return self.respond(question, images=[img_b64])

    def read_text(self, image_source: str) -> str:
        img_b64 = _load_image(image_source)
        return self.respond(
            "Extract and return ALL text visible in this image. Preserve formatting where possible.",
            images=[img_b64],
        )

    def analyze_ui(self, image_source: str) -> str:
        img_b64 = _load_image(image_source)
        return self.respond(
            "Analyse this UI screenshot. Describe the layout, identify any issues or errors, "
            "and suggest improvements to the user experience.",
            images=[img_b64],
        )

    def debug_screenshot(self, image_source: str, context: str = "") -> str:
        img_b64 = _load_image(image_source)
        prompt = "Look at this screenshot and identify any errors, warnings, or problems."
        if context:
            prompt += f"\n\nAdditional context: {context}"
        return self.respond(prompt, images=[img_b64])
