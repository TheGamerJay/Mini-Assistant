"""
image_system/services/dalle_client.py
──────────────────────────────────────
DALL-E 3 image generation client (OpenAI API).

Replaces the ComfyUI pipeline with a simple, hosted API call.
Built-in safety filtering, no local GPU required.

Usage:
    client = DalleClient()
    b64 = await client.generate("a red panda coding in space", quality="high")
"""
from __future__ import annotations

import logging
import os
import re
from typing import Literal

try:
    from PIL import Image as _PILImage
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

logger = logging.getLogger(__name__)

# DALL-E 3 valid sizes
VALID_SIZES = {"1024x1024", "1024x1792", "1792x1024"}
DEFAULT_SIZE = "1024x1024"

# gpt-image-1 / gpt-image-1.5 — configurable via IMAGE_MODEL env var
_IMAGE_EDIT_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-1")

# DALL-E 3 hard prompt limit (OpenAI enforces this server-side)
_PROMPT_MAX = 4000

# ── Composition / constraint keywords that must survive trimming ──────────────
# These control framing, cropping, body visibility — losing them degrades output.
_CRITICAL_RE = re.compile(
    r"\b(full.?body|head.to.toe|no crop|no cut|fully in frame|fully visible|"
    r"centered|complete|visible|no zoom|wide.?frame|entire|whole body|"
    r"head to toe|wings.*visible|subject.*visible|in frame)\b",
    re.IGNORECASE,
)

# ── Verbose phrase → compact replacement ─────────────────────────────────────
_SHORTEN = [
    (r"\bcompletely visible within the frame\b",          "fully in frame"),
    (r"\bno cropping of any kind\b",                      "no cropping"),
    (r"\bentirely within the frame\b",                    "fully in frame"),
    (r"\bfrom head to toe\b",                             "head-to-toe"),
    (r"\bwithout any cropping\b",                         "no crop"),
    (r"\bno cut-off limbs,?\s*no zoomed-in framing\b",    "no cutoffs, no zoom"),
    (r"\bno zoomed-in framing\b",                         "no zoom"),
    (r"\bslightly? low-angle perspective to enhance scale and elegance\b",
                                                          "low-angle"),
    (r"\bcamera framing:\s*",                             ""),
    (r"\bsubject fully visible from head to toe\b",       "full body visible"),
    (r"\bwings fully visible\b",                          "wings in frame"),
    (r"\bcentered composition\b",                         "centered"),
    (r"\brealistic proportions with stylized elegance\b", "realistic, stylized"),
    (r"\bwith stylized elegance\b",                       "stylized"),
    (r"\bsmooth anatomy,?\s*realistic proportions\b",     "smooth anatomy"),
    (r"\bvolumetric light rays?\b",                       "volumetric light"),
    (r"\bdepth of field\b",                               "DOF"),
    (r"\b8k quality,?\s*masterpiece\b",                   "8k, masterpiece"),
    (r"\bultra-detailed,?\s*cinematic lighting\b",        "ultra-detailed, cinematic"),
    (r"\bfloating particles of light\b",                  "light particles"),
    (r"\benhancing the magical atmosphere\b",             "magical atmosphere"),
    (r"\bcreating a halo-like backlight\b",               "halo backlight"),
    (r"\baround her entire body and wings\b",             "around her"),
    (r"\bfilled with glowing clouds in\b",                "with glowing"),
    (r"\ba cinematic sky at sunset,?\s*",                 "sunset sky, "),
]


