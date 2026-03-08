"""
Critic Brain for the Mini Assistant image system.

Evaluates whether a generation succeeded and recommends adjusted parameters
for a single retry if needed. The critic NEVER overrides the style family;
it only adjusts steps, cfg, seed, or suggests an alternative within the same
style family.
"""

import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

# Retry threshold — quality or anatomy below this triggers a retry recommendation
_RETRY_QUALITY_THRESHOLD = 0.60
_RETRY_ANATOMY_THRESHOLD = 0.50


class CriticBrain:
    """
    Post-generation evaluator that decides if a retry is worthwhile.

    Rules:
    - Only recommend ONE retry per request (caller enforces this).
    - Never change the style family; the router's decision is final.
    - Can adjust steps, cfg, seed, or suggest an alt checkpoint/workflow
      within the SAME style family.
    """

    # Alternative checkpoints within the same style family
    _STYLE_ALTS: dict = {
        "anime_general": ("anime_shojo", "anime_shonen"),
        "anime_shonen": ("anime_seinen", "anime_general"),
        "anime_seinen": ("anime_shonen", "anime_general"),
        "anime_shojo": ("anime_general", "anime_slice_of_life"),
        "anime_slice_of_life": ("anime_shojo", "anime_general"),
        "realistic": ("flux_premium", None),
        "fantasy": ("realistic", None),
        "flux_premium": ("realistic", None),
    }

    def __init__(self) -> None:
        from ..services.ollama_client import OllamaClient
        self._ollama = OllamaClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def evaluate(
        self,
        user_request: str,
        route_result: dict,
        image_review: dict,
    ) -> dict:
        """
        Evaluate whether the generation was successful.

        Args:
            user_request: The original user message.
            route_result: The RouteResult dict used for generation.
            image_review: The ImageReviewer's review dict.

        Returns:
            Dict with keys:
                should_retry (bool),
                adjusted_params (dict: steps, cfg, seed),
                alt_checkpoint (str or None),
                alt_workflow (str or None),
                reason (str).
        """
        quality = image_review.get("quality_score", 1.0)
        anatomy = image_review.get("anatomy_score", 1.0)
        style_match = image_review.get("style_match", 1.0)
        reviewer_retry = image_review.get("retry_recommended", False)
        issues = image_review.get("issues", [])

        current_checkpoint = route_result.get("selected_checkpoint", "anime_general")
        current_workflow = route_result.get("selected_workflow", "anime_general")
        current_steps = route_result.get("steps", 28)
        current_cfg = route_result.get("cfg", 7.0)

        # --- Decide whether to retry ---
        should_retry = (
            reviewer_retry
            or quality < _RETRY_QUALITY_THRESHOLD
            or anatomy < _RETRY_ANATOMY_THRESHOLD
        )

        if not should_retry:
            return {
                "should_retry": False,
                "adjusted_params": {},
                "alt_checkpoint": None,
                "alt_workflow": None,
                "reason": "Generation quality is acceptable.",
            }

        # --- Build adjusted params ---
        adjusted_params = await self.recommend_retry(route_result, issues)

        # --- Maybe suggest alternate checkpoint within same family ---
        alt_checkpoint = None
        alt_workflow = None

        # Only switch checkpoint if style match is also bad
        if style_match < 0.5:
            alts = self._STYLE_ALTS.get(current_checkpoint, (None, None))
            if alts[0] and alts[0] != current_checkpoint:
                alt_checkpoint = alts[0]
                alt_workflow = self._checkpoint_to_workflow(alt_checkpoint)

        # Build reason string
        reasons = []
        if quality < _RETRY_QUALITY_THRESHOLD:
            reasons.append(f"quality too low ({quality:.2f})")
        if anatomy < _RETRY_ANATOMY_THRESHOLD:
            reasons.append(f"anatomy score too low ({anatomy:.2f})")
        if style_match < 0.5:
            reasons.append(f"style mismatch ({style_match:.2f})")
        if issues:
            reasons.append(f"issues: {', '.join(issues[:3])}")
        reason = "Retry recommended: " + "; ".join(reasons)

        logger.info(
            "Critic: should_retry=True checkpoint=%s->%s reason=%s",
            current_checkpoint, alt_checkpoint or "same", reason[:80],
        )

        return {
            "should_retry": True,
            "adjusted_params": adjusted_params,
            "alt_checkpoint": alt_checkpoint,
            "alt_workflow": alt_workflow,
            "reason": reason,
        }

    async def recommend_retry(self, route_result: dict, issues: list) -> dict:
        """
        Compute adjusted generation parameters for a retry attempt.

        Increases steps slightly, adjusts CFG based on issues, and randomises
        the seed.

        Args:
            route_result: Current RouteResult dict.
            issues: List of issue strings from the reviewer.

        Returns:
            Dict with keys: steps (int), cfg (float), seed (int).
        """
        current_steps = int(route_result.get("steps", 28))
        current_cfg = float(route_result.get("cfg", 7.0))
        checkpoint = route_result.get("selected_checkpoint", "anime_general")

        # Increase steps by ~20% but cap at 50
        new_steps = min(50, int(current_steps * 1.2))

        # Adjust CFG based on issue types
        issues_lower = [i.lower() for i in issues]
        if any("blur" in i or "noise" in i or "quality" in i for i in issues_lower):
            # Higher CFG for sharpness
            new_cfg = min(9.0, current_cfg + 0.5)
        elif any("anatomy" in i or "hand" in i or "finger" in i for i in issues_lower):
            # Slightly lower CFG for anatomy issues (over-guidance can worsen them)
            new_cfg = max(5.5, current_cfg - 0.5)
        else:
            new_cfg = current_cfg

        # FLUX has fixed low CFG
        if checkpoint == "flux_premium":
            new_steps = 8
            new_cfg = 1.0

        new_seed = random.randint(0, 2**32 - 1)

        logger.debug(
            "recommend_retry: steps %d->%d cfg %.1f->%.1f seed=%d",
            current_steps, new_steps, current_cfg, new_cfg, new_seed,
        )

        return {"steps": new_steps, "cfg": new_cfg, "seed": new_seed}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _checkpoint_to_workflow(checkpoint: str) -> Optional[str]:
        """Map a checkpoint key to its primary workflow key."""
        mapping = {
            "anime_general": "anime_general",
            "anime_shonen": "anime_shonen_action",
            "anime_seinen": "anime_seinen_cinematic",
            "anime_shojo": "anime_shojo_romance",
            "anime_slice_of_life": "anime_slice_of_life",
            "realistic": "realistic_photo",
            "fantasy": "fantasy_cinematic",
            "flux_premium": "flux_high_realism",
        }
        return mapping.get(checkpoint)
