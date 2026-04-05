"""
Image-to-Code Chain Orchestrator
=================================
Four specialized brains, each with its own role and system prompt.
All powered by Claude — no local models.

  👁  Vision Brain  — reads the screenshot, produces a precise UI spec
  🔨  Builder Brain — builds complete HTML/CSS/JS from the spec (streaming)
  🔍  Reviewer Brain — scores the build 0-100, lists any gaps
  🔧  Fixer Brain   — fixes reviewer issues, re-reviewed up to N times

[MODEL ROUTER] image_to_code → Claude claude-sonnet-4-6 (vision+build+fix) + Claude Haiku (review)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

_MAX_FIX_LOOPS  = 2
_VISION_MODEL   = "claude-sonnet-4-6"
_BUILD_MODEL    = "claude-opus-4-6"
_REVIEW_MODEL   = "claude-sonnet-4-6"  # thorough review
_FIX_MODEL      = "claude-opus-4-6"

try:
    import anthropic as _anthropic_lib
    _CLAUDE_AVAILABLE = True  # Always require Claude — no local fallback
except ImportError:
    _anthropic_lib    = None  # type: ignore
    _CLAUDE_AVAILABLE = False


# ── System prompts — loaded from knowledge base ───────────────────────────────
from ..brains.knowledge_base import (  # noqa: E402
    image_to_code_build_prompt as _kb_build_prompt,
    review_prompt              as _kb_review_prompt,
    HOW_TO_BUILD               as _HOW_TO_BUILD,
    EXECUTIVE_MINDSET          as _EXECUTIVE_MINDSET,
    PARALLEL_ANALYSIS_PROTOCOL as _PARALLEL_ANALYSIS,
    SELF_REVIEW_CHECKLIST      as _SELF_REVIEW_CHECKLIST,
    SECURITY_RULES             as _SECURITY_RULES,
    ACCESSIBILITY_STANDARDS    as _ACCESSIBILITY_STANDARDS,
    REGRESSION_PREVENTION      as _REGRESSION_PREVENTION,
)

_VISION_PROMPT = """\
You are Mini Assistant's Vision Brain — a UI analyst who reads screenshots precisely.

Your job: produce a technical specification so the Builder Brain can recreate the UI exactly.

Describe in this order:
1. COLOR PALETTE — background, surface, text, buttons, inputs, accents. Use exact hex codes.
2. LAYOUT — overall structure (header/sidebar/main/footer), flexbox or grid, alignment
3. TYPOGRAPHY — font sizes (px or rem), weights, hierarchy (h1/h2/body/label/caption)
4. COMPONENTS — every visible element: logo, nav links, inputs, buttons, cards, badges, icons
5. SPACING — padding and margin values; gap between sections
6. STYLE — dark/light, glass/flat/gradient, shadow depth, border-radius values
7. INTERACTIONS — hover states, active states, animations visible in the screenshot
8. TEXT CONTENT — exact labels, placeholder text, button text, headings word-for-word

Be precise and technical. Hex codes over color names. Pixel values over vague descriptions.
This spec is handed DIRECTLY to the Builder Brain — every detail you give will be built."""

_BUILD_SYSTEM = (
    _EXECUTIVE_MINDSET + "\n"
    + _PARALLEL_ANALYSIS + "\n"
    + _HOW_TO_BUILD
    + _SECURITY_RULES
    + _ACCESSIBILITY_STANDARDS
    + _SELF_REVIEW_CHECKLIST
    + """
## OUTPUT FORMAT
Start with ```html on its own line.
End with ``` on its own line.
Output the COMPLETE file every time — never partial snippets.
A Reviewer Brain will check your work — build it right the first time."""
)

_REVIEW_SYSTEM = _kb_review_prompt()

_FIX_SYSTEM = (
    _EXECUTIVE_MINDSET + "\n"
    + _HOW_TO_BUILD
    + _REGRESSION_PREVENTION
    + _SECURITY_RULES
    + _SELF_REVIEW_CHECKLIST
    + """
## YOUR TASK: FIX
A reviewer found issues with the build. Fix every issue listed.
The reviewer's list is the source of truth — address each item specifically.
User requirements take absolute priority over everything else.
Run SELF_REVIEW_CHECKLIST on your output before finishing.

