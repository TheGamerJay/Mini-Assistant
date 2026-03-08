"""
Router Brain for the Mini Assistant image system.

Classifies user requests using qwen3:14b (with qwen2.5:7b fallback) and returns
a structured RouteResult dict that drives checkpoint and workflow selection.
"""

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intent constants
# ---------------------------------------------------------------------------

INTENT_CHAT = "chat"
INTENT_CODING = "coding"
INTENT_IMAGE_GENERATION = "image_generation"
INTENT_IMAGE_EDIT = "image_edit"
INTENT_IMAGE_ANALYSIS = "image_analysis"
INTENT_PLANNING = "planning"

VALID_INTENTS = {
    INTENT_CHAT, INTENT_CODING, INTENT_IMAGE_GENERATION,
    INTENT_IMAGE_EDIT, INTENT_IMAGE_ANALYSIS, INTENT_PLANNING,
}


class RouterBrain:
    """
    Classifies user requests and decides which image checkpoint + workflow to use.

    Routing priority (highest to lowest):
    1. qwen3:14b LLM classification with JSON mode.
    2. qwen2.5:7b fallback on parse failure.
    3. Local keyword matching as final safety net.
    """

    # ------------------------------------------------------------------
    # System prompt for the LLM
    # ------------------------------------------------------------------

    SYSTEM_PROMPT: str = """\
You are the routing brain of an AI assistant with image generation capabilities.

Your ONLY job is to classify the user's request and return a strict JSON object.
No markdown. No explanation. No extra text. ONLY the JSON object.

=== INTENT TYPES ===
- chat: casual conversation, questions, greetings, opinions, advice
- coding: write code, debug code, explain algorithms, programming questions
- image_generation: draw, generate, create, paint, illustrate, sketch any visual
- image_edit: edit, fix, modify, change, recolour an existing image
- image_analysis: describe, analyse, what is in, identify objects in an image
- planning: plan a project, make a schedule, brainstorm, outline

=== STYLE FAMILIES ===
- anime: any anime, manga, cartoon, 2D illustrated style
- realistic: photographs, DSLR, photorealistic, human portraits, product shots
- fantasy: concept art, epic fantasy, dragons, castles, RPG scenes, digital painting

=== ANIME GENRES ===
- shonen: battle, power-up, aura, energy, sword clash, tournament, rival, fierce
- seinen: dark, grim, mature, psychological, anti-hero, war, tragedy, melancholy
- shojo: romance, soft love, couple, flowers, pastel, magical girl, heartwarming
- slice_of_life: school, cafe, daily life, classroom, cozy, uniform, ordinary
- general: generic anime that does not fit the above

=== CHECKPOINT ROUTING RULES ===
Apply these rules in order (first match wins):

1. Keywords: ultra realistic, flux, premium quality, hyperrealistic 8k
   → checkpoint: flux_premium, workflow: flux_high_realism, style: realistic

2. Keywords: realistic, photo, dslr, portrait photography, cinematic photo, human skin, photograph, raw photo, bokeh, studio lighting
   → checkpoint: realistic, workflow: realistic_photo, style: realistic

3. Keywords: fantasy warrior, dragon, castle, magic, rpg, creature, epic cinematic, wizard, knight, mythical, dungeon, dark fantasy
   → checkpoint: fantasy, workflow: fantasy_cinematic, style: fantasy

4. Keywords: battle, aura, energy blast, sword clash, power up, shonen, combat, explosion, ki, chakra, berserker, tournament
   → checkpoint: anime_shonen, workflow: anime_shonen_action, style: anime, genre: shonen

5. Keywords: dark anime, grim, mature, emotional cinematic, serious warrior, seinen, psychological, anti-hero, tragedy, brutal, haunted
   → checkpoint: anime_seinen, workflow: anime_seinen_cinematic, style: anime, genre: seinen

6. Keywords: romance, shojo, soft love, elegant anime, couple, pretty anime, magical girl, flower, pastel, heartwarming
   → checkpoint: anime_shojo, workflow: anime_shojo_romance, style: anime, genre: shojo

7. Keywords: school, cafe, daily life, cozy anime, classroom, slice of life, everyday, uniform, convenience store
   → checkpoint: anime_slice_of_life, workflow: anime_slice_of_life, style: anime, genre: slice_of_life

8. Keywords: anime, manga, 2d, drawn, otaku, waifu, chibi, moe, kawaii, neko, fox girl, catgirl, isekai
   → checkpoint: anime_general, workflow: anime_general, style: anime, genre: general

=== VISUAL MODE ===
- portrait: character focused, single person, upper body or full body
- landscape: wide scene, environment, background heavy
- action: dynamic pose, movement, battle or sports
- cinematic: wide framing, moody, 16:9 feel
- casual: everyday, relaxed, medium shot
- square: no strong preference

=== OUTPUT FORMAT (strictly this JSON schema, no extra keys) ===
{
  "intent": "<one of the intent types>",
  "style_family": "<anime|realistic|fantasy|null>",
  "anime_genre": "<shonen|seinen|shojo|slice_of_life|general|null>",
  "visual_mode": "<portrait|landscape|action|cinematic|casual|square>",
  "needs_reference_analysis": false,
  "needs_upscale": false,
  "needs_face_detail": false,
  "selected_checkpoint": "<checkpoint key or null>",
  "selected_workflow": "<workflow key or null>",
  "anime_score": 0.0,
  "realism_score": 0.0,
  "fantasy_score": 0.0,
  "confidence": 0.0
}

Scores (anime_score, realism_score, fantasy_score) should sum to approximately 1.0.
confidence should reflect how certain you are about the routing decision (0.0-1.0).
"""

    def __init__(self) -> None:
        from ..services.ollama_client import OllamaClient
        self._ollama = OllamaClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def route(
        self, user_request: str, reference_image: Optional[bytes] = None
    ) -> dict:
        """
        Classify the user request and return a RouteResult dict.

        Tries qwen3:14b first; on failure falls back to qwen2.5:7b; final
        fallback is local keyword matching.

        Args:
            user_request: The raw user message.
            reference_image: Optional image bytes if the user attached one.

        Returns:
            Validated RouteResult dict.
        """
        prompt = self._build_prompt(user_request)

        # --- Primary: qwen3:14b ---
        try:
            raw = await self._ollama.run_router(prompt=prompt, system=self.SYSTEM_PROMPT)
            data = self._parse_json(raw)
            if data:
                result = self.validate_route(data)
                if result.get("confidence", 0) >= 0.3:
                    logger.info(
                        "Router (primary): intent=%s checkpoint=%s confidence=%.2f",
                        result["intent"], result.get("selected_checkpoint"), result["confidence"],
                    )
                    return result
        except Exception as exc:
            logger.warning("Primary router failed: %s", exc)

        # --- Fallback: qwen2.5:7b ---
        try:
            raw_fb = await self._ollama.run_router_fallback(
                prompt=prompt, system=self.SYSTEM_PROMPT
            )
            data_fb = self._parse_json(raw_fb)
            if data_fb:
                result_fb = self.validate_route(data_fb)
                logger.info(
                    "Router (fallback): intent=%s checkpoint=%s confidence=%.2f",
                    result_fb["intent"],
                    result_fb.get("selected_checkpoint"),
                    result_fb["confidence"],
                )
                return result_fb
        except Exception as exc:
            logger.warning("Fallback router failed: %s", exc)

        # --- Last resort: local keyword matching ---
        logger.warning("Both LLM routers failed; using keyword matching")
        return self._apply_keyword_rules(user_request)

    def validate_route(self, data: dict) -> dict:
        """
        Validate and normalise a raw router output dict.

        Fills sensible defaults for any missing or invalid fields.

        Args:
            data: Raw dict from the LLM.

        Returns:
            Normalised RouteResult dict.
        """
        intent = data.get("intent", INTENT_CHAT)
        if intent not in VALID_INTENTS:
            intent = INTENT_CHAT

        style_family = data.get("style_family") or None
        if style_family not in (None, "anime", "realistic", "fantasy"):
            style_family = None

        anime_genre = data.get("anime_genre") or None
        valid_genres = {"shonen", "seinen", "shojo", "slice_of_life", "general"}
        if anime_genre not in (None, *valid_genres):
            anime_genre = "general"

        visual_mode = data.get("visual_mode", "portrait")
        valid_modes = {"portrait", "landscape", "action", "cinematic", "casual", "square"}
        if visual_mode not in valid_modes:
            visual_mode = "portrait"

        # Apply keyword scoring as a second opinion on scores
        kw_scores = self._score_request_text(data.get("_original_request", ""))

        def _clamp(v: float) -> float:
            try:
                return max(0.0, min(1.0, float(v)))
            except (TypeError, ValueError):
                return 0.0

        anime_score = _clamp(data.get("anime_score", kw_scores["anime_score"]))
        realism_score = _clamp(data.get("realism_score", kw_scores["realism_score"]))
        fantasy_score = _clamp(data.get("fantasy_score", kw_scores["fantasy_score"]))
        confidence = _clamp(data.get("confidence", 0.5))

        selected_checkpoint = data.get("selected_checkpoint") or None
        selected_workflow = data.get("selected_workflow") or None

        # If checkpoint not provided for image intents, derive from style
        if intent == INTENT_IMAGE_GENERATION and not selected_checkpoint:
            selected_checkpoint, selected_workflow = self._derive_from_style(
                style_family, anime_genre
            )

        return {
            "intent": intent,
            "style_family": style_family,
            "anime_genre": anime_genre,
            "visual_mode": visual_mode,
            "needs_reference_analysis": bool(data.get("needs_reference_analysis", False)),
            "needs_upscale": bool(data.get("needs_upscale", False)),
            "needs_face_detail": bool(data.get("needs_face_detail", False)),
            "selected_checkpoint": selected_checkpoint,
            "selected_workflow": selected_workflow,
            "anime_score": anime_score,
            "realism_score": realism_score,
            "fantasy_score": fantasy_score,
            "confidence": confidence,
        }

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(self, user_request: str) -> str:
        """Build the full prompt string sent to the LLM."""
        return (
            f"User request: \"{user_request}\"\n\n"
            "Classify this request and return the JSON routing object."
        )

    # ------------------------------------------------------------------
    # Keyword-based routing (local fallback)
    # ------------------------------------------------------------------

    def _apply_keyword_rules(self, user_request: str) -> dict:
        """
        Local keyword matching used when LLM routing fails completely.

        Returns a RouteResult dict with intent and checkpoint derived
        purely from keyword presence.
        """
        text = user_request.lower()
        scores = self._score_request_text(text)

        # Detect non-image intents first
        intent = INTENT_IMAGE_GENERATION
        if any(kw in text for kw in ["write code", "python", "javascript", "debug", "function", "algorithm", "program"]):
            intent = INTENT_CODING
        elif any(kw in text for kw in ["what is", "who is", "explain", "tell me", "how does", "weather", "news"]):
            intent = INTENT_CHAT
        elif any(kw in text for kw in ["edit", "modify", "fix this image", "change the colour", "remove the"]):
            intent = INTENT_IMAGE_EDIT
        elif any(kw in text for kw in ["analyse this image", "describe this image", "what is in this", "identify"]):
            intent = INTENT_IMAGE_ANALYSIS

        # Image routing
        checkpoint, workflow, style_family, anime_genre, visual_mode = (
            "anime_general", "anime_general", "anime", "general", "portrait"
        )

        if any(kw in text for kw in ["ultra realistic", "flux", "premium quality"]):
            checkpoint, workflow = "flux_premium", "flux_high_realism"
            style_family, anime_genre = "realistic", None
        elif any(kw in text for kw in ["realistic", "photo", "dslr", "photograph", "raw photo", "bokeh"]):
            checkpoint, workflow = "realistic", "realistic_photo"
            style_family, anime_genre = "realistic", None
            visual_mode = "portrait"
        elif any(kw in text for kw in ["dragon", "castle", "magic", "rpg", "wizard", "knight", "dungeon", "fantasy"]):
            checkpoint, workflow = "fantasy", "fantasy_cinematic"
            style_family, anime_genre = "fantasy", None
            visual_mode = "landscape"
        elif any(kw in text for kw in ["battle", "aura", "energy", "sword clash", "power up", "shonen", "combat", "explosion"]):
            checkpoint, workflow = "anime_shonen", "anime_shonen_action"
            style_family, anime_genre = "anime", "shonen"
            visual_mode = "action"
        elif any(kw in text for kw in ["dark anime", "grim", "mature", "seinen", "psychological", "anti-hero", "tragedy"]):
            checkpoint, workflow = "anime_seinen", "anime_seinen_cinematic"
            style_family, anime_genre = "anime", "seinen"
            visual_mode = "cinematic"
        elif any(kw in text for kw in ["romance", "shojo", "soft love", "couple", "magical girl", "pastel", "flower"]):
            checkpoint, workflow = "anime_shojo", "anime_shojo_romance"
            style_family, anime_genre = "anime", "shojo"
        elif any(kw in text for kw in ["school", "cafe", "daily life", "classroom", "slice of life", "uniform", "cozy anime"]):
            checkpoint, workflow = "anime_slice_of_life", "anime_slice_of_life"
            style_family, anime_genre = "anime", "slice_of_life"

        if intent != INTENT_IMAGE_GENERATION:
            checkpoint = None
            workflow = None
            style_family = None
            anime_genre = None

        return {
            "intent": intent,
            "style_family": style_family,
            "anime_genre": anime_genre,
            "visual_mode": visual_mode,
            "needs_reference_analysis": False,
            "needs_upscale": False,
            "needs_face_detail": False,
            "selected_checkpoint": checkpoint,
            "selected_workflow": workflow,
            "anime_score": scores["anime_score"],
            "realism_score": scores["realism_score"],
            "fantasy_score": scores["fantasy_score"],
            "confidence": 0.6,  # keyword match is moderately confident
        }

    # ------------------------------------------------------------------
    # Keyword scoring
    # ------------------------------------------------------------------

    _ANIME_KEYWORDS = [
        "anime", "manga", "2d", "drawn", "otaku", "waifu", "chibi", "moe",
        "kawaii", "neko", "fox girl", "catgirl", "isekai", "shonen", "seinen",
        "shojo", "slice of life", "battle", "aura", "energy",
    ]
    _REALISM_KEYWORDS = [
        "realistic", "photo", "dslr", "photograph", "photorealistic", "raw photo",
        "bokeh", "studio lighting", "human skin", "portrait photography", "lens",
        "camera", "cinematic photo", "ultra realistic", "flux",
    ]
    _FANTASY_KEYWORDS = [
        "dragon", "castle", "magic", "rpg", "wizard", "knight", "dungeon",
        "fantasy", "creature", "epic", "mystical", "mythical", "ancient ruins",
        "dark fantasy", "sorcerer",
    ]

    def _score_request_text(self, text: str) -> dict:
        """
        Count keyword hits and return normalised scores summing to ~1.

        Args:
            text: Lower-cased user request.

        Returns:
            Dict with anime_score, realism_score, fantasy_score.
        """
        a = sum(1 for kw in self._ANIME_KEYWORDS if kw in text)
        r = sum(1 for kw in self._REALISM_KEYWORDS if kw in text)
        f = sum(1 for kw in self._FANTASY_KEYWORDS if kw in text)
        total = a + r + f or 1  # avoid division by zero
        return {
            "anime_score": round(a / total, 3),
            "realism_score": round(r / total, 3),
            "fantasy_score": round(f / total, 3),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(raw: str) -> Optional[dict]:
        """
        Attempt to parse a JSON object from the model's raw text output.

        Strips markdown fences and falls back to regex extraction.
        """
        text = raw.strip()
        # Strip ```json ... ``` or ``` ... ```
        if text.startswith("```"):
            lines = text.splitlines()
            inner_lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            text = "\n".join(inner_lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to find first {...} block in surrounding text
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        logger.warning("Could not parse JSON from router response: %s", raw[:200])
        return None

    @staticmethod
    def _derive_from_style(
        style_family: Optional[str], anime_genre: Optional[str]
    ) -> tuple:
        """Return (checkpoint, workflow) defaults for the given style."""
        if style_family == "realistic":
            return "realistic", "realistic_photo"
        if style_family == "fantasy":
            return "fantasy", "fantasy_cinematic"
        # anime fallback by genre
        genre_map = {
            "shonen": ("anime_shonen", "anime_shonen_action"),
            "seinen": ("anime_seinen", "anime_seinen_cinematic"),
            "shojo": ("anime_shojo", "anime_shojo_romance"),
            "slice_of_life": ("anime_slice_of_life", "anime_slice_of_life"),
        }
        return genre_map.get(anime_genre or "", ("anime_general", "anime_general"))
