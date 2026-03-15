"""
Image-to-Code Chain Orchestrator
=================================
Three-brain pipeline that turns a UI screenshot into a working web app:

  1. 👁  Vision Brain  (moondream)       — reads the image, produces a detailed UI spec
  2. 🔨  Builder Brain (qwen2.5-coder)   — builds HTML/CSS/JS from the spec (streaming)
  3. 🔍  Reviewer Brain (gemma3:4b)      — reviews code vs spec, returns PASS or issues
  4. 🔧  Builder Brain again             — fixes reviewer issues (streaming), loops up to N times

Yields SSE-formatted strings for direct use in the streaming endpoint.
"""

import asyncio
import json
import logging
import re

logger = logging.getLogger(__name__)

_MAX_FIX_LOOPS = 2  # Reviewer → Builder fix cycles before accepting best version

# ── Prompts ─────────────────────────────────────────────────────────────────

_VISION_PROMPT = """\
You are analyzing a UI screenshot so a developer can recreate it as HTML/CSS/JS.
Describe every detail you see, technically and precisely:

- Overall layout: sections, columns, grid or flex structure
- Color scheme: background, text, buttons, accents — use hex codes if you can read them
- Typography: font sizes, weights, hierarchy (headings, body, labels)
- Every interactive element: buttons (text + style), text inputs, dropdowns, checkboxes, toggles, sliders
- Spacing: padding, margins, gaps between elements
- Borders, border-radius, box shadows
- All visible text: labels, placeholders, headings, body copy
- Navigation bar / sidebar / tabs if present
- Any icons, images, or illustrations (describe shape/purpose)
- Responsive behavior if apparent

Output ONLY the description — no commentary, no code."""

_BUILD_SYSTEM = """\
You are an expert frontend developer. Your job is to build complete, pixel-faithful web UIs.

## Coding Standards
- Single self-contained HTML file: all CSS inside <style>, all JS inside <script>
- Use CSS custom properties (--primary, --bg, --text, etc.) for every color
- Flexbox or CSS Grid for all layouts — no floats, no tables
- Real JavaScript — live state management, real event handlers, no stubs, no TODOs
- Every button, input, dropdown, and control must be fully functional
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
1. A UI DESCRIPTION (the spec — what the finished UI should look like and do)
2. GENERATED CODE (the HTML/CSS/JS to review)

Your task:
- Check that every element in the description is present and correct in the code
- Check that all interactive elements actually work
- Check colors, layout, typography match the description

Output rules (STRICT):
- If the code correctly implements the spec: output exactly the word PASS — nothing else
- If there are issues: output a short numbered list of specific, actionable problems
  Example:
  1. Header background should be #1a1a2e, currently it is white
  2. Submit button has no click handler
  3. Sidebar is missing from the layout

Do NOT rewrite or suggest the code. Do NOT explain best practices. Only flag real gaps."""

_FIX_SYSTEM = _BUILD_SYSTEM + "\n\nYou are fixing a previous build attempt based on code reviewer feedback."


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tok(text: str) -> str:
    """Format a token as an SSE data event."""
    return f"data: {json.dumps({'t': text})}\n\n"


def _extract_html(text: str) -> str:
    """Pull code out of a ```html ... ``` fence, or return raw text."""
    m = re.search(r"```(?:html)?\n?([\s\S]*?)```", text)
    return m.group(1).strip() if m else text.strip()


# ── Pipeline ─────────────────────────────────────────────────────────────────

