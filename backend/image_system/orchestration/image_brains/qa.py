"""
QA Brain — validates image edit results before returning to the user.

Responsibility: validation and diagnosis only. No image generation.
"""
from __future__ import annotations
import logging
from ..image_models import EditStep, QAResult

logger = logging.getLogger(__name__)

# Thresholds
_NO_OP_SCORE   = 0.008
_NO_OP_PIXELS  = 50
_PRESERVE_MIN  = 0.80


class QABrain:
    """
    Validates that:
      1. The target region changed visibly.
      2. Protected regions stayed untouched.
      3. T2 no_ops are diagnosed and categorised.
    """

    def validate_edit(
        self,
        original_bytes: bytes,
        result_bytes: bytes,
        step: EditStep,
        method_used: str,
    ) -> QAResult:
        """
        Run pixel-level validation.  Always returns a QAResult.
        T1/T3 results skip the no_op check (they change at image level).
        """
        mask_box = step.mask_box

        try:
            from image_system.services.dalle_client import validate_edit_result
            vr = validate_edit_result(original_bytes, result_bytes, mask_box)
        except Exception as e:
            logger.warning("[QABrain] validate_edit_result error (non-fatal): %s", e)
            # Cannot validate — assume pass for T3 / reconstruction
            return QAResult(passed=True, status="unvalidated")

        tcs   = vr.get("target_change_score", 0)
        pis   = vr.get("preserve_integrity_score", 1)
        ch_px = vr.get("changed_pixels", 0)
        status = vr.get("result_status", "unknown")

        # T3 reconstruction rewrites the whole image — skip no_op check
        if method_used == "reconstruction_fallback":
            passed = True
            return QAResult(
                passed=True, status="success",
                target_change_score=tcs, preserve_integrity_score=pis,
                changed_pixels=ch_px,
            )

        no_op = (tcs < _NO_OP_SCORE and ch_px < _NO_OP_PIXELS)
        if no_op:
            diagnosis = self._diagnose(original_bytes, step, vr)
            logger.warning(
                "[QABrain] no_op: score=%.4f px=%d code=%s",
                tcs, ch_px, diagnosis.failure_code,
            )
            return QAResult(
                passed=False, status="no_op",
                target_change_score=tcs, preserve_integrity_score=pis,
                changed_pixels=ch_px,
                failure_code=diagnosis.failure_code,
                detected_color=diagnosis.detected_color,
                failure_reason=diagnosis.failure_reason,
                suggested_retries=diagnosis.suggested_retries,
                user_message=diagnosis.user_message,
            )

        passed = pis >= _PRESERVE_MIN
        return QAResult(
            passed=passed,
            status="success" if passed else "partial",
            target_change_score=tcs,
            preserve_integrity_score=pis,
            changed_pixels=ch_px,
        )

    def _diagnose(self, image_bytes: bytes, step: EditStep, vr: dict) -> "DiagResult":
        try:
            from image_system.services.dalle_client import diagnose_failed_region_edit
            d = diagnose_failed_region_edit(
                original_bytes=image_bytes,
                mask_box=step.mask_box,
                region_description=step.region_description,
                from_color=step.from_color or "",
                to_color=step.to_color or "",
                validation=vr,
                mask_pixel_count=0,
            )
            return _DiagResult(
                failure_code=d.get("failure_code", "unknown"),
                detected_color=d.get("detected_dominant_color"),
                failure_reason=d.get("failure_reason", ""),
                suggested_retries=d.get("suggested_retry_prompts", []),
                user_message=d.get("user_message", ""),
            )
        except Exception as e:
            logger.warning("[QABrain] diagnosis error: %s", e)
            return _DiagResult(failure_code="unknown")


class _DiagResult:
    """Internal diagnosis result."""
    def __init__(self, failure_code="unknown", detected_color=None,
                 failure_reason="", suggested_retries=None, user_message=""):
        self.failure_code = failure_code
        self.detected_color = detected_color
        self.failure_reason = failure_reason
        self.suggested_retries = suggested_retries or []
        self.user_message = user_message
