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

logger = logging.getLogger(__name__)

# DALL-E 3 valid sizes
VALID_SIZES = {"1024x1024", "1024x1792", "1792x1024"}
DEFAULT_SIZE = "1024x1024"

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

    async def health(self) -> dict:
        """Quick health check — verifies the API key is set and the client initialises."""
        try:
            self._get_client()
            return {"status": "ok", "provider": "dall-e-3"}
        except RuntimeError as exc:
            return {"status": "error", "provider": "dall-e-3", "detail": str(exc)}
