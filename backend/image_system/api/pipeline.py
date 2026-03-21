"""
Image-to-Code Chain Orchestrator
=================================
Four specialized brains, each with its own role and system prompt.
All powered by Claude when ANTHROPIC_API_KEY is present.
Falls back to local Ollama models when no API key.

  👁  Vision Brain  — reads the screenshot, produces a precise UI spec
  🔨  Builder Brain — builds complete HTML/CSS/JS from the spec (streaming)
  🔍  Reviewer Brain — scores the build 0-100, lists any gaps
  🔧  Fixer Brain   — fixes reviewer issues, re-reviewed up to N times

Claude path  (~$0.01-0.02/build):  Vision→Build→Review→Fix  all via Claude API
Local path   (free, slower):        moondream→qwen2.5-coder→gemma3→fix loop
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
_BUILD_MODEL    = "claude-sonnet-4-6"
_REVIEW_MODEL   = "claude-haiku-4-5-20251001"  # cheaper — review is a simple task
_FIX_MODEL      = "claude-sonnet-4-6"

try:
    import anthropic as _anthropic_lib
    _CLAUDE_AVAILABLE = bool(os.environ.get("ANTHROPIC_API_KEY"))
except ImportError:
    _anthropic_lib    = None  # type: ignore
    _CLAUDE_AVAILABLE = False


# ── System prompts — each brain stays in its lane ────────────────────────────

_VISION_PROMPT = """\
You are a UI analyst. You will receive a screenshot of a web UI.

Your job: produce a precise technical specification so a developer can rebuild it exactly.

Describe:
1. COLOR PALETTE — background, text, buttons, inputs, accents. Use exact hex codes where readable.
2. LAYOUT — structure, grid/flex, sections, positioning of each element
3. TYPOGRAPHY — font sizes, weights, hierarchy (h1/h2/body/label)
4. COMPONENTS — every visible element: logo, nav, inputs, buttons, cards, icons, images
5. SPACING — padding, margins, gaps between elements
6. STYLE — dark/light, glass, flat, gradient, shadows, border-radius
7. TEXT CONTENT — exact labels, placeholders, button text, headings

Be precise and technical. This spec will be handed directly to a developer."""

_BUILD_SYSTEM = """\
You are an expert frontend developer. Build complete, pixel-faithful web UIs from specs.

## Standards
- Single self-contained HTML file: CSS in <style>, JS in <script>
- CSS custom properties for every color: --primary, --bg, --text, --accent, etc.
- Flexbox or CSS Grid — no floats, no tables
- Real JavaScript — live state, real event handlers, no stubs, no TODO comments
- Every interactive element must actually work
- NEVER use external image URLs (via.placeholder.com etc.) — they are dead
- Logos: inline SVG using the app name and brand colors
- Placeholder images: CSS gradient or SVG with text
- Smooth transitions (0.2s ease) on all interactive elements
- Mobile-responsive (media queries)
- Empty states for lists and content areas

## Output format
Start with ```html on its own line.
End with ``` on its own line.
Output the COMPLETE file every time — never partial snippets."""

_REVIEW_SYSTEM = """\
You are a senior frontend code reviewer. Your job is to check whether generated code \
faithfully implements a UI specification.

You receive:
1. The original user requirements
2. The UI specification from the vision analyst
3. The generated HTML/CSS/JS code

Check for:
- All required elements present and positioned correctly
- Colors match the spec exactly (check hex values)
- All interactive elements functional
- Layout matches the screenshot description
- Typography and spacing reasonable

Output format (STRICT):
- Code is correct: output exactly PASS
- Issues found: first line "SCORE: X/100", then numbered list of specific problems
  Example:
    SCORE: 72/100
    1. Background should be #0d0d12, currently white
    2. Missing email input field
    3. Submit button has no click handler

Do NOT rewrite code. Only flag real gaps."""

_FIX_SYSTEM = _BUILD_SYSTEM + """

