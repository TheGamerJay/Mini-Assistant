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

# Image EDIT model — OpenAI /v1/images/edits only supports dall-e-2.
# gpt-image-1 cannot be used here regardless of IMAGE_MODEL env var.
_IMAGE_EDIT_MODEL = "dall-e-2"

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


def build_refined_mask(
    image_bytes: bytes,
    mask_box: dict,
    tolerance: int = 50,
    feather_px: int = 3,
) -> bytes | None:
    """
    Pixel-level segmentation mask refined from a bounding box.

    Algorithm:
      1. Crop to mask_box region of interest
      2. Sample dominant color from center 25% of box
      3. Threshold pixels by Euclidean RGB distance from dominant color
      4. Apply edge map — exclude pixels sitting on sharp boundaries
         so the mask respects clothing/skin transitions
      5. Feather edges with Gaussian blur for natural blending

    Returns PNG mask bytes:
      alpha=0   (transparent) → DALL-E edits these pixels
      alpha=255 (opaque)      → DALL-E preserves these exactly
      0<alpha<255             → feathered blend zone at region boundary

    Falls back to None if PIL or numpy is unavailable, or on any error —
    caller should use the coarse bounding-box mask in that case.
    """
    if not _PIL_AVAILABLE:
        return None

    try:
        import io as _io
        import numpy as _np
        from PIL import ImageFilter as _IF

        img = _PILImage.open(_io.BytesIO(image_bytes)).convert("RGBA")
        W, H = img.size
        arr = _np.array(img, dtype=_np.float32)

        # ── Convert mask_box % → pixel coordinates ────────────────────────
        bx  = max(0, round(mask_box.get("left",   0) / 100 * W))
        by  = max(0, round(mask_box.get("top",    0) / 100 * H))
        bw  = max(1, round(mask_box.get("width",  100) / 100 * W))
        bh  = max(1, round(mask_box.get("height", 100) / 100 * H))
        bx2 = min(W, bx + bw)
        by2 = min(H, by + bh)

        if bx2 <= bx or by2 <= by:
            return None

        # ── Sample dominant color from center 25% of box ──────────────────
        # Using median over a central patch avoids outlier influence.
        cw = max(1, (bx2 - bx) // 4)
        ch = max(1, (by2 - by) // 4)
        cx, cy = (bx + bx2) // 2, (by + by2) // 2
        sx1 = max(bx, cx - cw);  sy1 = max(by, cy - ch)
        sx2 = min(bx2, cx + cw); sy2 = min(by2, cy + ch)
        sample = arr[sy1:sy2, sx1:sx2, :3]
        if sample.size == 0:
            return None
        dominant = _np.median(sample.reshape(-1, 3), axis=0)

        # ── Color-distance threshold within the box ───────────────────────
        # Euclidean distance in RGB space — pixels close to dominant color
        # are in the target region.
        box_rgb     = arr[by:by2, bx:bx2, :3]
        dist        = _np.sqrt(_np.sum((box_rgb - dominant) ** 2, axis=-1))
        color_match = dist < tolerance

        # ── Edge map — exclude pixels on sharp color boundaries ───────────
        # Sobel-like edge strength from PIL FIND_EDGES.  Strong edges mark
        # clothing/skin transitions; we do NOT include those in the mask
        # so the edit doesn't bleed across material boundaries.
        gray_arr = _np.dot(arr[by:by2, bx:bx2, :3],
                           [0.299, 0.587, 0.114]).astype(_np.uint8)
        gray_img = _PILImage.fromarray(gray_arr, "L")
        edge_arr = _np.array(gray_img.filter(_IF.FIND_EDGES)).astype(_np.float32)
        not_edge = edge_arr < 20.0   # True = not a strong edge

        # ── Refined region: color-close AND not on an edge ───────────────
        refined = (color_match & not_edge)   # bool array, shape (bh, bw)

        # ── Build full-image alpha channel ─────────────────────────────────
        # 255 = preserve, 0 = edit.  Start fully preserved.
        alpha = _np.full((H, W), 255, dtype=_np.uint8)
        alpha[by:by2, bx:bx2] = _np.where(refined, 0, 255)

        # ── Feather: Gaussian blur on alpha softens the 0↔255 boundary ───
        # This prevents harsh boxy edges in the final composited image.
        alpha_img     = _PILImage.fromarray(alpha, "L")
        alpha_blurred = _np.array(alpha_img.filter(_IF.GaussianBlur(radius=feather_px)),
                                  dtype=_np.uint8)

        # ── Compose: RGBA mask (RGB=black, alpha=feathered) ──────────────
        mask_arr          = _np.zeros((H, W, 4), dtype=_np.uint8)
        mask_arr[:, :, 3] = alpha_blurred
        result = _PILImage.fromarray(mask_arr, "RGBA")
        buf = _io.BytesIO()
        result.save(buf, format="PNG")

        n_edit_px = int(_np.sum(alpha_blurred < 128))
        logger.info(
            "build_refined_mask: box=%dx%d dominant=RGB%s edit_px=%d feather=%dpx",
            bw, bh, dominant.astype(int).tolist(), n_edit_px, feather_px,
        )
        return buf.getvalue()

    except Exception as exc:
        logger.warning("build_refined_mask failed (caller uses box mask): %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────


async def analyze_region_colors(
    client,
    image_bytes: bytes,
    target_color: str,
    target_region: str,
) -> dict:
    """
    GPT-4o vision pre-flight: identify every element that is `target_color`,
    split into elements TO CHANGE (target_region) vs elements TO PRESERVE.

    Returns:
        {
            "target_elements":   ["fur", "body"],
            "preserve_elements": ["eyes", "shoes", "headset ring"],
            "full_description":  "<detailed character description>"
        }
    """
    import base64 as _b64
    import json as _json

    # Detect actual image mime type from magic bytes
    _mime = "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        _mime = "image/jpeg"
    elif image_bytes[:4] == b"RIFF":
        _mime = "image/webp"
    img_b64 = _b64.b64encode(image_bytes).decode()
    prompt = (
        f"I need to change ONLY the character's {target_region} color from {target_color} "
        f"to a different color, leaving everything else unchanged.\n\n"
        f"Answer three things:\n\n"
        f"1. List every visible element that is currently {target_color}:\n"
        f"   - target_elements: parts of the {target_region} itself (body surface, fur, skin)\n"
        f"   - preserve_elements: ALL other {target_color} elements that must NOT change\n"
        f"     (e.g. eyes, shoes, headset ring, clothing trim, accessories, outlines)\n\n"
        f"2. Estimate a TIGHT bounding box around ONLY the {target_region} area (as % of image):\n"
        f"   top=% from top edge, left=% from left edge, width=% of image width, height=% of image height.\n"
        f"   The box must enclose just the {target_region} — not the full image, not accessories.\n\n"
        f"3. Write a full detailed character description for recreation.\n\n"
        f"Return ONLY valid JSON:\n"
        f'{{"target_elements": [...], "preserve_elements": [...], '
        f'"mask_box": {{"top": 0, "left": 0, "width": 100, "height": 100}}, '
        f'"full_description": "..."}}'
    )
    resp = await client.chat.completions.create(
        model="gpt-4o",
        max_tokens=800,
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{_mime};base64,{img_b64}", "detail": "high"}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        result = _json.loads(raw)
    except Exception:
        result = {}
    logger.info(
        "analyze_region_colors: target=%s preserve=%s mask_box=%s",
        result.get("target_elements", []),
        result.get("preserve_elements", []),
        result.get("mask_box"),
    )
    return result


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

        # dall-e-2 edit requires: square RGBA PNG, mask must match image size exactly.
        img_data = image_bytes
        mask_data = mask_bytes  # will be cropped/resized alongside image
        _crop_box: tuple | None = None
        _final_side: int = 0
        if _PIL_AVAILABLE:
            try:
                _pil = _PILImage.open(_io.BytesIO(image_bytes)).convert("RGBA")
                w, h = _pil.size
                # Make square — record the crop box so we can apply it to the mask too
                if w != h:
                    side = min(w, h)
                    _crop_box = ((w - side) // 2, (h - side) // 2,
                                 (w + side) // 2, (h + side) // 2)
                    _pil = _pil.crop(_crop_box)
                # Cap at 1024x1024
                _final_side = _pil.width
                if _pil.width > 1024:
                    _pil = _pil.resize((1024, 1024), _PILImage.LANCZOS)
                    _final_side = 1024
                buf = _io.BytesIO()
                _pil.save(buf, format="PNG", optimize=True)
                img_data = buf.getvalue()

                # Apply identical crop + resize to mask so dimensions always match
                if mask_bytes is not None:
                    try:
                        _mpil = _PILImage.open(_io.BytesIO(mask_bytes)).convert("RGBA")
                        if _crop_box:
                            _mpil = _mpil.crop(_crop_box)
                        if _mpil.width != _final_side:
                            _mpil = _mpil.resize((_final_side, _final_side), _PILImage.LANCZOS)
                        mbuf = _io.BytesIO()
                        _mpil.save(mbuf, format="PNG")
                        mask_data = mbuf.getvalue()
                    except Exception as _me:
                        logger.warning("Mask resize failed, skipping mask: %s", _me)
                        mask_data = None
            except Exception as _e:
                logger.warning("PIL PNG conversion failed, passing raw bytes: %s", _e)

        image_file = _io.BytesIO(img_data)
        image_file.name = "image.png"

        kwargs: dict = dict(
            model=_IMAGE_EDIT_MODEL,
            image=image_file,
            prompt=prompt,
            size=size,  # type: ignore[arg-type]
            response_format="b64_json",
        )

        if mask_data is not None:
            mask_file = _io.BytesIO(mask_data)
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
        preserve_elements: list | None = None,
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
            _dr_mime = "image/png"
            if image_bytes[:3] == b"\xff\xd8\xff":
                _dr_mime = "image/jpeg"
            elif image_bytes[:4] == b"RIFF":
                _dr_mime = "image/webp"
            img_b64 = _b64.b64encode(image_bytes).decode()
            logger.info("describe_and_recolor: analyzing reference image (%s→%s, mime=%s)", from_color, to_color, _dr_mime)
            vision = await client.chat.completions.create(
                model="gpt-4o",
                max_tokens=900,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{_dr_mime};base64,{img_b64}", "detail": "high"},
                        },
                        {
                            "type": "text",
                            "text": (
                                "Describe this character image in exhaustive detail so it can be recreated exactly. "
                                "Be highly specific about:\n"
                                "1. ART STYLE: rendering style (e.g. 3D CGI, flat cartoon, anime, pixel art, watercolor, photorealistic)\n"
                                "2. CHARACTER SPECIES/TYPE: exact species or character type (e.g. anthropomorphic fox, human, robot, dragon)\n"
                                "3. BODY: exact body proportions, build, and posture\n"
                                "4. FACE: facial structure, expression, eye shape, eye color, nose/muzzle type\n"
                                f"5. {region.upper()} COLOR: exact current color with any gradients or markings\n"
                                "6. HAIR/FUR DETAILS: texture, length, style of hair or fur pattern\n"
                                "7. CLOTHING: every item with exact color, style, and fit\n"
                                "8. ACCESSORIES: any jewelry, bags, weapons, props\n"
                                "9. POSE: exact body position and limb placement\n"
                                "10. BACKGROUND: setting, colors, elements\n"
                                "11. LIGHTING: light direction, shadow style, ambient color\n"
                                "Output ONLY the description. No preamble or commentary."
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
            # Use capturing group instead of variable-width look-behind
            swapped = re.sub(
                rf"({re.escape(region)}\s+(?:is|are|(?:color\s*[:\s]+))){re.escape(from_color)}\b",
                lambda m: m.group(1) + to_color, swapped, flags=re.IGNORECASE,
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
        # Build explicit preserve note from scan results
        if preserve_elements:
            _pres_note = (
                "DO NOT recolor any of these — they must keep their original colors: " +
                ", ".join(preserve_elements) + "."
            )
        else:
            _pres_note = (
                "DO NOT recolor: eyes, headset ring, shoes, clothing, accessories, outlines — "
                "these must keep their exact original colors."
            )

        # Extract art style from description to lock it in
        _art_style_hint = ""
        if modified:
            _first_line = modified.split(".")[0].strip()
            if any(kw in _first_line.lower() for kw in ("3d", "cgi", "cartoon", "anime", "pixel", "render", "watercolor", "realistic")):
                _art_style_hint = f"Art style: {_first_line}. "

        prompt = (
            f"{_art_style_hint}"
            f"Recreate this EXACT character with {to_color} {region} instead of {from_color} {region}.\n\n"
            f"WHAT CHANGES: only the {region} surface color: {from_color} → {to_color}.\n"
            f"WHAT DOES NOT CHANGE: {_pres_note}\n\n"
            f"CRITICAL — maintain EXACTLY:\n"
            f"- Same character species and design (do NOT substitute a different creature)\n"
            f"- Same art style (3D CGI stays 3D CGI, flat cartoon stays flat cartoon, etc.)\n"
            f"- Same face shape, eyes, and expression\n"
            f"- Same body proportions and pose\n"
            f"- Same clothing colors, patterns, and styles\n"
            f"- Same background and lighting\n\n"
            f"Character description (final state with {to_color} {region}):\n{modified}\n\n"
            "Render the full character head-to-toe. Do not crop or reframe."
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
        pixel_mask_bytes: bytes | None = None,
    ) -> str | None:
        """
        Programmatic hue-based color replacement restricted to a region mask.

        When pixel_mask_bytes is provided (a refined segmentation mask PNG),
        only pixels where mask alpha < 128 (transparent = edit) are recolored.
        This gives pixel-level precision — hoodie pixels inside the box but
        outside the skin region are left untouched.

        When pixel_mask_bytes is None, falls back to the coarse bounding box.

        Args:
            image_bytes:      Raw image bytes (any PIL-supported format).
            from_color:       Color name to replace (e.g. "blue").
            to_color:         Color name to shift to   (e.g. "purple").
            mask_box:         Dict with top/left/width/height as percentages 0-100.
            tolerance:        Hue tolerance in degrees around the center hue.
            pixel_mask_bytes: Optional refined segmentation mask PNG. Alpha channel
                              encodes the edit region (0=edit, 255=preserve).

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
        # Achromatic/metallic targets — cannot be produced by hue rotation.
        # Each entry is a target (R, G, B) that matched pixels are blended toward.
        _ACHROMATIC_TARGETS: dict[str, tuple] = {
            "silver":   (172, 172, 175),
            "metallic": (172, 172, 175),
            "chrome":   (180, 180, 186),
            "gold":     (212, 175,  55),
            "bronze":   (140, 100,  50),
            "white":    (238, 238, 238),
            "black":    ( 22,  22,  22),
            "gray":     (130, 130, 130),
            "grey":     (130, 130, 130),
            "dark":     ( 40,  40,  40),
            "brown":    (101,  67,  33),
            "tan":      (210, 180, 140),
            "beige":    (245, 245, 220),
            "cream":    (255, 253, 208),
            "peach":    (255, 218, 185),
        }

        fc = from_color.lower().strip()
        tc = to_color.lower().strip()
        from_hue = _HUE_CENTER.get(fc)
        _achromatic_target = _ACHROMATIC_TARGETS.get(tc)
        to_hue   = _HUE_CENTER.get(tc)
        if from_hue is None:
            logger.warning("color_replace_region: unknown source color '%s'", fc)
            return None
        if _achromatic_target is None and to_hue is None:
            logger.warning("color_replace_region: unknown target color '%s'", tc)
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

            # ── Build pixel-level region mask ─────────────────────────────────
            # Prefer refined segmentation mask (alpha < 128 = edit region).
            # Fall back to coarse bounding-box mask when not available.
            if pixel_mask_bytes is not None:
                try:
                    _pm_img   = _PILImage.open(_io.BytesIO(pixel_mask_bytes)).convert("RGBA")
                    _pm_alpha = _np.array(_pm_img)[:, :, 3].astype(_np.float32)
                    # alpha=0 (transparent) → edit; alpha=255 (opaque) → preserve
                    region_mask = _pm_alpha < 128
                    logger.info(
                        "color_replace_region: using refined mask (%d edit pixels)",
                        int(_np.sum(region_mask)),
                    )
                except Exception as _pm_err:
                    logger.warning("pixel_mask decode failed, using box: %s", _pm_err)
                    region_mask = _np.zeros((H, W), dtype=bool)
                    region_mask[box_top:box_bottom, box_left:box_right] = True
            else:
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

            # Saturation threshold: 0.10 catches lightly-saturated skin/fur tones
            # (e.g. pale blue, desaturated orange). 0.25 was too high and missed them.
            target_mask = hue_match & (sat > 0.10) & (val > 0.10) & region_mask

            if not _np.any(target_mask):
                logger.warning("color_replace_region: no matching pixels in region for '%s'", fc)
                return None

            out = arr.copy()

            if _achromatic_target is not None:
                # ── Achromatic / metallic target (silver, gold, white, black…) ──
                # Hue rotation cannot produce these — instead we blend each matched
                # pixel's luminance with the target RGB, preserving lighting variation.
                tr, tg, tb = _achromatic_target
                # Weighted luminance of original pixel (perceptual brightness)
                lum = (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]) / 255.0
                # Normalised target luminance so we can scale the target color
                t_lum = (0.299 * tr + 0.587 * tg + 0.114 * tb) / 255.0
                # Scale factor preserves per-pixel light/shadow from the original
                scale = _np.where(t_lum > 0.01, lum / t_lum, 1.0)
                # Blend: 70% target-scaled-to-match-luminance, 30% desaturated original
                # This keeps shading and contact shadows from the source art.
                orig_lum = lum[..., _np.newaxis] * 255.0  # broadcast-ready
                target_rgb = _np.stack([
                    _np.clip(tr * scale, 0, 255),
                    _np.clip(tg * scale, 0, 255),
                    _np.clip(tb * scale, 0, 255),
                ], axis=-1)
                desaturated = _np.stack([orig_lum[..., 0]] * 3, axis=-1)
                blended = 0.7 * target_rgb + 0.3 * desaturated
                out[target_mask, 0] = _np.clip(blended[target_mask, 0], 0, 255)
                out[target_mask, 1] = _np.clip(blended[target_mask, 1], 0, 255)
                out[target_mask, 2] = _np.clip(blended[target_mask, 2], 0, 255)
            else:
                # ── Chromatic target — shift hue, preserve saturation + value ──
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
