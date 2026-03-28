"""
Analysis Brain — examines the image to locate target regions.

Responsibility: image analysis only. No edits, no generation.
"""
from __future__ import annotations
import io
import logging
from ..image_models import EditStep, RegionScanResult

logger = logging.getLogger(__name__)


class AnalysisBrain:
    """
    Scans the image to locate the target region, build a tight mask_box,
    identify preserve_elements, and build a pixel-level refined mask.
    """

    async def scan_region(
        self,
        image_bytes: bytes,
        step: EditStep,
        openai_client,
    ) -> RegionScanResult:
        """Run GPT-4o vision scan + refined mask build for a named-region edit."""
        result = RegionScanResult(
            mask_box=step.mask_box,
            preserve_elements=list(step.preserve_regions),
        )

        # ── GPT-4o vision scan ────────────────────────────────────────────────
        query_color = step.from_color or step.to_color or "color"
        try:
            from image_system.services.dalle_client import analyze_region_colors
            scan = await analyze_region_colors(
                openai_client, image_bytes, query_color, step.region_description
            )
            result.mask_box = scan.get("mask_box") or result.mask_box
            scan_preserve = scan.get("preserve_elements", [])
            if scan_preserve:
                result.preserve_elements = scan_preserve
            result.cached_description = scan.get("full_description") or None
            logger.info(
                "[AnalysisBrain] scan → mask_box=%s preserve=%d",
                result.mask_box, len(result.preserve_elements),
            )
        except Exception as e:
            logger.warning("[AnalysisBrain] vision scan failed (non-fatal): %s", e)

        # ── Build pixel-level refined mask ────────────────────────────────────
        if result.mask_box and image_bytes:
            result.refined_mask_bytes = self._build_refined_mask(
                image_bytes, result.mask_box
            )
        return result

    def _build_refined_mask(self, image_bytes: bytes, mask_box: dict) -> bytes | None:
        try:
            from image_system.services.dalle_client import build_refined_mask
            return build_refined_mask(image_bytes, mask_box)
        except Exception as e:
            logger.warning("[AnalysisBrain] build_refined_mask failed: %s", e)
            return self._build_coarse_mask(image_bytes, mask_box)

    def _build_coarse_mask(self, image_bytes: bytes, mask_box: dict) -> bytes | None:
        try:
            from PIL import Image as PILImage
            img = PILImage.open(io.BytesIO(image_bytes)).convert("RGBA")
            W, H = img.size
            mask = PILImage.new("RGBA", (W, H), (0, 0, 0, 255))
            px = round(mask_box.get("left", 0) / 100 * W)
            py = round(mask_box.get("top", 0) / 100 * H)
            pw = round(mask_box.get("width", 100) / 100 * W)
            ph = round(mask_box.get("height", 100) / 100 * H)
            mpix = mask.load()
            for y in range(py, min(py + ph, H)):
                for x in range(px, min(px + pw, W)):
                    mpix[x, y] = (0, 0, 0, 0)
            buf = io.BytesIO()
            mask.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            logger.warning("[AnalysisBrain] coarse mask build failed: %s", e)
            return None
