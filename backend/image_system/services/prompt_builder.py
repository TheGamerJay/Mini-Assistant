"""
Prompt engineering service for the Mini Assistant image system.

Transforms raw user requests into optimised positive/negative prompts for each
model family, optionally using the coder brain to rewrite the prompt.
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    Builds positive and negative prompts tailored to each checkpoint type.

    The main entry point is :meth:`build`, which calls the Ollama coder brain
    to semantically expand the user request and then appends style-specific
    quality tokens.
    """

    # ------------------------------------------------------------------
    # Quality tag libraries (prepended to positive prompt)
    # ------------------------------------------------------------------

    _QUALITY_TAGS: dict = {
        "anime": "masterpiece, best quality, highres, detailed anime art, perfect lighting",
        "realistic": "RAW photo, DSLR, 8k, sharp focus, professional photography, photorealistic",
        "fantasy": "concept art, digital painting, epic fantasy illustration, volumetric lighting, artstation",
        "flux": "ultra detailed, professional, 8k resolution",
    }

    # Per-checkpoint additional style tokens that complement the quality tags
    _CHECKPOINT_STYLE_TOKENS: dict = {
        "anime_general": "intricate anime details, vibrant colours, smooth shading",
        "anime_shonen": "dynamic action, energy lines, fierce expression, motion blur",
        "anime_seinen": "dark atmosphere, moody lighting, cinematic framing, detailed shadows",
        "anime_shojo": "soft pastel colours, floral accents, gentle smile, romantic atmosphere",
        "anime_slice_of_life": "warm lighting, cozy setting, everyday charm, natural poses",
        "realistic": "natural skin texture, subsurface scattering, sharp focus",
        "fantasy": "epic scale, dramatic lighting, intricate armour or robes, glowing magical effects",
        "flux_premium": "ultra sharp, flawless detail, professional composition",
    }

    # ------------------------------------------------------------------
    # Negative prompt libraries
    # ------------------------------------------------------------------

    _NEGATIVE_PROMPTS: dict = {
        "anime": (
            "lowres, bad anatomy, bad hands, extra fingers, missing fingers, "
            "cropped, worst quality, watermark, signature, text, username, "
            "blurry, jpeg artifacts, deformed, ugly, error"
        ),
        "realistic": (
            "cartoon, anime, illustration, painting, sketch, watermark, deformed, "
            "blurry, ugly, bad anatomy, duplicate, morbid, mutilated, extra limbs, "
            "poorly drawn face, poorly drawn hands, lowres, worst quality"
        ),
        "fantasy": (
            "photo, realistic photograph, lowres, bad anatomy, watermark, amateur, "
            "poorly drawn, blurry, ugly, extra limbs, missing limbs, text, signature"
        ),
        "flux": (
            "blurry, low quality, watermark, text, signature, deformed, ugly"
        ),
    }

    # ------------------------------------------------------------------
    # LoRA suggestion notes (informational only, not injected into prompts)
    # ------------------------------------------------------------------

    _LORA_SUGGESTIONS: dict = {
        "anime_general": "Consider: detail_tweaker_xl LoRA for extra sharpness",
        "anime_shonen": "Consider: dynamic_poses LoRA or action_lines LoRA",
        "anime_seinen": "Consider: dark_fantasy_xl LoRA for moody cinematic feel",
        "anime_shojo": "Consider: soft_lighting LoRA or pastel_style LoRA",
        "anime_slice_of_life": "Consider: school_scene LoRA or cafe_background LoRA",
        "realistic": "Consider: add_detail LoRA or face_detail LoRA",
        "fantasy": "Consider: concept_art LoRA or epic_fantasy LoRA",
        "flux_premium": "FLUX models do not use LoRAs in standard pipelines",
    }

    def __init__(self) -> None:
        # Import here to avoid circular imports at module load time
        from .ollama_client import OllamaClient
        self._ollama = OllamaClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def build(self, user_request: str, route_result: dict) -> dict:
        """
        Main build method: use the coder brain to expand the user's request,
        then attach style-specific quality and negative tokens.

        Args:
            user_request: Raw user message (e.g. "draw a shonen warrior").
            route_result: RouteResult dict from RouterBrain.

        Returns:
            Dict with keys ``positive`` and ``negative``.
        """
        style_family: str = route_result.get("style_family", "anime")
        checkpoint_key: str = route_result.get("selected_checkpoint", "anime_general")
        visual_mode: str = route_result.get("visual_mode", "portrait")

        # Ask the coder brain to expand the artistic description
        expanded = await self._expand_with_coder(user_request, style_family, checkpoint_key)

        positive = self.generate_positive(expanded, style_family, visual_mode, checkpoint_key)
        negative = self.generate_negative(style_family, checkpoint_key)

        lora_note = self._LORA_SUGGESTIONS.get(checkpoint_key, "")
        if lora_note:
            logger.debug("LoRA suggestion for %s: %s", checkpoint_key, lora_note)

        return {"positive": positive, "negative": negative}

    def generate_positive(
        self,
        user_request: str,
        style_family: str,
        visual_mode: str,
        checkpoint_key: str,
    ) -> str:
        """
        Construct the positive prompt from quality tags + checkpoint style tokens
        + the (potentially expanded) user request.

        Args:
            user_request: Core scene description (may already be LLM-expanded).
            style_family: One of "anime", "realistic", "fantasy", "flux".
            visual_mode: One of "portrait", "landscape", "square", "action", etc.
            checkpoint_key: Key from model_registry (e.g. "anime_shonen").

        Returns:
            Full positive prompt string.
        """
        # Normalise family name so flux checkpoints resolve correctly
        family_key = "flux" if "flux" in checkpoint_key else style_family
        quality_tags = self._QUALITY_TAGS.get(family_key, self._QUALITY_TAGS["anime"])
        style_tokens = self._CHECKPOINT_STYLE_TOKENS.get(checkpoint_key, "")
        visual_token = self._visual_mode_token(visual_mode)

        parts = [quality_tags]
        if style_tokens:
            parts.append(style_tokens)
        parts.append(user_request.strip())
        if visual_token:
            parts.append(visual_token)

        positive = ", ".join(p for p in parts if p)
        logger.debug(
            "generate_positive style=%s checkpoint=%s len=%d",
            style_family, checkpoint_key, len(positive),
        )
        return positive

    def generate_negative(self, style_family: str, checkpoint_key: str) -> str:
        """
        Return the appropriate negative prompt for the given style.

        Args:
            style_family: One of "anime", "realistic", "fantasy".
            checkpoint_key: For future per-checkpoint overrides.

        Returns:
            Negative prompt string.
        """
        # flux always uses the terse flux negative
        if "flux" in checkpoint_key:
            return self._NEGATIVE_PROMPTS["flux"]
        return self._NEGATIVE_PROMPTS.get(style_family, self._NEGATIVE_PROMPTS["anime"])

    def size_for_visual_mode(
        self, visual_mode: str, checkpoint_type: str, quality: str = "balanced"
    ) -> Tuple[int, int]:
        """
        Return (width, height) for the given visual mode and checkpoint type.

        Args:
            visual_mode: Layout hint from the router ("portrait", "landscape", etc.).
            checkpoint_type: "SD1.5", "SDXL", or "FLUX".
            quality: Ignored here but reserved for future scaling logic.

        Returns:
            (width, height) tuple in pixels.
        """
        size_map = {
            "SD1.5": {
                "portrait": (512, 768),
                "landscape": (768, 512),
                "square": (512, 512),
                "action": (640, 512),
                "cinematic": (768, 432),
                "casual": (512, 512),
            },
            "SDXL": {
                "portrait": (832, 1216),
                "landscape": (1216, 832),
                "square": (1024, 1024),
                "action": (1024, 768),
                "cinematic": (1280, 720),
                "casual": (1024, 1024),
            },
            "FLUX": {
                "portrait": (768, 1024),
                "landscape": (1024, 768),
                "square": (1024, 1024),
                "action": (1024, 768),
                "cinematic": (1280, 720),
                "casual": (1024, 1024),
            },
        }
        defaults = size_map.get(checkpoint_type, size_map["SD1.5"])
        return defaults.get(visual_mode, defaults["portrait"])

    def steps_for_quality(self, quality: str, checkpoint_type: str) -> int:
        """
        Return the recommended number of sampling steps.

        Args:
            quality: "fast", "balanced", or "high".
            checkpoint_type: "SD1.5", "SDXL", or "FLUX".

        Returns:
            Integer step count.
        """
        # FLUX uses very few steps natively
        if checkpoint_type == "FLUX":
            return {"fast": 4, "balanced": 4, "high": 8}.get(quality, 4)

        return {
            "fast": 20,
            "balanced": 28,
            "high": 40,
        }.get(quality, 28)

    def cfg_for_style(self, style_family: str) -> float:
        """
        Return a sensible CFG scale for the given style family.

        Args:
            style_family: "anime", "realistic", "fantasy", or "flux".

        Returns:
            CFG scale float.
        """
        return {
            "anime": 7.0,
            "realistic": 7.0,
            "fantasy": 7.5,
            "flux": 1.0,  # FLUX Schnell ignores CFG above ~1
        }.get(style_family, 7.0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _expand_with_coder(
        self,
        user_request: str,
        style_family: str,
        checkpoint_key: str,
    ) -> str:
        """
        Ask the coder brain to rewrite the user request as a vivid image prompt.

        Falls back to the original request on any error.
        """
        style_hint = {
            "anime": "anime illustration",
            "realistic": "photorealistic photograph",
            "fantasy": "epic fantasy digital painting",
        }.get(style_family, "illustration")

        system = (
            "You are an expert Stable Diffusion prompt engineer. "
            "Rewrite the user's scene description as a concise, comma-separated "
            f"list of descriptive tokens suitable for a {style_hint}. "
            "Do NOT include quality tags like 'masterpiece' — those are added separately. "
            "Output ONLY the token list, no explanation, no markdown."
        )
        prompt = f"Rewrite this as vivid image tokens:\n{user_request}"

        try:
            expanded = await self._ollama.run_coder(prompt, system=system)
            # Strip any accidental surrounding quotes or newlines
            expanded = expanded.strip().strip('"').strip("'")
            if not expanded:
                return user_request
            return expanded
        except Exception as exc:
            logger.warning("Coder expansion failed, using raw request: %s", exc)
            return user_request

    @staticmethod
    def _visual_mode_token(visual_mode: str) -> str:
        """Return an extra compositional token for the visual mode."""
        tokens = {
            "portrait": "upper body, portrait composition",
            "landscape": "wide shot, establishing shot",
            "action": "dynamic angle, motion, action shot",
            "cinematic": "cinematic composition, widescreen",
            "casual": "medium shot",
            "square": "",
        }
        return tokens.get(visual_mode, "")
