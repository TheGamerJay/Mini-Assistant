"""
Image CEO Brain — system controller for the image pipeline.

The CEO is a deterministic Python state machine, not a GPT call.
It receives a task, routes it, delegates to specialist brains,
validates results through the QA Brain, and retries/revises on failure.

Pipeline for image_edit:
  EditPlannerBrain → (per step) → AnalysisBrain → ImageExecutionBrain → QABrain
  On QA failure: CEO revises step and retries once before returning failure.

Pipeline for image_generation:
  ImageExecutionBrain.generate_image → QABrain (light check) → return

The user experience: one natural-language command in, one accurate image out.
The CEO handles all the complexity behind the scenes.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from .image_models import (
    EditStep, ImageTaskRequest, ImageTaskResult,
    QAResult, RegionScanResult, SessionContext, TierResult,
)
from .image_brains.edit_planner import EditPlannerBrain
from .image_brains.analysis import AnalysisBrain
from .image_brains.image_execution import ImageExecutionBrain
from .image_brains.qa import QABrain
from .image_brains.memory import MemoryBrain

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2   # 1 main attempt + 1 CEO-directed correction pass


class ImageCEO:
    """
    CEO Brain — owns the image task lifecycle.

    Roles:
      - Classify and route the task
      - Delegate to specialist brains
      - Validate results via QA Brain
      - Decide retry / revise / fail
      - Return one clean result

    Does NOT: call GPT directly, manipulate pixels, or touch image APIs.
    """

    def __init__(self) -> None:
        self.edit_planner  = EditPlannerBrain()
        self.analysis      = AnalysisBrain()
        self.image_exec    = ImageExecutionBrain()
        self.qa            = QABrain()
        self.memory        = MemoryBrain()

    # ── Public entry point ────────────────────────────────────────────────────

    async def process_edit(
        self,
        request: ImageTaskRequest,
        openai_client: Any,
    ) -> ImageTaskResult:
        """
        Full image-edit pipeline.
        Returns ImageTaskResult with success/failure, image, reply, metadata.
        """
        t_start = time.perf_counter()
        logger.info("[CEO] process_edit session=%s", request.session_id)

        # ── 1. Plan ───────────────────────────────────────────────────────────
        steps = await self.edit_planner.plan(request.user_message)
        if not steps:
            return self._fail("Could not parse an edit from your request.")

        # ── 2. Execute steps in chain ─────────────────────────────────────────
        current_bytes = request.image_bytes
        current_b64: str | None = None
        step_metadata: list[dict] = []
        all_retries: list[str] = []
        total_attempts = 0

        for step_i, step in enumerate(steps):
            logger.info("[CEO] step %d/%d etype=%s from=%s to=%s region='%s'",
                        step_i + 1, len(steps),
                        step.edit_type, step.from_color, step.to_color,
                        step.region_description)

            if not current_bytes:
                return self._fail("No image available for this edit step.")

            # Load session context from memory
            ctx = self.memory.get_context(request.session_id)
            # Pull scan from memory if this is not the first step
            scan = RegionScanResult(
                mask_box=step.mask_box,
                preserve_elements=ctx.preserve_elements,
                cached_description=ctx.cached_description,
            )

            # ── 2a. Analysis: vision scan for named-region edits ──────────────
            is_named = bool(step.region_description)
            if is_named and (step.edit_type == "color_change" or not step.mask_box):
                scan = await self.analysis.scan_region(current_bytes, step, openai_client)
                step.mask_box = scan.mask_box or step.mask_box
                ctx.cached_description = scan.cached_description or ctx.cached_description
                ctx.preserve_elements = scan.preserve_elements or ctx.preserve_elements
                self.memory.merge_scan(ctx, request.session_id)

            # Build refined mask if not already built by scan
            if not scan.refined_mask_bytes and scan.mask_box and current_bytes:
                scan.refined_mask_bytes = self.analysis._build_refined_mask(
                    current_bytes, scan.mask_box
                )

            original_bytes = current_bytes
            step_result: dict = {}
            prior_t2_diag: dict | None = None
            step_succeeded = False

            # ── 2b. Attempt loop (1 main + 1 correction pass) ─────────────────
            qa: QAResult | None = None  # initialise so it's always bound after the loop
            for attempt in range(_MAX_ATTEMPTS):
                total_attempts += 1
                logger.info("[CEO] step %d attempt %d", step_i + 1, attempt + 1)

                # Delegate to Image Execution Brain
                tier: TierResult = await self.image_exec.execute_edit(
                    step, current_bytes, scan, ctx,
                    t2_diagnosis=prior_t2_diag,
                )

                if not tier.success:
                    logger.warning("[CEO] all tiers failed on attempt %d", attempt + 1)
                    if tier.t2_diagnosis:
                        diag = tier.t2_diagnosis
                        all_retries.extend(diag.get("suggested_retry_prompts", []))
                        step_result = {
                            "step": step_i + 1,
                            "method_used": "failed",
                            "failure_code": diag.get("failure_code"),
                            "user_message": diag.get("user_message", ""),
                        }
                    qa = None  # no QA result when tiers all failed

                    # On first attempt: retry with T3 enabled.
                    # T3 (DALL-E 3 reconstruction) is the last resort when T1+T2 both fail.
                    if attempt < _MAX_ATTEMPTS - 1:
                        prior_t2_diag = tier.t2_diagnosis or {
                            "failure_code": "all_tiers_failed",
                            "detected_dominant_color": None,
                        }
                        revised = EditStep(**step.__dict__)
                        revised.allow_reconstruction = True
                        step = revised
                        logger.info("[CEO] all tiers failed — enabling T3 for correction pass")
                        continue  # retry with T3 unlocked
                    break  # second attempt also failed — give up

                # Delegate to QA Brain
                qa: QAResult = self.qa.validate_edit(
                    original_bytes, tier.image_bytes, step, tier.method_used
                )
                all_retries.extend(qa.suggested_retries)

                step_result = {
                    "step": step_i + 1,
                    "method_used": tier.method_used,
                    "source_preserved": tier.source_preserved,
                    "reconstruction_fallback_used": tier.reconstruction_fallback,
                    "confidence_score": tier.confidence,
                    "target_change_score": qa.target_change_score,
                    "preserve_integrity_score": qa.preserve_integrity_score,
                    "changed_pixels": qa.changed_pixels,
                    "qa_status": qa.status,
                }

                if qa.passed:
                    logger.info("[CEO] step %d QA passed (method=%s)", step_i + 1, tier.method_used)
                    current_bytes = tier.image_bytes
                    current_b64 = tier.b64
                    # Update context cache with any description used by T3
                    if ctx.cached_description:
                        self.memory.update_description(request.session_id, ctx.cached_description)
                    step_succeeded = True
                    break

                # QA failed — CEO decides whether to revise + retry
                if attempt < _MAX_ATTEMPTS - 1:
                    prior_t2_diag = {
                        "failure_code": qa.failure_code,
                        "detected_dominant_color": qa.detected_color,
                        "failure_reason": qa.failure_reason,
                        "suggested_retry_prompts": qa.suggested_retries,
                    }
                    revised = self._revise_step(step, qa)
                    if revised:
                        logger.info(
                            "[CEO] QA failed (code=%s detected=%s) — CEO issuing correction pass",
                            qa.failure_code, qa.detected_color,
                        )
                        step = revised
                    else:
                        logger.info("[CEO] QA failed — no viable revision, ending attempts")
                        break

            step_metadata.append(step_result)

            if not step_succeeded and current_b64 is None:
                # Step failed entirely — surface the best user message we have
                user_msg = step_result.get("user_message", "")
                if not user_msg and qa and qa.user_message:
                    user_msg = qa.user_message
                if not user_msg:
                    user_msg = "The edit didn't produce a visible change."
                return ImageTaskResult(
                    success=False,
                    reply=user_msg,
                    suggested_retries=list(dict.fromkeys(all_retries)),  # dedupe
                    attempt_count=total_attempts,
                    metadata={"steps": step_metadata},
                )

        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 1)
        recon_used = any(s.get("reconstruction_fallback_used") for s in step_metadata)
        reply = (
            "Used enhanced reconstruction for a cleaner result — "
            "character composition may vary slightly from the original."
            if recon_used else "Image edited."
        )
        return ImageTaskResult(
            success=True,
            image_b64=current_b64,
            reply=reply,
            suggested_retries=[],
            attempt_count=total_attempts,
            metadata={
                "steps": step_metadata,
                "generation_time_ms": elapsed_ms,
                "method_used": step_metadata[-1].get("method_used", "unknown") if step_metadata else "unknown",
                "source_preserved": all(s.get("source_preserved", False) for s in step_metadata),
                "reconstruction_fallback_used": recon_used,
                "confidence_score": min(
                    (s.get("confidence_score", 0) for s in step_metadata), default=0.0
                ),
            },
        )

    async def process_generation(self, prompt: str, session_id: str) -> ImageTaskResult:
        """Pure text-to-image generation via Image Execution Brain."""
        logger.info("[CEO] process_generation session=%s", session_id)
        tier = await self.image_exec.generate_image(prompt)
        if tier.success:
            return ImageTaskResult(
                success=True,
                image_b64=tier.b64,
                reply="Image generated.",
                metadata={"method_used": tier.method_used},
            )
        return self._fail("Image generation failed: " + "; ".join(tier.tier_errors))

    # ── CEO decision logic (deterministic, no GPT) ────────────────────────────

    def _revise_step(self, step: EditStep, qa: QAResult) -> EditStep | None:
        """
        CEO decides how to revise a failed step.
        Returns revised EditStep or None if no viable revision.
        """
        if qa.failure_code == "dark_variant" and qa.detected_color:
            # T2 saw a dark shade — retry T2 with the actual detected color as from_color
            revised = EditStep(
                edit_type=step.edit_type,
                region_description=step.region_description,
                from_color=qa.detected_color,    # use actual color
                to_color=step.to_color,
                mask_box=step.mask_box,
                allow_reconstruction=True,        # allow T3 on second attempt
                preserve_regions=step.preserve_regions,
                final_instruction=step.final_instruction,
                color_overlap_risk=step.color_overlap_risk,
            )
            logger.info("[CEO] revision: from_color %s → %s", step.from_color, qa.detected_color)
            return revised

        if qa.failure_code == "source_color_mismatch" and qa.detected_color:
            # Wrong color targeted — retry with detected color
            revised = EditStep(
                edit_type=step.edit_type,
                region_description=step.region_description,
                from_color=qa.detected_color,
                to_color=step.to_color,
                mask_box=step.mask_box,
                allow_reconstruction=True,
                preserve_regions=step.preserve_regions,
                final_instruction=step.final_instruction,
                color_overlap_risk=step.color_overlap_risk,
            )
            logger.info("[CEO] revision: mismatch — using detected color %s", qa.detected_color)
            return revised

        if qa.failure_code in ("low_change", "unknown") and qa.detected_color:
            # Low change — allow T3 on retry
            revised = EditStep(**step.__dict__)
            revised.allow_reconstruction = True
            return revised

        # Fallback: always give T3 a chance on the second attempt.
        # T3 (describe + DALL-E 3 reconstruct) can succeed even when
        # T2 color targeting found nothing and detected_color is unknown.
        revised = EditStep(**step.__dict__)
        revised.allow_reconstruction = True
        return revised

    def _fail(self, message: str) -> ImageTaskResult:
        return ImageTaskResult(success=False, reply=message)
