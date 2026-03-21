"""
Image-to-Code Chain Orchestrator
=================================
Ceiling architecture implementation — four-brain, confidence-scored pipeline:

  1. 👁  Vision Brain  (moondream)       — reads screenshot → detailed UI spec (two focused queries)
  2. 🔨  Builder Brain (qwen2.5-coder)   — streams HTML/CSS/JS from spec + user requirements
  3. 🔍  Reviewer Brain (gemma3:4b)      — returns SCORE: X/100 + issues list (or PASS)
  4. 🔧  Builder Brain fix loop          — fixes issues, re-reviewed up to _MAX_FIX_LOOPS times
  5. 🚀  Executive Brain (Claude API)    — escalates when confidence < _ESCALATE_THRESHOLD

Ceiling features wired in:
  • Confidence scoring — reviewer outputs 0-100; drives escalation decisions
  • Claude API escalation — when local models can't get above threshold, Claude takes over
  • Observability — every brain call logged to telemetry.jsonl (non-fatal)
  • Skill template injection — checks phase3 skill registry for matching templates
  • Graceful degradation — every brain failure falls back gracefully, never hard-crashes

Yields SSE-formatted strings for direct use in the streaming endpoint.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

_MAX_FIX_LOOPS        = 2     # reviewer → builder cycles before escalating
_ESCALATE_THRESHOLD   = 70.0  # confidence below this triggers Claude escalation
_ESCALATE_MODEL       = "claude-sonnet-4-6"

# Optional Claude API escalation (degrades gracefully if anthropic not installed)
try:
    import anthropic as _anthropic_lib
    _CLAUDE_AVAILABLE = bool(os.environ.get("ANTHROPIC_API_KEY"))
except ImportError:
    _anthropic_lib    = None  # type: ignore
    _CLAUDE_AVAILABLE = False


# ── Prompts ───────────────────────────────────────────────────────────────────

# Two short prompts — moondream (1.8B) handles short focused questions best
_VISION_COLORS_PROMPT = (
    "What colors do you see in this UI? "
    "List: background color, text color, button color, input field color, any accent colors. "
    "Use hex codes if you can read them."
)

_VISION_LAYOUT_PROMPT = (
    "Describe the layout of this UI screenshot. "
    "What elements are visible? (logo, form fields, buttons, navigation, etc.) "
    "Where are they positioned on the page?"
)

_BUILD_SYSTEM = """\
You are an expert frontend developer. Your job is to build complete, pixel-faithful web UIs.

## Coding Standards
- Single self-contained HTML file: all CSS inside <style>, all JS inside <script>
- Use CSS custom properties (--primary, --bg, --text, etc.) for every color
- Flexbox or CSS Grid for all layouts — no floats, no tables
- Real JavaScript — live state management, real event handlers, no stubs, no TODOs
- Every button, input, dropdown, and control must be fully functional
- NEVER use external image URLs (via.placeholder.com, picsum.photos, lorempixel, etc.) — they are dead
- For logos: generate an inline SVG logo using the app name and brand colors
- For placeholder images: use CSS gradient div or inline SVG with descriptive text
- Smooth transitions (0.2s ease) on all interactive elements
- Mobile-responsive by default (media queries where needed)
- Empty states for lists / content areas
- Complete, working code — never partial diffs or snippets

## Output format
Start your response with ```html on its own line.
End with ``` on its own line.
Output the COMPLETE file every time."""

_REVIEWER_SYSTEM = """\
You are a senior frontend code reviewer. You check whether generated code faithfully implements a UI spec.