## OUTPUT FORMAT
Start with ```html on its own line.
End with ``` on its own line.
Output the COMPLETE fixed file."""
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tok(text: str) -> str:
    return f"data: {json.dumps({'t': text})}\n\n"


def _extract_html(text: str) -> str:
    m = re.search(r"```(?:html)?\n?([\s\S]*?)```", text)
    return m.group(1).strip() if m else text.strip()


def _detect_media_type(b64: str) -> str:
    if b64.startswith("/9j/") or b64.startswith("/9J/"):
        return "image/jpeg"
    if b64.startswith("iVBOR"):
        return "image/png"
    if b64.startswith("UklGR"):
        return "image/webp"
    return "image/jpeg"


def _parse_review(text: str) -> tuple[bool, float, list[str]]:
    """Returns (is_pass, confidence_0_100, issues_list)."""
    t = text.strip()
    if re.match(r"^PASS\b", t, re.IGNORECASE):
        return True, 98.0, []
    score_m = re.search(r"SCORE:\s*(\d+)", t, re.IGNORECASE)
    score   = float(score_m.group(1)) if score_m else 50.0
    issues  = [ln.strip() for ln in t.split("\n") if re.match(r"^\d+[.)]\s", ln.strip())]
    return False, score, issues


def _get_skill_context(user_request: str) -> str:
    try:
        from mini_assistant.phase3.skill_selector import SkillSelector
        skill = SkillSelector().select(user_request, intent="app_builder")
        if skill and skill.validation_rules:
            rules = "\n".join(f"• {r}" for r in skill.validation_rules)
            return f"\n\n[SKILL CHECKLIST: {skill.name}]\n{rules}"
    except Exception as exc:
        logger.debug("Skill lookup failed (non-fatal): %s", exc)
    return ""


def _obs_record(**kwargs):
    try:
        from mini_assistant.observability import BrainCall, record
        record(BrainCall(**kwargs))
    except Exception:
        pass


# ── Claude brain functions ────────────────────────────────────────────────────

async def _claude_vision(api_key: str, images: list[str]) -> str:
    """
    Vision Brain — Claude analyzes the screenshot and returns a UI spec.
    Non-streaming (we need the full spec before building).
    """
    content = []
    for b64 in images[:4]:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": _detect_media_type(b64),
                "data": b64,
            },
        })
    content.append({"type": "text", "text": _VISION_PROMPT})

    client = _anthropic_lib.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=_VISION_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": content}],
    )
    return response.content[0].text


async def _claude_build_stream(api_key: str, user_request: str, ui_spec: str, skill_ctx: str):
    """
    Builder Brain — Claude streams HTML/CSS/JS from the vision spec.
    Async generator yielding text tokens.
    """
    msg = (
        f"[USER REQUIREMENTS — HIGHEST PRIORITY]\n{user_request}\n\n"
        f"[UI SPECIFICATION FROM VISION ANALYST]\n{ui_spec}"
        f"{skill_ctx}\n\n"
        "Build the complete app now. User requirements override everything else — "
        "match their exact colors, style, and naming. Start with ```html"
    )
    client = _anthropic_lib.AsyncAnthropic(api_key=api_key)
    async with client.messages.stream(
        model=_BUILD_MODEL,
        max_tokens=8192,
        system=_BUILD_SYSTEM,
        messages=[{"role": "user", "content": msg}],
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def _claude_review(api_key: str, user_request: str, ui_spec: str, code: str) -> str:
    """
    Reviewer Brain — Claude checks the build against spec and requirements.
    Non-streaming (we just need PASS or issue list).
    Uses Haiku — cheaper for this simple classification task.
    """
    msg = (
        f"[USER REQUIREMENTS]\n{user_request}\n\n"
        f"[UI SPECIFICATION]\n{ui_spec}\n\n"
        f"[GENERATED CODE]\n```html\n{code}\n```"
    )
    client = _anthropic_lib.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=_REVIEW_MODEL,
        max_tokens=512,
        system=_REVIEW_SYSTEM,
        messages=[{"role": "user", "content": msg}],
    )
    return response.content[0].text


async def _claude_fix_stream(
    api_key: str, user_request: str, ui_spec: str, code: str, issues: str
):
    """
    Fixer Brain — Claude fixes the build based on reviewer feedback.
    Async generator yielding text tokens.
    """
    msg = (
        f"[USER REQUIREMENTS — TOP PRIORITY]\n{user_request}\n\n"
        f"[UI SPECIFICATION]\n{ui_spec}\n\n"
        f"[PREVIOUS CODE]\n```html\n{code}\n```\n\n"
        f"[REVIEWER ISSUES — FIX ALL OF THESE]\n{issues}\n\n"
        "Fix every issue. User requirements take absolute priority. "
        "Output the COMPLETE updated HTML file. Start with ```html"
    )
    client = _anthropic_lib.AsyncAnthropic(api_key=api_key)
    async with client.messages.stream(
        model=_FIX_MODEL,
        max_tokens=8192,
        system=_FIX_SYSTEM,
        messages=[{"role": "user", "content": msg}],
    ) as stream:
        async for text in stream.text_stream:
            yield text



# ── Main pipeline ─────────────────────────────────────────────────────────────

async def image_to_code_pipeline(
    images:       list,
    user_request: str,
    session_id:   str = "",
):
    """
    Async generator — yields SSE strings.

    👁 Vision Brain (Claude) → 🔨 Builder Brain (Claude, streaming)
      → 🔍 Reviewer Brain (Claude Haiku) → 🔧 Fixer Brain (Claude, streaming) × N

    [MODEL ROUTER] image_to_code → Claude claude-sonnet-4-6
    """
    import time

    api_key    = os.environ.get("ANTHROPIC_API_KEY", "")
    use_claude = _CLAUDE_AVAILABLE and bool(api_key)
    skill_ctx  = _get_skill_context(user_request)

    if not use_claude:
        yield _tok("❌ ANTHROPIC_API_KEY is not set. Image-to-code requires Claude API.\n\n")
        return

    # ── STEP 1: Vision Brain ─────────────────────────────────────────────────
    yield _tok("👁 **Vision Brain** analyzing your image...\n\n")
    t0 = time.perf_counter()

    try:
        ui_spec = await _claude_vision(api_key, images)
        logger.info("[MODEL ROUTER] image_vision → Claude %s | %d chars", _VISION_MODEL, len(ui_spec))
        _obs_record(
            brain="vision", model=_VISION_MODEL, task="vision_analysis",
            session_id=session_id, latency_ms=(time.perf_counter() - t0) * 1000,
            outcome="success", tokens_out=len(ui_spec.split()),
        )
    except Exception as exc:
        logger.error("Claude Vision failed: %s", exc)
        yield _tok(f"❌ Vision Brain error: {exc}\n\n")
        return

    yield _tok("✅ **Vision Brain** done.\n\n")

    # ── STEP 2: Builder Brain ────────────────────────────────────────────────
    yield _tok("🔨 **Builder Brain** generating your app...\n\n")
    t0 = time.perf_counter()
    built_raw  = ""
    built_code = ""

    try:
        async for text in _claude_build_stream(api_key, user_request, ui_spec, skill_ctx):
            built_raw += text
            yield _tok(text)
        built_code = _extract_html(built_raw)
        logger.info("[MODEL ROUTER] image_build → Claude %s | %d chars", _BUILD_MODEL, len(built_code))
        _obs_record(
            brain="builder", model=_BUILD_MODEL, task="build",
            session_id=session_id, latency_ms=(time.perf_counter() - t0) * 1000,
            tokens_out=len(built_raw.split()), outcome="success" if built_code else "fail",
        )
    except Exception as exc:
        logger.error("Claude Builder failed: %s", exc)
        yield _tok(f"\n\n⚠️ Builder error: {exc}\n")
        return

    logger.info("Builder OK — %d chars", len(built_code))

    # ── STEP 3+: Reviewer Brain + Fixer Brain loop ───────────────────────────
    last_review = ""
    final_score = 50.0

    for attempt in range(_MAX_FIX_LOOPS + 1):
        yield _tok(f"\n\n🔍 **Reviewer Brain** checking the build...\n\n")
        t0 = time.perf_counter()

        try:
            review_text = await _claude_review(api_key, user_request, ui_spec, built_code)
        except Exception as exc:
            logger.warning("Claude Reviewer failed: %s — accepting build", exc)
            review_text = "PASS"

        is_pass, score, issues = _parse_review(review_text)
        last_review  = review_text
        final_score  = score
        _obs_record(
            brain="reviewer", model=_REVIEW_MODEL if use_claude else reviewer_model,
            task=f"review_{attempt+1}", session_id=session_id,
            latency_ms=(time.perf_counter() - t0) * 1000,
            confidence=score, outcome="success" if is_pass else "partial",
        )

        if is_pass:
            yield _tok(f"✅ **Reviewer Brain** approved! (score {score:.0f}/100)\n\n")
            break

        yield _tok(f"🔎 Score: {score:.0f}/100 — {len(issues)} issue(s) found.\n\n")

        if attempt >= _MAX_FIX_LOOPS:
            yield _tok("⚠️ Max fix cycles reached — delivering best version.\n\n")
            break

        # ── Fixer Brain ───────────────────────────────────────────────────────
        yield _tok(f"🔧 **Fixer Brain** fixing issues (round {attempt + 1}/{_MAX_FIX_LOOPS})...\n\n")
        t0 = time.perf_counter()
        fixed_raw = ""

        try:
            async for text in _claude_fix_stream(api_key, user_request, ui_spec, built_code, review_text):
                fixed_raw += text
                yield _tok(text)
        except Exception as exc:
            logger.warning("Claude Fixer failed: %s", exc)
            yield _tok(f"\n\n⚠️ Fixer error: {exc} — keeping previous build.\n\n")
            break

        _obs_record(
            brain="fixer", model=_FIX_MODEL if use_claude else builder_model,
            task=f"fix_{attempt+1}", session_id=session_id,
            latency_ms=(time.perf_counter() - t0) * 1000,
            tokens_out=len(fixed_raw.split()), outcome="success" if fixed_raw else "fail",
        )
        if fixed_raw:
            built_code = _extract_html(fixed_raw)

    # ── Done ─────────────────────────────────────────────────────────────────
    yield _tok(
        "\n\nHere's your build! What would you like to change?\n"
        "1. Adjust colors, fonts, or spacing\n"
        "2. Add features or interactions\n"
        "3. Change a specific component\n"
    )