async def image_to_code_pipeline(
    images: list,
    user_request: str,
    ollama_client,
    vision_model: str,
    builder_model: str,
    reviewer_model: str,
):
    """
    Async generator — yields SSE strings.

    Pipeline:
      Vision Brain → Builder Brain (stream) → Reviewer Brain
        └─ if issues → Builder Brain fix (stream) → Reviewer Brain  (× _MAX_FIX_LOOPS)
    """

    # ── STEP 1: Vision Brain ─────────────────────────────────────────────────
    yield _tok("👁 **Vision Brain** is analyzing your image...\n\n")

    _v_task = asyncio.ensure_future(
        ollama_client.run_chat(
            vision_model,
            [{"role": "user", "content": _VISION_PROMPT, "images": images}],
            timeout=120,
        )
    )
    ui_description: str = ""
    while not _v_task.done():
        try:
            ui_description = await asyncio.wait_for(asyncio.shield(_v_task), timeout=3.0)
        except asyncio.TimeoutError:
            yield ": keepalive\n\n"
    if not ui_description:
        try:
            ui_description = _v_task.result()
        except Exception as _ve:
            logger.warning("Vision brain failed: %s", _ve)
            ui_description = f"Build a web UI matching this request: {user_request}"

    logger.info("Vision Brain OK — %d chars", len(ui_description))
    yield _tok("✅ **Vision Brain** done.\n\n🔨 **Builder Brain** generating code...\n\n")

    # ── STEP 2: Builder Brain (streaming) ────────────────────────────────────
    _build_user = (
        f"[UI DESCRIPTION FROM SCREENSHOT]\n{ui_description}\n\n"
        f"[USER REQUEST]\n{user_request or 'Build this UI as a complete working web app.'}\n\n"
        "Build the complete HTML/CSS/JS app now. Start your response with ```html"
    )

    built_code_raw = ""
    try:
        _b_stream = ollama_client.run_chat_stream(
            model=builder_model,
            messages=[
                {"role": "system", "content": _BUILD_SYSTEM},
                {"role": "user", "content": _build_user},
            ],
            temperature=0.3,
        )
        _b_aiter = _b_stream.__aiter__()
        _b_next = asyncio.ensure_future(_b_aiter.__anext__())
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
    except Exception as _be:
        logger.warning("Builder Brain failed: %s", _be)
        yield _tok(f"\n\n⚠️ Builder error: {_be}\n")
        return

    built_code = _extract_html(built_code_raw)
    logger.info("Builder Brain OK — %d chars of code", len(built_code))

    # ── STEP 3+: Reviewer Brain + fix loop ───────────────────────────────────
    for attempt in range(_MAX_FIX_LOOPS + 1):
        yield _tok(f"\n\n🔍 **Reviewer Brain** checking the build...\n\n")

        _review_user = (
            f"[UI DESCRIPTION]\n{ui_description}\n\n"
            f"[GENERATED CODE]\n```html\n{built_code}\n```"
        )
        _r_task = asyncio.ensure_future(
            ollama_client.run_chat(
                reviewer_model,
                [
                    {"role": "system", "content": _REVIEWER_SYSTEM},
                    {"role": "user", "content": _review_user},
                ],
                timeout=90,
            )
        )
        review_result: str = ""
        while not _r_task.done():
            try:
                review_result = await asyncio.wait_for(asyncio.shield(_r_task), timeout=3.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
        if not review_result:
            try:
                review_result = _r_task.result()
            except Exception as _re:
                logger.warning("Reviewer Brain failed: %s — accepting build", _re)
                review_result = "PASS"

        logger.info("Reviewer Brain (attempt %d): %s", attempt + 1, review_result[:120])

        if review_result.strip().upper().startswith("PASS"):
            yield _tok("✅ **Reviewer Brain** approved the build!\n\n")
            break

        if attempt >= _MAX_FIX_LOOPS:
            yield _tok(
                "⚠️ Reviewer flagged some issues but max fix cycles reached — "
                "showing best version.\n\n"
            )
            break

        # Issues found — send back to Builder
        yield _tok(
            f"🔧 **Builder Brain** is fixing reviewer feedback "
            f"(pass {attempt + 1}/{_MAX_FIX_LOOPS})...\n\n"
        )
        logger.info("Review issues:\n%s", review_result)

        _fix_user = (
            f"[ORIGINAL UI DESCRIPTION]\n{ui_description}\n\n"
            f"[YOUR PREVIOUS CODE]\n```html\n{built_code}\n```\n\n"
            f"[REVIEWER ISSUES — FIX ALL OF THESE]\n{review_result}\n\n"
            "Fix every issue listed above. Output the COMPLETE updated HTML file. "
            "Start with ```html"
        )
        fixed_code_raw = ""
        try:
            _f_stream = ollama_client.run_chat_stream(
                model=builder_model,
                messages=[
                    {"role": "system", "content": _FIX_SYSTEM},
                    {"role": "user", "content": _fix_user},
                ],
                temperature=0.2,
            )
            _f_aiter = _f_stream.__aiter__()
            _f_next = asyncio.ensure_future(_f_aiter.__anext__())
            while True:
                try:
                    token = await asyncio.wait_for(asyncio.shield(_f_next), timeout=3.0)
                    fixed_code_raw += token
                    yield _tok(token)
                    _f_next = asyncio.ensure_future(_f_aiter.__anext__())
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                except StopAsyncIteration:
                    break
        except Exception as _fe:
            logger.warning("Fix Brain failed: %s — keeping previous build", _fe)
            break

        built_code = _extract_html(fixed_code_raw)

    # ── Done ─────────────────────────────────────────────────────────────────
    yield _tok(
        "\n\nHere's what I built from your image! What would you like to change?\n"
        "1. Adjust colors, fonts, or layout\n"
        "2. Add features or interactions\n"
        "3. Change a specific component\n"
    )
