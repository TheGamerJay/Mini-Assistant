"""
Image Execution Brain — executes image operations via T1/T2/T3 tiers.

T1: dall-e-2 masked inpaint (source-preserving, structural edits)
T2: PIL hue-rotation / achromatic blend (source-preserving, color edits)
T3: GPT-4o describe + DALL-E 3 reconstruct (not source-preserving, last resort)

Responsibility: image API calls only. No planning, no validation.
"""
from __future__ import annotations
import base64
import logging
from ..image_models import EditStep, RegionScanResult, SessionContext, TierResult

logger = logging.getLogger(__name__)


class ImageExecutionBrain:
    """
    Dispatches edit steps through a three-tier pipeline.
    Returns a TierResult regardless of which tier succeeded.
    """

    async def execute_edit(
        self,
        step: EditStep,
        image_bytes: bytes,
        scan: RegionScanResult,
        ctx: SessionContext,
        t2_diagnosis: dict | None = None,
    ) -> TierResult:
        """
        Try T1 → T2 → T3 in order, stopping at the first success.
        t2_diagnosis is passed in from a prior attempt so T3 can use detected_color.
        """
        from image_system.services.dalle_client import DalleClient
        dalle = DalleClient()
        tier_errors: list[str] = []
        t2_diag: dict | None = None

        # ── T1: dall-e-2 masked inpaint ──────────────────────────────────────
        t1 = await self._try_tier1(dalle, step, image_bytes, scan, tier_errors)
        if t1.success:
            return t1

        # ── T2: PIL masked recolor ────────────────────────────────────────────
        # Skip T2 on the second attempt when we already know it's a no_op
        # (t2_diagnosis comes from the CEO's prior attempt diagnosis).
        t2_diag: dict | None = None
        if t2_diagnosis is None:
            t2 = await self._try_tier2(dalle, step, image_bytes, scan, tier_errors)
            if t2.success:
                return t2  # genuine T2 success — no prior no_op, return it
            t2_diag = t2.t2_diagnosis
        else:
            tier_errors.append("T2:skipped — prior no_op diagnosis, going to T3")

        # ── T3: Controlled reconstruction ─────────────────────────────────────
        # Allowed if: step.allow_reconstruction=True
        #          OR T2 produced a no_op diagnosis this attempt
        #          OR a prior attempt already showed T2 was a no_op
        t3_allowed = step.allow_reconstruction or (t2_diag is not None) or (t2_diagnosis is not None)
        if t3_allowed:
            prior_diag = t2_diag or t2_diagnosis
            t3 = await self._try_tier3(dalle, step, image_bytes, scan, ctx, prior_diag, tier_errors)
            if t3.success:
                return t3

        return TierResult(
            success=False,
            tier_errors=tier_errors,
            t2_diagnosis=t2_diag,
        )

    async def generate_image(self, prompt: str) -> TierResult:
        """Pure text-to-image via DALL-E 3."""
        try:
            from image_system.services.dalle_client import DalleClient
            dalle = DalleClient()
            b64 = await dalle.generate(prompt)
            img_bytes = base64.b64decode(b64)
            return TierResult(
                success=True, b64=b64, image_bytes=img_bytes,
                method_used="dalle3_generation", source_preserved=False,
                confidence=0.9,
            )
        except Exception as e:
            logger.error("[ImageExecutionBrain] generate failed: %s", e)
            return TierResult(success=False, tier_errors=[str(e)])

    # ── Tier implementations ──────────────────────────────────────────────────

    async def _try_tier1(
        self,
        dalle,
        step: EditStep,
        image_bytes: bytes,
        scan: RegionScanResult,
        tier_errors: list[str],
    ) -> TierResult:
        if step.edit_type == "color_change":
            tier_errors.append("T1:skipped — color_change uses T2 (PIL recolor)")
            return TierResult(success=False, tier_errors=tier_errors)
        mask = scan.refined_mask_bytes
        if not (mask and image_bytes):
            tier_errors.append("T1:skipped — no mask")
            return TierResult(success=False, tier_errors=tier_errors)
        prompt = (
            f"{step.to_color or ''} {step.region_description or 'region'}. "
            "Match the art style, shading, texture, and lighting of the rest of the character. "
            "Blend seamlessly with the surrounding image."
        )
        try:
            b64 = await dalle.edit(image_bytes, prompt, mask_bytes=mask)
            img_bytes = base64.b64decode(b64)
            logger.info("[ImageExecutionBrain] T1/masked_ai_edit OK")
            return TierResult(
                success=True, b64=b64, image_bytes=img_bytes,
                method_used="masked_ai_edit", source_preserved=True,
                confidence=0.85,
            )
        except Exception as e:
            logger.error("[ImageExecutionBrain] T1 failed: %s", e)
            tier_errors.append(f"T1:{type(e).__name__}:{str(e)[:120]}")
            return TierResult(success=False, tier_errors=tier_errors)

    async def _try_tier2(
        self,
        dalle,
        step: EditStep,
        image_bytes: bytes,
        scan: RegionScanResult,
        tier_errors: list[str],
    ) -> TierResult:
        if not (scan.mask_box and step.from_color and step.to_color and image_bytes):
            missing = ("mask_box" if not scan.mask_box else
                       "from_color" if not step.from_color else
                       "to_color" if not step.to_color else "image")
            tier_errors.append(f"T2:skipped — no {missing}")
            return TierResult(success=False, tier_errors=tier_errors)
        try:
            result_bytes = dalle.color_replace_region(
                image_bytes,
                from_color=step.from_color,
                to_color=step.to_color,
                mask_box=scan.mask_box,
                pixel_mask_bytes=scan.refined_mask_bytes,
            )
            b64 = base64.b64encode(result_bytes).decode()
            logger.info("[ImageExecutionBrain] T2/masked_pil_recolor OK (pre-QA)")
            return TierResult(
                success=True, b64=b64, image_bytes=result_bytes,
                method_used="masked_pil_recolor", source_preserved=True,
                confidence=0.7,
            )
        except Exception as e:
            logger.warning("[ImageExecutionBrain] T2 failed: %s", e)
            tier_errors.append(f"T2:{type(e).__name__}:{str(e)[:120]}")
            return TierResult(success=False, tier_errors=tier_errors)

    async def _try_tier3(
        self,
        dalle,
        step: EditStep,
        image_bytes: bytes,
        scan: RegionScanResult,
        ctx: SessionContext,
        prior_diagnosis: dict | None,
        tier_errors: list[str],
    ) -> TierResult:
        detected = (prior_diagnosis or {}).get("detected_dominant_color") if prior_diagnosis else None
        region = step.region_description or "skin/fur"
        t3_from = step.from_color or "current color"
        t3_to = step.to_color or ""
        logger.info("[ImageExecutionBrain] T3/reconstruction %s→%s region=%s detected=%s",
                    t3_from, t3_to, region, detected)
        try:
            b64, desc_used = await dalle.describe_and_recolor(
                image_bytes, t3_from, t3_to,
                region=region,
                cached_description=ctx.cached_description,
                preserve_elements=scan.preserve_elements or None,
                detected_color=detected,
            )
            ctx.cached_description = desc_used  # update cache
            img_bytes = base64.b64decode(b64)
            logger.info("[ImageExecutionBrain] T3/reconstruction OK")
            return TierResult(
                success=True, b64=b64, image_bytes=img_bytes,
                method_used="reconstruction_fallback", source_preserved=False,
                reconstruction_fallback=True, confidence=0.5,
                tier_errors=tier_errors,
            )
        except Exception as e:
            logger.error("[ImageExecutionBrain] T3 failed: %s", e)
            tier_errors.append(f"T3:{type(e).__name__}:{str(e)[:120]}")
            return TierResult(success=False, tier_errors=tier_errors)