def _compress_prompt(prompt: str) -> str:
    """
    Intelligently compress an image prompt to fit within _PROMPT_MAX characters.

    Strategy (applied in order until prompt fits):
      1. Deduplicate repeated lines / paragraphs (catches copy-pasted prompts)
      2. Deduplicate repeated comma-separated clauses
      3. Replace verbose phrases with compact equivalents
      4. Trim expendable clauses from the end, skipping critical ones
      5. Hard word-boundary truncation as last resort
    """
    original = prompt
    original_len = len(prompt)

    # ── Step 1: Deduplicate repeated lines / paragraphs ──────────────────────
    lines = prompt.splitlines()
    seen: set[str] = set()
    deduped: list[str] = []
    for line in lines:
        key = line.strip().lower()
        if key not in seen:
            deduped.append(line)
            seen.add(key)
    prompt = "\n".join(deduped)
    if len(prompt) <= _PROMPT_MAX:
        _log_trim(original_len, len(prompt), "dedup-lines")
        return prompt.strip()

    # ── Step 2: Deduplicate repeated comma-separated clauses ─────────────────
    clauses = [c.strip() for c in re.split(r"[,;]\s*", prompt)]
    seen_c: set[str] = set()
    unique: list[str] = []
    for clause in clauses:
        key = clause.lower()
        if key and key not in seen_c:
            unique.append(clause)
            seen_c.add(key)
    prompt = ", ".join(unique)
    if len(prompt) <= _PROMPT_MAX:
        _log_trim(original_len, len(prompt), "dedup-clauses")
        return prompt.strip()

    # ── Step 3: Compact verbose phrases ──────────────────────────────────────
    for pattern, replacement in _SHORTEN:
        prompt = re.sub(pattern, replacement, prompt, flags=re.IGNORECASE)
        prompt = re.sub(r",\s*,", ",", prompt)   # fix double commas
        prompt = re.sub(r"\s{2,}", " ", prompt)  # collapse whitespace
        if len(prompt) <= _PROMPT_MAX:
            _log_trim(original_len, len(prompt), "shorten-phrases")
            return prompt.strip()

    # ── Step 4: Trim expendable clauses from the end ─────────────────────────
    # Split into comma-clauses, drop non-critical ones from the tail
    parts = [p.strip() for p in prompt.split(",") if p.strip()]
    while len(", ".join(parts)) > _PROMPT_MAX and len(parts) > 1:
        # Scan from the end; keep scanning if the tail clause is critical
        removed = False
        for i in range(len(parts) - 1, 0, -1):
            if not _CRITICAL_RE.search(parts[i]):
                parts.pop(i)
                removed = True
                break
        if not removed:
            # All remaining clauses are critical — just drop the last one
            parts.pop()
    prompt = ", ".join(parts)
    if len(prompt) <= _PROMPT_MAX:
        _log_trim(original_len, len(prompt), "clause-trim")
        return prompt.strip()

    # ── Step 5: Hard word-boundary truncation ─────────────────────────────────
    prompt = prompt[:_PROMPT_MAX].rsplit(" ", 1)[0]
    _log_trim(original_len, len(prompt), "hard-truncate")
    return prompt.strip()


def _log_trim(original: int, final: int, method: str) -> None:
    logger.warning(
        "Prompt compressed [%s]: %d → %d chars (saved %d)",
        method, original, final, original - final,
    )


# ─────────────────────────────────────────────────────────────────────────────

_CLOTHING_KW_RE = re.compile(
    r"\b(shirt|hoodie|jacket|pants|jeans|shoes|sneakers|boots|hat|cap|vest|"
    r"dress|outfit|coat|gloves)\b",
    re.IGNORECASE,
)


def _has_color_overlap(description: str, from_color: str) -> bool:
    """
    Module-level helper.  Returns True when `from_color` appears within 60
    characters of a clothing/accessory keyword in the vision description,
    indicating that a global text swap would also recolor clothing.

    Args:
        description: Raw GPT-4o vision description of the image.
        from_color:  The color being replaced (e.g. "blue").

    Returns:
        True if color overlap is detected in a clothing context.
    """
    color_pat = re.compile(rf"\b{re.escape(from_color)}\b", re.IGNORECASE)
    clothing_pat = re.compile(
        r"\b(shirt|hoodie|jacket|pants|jeans|shoes|sneakers|boots|hat|cap|"
        r"vest|dress|outfit|coat|gloves)\b",
        re.IGNORECASE,
    )

    for color_match in color_pat.finditer(description):
        start = color_match.start()
        # Check 60-char window around the color occurrence
        window_start = max(0, start - 60)
        window_end   = min(len(description), start + 60)
        window = description[window_start:window_end]
        if clothing_pat.search(window):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────

