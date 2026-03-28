"""
Edit Planner Brain — converts a user request into ordered EditStep list.

Responsibility: planning only. No image APIs, no pixel work.
"""
from __future__ import annotations
import logging
import re
from ..image_models import EditStep

logger = logging.getLogger(__name__)

_COLOR_WORDS = (
    r"(red|orange|yellow|green|blue|purple|pink|brown|black|white|gray|grey|"
    r"cyan|magenta|violet|gold|silver|teal|navy|maroon|coral|lime|indigo|"
    r"turquoise|beige|tan|lavender|crimson)"
)
_REGION_WORDS = (
    r"(skin|fur|body|hair|eyes?|eye|shirt|hoodie|jacket|pants|shoes?|"
    r"sneakers?|boots?|tail|ears?|nose)"
)


class EditPlannerBrain:
    """
    Parses a user edit request into an ordered list of EditSteps.

    Primary path: GPT-4o analyze_edit_request (prompt_enhancer).
    Fallback: local regex extraction when GPT is unavailable.
    """

    async def plan(self, user_message: str) -> list[EditStep]:
        steps = await self._try_gpt_plan(user_message)
        if not steps:
            steps = self._fallback_regex_plan(user_message)
        logger.info("[EditPlannerBrain] → %d step(s)", len(steps))
        return steps

    async def _try_gpt_plan(self, user_message: str) -> list[EditStep]:
        try:
            from mini_assistant.phase2.prompt_enhancer import analyze_edit_request
            raw = await analyze_edit_request(user_message.strip())
            if not raw:
                return []
            return [self._raw_to_step(r) for r in raw]
        except Exception as e:
            logger.warning("[EditPlannerBrain] GPT plan failed: %s", e)
            return []

    def _raw_to_step(self, raw: dict) -> EditStep:
        allow_recon_flag = raw.get("allow_reconstruction_fallback", None)
        is_named = bool((raw.get("region_description") or "").strip())
        if allow_recon_flag is None:
            allow_recon = True
        else:
            allow_recon = bool(allow_recon_flag)
        return EditStep(
            edit_type=raw.get("edit_type", "structural_edit"),
            region_description=(raw.get("region_description") or "").lower().strip(),
            from_color=(raw.get("from_color") or "").lower().strip() or None,
            to_color=(raw.get("to_color") or "").lower().strip() or None,
            mask_box=raw.get("mask_box"),
            allow_reconstruction=allow_recon,
            preserve_regions=raw.get("preserve_regions", []),
            final_instruction=raw.get("final_instruction"),
            color_overlap_risk=bool(raw.get("color_overlap_risk", False)),
        )

    def _fallback_regex_plan(self, user_message: str) -> list[EditStep]:
        msg = user_message.lower()
        region_match = re.search(_REGION_WORDS, msg)
        region_name = region_match.group(1) if region_match else None
        is_skin_kw = region_name and re.search(r"skin|fur|body|tail|ears?", region_name)
        all_colors = re.findall(rf"\b{_COLOR_WORDS}\b", msg)
        fb_from = all_colors[0] if len(all_colors) >= 2 else None
        fb_to = all_colors[-1] if all_colors else None
        etype = "color_change" if (all_colors or region_name) else "structural_edit"
        step = EditStep(
            edit_type=etype,
            region_description=region_name or ("skin/fur" if is_skin_kw else ""),
            from_color=fb_from,
            to_color=fb_to,
            allow_reconstruction=True,
        )
        logger.info("[EditPlannerBrain] fallback → etype=%s from=%s to=%s region=%s",
                    etype, fb_from, fb_to, region_name)
        return [step]