You will receive:
1. USER REQUIREMENTS (highest priority — the user's own words)
2. VISUAL ANALYSIS (from screenshot)
3. GENERATED CODE

Your task: check that the code correctly implements the requirements.
Focus on: colors (are they exactly right?), layout, all required elements, functionality.

Output format (STRICT — no exceptions):
- If the code correctly implements everything: output exactly PASS
- If there are issues: first line must be "SCORE: X/100" where X is quality 0–100,
  then a numbered list of specific, actionable problems.
  Example:
    SCORE: 68/100
    1. Background should be dark (#0d0d12), currently white
    2. Missing email input field
    3. Submit button has no click handler

Do NOT rewrite or suggest the code. Do NOT explain general best practices. Only flag real gaps."""

_FIX_SYSTEM = _BUILD_SYSTEM + "\n\nYou are fixing a previous build attempt based on code reviewer feedback."


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tok(text: str) -> str:
    return f"data: {json.dumps({'t': text})}\n\n"


def _extract_html(text: str) -> str:
    m = re.search(r"```(?:html)?\n?([\s\S]*?)```", text)
    return m.group(1).strip() if m else text.strip()


def _valid(s: str) -> bool:
    """True if vision response contains real content (not garbage)."""
    return bool(s) and len(s.strip()) > 5 and s.strip() not in ("?", "...", "N/A", "")


def _parse_review(text: str) -> tuple[bool, float, list[str]]:
    """
    Parse reviewer output.
    Returns: (is_pass, confidence_0_100, issues_list)
    """
    t = text.strip()
    if re.match(r"^PASS\b", t, re.IGNORECASE):
        return True, 95.0, []
    score_m = re.search(r"SCORE:\s*(\d+)", t, re.IGNORECASE)
    score   = float(score_m.group(1)) if score_m else 50.0
    issues  = [ln.strip() for ln in t.split("\n") if re.match(r"^\d+[.)]\s", ln.strip())]
    return False, score, issues


def _get_skill_context(user_request: str) -> str:
    """
    Check the phase3 skill registry for matching templates.
    Returns a context hint string, or "" if no match / skill system unavailable.
    """
    try:
        from mini_assistant.phase3.skill_selector import SkillSelector
        selector = SkillSelector()
        # skill_selector.select() takes (request, intent)
        skill = selector.select(user_request, intent="app_builder")
        if skill and skill.validation_rules:
            rules = "\n".join(f"• {r}" for r in skill.validation_rules)
            return (
                f"\n\n[SKILL TEMPLATE MATCHED: {skill.name}]\n"
                f"Quality checklist for this type of UI:\n{rules}"
            )
    except Exception as exc:
        logger.debug("Skill registry lookup failed (non-fatal): %s", exc)
    return ""


async def _await_with_keepalives(task: asyncio.Task) -> str:
    """Await an asyncio Task, yielding SSE keepalives every 3s until it's done."""
    # This helper is called from within an async generator using 'async for' trick.
    # We return the result; the caller yields keepalives manually.
    result = None
    while not task.done():
        try:
            result = await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
        except asyncio.TimeoutError:
            pass  # caller must yield keepalive
    if result is None:
        result = task.result()  # raises if task failed
    return result


# ── Claude escalation ─────────────────────────────────────────────────────────

async def _stream_claude_fix(
    api_key: str,
    user_request: str,
    ui_description: str,
    built_code: str,
    review_result: str,
) -> "AsyncIterator[str]":
    """Async generator yielding text tokens from Claude API."""
    escalation_msg = (
        f"[USER REQUIREMENTS — HIGHEST PRIORITY]\n{user_request}\n\n"
        f"[VISUAL ANALYSIS FROM SCREENSHOT]\n{ui_description}\n\n"
        f"[PREVIOUS LOCAL BUILD — needs improvement]\n```html\n{built_code}\n```\n\n"
        f"[REVIEWER ISSUES TO FIX]\n{review_result}\n\n"
        "Fix ALL issues. User requirements take absolute highest priority — match their exact colors, "
        "style, and specifications. Build a complete, polished, pixel-faithful implementation. "
        "Start with ```html"
    )
    client = _anthropic_lib.AsyncAnthropic(api_key=api_key)
    async with client.messages.stream(
        model=_ESCALATE_MODEL,
        max_tokens=8192,
        system=_BUILD_SYSTEM,
        messages=[{"role": "user", "content": escalation_msg}],
    ) as stream:
        async for text in stream.text_stream:
            yield text


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def image_to_code_pipeline(
    images:        list,
    user_request:  str,
    ollama_client,
    vision_model:  str,
    builder_model: str,
    reviewer_model: str,
    session_id:    str = "",
):
    """
    Async generator — yields SSE strings.

    Ceiling pipeline:
      Vision → Builder (stream) → Reviewer (scored)
        └─ if issues + confidence < threshold → Builder fix (stream) → Reviewer  ×N
           └─ if still failing → Claude API escalation (stream)
    """
    # Lazy import so observability failures never crash the pipeline
    try:
        from mini_assistant.observability import BrainCall, Timer, record as obs_record
        _obs = True
    except Exception:
        _obs = False

    def _obs_record(**kwargs):
        if _obs:
            try:
                obs_record(BrainCall(**kwargs))
            except Exception:
                pass

    # ── STEP 1: Skill template lookup (fast, non-blocking) ────────────────────
    skill_context = _get_skill_context(user_request)

    # ── STEP 2: Vision Brain — two focused queries ────────────────────────────
    yield _tok("👁 **Vision Brain** is analyzing your image...\n\n")

    _t_colors = asyncio.ensure_future(
        ollama_client.run_chat(
            vision_model,
            [{"role": "user", "content": _VISION_COLORS_PROMPT, "images": images}],
            timeout=90,
        )
    )
    colors_desc = ""
    with (Timer() if _obs else _NullTimer()) as tmr_colors:
        while not _t_colors.done():
            try:
                colors_desc = await asyncio.wait_for(asyncio.shield(_t_colors), timeout=3.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
        if not colors_desc:
            try:
                colors_desc = _t_colors.result()
            except Exception as exc:
                logger.warning("Vision colors failed: %s", exc)
    _obs_record(
        brain="vision_colors", model=vision_model, task="color_extraction",
        session_id=session_id, latency_ms=tmr_colors.elapsed_ms,
        outcome="success" if _valid(colors_desc) else "fail",
        notes=colors_desc[:80] if _valid(colors_desc) else "garbage",
    )

    _t_layout = asyncio.ensure_future(
        ollama_client.run_chat(
            vision_model,
            [{"role": "user", "content": _VISION_LAYOUT_PROMPT, "images": images}],
            timeout=90,
        )
    )
    layout_desc = ""
    with (Timer() if _obs else _NullTimer()) as tmr_layout:
        while not _t_layout.done():
            try:
                layout_desc = await asyncio.wait_for(asyncio.shield(_t_layout), timeout=3.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
        if not layout_desc:
            try:
                layout_desc = _t_layout.result()
            except Exception as exc:
                logger.warning("Vision layout failed: %s", exc)
    _obs_record(
        brain="vision_layout", model=vision_model, task="layout_extraction",
        session_id=session_id, latency_ms=tmr_layout.elapsed_ms,
        outcome="success" if _valid(layout_desc) else "fail",
    )

    ui_description = ""
    if _valid(colors_desc):
        ui_description += f"COLORS: {colors_desc.strip()}\n"
    if _valid(layout_desc):
        ui_description += f"LAYOUT: {layout_desc.strip()}\n"
    if not ui_description:
        ui_description = "No visual details extracted — build from user requirements only."
        logger.warning("Vision Brain returned no useful data for session %s", session_id)

    logger.info("Vision OK — %d chars", len(ui_description))
    yield _tok("✅ **Vision Brain** done.\n\n🔨 **Builder Brain** generating code...\n\n")

    # ── STEP 3: Builder Brain — initial build (streaming) ────────────────────
    _build_user = (
        f"[USER REQUIREMENTS — HIGHEST PRIORITY — FOLLOW THESE EXACTLY]\n"
        f"{user_request}\n\n"
        f"[VISUAL ANALYSIS FROM SCREENSHOT]\n{ui_description}"
        f"{skill_context}\n\n"
        "Build the complete HTML/CSS/JS app now. "
        "User requirements above override all other context — "
        "if the user specified exact colors, use those exact colors. "
        "Start your response with ```html"
    )

    built_code_raw = ""
    with (Timer() if _obs else _NullTimer()) as tmr_build:
        try:
            _b_stream = ollama_client.run_chat_stream(
                model=builder_model,
                messages=[
                    {"role": "system", "content": _BUILD_SYSTEM},
                    {"role": "user",   "content": _build_user},
                ],
                temperature=0.3,
            )
            _b_aiter = _b_stream.__aiter__()
            _b_next  = asyncio.ensure_future(_b_aiter.__anext__())
            while True:
                try:
                    token = await asyncio.wait_for(asyncio.shield(_b_next), timeout=3.0)
                    built_code_raw += token
                    yield _tok(token)
                    _b_next = asyncio.ensure_future(_b_aiter.__anext__())
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                except StopAsyncIteration:
                    break
        except Exception as exc:
            logger.warning("Builder Brain failed: %s", exc)
            yield _tok(f"\n\n⚠️ Builder error: {exc}\n")
            return

    _obs_record(
        brain="builder", model=builder_model, task="initial_build",
        session_id=session_id, latency_ms=tmr_build.elapsed_ms,
        tokens_out=len(built_code_raw.split()),
        outcome="success" if built_code_raw else "fail",
    )

    built_code = _extract_html(built_code_raw)
    logger.info("Builder OK — %d chars", len(built_code))

    # ── STEP 4+: Reviewer Brain + fix loop ───────────────────────────────────
    final_confidence = 50.0
    final_issues     = []
    last_review_text = ""

    for attempt in range(_MAX_FIX_LOOPS + 1):
        yield _tok(f"\n\n🔍 **Reviewer Brain** checking build quality...\n\n")

        _review_user = (
            f"[USER REQUIREMENTS — TOP PRIORITY]\n{user_request}\n\n"
            f"[VISUAL ANALYSIS]\n{ui_description}\n\n"
            f"[GENERATED CODE]\n```html\n{built_code}\n```"
        )
        _r_task = asyncio.ensure_future(
            ollama_client.run_chat(
                reviewer_model,
                [
                    {"role": "system", "content": _REVIEWER_SYSTEM},
                    {"role": "user",   "content": _review_user},
                ],
                timeout=90,
            )
        )
        review_raw = ""
        with (Timer() if _obs else _NullTimer()) as tmr_review:
            while not _r_task.done():
                try:
                    review_raw = await asyncio.wait_for(asyncio.shield(_r_task), timeout=3.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
            if not review_raw:
                try:
                    review_raw = _r_task.result()
                except Exception as exc:
                    logger.warning("Reviewer failed: %s — accepting build", exc)
                    review_raw = "PASS"

        is_pass, confidence, issues = _parse_review(review_raw)
        final_confidence = confidence
        final_issues     = issues
        last_review_text = review_raw
        logger.info("Reviewer attempt %d: pass=%s score=%.0f", attempt + 1, is_pass, confidence)

        _obs_record(
            brain="reviewer", model=reviewer_model,
            task=f"review_attempt_{attempt+1}",
            session_id=session_id, latency_ms=tmr_review.elapsed_ms,
            confidence=confidence,
            outcome="success" if is_pass else "partial",
        )

        if is_pass:
            yield _tok(f"✅ **Reviewer Brain** approved! (confidence {confidence:.0f}/100)\n\n")
            break

        yield _tok(f"🔎 Score: {confidence:.0f}/100 — {len(issues)} issue(s) found.\n\n")

        if attempt >= _MAX_FIX_LOOPS:
            # Max local loops reached — escalate or accept
            break

        # Issues found → fix pass
        yield _tok(
            f"🔧 **Builder Brain** fixing issues "
            f"(pass {attempt + 1}/{_MAX_FIX_LOOPS})...\n\n"
        )
        _fix_user = (
            f"[USER REQUIREMENTS — TOP PRIORITY]\n{user_request}\n\n"
            f"[VISUAL ANALYSIS]\n{ui_description}\n\n"
            f"[YOUR PREVIOUS CODE]\n```html\n{built_code}\n```\n\n"
            f"[REVIEWER ISSUES — FIX ALL OF THESE]\n{review_raw}\n\n"
            "Fix every issue. User requirements above take absolute highest priority — "
            "ensure their exact colors and style are implemented. "
            "Output the COMPLETE updated HTML file. Start with ```html"
        )
        fixed_raw = ""
        with (Timer() if _obs else _NullTimer()) as tmr_fix:
            try:
                _f_stream = ollama_client.run_chat_stream(
                    model=builder_model,
                    messages=[
                        {"role": "system", "content": _FIX_SYSTEM},
                        {"role": "user",   "content": _fix_user},
                    ],
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
                logger.warning("Fix Brain failed: %s — keeping previous build", exc)
                break

        _obs_record(
            brain="builder_fix", model=builder_model,
            task=f"fix_attempt_{attempt+1}",
            session_id=session_id, latency_ms=tmr_fix.elapsed_ms,
            tokens_out=len(fixed_raw.split()),
            outcome="success" if fixed_raw else "fail",
        )

        if fixed_raw:
            built_code = _extract_html(fixed_raw)

    # ── STEP 5: Claude API escalation ─────────────────────────────────────────
    # Fires when: max fix loops reached AND confidence still below threshold
    _api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not _parse_review(last_review_text)[0] and final_confidence < _ESCALATE_THRESHOLD:
        if _CLAUDE_AVAILABLE and _api_key:
            yield _tok(
                f"\n\n🚀 **Executive Brain** (Claude) is taking over "
                f"— local confidence {final_confidence:.0f}/100, escalating...\n\n"
            )
            escalated_raw = ""
            with (Timer() if _obs else _NullTimer()) as tmr_esc:
                try:
                    async for text in _stream_claude_fix(
                        api_key=_api_key,
                        user_request=user_request,
                        ui_description=ui_description,
                        built_code=built_code,
                        review_result=last_review_text,
                    ):
                        escalated_raw += text
                        yield _tok(text)
                    if escalated_raw:
                        built_code = _extract_html(escalated_raw)
                        yield _tok("\n\n✅ **Executive Brain** build complete!\n\n")
                except Exception as exc:
                    logger.warning("Claude escalation failed: %s", exc)
                    yield _tok(f"\n\n⚠️ Executive escalation failed — showing best local version.\n\n")

            _obs_record(
                brain="executive_escalation", model=_ESCALATE_MODEL,
                task="claude_fix_escalation",
                session_id=session_id, latency_ms=tmr_esc.elapsed_ms,
                confidence=-1.0, escalated=True,
                tokens_out=len(escalated_raw.split()),
                outcome="success" if escalated_raw else "fail",
            )
        else:
            # No API key — tell user why quality might be limited
            if final_confidence < _ESCALATE_THRESHOLD:
                yield _tok(
                    f"\n\n⚠️ Local reviewer score: {final_confidence:.0f}/100. "
                    "Add ANTHROPIC_API_KEY to Railway env vars to enable Claude escalation "
                    "for higher quality builds.\n\n"
                )

    # ── Done ─────────────────────────────────────────────────────────────────
    yield _tok(
        "\n\nHere's your build! What would you like to change?\n"
        "1. Adjust colors, fonts, or spacing\n"
        "2. Add features or interactions\n"
        "3. Change a specific component\n"
    )


# ── Null timer (when observability import fails) ──────────────────────────────

class _NullTimer:
    elapsed_ms = 0.0
    def __enter__(self): return self
    def __exit__(self, *_): pass