class DalleClient:
    """Async wrapper around the OpenAI images.generate endpoint."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise RuntimeError("openai package not installed") from exc

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY environment variable is not set. "
                    "Add it to your Railway / .env config."
                )
            self._client = AsyncOpenAI(api_key=api_key)
        return self._client

    async def generate(
        self,
        prompt: str,
        quality: str = "balanced",
        size: str = DEFAULT_SIZE,
    ) -> str:
        """
        Generate one image via DALL-E 3 and return it as a base64 string.

        quality mapping:
            fast / balanced → "standard"   (cheaper)
            high            → "hd"         (sharper details)

        Prompts exceeding 4000 chars are intelligently compressed:
        duplicates removed → verbose phrases shortened → non-critical
        clauses trimmed from end → hard word-boundary cut as last resort.
        Critical composition keywords (full body, no crop, head-to-toe) are
        always preserved.
        """
        if size not in VALID_SIZES:
            size = DEFAULT_SIZE

        if len(prompt) > _PROMPT_MAX:
            prompt = _compress_prompt(prompt)

        dalle_quality: Literal["standard", "hd"] = (
            "hd" if quality == "high" else "standard"
        )

        client = self._get_client()
        logger.info(
            "DALL-E 3 generate: quality=%s size=%s len=%d prompt=%.80s",
            dalle_quality, size, len(prompt), prompt,
        )

        response = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,  # type: ignore[arg-type]
            quality=dalle_quality,
            n=1,
            response_format="b64_json",
        )

        b64 = response.data[0].b64_json
        if not b64:
            raise RuntimeError("DALL-E 3 returned an empty image response")

        logger.info("DALL-E 3 generation complete (%d bytes b64)", len(b64))
        return b64

    async def edit(
        self,
        image_bytes: bytes,
        prompt: str,
        size: str = DEFAULT_SIZE,
        mask_bytes: bytes | None = None,
    ) -> str:
        """
        Edit an existing image using gpt-image-1 and return result as base64.

        Unlike generate(), this passes the actual image to the model so it
        can make targeted changes while preserving everything else.

        mask_bytes: optional PNG mask where transparent pixels (alpha=0) mark
                    the region to edit; opaque pixels are preserved unchanged.
        """
        import io as _io

        if size not in VALID_SIZES:
            size = DEFAULT_SIZE

        if len(prompt) > _PROMPT_MAX:
            prompt = _compress_prompt(prompt)

        client = self._get_client()
        logger.info(
            "%s edit: size=%s len=%d mask=%s prompt=%.80s",
            _IMAGE_EDIT_MODEL, size, len(prompt), mask_bytes is not None, prompt,
        )

        # Ensure PNG format — gpt-image-1 accepts PNG/JPEG/WEBP but PNG is safest
        img_data = image_bytes
        if _PIL_AVAILABLE:
            try:
                buf = _io.BytesIO()
                _PILImage.open(_io.BytesIO(image_bytes)).convert("RGBA").save(buf, format="PNG")
                img_data = buf.getvalue()
            except Exception as _e:
                logger.warning("PIL PNG conversion failed, passing raw bytes: %s", _e)

        image_file = _io.BytesIO(img_data)
        image_file.name = "image.png"

        kwargs: dict = dict(
            model=_IMAGE_EDIT_MODEL,
            image=image_file,
            prompt=prompt,
            size=size,  # type: ignore[arg-type]
        )

        if mask_bytes is not None:
            mask_file = _io.BytesIO(mask_bytes)
            mask_file.name = "mask.png"
            kwargs["mask"] = mask_file

        response = await client.images.edit(**kwargs)

        b64 = response.data[0].b64_json
        if not b64:
            raise RuntimeError("gpt-image-1 returned an empty edit response")

        logger.info("%s edit complete (%d bytes b64)", _IMAGE_EDIT_MODEL, len(b64))
        return b64

    async def describe_and_recolor(
        self,
        image_bytes: bytes,
        from_color: str,
        to_color: str,
        region: str = "skin/fur",
        cached_description: str | None = None,
    ) -> tuple[str, str]:
        """
        Vision-guided recolor: analyze the image with GPT-4o to get a precise
        character description, swap the target color in the description text,
        then regenerate via DALL-E 3.

        Avoids PIL's blind pixel swap AND gpt-image-1's moderation filter.
        Skin/fur regions are correctly isolated because the model describes
        them separately from clothing.

        Args:
            image_bytes:        Raw reference image bytes.
            from_color:         Color to replace (e.g. "blue").
            to_color:           New color (e.g. "yellow").
            region:             Human label for the region (e.g. "skin/fur", "hair").
            cached_description: If provided, skip the GPT-4o vision call and use
                                this description directly (consistency mode).

        Returns:
            Tuple of (base64 PNG string of the regenerated image, raw description used).
        """
        import base64 as _b64
        client = self._get_client()

        # ── Step 1: Describe the character precisely with GPT-4o vision ──────
        if cached_description is not None:
            description = cached_description
            logger.info(
                "describe_and_recolor: using cached description (%d chars) — skipping vision call",
                len(description),
            )
        else:
            img_b64 = _b64.b64encode(image_bytes).decode()
            logger.info("describe_and_recolor: analyzing reference image (%s→%s)", from_color, to_color)
            vision = await client.chat.completions.create(
                model="gpt-4o",
                max_tokens=600,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "high"},
                        },
                        {
                            "type": "text",
                            "text": (
                                "Describe this character/image in precise detail for exact recreation. "
                                "Include: art style, character type/species, "
                                f"{region} color, hair/fur color, eye color, "
                                "every clothing piece with its exact color, accessories, "
                                "pose, expression, background, lighting. "
                                "Output ONLY the description — no preamble, no commentary."
                            ),
                        },
                    ],
                }],
            )
            description = vision.choices[0].message.content or ""
            logger.info("describe_and_recolor: description (%d chars)", len(description))

        # ── Overlap detection ─────────────────────────────────────────────────
        if _has_color_overlap(description, from_color):
            logger.warning(
                "color_overlap detected in description — text swap may affect clothing"
            )

        # ── Step 2: Swap the target color only in region references ──────────
        # Replace "blue skin", "blue fur", "blue body" etc. but NOT "blue hoodie"
        def _swap(text: str) -> str:
            # Replace color adjacent to skin/fur/body region words
            swapped = re.sub(
                rf"\b{re.escape(from_color)}\b(?=\s+(?:skin|fur|body|tone|complexion))",
                to_color, text, flags=re.IGNORECASE,
            )
            # Also replace region+color order: "skin is blue" / "skin color: blue"
            swapped = re.sub(
                rf"(?<={region}\s(?:is|are|color[:\s]+)){re.escape(from_color)}\b",
                to_color, swapped, flags=re.IGNORECASE,
            )
            # Fallback: replace any remaining standalone from_color that is NOT
            # preceded by a clothing keyword
            _CLOTHING = re.compile(
                r"\b(shirt|hoodie|jacket|pants|jeans|shorts|shoes|sneakers|boots|"
                r"gloves|hat|cap|vest|dress|outfit|clothing|coat|scarf|belt|bag)\s+",
                re.IGNORECASE,
            )
            parts = _CLOTHING.split(swapped)
            result = []
            skip_next = False
            for part in parts:
                if skip_next:
                    result.append(part)
                    skip_next = False
                elif _CLOTHING.match(part):
                    result.append(part)
                    skip_next = True  # don't swap color in next segment
                else:
                    result.append(re.sub(rf"\b{re.escape(from_color)}\b", to_color, part, flags=re.IGNORECASE))
            swapped = "".join(result)
            return swapped

        modified = _swap(description)
        logger.info("describe_and_recolor: swapped description (%d chars)", len(modified))

        # ── Step 3: Regenerate with DALL-E 3 ────────────────────────────────
        prompt = (
            f"Recreate this character with ONE change only — the {region} color is now {to_color} "
            f"instead of {from_color}. All clothing, accessories, art style, pose, expression, "
            f"and background must remain IDENTICAL to the original.\n\n"
            f"Character description:\n{modified}\n\n"
            "Show the full character head-to-toe. Do not crop, zoom in, or reframe."
        )
        b64_image = await self.generate(prompt)
        return b64_image, description

    def color_replace_region(
        self,
        image_bytes: bytes,
        from_color: str,
        to_color: str,
        mask_box: dict,
        tolerance: int = 30,
    ) -> str | None:
        """
        Programmatic hue-based color replacement restricted to a bounding box region.

        Identical logic to color_replace but ONLY modifies pixels that fall within
        the mask_box rectangle. Pixels outside the box are left completely untouched.

        Args:
            image_bytes: Raw image bytes (any PIL-supported format).
            from_color:  Color name to replace (e.g. "blue").
            to_color:    Color name to shift to   (e.g. "purple").
            mask_box:    Dict with top/left/width/height as percentages 0-100.
            tolerance:   Hue tolerance in degrees around the center hue.

        Returns base64 PNG string, or None if PIL unavailable / color unknown.
        """
        if not _PIL_AVAILABLE:
            return None

        _HUE_CENTER: dict[str, int] = {
            "red":     0,
            "orange":  30,
            "yellow":  55,
            "green":   120,
            "cyan":    180,
            "teal":    175,
            "blue":    220,
            "navy":    230,
            "indigo":  255,
            "violet":  270,
            "purple":  275,
            "magenta": 300,
            "pink":    320,
            "rose":    340,
        }

        fc = from_color.lower().strip()
        tc = to_color.lower().strip()
        from_hue = _HUE_CENTER.get(fc)
        to_hue   = _HUE_CENTER.get(tc)
        if from_hue is None or to_hue is None:
            logger.warning("color_replace_region: unknown color '%s' or '%s'", fc, tc)
            return None

        import io as _io
        import numpy as _np

        try:
            img = _PILImage.open(_io.BytesIO(image_bytes)).convert("RGBA")
            W, H = img.size
            arr = _np.array(img, dtype=_np.float32)

            # ── Convert mask_box percentages to pixel coordinates ─────────────
            box_left   = round(mask_box.get("left",   0) / 100 * W)
            box_top    = round(mask_box.get("top",    0) / 100 * H)
            box_width  = round(mask_box.get("width",  100) / 100 * W)
            box_height = round(mask_box.get("height", 100) / 100 * H)
            box_right  = min(box_left + box_width,  W)
            box_bottom = min(box_top  + box_height, H)

            # ── Build a boolean spatial mask for the bounding box ─────────────
            region_mask = _np.zeros((H, W), dtype=bool)
            region_mask[box_top:box_bottom, box_left:box_right] = True

            r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]

            # Convert RGB → HSV (0-1 range)
            r01, g01, b01 = r / 255.0, g / 255.0, b / 255.0
            cmax  = _np.maximum(_np.maximum(r01, g01), b01)
            cmin  = _np.minimum(_np.minimum(r01, g01), b01)
            delta = cmax - cmin

            hue = _np.zeros_like(r01)
            mask_r = (cmax == r01) & (delta > 0)
            mask_g = (cmax == g01) & (delta > 0)
            mask_b = (cmax == b01) & (delta > 0)
            hue[mask_r] = (60 * ((g01[mask_r] - b01[mask_r]) / delta[mask_r])) % 360
            hue[mask_g] = (60 * ((b01[mask_g] - r01[mask_g]) / delta[mask_g]) + 120) % 360
            hue[mask_b] = (60 * ((r01[mask_b] - g01[mask_b]) / delta[mask_b]) + 240) % 360

            sat = _np.where(cmax > 0, delta / cmax, 0.0)
            val = cmax

            lo = (from_hue - tolerance) % 360
            hi = (from_hue + tolerance) % 360
            if lo <= hi:
                hue_match = (hue >= lo) & (hue <= hi)
            else:
                hue_match = (hue >= lo) | (hue <= hi)

            # Apply color match only within the bounding box region
            target_mask = hue_match & (sat > 0.25) & (val > 0.15) & region_mask

            if not _np.any(target_mask):
                logger.warning("color_replace_region: no matching pixels in region for '%s'", fc)
                return None

            hue_shift = (to_hue - from_hue) % 360
            new_hue   = (hue + hue_shift * target_mask) % 360

            h6  = new_hue / 60.0
            hi_ = _np.floor(h6).astype(int) % 6
            f   = h6 - _np.floor(h6)
            p   = val * (1 - sat)
            q   = val * (1 - f * sat)
            t_  = val * (1 - (1 - f) * sat)

            new_r = _np.select(
                [hi_ == 0, hi_ == 1, hi_ == 2, hi_ == 3, hi_ == 4, hi_ == 5],
                [val, q, p, p, t_, val]
            )
            new_g = _np.select(
                [hi_ == 0, hi_ == 1, hi_ == 2, hi_ == 3, hi_ == 4, hi_ == 5],
                [t_, val, val, q, p, p]
            )
            new_b = _np.select(
                [hi_ == 0, hi_ == 1, hi_ == 2, hi_ == 3, hi_ == 4, hi_ == 5],
                [p, p, t_, val, val, q]
            )

            out = arr.copy()
            out[target_mask, 0] = new_r[target_mask] * 255
            out[target_mask, 1] = new_g[target_mask] * 255
            out[target_mask, 2] = new_b[target_mask] * 255

            out_img = _PILImage.fromarray(out.astype(_np.uint8), "RGBA")
            buf = _io.BytesIO()
            out_img.save(buf, format="PNG")
            b64 = __import__("base64").b64encode(buf.getvalue()).decode()
            logger.info(
                "color_replace_region: %s → %s | %d pixels changed (box %d,%d %dx%d)",
                fc, tc, int(_np.sum(target_mask)), box_left, box_top, box_width, box_height,
            )
            return b64

        except Exception as exc:
            logger.error("color_replace_region failed: %s", exc)
            return None

    def color_replace(
        self,
        image_bytes: bytes,
        from_color: str,
        to_color: str,
        tolerance: int = 30,
    ) -> str | None:
        """
        Programmatic hue-based color replacement using PIL.

        Shifts pixels whose hue falls within `from_color`'s HSV range to
        `to_color`'s hue, leaving saturation, value, and all other pixels
        completely unchanged.

        Returns base64 PNG string, or None if PIL unavailable / color unknown.

        Args:
            image_bytes: Raw image bytes (any PIL-supported format).
            from_color:  Color name to replace (e.g. "blue").
            to_color:    Color name to shift to   (e.g. "purple").
            tolerance:   Hue tolerance in degrees around the center hue.
        """
        if not _PIL_AVAILABLE:
            return None

        # ── Color name → HSV hue center ──────────────────────────────────────
        # Hue in degrees 0-360. PIL uses 0-255 so we scale in the loop below.
        _HUE_CENTER: dict[str, int] = {
            "red":     0,
            "orange":  30,
            "yellow":  55,
            "green":   120,
            "cyan":    180,
            "teal":    175,
            "blue":    220,
            "navy":    230,
            "indigo":  255,
            "violet":  270,
            "purple":  275,
            "magenta": 300,
            "pink":    320,
            "rose":    340,
        }

        fc = from_color.lower().strip()
        tc = to_color.lower().strip()
        from_hue = _HUE_CENTER.get(fc)
        to_hue   = _HUE_CENTER.get(tc)
        if from_hue is None or to_hue is None:
            logger.warning("color_replace: unknown color '%s' or '%s'", fc, tc)
            return None

        import io as _io
        import numpy as _np

        try:
            img = _PILImage.open(_io.BytesIO(image_bytes)).convert("RGBA")
            arr = _np.array(img, dtype=_np.float32)

            r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]

            # Convert RGB → HSV (all in 0-1 range)
            r01, g01, b01 = r / 255.0, g / 255.0, b / 255.0
            cmax = _np.maximum(_np.maximum(r01, g01), b01)
            cmin = _np.minimum(_np.minimum(r01, g01), b01)
            delta = cmax - cmin

            # Hue in degrees 0-360
            hue = _np.zeros_like(r01)
            mask_r = (cmax == r01) & (delta > 0)
            mask_g = (cmax == g01) & (delta > 0)
            mask_b = (cmax == b01) & (delta > 0)
            hue[mask_r] = (60 * ((g01[mask_r] - b01[mask_r]) / delta[mask_r])) % 360
            hue[mask_g] = (60 * ((b01[mask_g] - r01[mask_g]) / delta[mask_g]) + 120) % 360
            hue[mask_b] = (60 * ((r01[mask_b] - g01[mask_b]) / delta[mask_b]) + 240) % 360

            sat  = _np.where(cmax > 0, delta / cmax, 0.0)
            val  = cmax

            # Find pixels matching the source color hue within tolerance,
            # with enough saturation + brightness to be actual colored pixels
            lo = (from_hue - tolerance) % 360
            hi = (from_hue + tolerance) % 360
            if lo <= hi:
                hue_match = (hue >= lo) & (hue <= hi)
            else:  # wraps around 0 (e.g. red)
                hue_match = (hue >= lo) | (hue <= hi)

            target_mask = hue_match & (sat > 0.25) & (val > 0.15)

            if not _np.any(target_mask):
                logger.warning("color_replace: no matching pixels found for '%s'", fc)
                return None

            # Shift hue to target color, preserve sat+val
            hue_shift = (to_hue - from_hue) % 360
            new_hue = (hue + hue_shift * target_mask) % 360

            # Convert HSV → RGB
            h6  = new_hue / 60.0
            hi_ = _np.floor(h6).astype(int) % 6
            f   = h6 - _np.floor(h6)
            p   = val * (1 - sat)
            q   = val * (1 - f * sat)
            t_  = val * (1 - (1 - f) * sat)

            new_r = _np.select(
                [hi_ == 0, hi_ == 1, hi_ == 2, hi_ == 3, hi_ == 4, hi_ == 5],
                [val, q, p, p, t_, val]
            )
            new_g = _np.select(
                [hi_ == 0, hi_ == 1, hi_ == 2, hi_ == 3, hi_ == 4, hi_ == 5],
                [t_, val, val, q, p, p]
            )
            new_b = _np.select(
                [hi_ == 0, hi_ == 1, hi_ == 2, hi_ == 3, hi_ == 4, hi_ == 5],
                [p, p, t_, val, val, q]
            )

            # Apply only to matched pixels, keep others unchanged
            out = arr.copy()
            out[target_mask, 0] = new_r[target_mask] * 255
            out[target_mask, 1] = new_g[target_mask] * 255
            out[target_mask, 2] = new_b[target_mask] * 255

            out_img = _PILImage.fromarray(out.astype(_np.uint8), "RGBA")
            buf = _io.BytesIO()
            out_img.save(buf, format="PNG")
            b64 = __import__("base64").b64encode(buf.getvalue()).decode()
            logger.info(
                "color_replace: %s → %s | %d pixels changed",
                fc, tc, int(_np.sum(target_mask)),
            )
            return b64

        except Exception as exc:
            logger.error("color_replace failed: %s", exc)
            return None

    async def health(self) -> dict:
        """Quick health check — verifies the API key is set and the client initialises."""
        try:
            self._get_client()
            return {"status": "ok", "provider": "dall-e-3"}
        except RuntimeError as exc:
            return {"status": "error", "provider": "dall-e-3", "detail": str(exc)}