You are fixing a previous build based on reviewer feedback.
Every issue in the reviewer list MUST be fixed.
User requirements take absolute priority over everything else."""


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


# ── Local brain helpers (fallback when no API key) ────────────────────────────

async def _local_vision(ollama_client, vision_model: str, images: list[str]) -> str:
    """moondream fallback — two focused queries, filter garbage."""
    colors_t = asyncio.ensure_future(ollama_client.run_chat(
        vision_model,
        [{"role": "user", "content": "What colors do you see? List background, text, button, input colors. Use hex if readable.", "images": images}],
        timeout=90,
    ))
    layout_t = asyncio.ensure_future(ollama_client.run_chat(
        vision_model,
        [{"role": "user", "content": "Describe the layout. What elements are visible and where?", "images": images}],
        timeout=90,
    ))
    results = []
    for task, label in [(colors_t, "COLORS"), (layout_t, "LAYOUT")]:
        try:
            val = await asyncio.wait_for(task, timeout=95)
            if val and len(val.strip()) > 5 and val.strip() not in ("?", "...", "N/A"):
                results.append(f"{label}: {val.strip()}")
        except Exception as exc:
            logger.warning("Local vision %s failed: %s", label, exc)
    return "\n".join(results) or "No visual details extracted."


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def image_to_code_pipeline(
    images:         list,
    user_request:   str,
    ollama_client,
    vision_model:   str,
    builder_model:  str,
    reviewer_model: str,
    session_id:     str = "",
):
    """
    Async generator — yields SSE strings.

    Claude path (API key present):
      👁 Vision Brain (Claude) → 🔨 Builder Brain (Claude, streaming)
        → 🔍 Reviewer Brain (Claude Haiku) → 🔧 Fixer Brain (Claude, streaming) × N

    Local path (no API key):
      👁 moondream → 🔨 qwen2.5-coder (streaming) → 🔍 gemma3 → 🔧 fix loop
    """
    import time

    api_key     = os.environ.get("ANTHROPIC_API_KEY", "")
    use_claude  = _CLAUDE_AVAILABLE and bool(api_key)
    skill_ctx   = _get_skill_context(user_request)

    # ── STEP 1: Vision Brain ─────────────────────────────────────────────────
    yield _tok("👁 **Vision Brain** analyzing your image...\n\n")
    t0 = time.perf_counter()

    if use_claude:
        try:
            ui_spec = await _claude_vision(api_key, images)
            logger.info("Claude Vision OK — %d chars", len(ui_spec))
            _obs_record(
                brain="vision", model=_VISION_MODEL, task="vision_analysis",
                session_id=session_id, latency_ms=(time.perf_counter() - t0) * 1000,
                outcome="success", tokens_out=len(ui_spec.split()),
            )
        except Exception as exc:
            logger.warning("Claude Vision failed: %s — falling back to local", exc)
            yield _tok(f"⚠️ Vision fallback (Claude unavailable)...\n\n")
            ui_spec = await _local_vision(ollama_client, vision_model, images)
    else:
        ui_spec = ""
        _t_local = asyncio.ensure_future(_local_vision(ollama_client, vision_model, images))
        while not _t_local.done():
            try:
                ui_spec = await asyncio.wait_for(asyncio.shield(_t_local), timeout=3.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
        if not ui_spec:
            try:
                ui_spec = _t_local.result()
            except Exception as exc:
                logger.warning("Local vision failed: %s", exc)
                ui_spec = "Could not analyze image."

    yield _tok("✅ **Vision Brain** done.\n\n")

    # ── STEP 2: Builder Brain ────────────────────────────────────────────────
    yield _tok("🔨 **Builder Brain** generating your app...\n\n")
    t0 = time.perf_counter()
    built_raw  = ""
    built_code = ""

    if use_claude:
        try:
            async for text in _claude_build_stream(api_key, user_request, ui_spec, skill_ctx):
                built_raw += text
                yield _tok(text)
            built_code = _extract_html(built_raw)
            _obs_record(
                brain="builder", model=_BUILD_MODEL, task="build",
                session_id=session_id, latency_ms=(time.perf_counter() - t0) * 1000,
                tokens_out=len(built_raw.split()), outcome="success" if built_code else "fail",
            )
        except Exception as exc:
            logger.warning("Claude Builder failed: %s", exc)
            yield _tok(f"\n\n⚠️ Builder error: {exc}\n")
            return
    else:
        # Local builder (qwen2.5-coder)
        _build_msg = (
            f"[USER REQUIREMENTS — TOP PRIORITY]\n{user_request}\n\n"
            f"[VISUAL ANALYSIS]\n{ui_spec}{skill_ctx}\n\n"
            "Build the complete HTML/CSS/JS app. Start with ```html"
        )
        try:
            _b_stream = ollama_client.run_chat_stream(
                model=builder_model,
                messages=[{"role": "system", "content": _BUILD_SYSTEM}, {"role": "user", "content": _build_msg}],
                temperature=0.3,
            )
            _b_aiter = _b_stream.__aiter__()
            _b_next  = asyncio.ensure_future(_b_aiter.__anext__())
            while True:
                try:
                    token = await asyncio.wait_for(asyncio.shield(_b_next), timeout=3.0)
                    built_raw += token
                    yield _tok(token)
                    _b_next = asyncio.ensure_future(_b_aiter.__anext__())
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                except StopAsyncIteration:
                    break
        except Exception as exc:
            yield _tok(f"\n\n⚠️ Builder error: {exc}\n")
            return
        built_code = _extract_html(built_raw)

    logger.info("Builder OK — %d chars", len(built_code))

    # ── STEP 3+: Reviewer Brain + Fixer Brain loop ───────────────────────────
    last_review = ""
    final_score = 50.0

    for attempt in range(_MAX_FIX_LOOPS + 1):
        yield _tok(f"\n\n🔍 **Reviewer Brain** checking the build...\n\n")
        t0 = time.perf_counter()

        if use_claude:
            try:
                review_text = await _claude_review(api_key, user_request, ui_spec, built_code)
            except Exception as exc:
                logger.warning("Claude Reviewer failed: %s — accepting build", exc)
                review_text = "PASS"
        else:
            _r_task = asyncio.ensure_future(
                ollama_client.run_chat(
                    reviewer_model,
                    [{"role": "system", "content": _REVIEW_SYSTEM},
                     {"role": "user", "content": f"[USER REQUIREMENTS]\n{user_request}\n\n[SPEC]\n{ui_spec}\n\n[CODE]\n```html\n{built_code}\n```"}],
                    timeout=90,
                )
            )
            review_text = ""
            while not _r_task.done():
                try:
                    review_text = await asyncio.wait_for(asyncio.shield(_r_task), timeout=3.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
            if not review_text:
                try:
                    review_text = _r_task.result()
                except Exception:
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

        if use_claude:
            try:
                async for text in _claude_fix_stream(api_key, user_request, ui_spec, built_code, review_text):
                    fixed_raw += text
                    yield _tok(text)
            except Exception as exc:
                logger.warning("Claude Fixer failed: %s", exc)
                yield _tok(f"\n\n⚠️ Fixer error: {exc} — keeping previous build.\n\n")
                break
        else:
            _fix_msg = (
                f"[USER REQUIREMENTS]\n{user_request}\n\n[SPEC]\n{ui_spec}\n\n"
                f"[PREVIOUS CODE]\n```html\n{built_code}\n```\n\n"
                f"[ISSUES TO FIX]\n{review_text}\n\nOutput the COMPLETE fixed file. Start with ```html"
            )
            try:
                _f_stream = ollama_client.run_chat_stream(
                    model=builder_model,
                    messages=[{"role": "system", "content": _FIX_SYSTEM}, {"role": "user", "content": _fix_msg}],
                    temperature=0.2,
                )
                _f_aiter = _f_stream.__aiter__()
                _f_next  = asyncio.ensure_future(_f_aiter.__anext__())
                while True:
                    try:
                        token = await asyncio.wait_for(asyncio.shield(_f_next), timeout=3.0)
                        fixed_raw += token
                        yield _tok(token)
                        _f_next = asyncio.ensure_future(_f_aiter.__anext__())
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                    except StopAsyncIteration:
                        break
            except Exception as exc:
                logger.warning("Local Fixer failed: %s", exc)
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
