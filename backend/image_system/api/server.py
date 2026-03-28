"""
FastAPI server for the Mini Assistant image system.

Exposes endpoints for image generation, routing, vision analysis, chat,
model management, and health checks.

Run with:
    uvicorn backend.image_system.api.server:app --host 0.0.0.0 --port 7860
"""

import asyncio
import base64
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import io
try:
    from PIL import Image as _PILImage
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from fastapi.responses import JSONResponse, StreamingResponse

from .models import (
    GenerateRequest,
    GenerateResponse,
    GenerationPlan,
    DryRunResponse,
    RouteRequest,
    AnalyzeRequest,
    ChatRequest,
    AutoFixRequest,
    SummarizeRequest,
    ShareRequest,
    CommunityRequest,
    VisualReviewRequest,
    OrchestrationRequest,
    CreationExportRequest,
    PullModelsRequest,
    ModelStatusResponse,
    ErrorResponse,
)
from .conversation_store import (
    load_conversation,
    save_message,
    trim_html_in_old_messages,
    harvest_patterns_if_ready,
)
from ..brains.search_brain import search as _memory_search

logger = logging.getLogger(__name__)


def _friendly_error(exc) -> str:
    """Convert a raw exception into a user-facing Mini Assistant error message."""
    logger.error("chat_stream error: %s: %s", type(exc).__name__, exc)
    s = str(exc).lower()
    t = type(exc).__name__.lower()
    if any(kw in s for kw in ("cannot connect to host", "connection refused", "connect call failed",
                               "connectionrefused", "clientconnectorerror", "nodename nor servname",
                               "name or service not known", "getaddrinfo")):
        return "Mini Assistant may be offline — try again in a moment."
    if any(kw in s for kw in ("timed out", "timeout", "524", "read timeout", "gateway")):
        return "Mini Assistant is taking longer than expected. Please try again."
    if any(kw in s for kw in ("not found", "pull", "no such", "unknown model", "404")):
        return "The AI model isn't available yet — try pulling it in Ollama, or switch models in the selector."
    if any(kw in s or kw in t for kw in ("cancelled", "cancel")):
        return "Request cancelled."
    if "serverdisconnected" in t or "disconnect" in s:
        return "Mini Assistant disconnected mid-response — try again."
    if "clientpayload" in t or "payload" in s:
        return "Mini Assistant had a network hiccup — try again."
    # Log full traceback for unknown errors so Railway logs show the real cause
    import traceback as _tb
    logger.error("Unhandled streaming error:\n%s", _tb.format_exc())
    return f"Mini Assistant ran into an issue ({type(exc).__name__}). Please try again."


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Mini Assistant Image System",
    description="Local image generation using Ollama brains + ComfyUI",
    version="1.0.0",
)

_CORS_ALWAYS = [
    "https://mini-assistant-production.up.railway.app",
    "https://www.miniassistantai.com",
    "https://miniassistantai.com",
    "https://ai.miniassistantai.com",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://localhost:8080",
]
_extra = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
_cors_origins = list(dict.fromkeys(_CORS_ALWAYS + _extra))
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class COOPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        return response

app.add_middleware(COOPMiddleware)

# ---------------------------------------------------------------------------
# Phase 10: Production middleware stack
# ---------------------------------------------------------------------------
try:
    from mini_assistant.phase10.request_tracer  import attach_tracer
    from mini_assistant.phase10.rate_limiter    import attach_rate_limiter
    from mini_assistant.phase10.auth_middleware import attach_auth
    attach_tracer(app)
    # phase10 IP-based rate limiter disabled — Railway proxies all traffic through
    # the same IP, causing all users to share one bucket. Per-user limits are
    # enforced by safety.py (enforce_rate_limit) keyed by JWT uid instead.
    # attach_rate_limiter(app)
    attach_auth(app)
    logger.info("✓ Phase 10 middleware stack attached (image_system)")
except Exception as _p10_err:
    logger.warning("Phase 10 middleware unavailable (image_system): %s", _p10_err)

# ---------------------------------------------------------------------------
# Image compression helper — shrinks base64 images before sending to Ollama
# to avoid Cloudflare tunnel timeouts on large payloads.
# ---------------------------------------------------------------------------

def _compress_image_b64(b64: str, max_px: int = 512, quality: int = 65) -> str:
    """Resize + JPEG-compress a base64 image. Returns original string if PIL unavailable."""
    if not _PIL_AVAILABLE or not b64:
        return b64
    try:
        raw = base64.b64decode(b64)
        img = _PILImage.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        if max(w, h) > max_px:
            scale = max_px / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), _PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return b64

# ---------------------------------------------------------------------------
# Watermark — applied to generated images for free-plan users
# ---------------------------------------------------------------------------

def _apply_watermark(b64: str) -> str:
    """Stamp 'Mini Assistant AI' at the bottom-right of a base64 image."""
    if not _PIL_AVAILABLE or not b64:
        return b64
    try:
        from PIL import ImageDraw, ImageFont
        raw = base64.b64decode(b64)
        img = _PILImage.open(io.BytesIO(raw)).convert("RGBA")
        w, h = img.size

        # Transparent overlay layer
        overlay = _PILImage.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        label = "Built with Mini Assistant AI"
        font_size = max(12, int(h * 0.022))  # ~2% of image height

        # Try system fonts, fall back to PIL default
        font = None
        for font_path in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]:
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except Exception:
                pass
        if font is None:
            font = ImageFont.load_default()

        # Measure text
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        # Position: bottom-right with padding
        pad = int(h * 0.018)
        x = w - tw - pad
        y = h - th - pad

        # Semi-transparent dark pill behind text
        pill_pad = 4
        draw.rounded_rectangle(
            [x - pill_pad, y - pill_pad, x + tw + pill_pad, y + th + pill_pad],
            radius=4, fill=(0, 0, 0, 140)
        )
        # White text with slight shadow
        draw.text((x + 1, y + 1), label, font=font, fill=(0, 0, 0, 100))
        draw.text((x, y), label, font=font, fill=(255, 255, 255, 200))

        # Composite and return as PNG
        watermarked = _PILImage.alpha_composite(img, overlay).convert("RGB")
        buf = io.BytesIO()
        watermarked.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as _wm_err:
        logger.debug("Watermark failed (non-fatal): %s", _wm_err)
        return b64


# ---------------------------------------------------------------------------
# Active generation tracking (for cancellation)
# ---------------------------------------------------------------------------

_active_generations: Dict[str, asyncio.Task] = {}

# ---------------------------------------------------------------------------
# Lazy brain / service singletons (created on first use to avoid import errors)
# ---------------------------------------------------------------------------

_router_brain = None
_coding_brain = None
_vision_brain = None
_embed_brain = None
_critic_brain = None
_prompt_builder = None
_comfyui_client = None
_ollama_client = None

# ---------------------------------------------------------------------------
# App Builder coding standards — injected into every build/update turn
# ---------------------------------------------------------------------------
# ── Knowledge Base import — all builder training lives there ─────────────────
try:
    from .brains.knowledge_base import (
        fresh_build_prompt   as _kb_fresh_build,
        patch_prompt         as _kb_patch,
        requirements_prompt  as _kb_requirements,
        debug_agent_prompt   as _kb_debug_agent,
        self_review_prompt   as _kb_self_review,
        review_prompt        as _kb_review,
        WHEN_TO_DO_WHAT      as _KB_WHEN,
        HOW_TO_BUILD         as _KB_HOW_TO_BUILD,
        PERSONALITY          as _KB_PERSONALITY,
        EXECUTIVE_MINDSET    as _KB_EXECUTIVE,
        PARALLEL_ANALYSIS_PROTOCOL as _KB_PARALLEL,
        MODE_AWARENESS       as _KB_MODE_AWARENESS,
    )
    _KB_LOADED = True
except ImportError:
    _KB_LOADED = False
    _kb_fresh_build   = lambda: ""
    _kb_patch         = lambda: ""
    _kb_requirements  = lambda: ""
    _kb_debug_agent   = lambda: ""
    _kb_self_review   = lambda: ""
    _kb_review        = lambda: ""

try:
    from .brains.lesson_memory import (
        format_lessons_for_prompt  as _lessons_for_prompt,
        save_lesson                as _save_lesson,
        extract_lessons_from_fix_report as _extract_lessons,
    )
    _LESSONS_LOADED = True
except ImportError:
    _LESSONS_LOADED = False
    _lessons_for_prompt   = lambda: ""
    _save_lesson          = lambda *a, **kw: None
    _extract_lessons      = lambda r: []

try:
    from .brains.user_memory import (
        format_prefs_for_prompt      as _user_prefs_for_prompt,
        update_prefs_from_conversation as _update_user_prefs,
    )
    _USER_MEMORY_LOADED = True
except ImportError:
    _USER_MEMORY_LOADED = False
    _user_prefs_for_prompt = lambda: ""
    _update_user_prefs     = lambda *a, **kw: None

_APP_BUILDER_CODING_STANDARDS = """
## CODING STANDARDS (follow these exactly when building apps)

### File structure
- Always output ONE self-contained HTML file. All CSS in <style>, all JS in <script>.
- No external CDN links, no npm packages, no imports. Everything inline.
- Order: <!DOCTYPE html> → <html> → <head> (meta + style) → <body> (markup + script).

### HTML
- Use semantic elements: <header>, <main>, <section>, <article>, <nav>, <footer>, <button>, <form>, <input>.
- Every interactive element needs an id or data attribute if JS references it.
- Never use divs as buttons. Use <button type="button">.
- Forms must have proper labels (htmlFor or wrapping <label>).

### CSS — write CSS like a senior frontend engineer
- Always define CSS custom properties (variables) at :root for colors, spacing, radii.
  Example: --color-bg: #0d0d12; --color-surface: #161622; --color-accent: #7c3aed; --radius: 8px;
- Use flexbox or grid for ALL layouts — never use float, never use absolute positioning for layout.
- Mobile-first, responsive by default. Use clamp() for fluid type. Max-width containers.
- Dark-mode-first design. Background #0d0d12 or similar deep dark. Text #e2e8f0 or similar.
- Every interactive element must have :hover, :focus-visible, and :active states.
- Use transitions: transition: all 0.15s ease for micro-interactions.
- Buttons: padding 0.5em 1.25em, border-radius var(--radius), cursor: pointer, no outline on click (outline on focus-visible only).
- Inputs: same radius, background slightly lighter than bg, border 1px solid rgba(255,255,255,0.12), color: inherit.
- Scrollbars: style them. ::-webkit-scrollbar { width: 6px } ::-webkit-scrollbar-track { background: transparent } ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 99px }
- Cards/surfaces: background var(--color-surface), border: 1px solid rgba(255,255,255,0.07), border-radius var(--radius), padding 1rem.

### JavaScript — write JS like a senior engineer, not a beginner
- Use const/let — never var.
- State is a plain object at the top of the script. Mutate it directly, then call a render function.
  Example pattern:
    const state = { items: [], filter: 'all', darkMode: true };
    function render() { /* read state, update DOM */ }
- Never innerHTML += — always build a string or array then set innerHTML once.
- Use event delegation for lists: one listener on the container, check e.target.closest('[data-action]').
- Use template literals for all HTML generation.
- LocalStorage persistence: on state change, localStorage.setItem('app_state', JSON.stringify(state)).
  On load: try { Object.assign(state, JSON.parse(localStorage.getItem('app_state') || '{}')); } catch {}
- Animations: use CSS classes + requestAnimationFrame, not setTimeout chains.
- Error handling: wrap async operations in try/catch. Show inline error messages, not console.error only.
- Functions should be short and do one thing. Split large functions.

### Images and logos
- NEVER use via.placeholder.com, picsum.photos, lorempixel, or any external image URL — they are dead/blocked.
- For app logos: create an inline SVG using the app name and brand colors.
  Example: <svg viewBox="0 0 120 40"><rect .../><text ...>AppName</text></svg>
- For placeholder images: use a <div> with a CSS gradient background, or an inline SVG rectangle with text.

### UX patterns to always include
- Empty states: when a list is empty, show a helpful illustrated placeholder with a call-to-action.
- Loading states: show a spinner or skeleton when fetching/processing.
- Success/error feedback: brief toast notification or inline message after actions.
- Keyboard accessible: Enter submits forms, Escape closes modals/dialogs.
- Smooth page feel: add a subtle entrance animation (opacity 0 → 1, translateY 8px → 0) on mount.

### Design defaults (use these unless the user specified otherwise)
- Font: system-ui, -apple-system, sans-serif
- Background: #0d0d12
- Surface: #161622
- Border: rgba(255,255,255,0.07)
- Accent: #7c3aed (purple) or #06b6d4 (cyan) — pick one and use it consistently
- Text primary: #e2e8f0
- Text muted: #64748b
- Danger: #ef4444
- Success: #22c55e
- Border radius: 8px default, 4px for small, 12px for cards, 999px for pills/badges
- Spacing: 4px base unit. Use 4, 8, 12, 16, 24, 32, 48px.

### What "complete and working" means
- EVERY button does something. No "coming soon", no alert("TODO").
- EVERY form validates and gives feedback.
- EVERY list renders correctly with 0, 1, and many items.
- EVERY modal/dialog can be opened AND closed.
- The app could be shipped to a real user right now.
"""

# ---------------------------------------------------------------------------
# Code assistant prompt — injected when user pastes code or asks a code question
# ---------------------------------------------------------------------------
_CODE_ASSISTANT_PROMPT = """
## CODE ASSISTANT MODE

The user has shared code or asked a coding question. Respond like a senior engineer doing a real code review.

### When the user pastes code with NO instruction:
1. **Identify** the language, framework, and what the code does (1-2 sentences max).
2. **Spot issues** — bugs, logic errors, security holes, performance problems, bad patterns. Be specific with line references.
3. **Suggest improvements** — cleaner patterns, better naming, missing error handling, edge cases not covered.
4. **Show the fixed version** — output the corrected/improved code in a fenced code block with the correct language tag.
5. End with: "What would you like to change or explore next?"

### When the user pastes code WITH an instruction (fix this, add X, explain this, refactor):
- Do exactly what they asked. No more, no less.
- If fixing: output the complete corrected file/function, not just the changed lines (unless it's a huge file).
- If explaining: walk through the logic clearly, call out non-obvious parts.
- If adding a feature: integrate it cleanly into the existing code style.
- Always output code in a properly tagged fenced block (```python, ```js, ```ts, etc).

### Code quality rules (apply these when writing or fixing code):
- Match the existing code style exactly — indentation, naming conventions, patterns.
- Never remove existing functionality unless told to.
- Add comments only where the logic is genuinely non-obvious.
- Prefer the simplest correct solution over a clever one.
- Handle edge cases: null/undefined, empty arrays, network errors, type mismatches.
- For Python: use type hints, f-strings, context managers. Avoid bare except:.
- For JavaScript/TypeScript: use const/let, async/await, optional chaining (?.), nullish coalescing (??).
- For React: functional components + hooks only. No class components. Keep components small.

### What NOT to do:
- Don't rewrite everything just because you could do it differently.
- Don't add features that weren't asked for.
- Don't lecture about code style unless it's causing a real bug.
- Don't say "Great code!" or pad the response with praise.
- After every fix or code change: end with a short check-in like "Try it now — does that fix it?" or "Give it a run and let me know!"
- You're a partner, not a ticket-closer. The job isn't done until the user confirms it works.
"""

# ---------------------------------------------------------------------------
# Mini Assistant identity system prompt
# ---------------------------------------------------------------------------

_MINI_SYSTEM_PROMPT = """\
You are Mini Assistant — a smart, capable AI workspace assistant built for developers and creators.

## What you CAN do:
- Answer questions on any topic using your knowledge
- Generate AI images from text descriptions (e.g. "draw a dragon", "paint an anime warrior") or via /image
- Analyze and describe images that users attach
- Write, review, debug, and execute code in any programming language
- Help build complete web apps, UI components, and full projects through the workspace
- Fetch real-time weather data for any location
- Plan and manage multi-step development tasks
- Search and research topics, summarize documents, brainstorm ideas

## What is coming soon (not yet available):
- Video generation

## App / UI Building — Situation Awareness (CRITICAL)
Before every build response, identify which situation you are in and act accordingly.

SITUATION 1 — First contact, no code, no image → Ask 2 short questions (style + purpose). End: "Let's build it! 🚀". NO CODE YET.
SITUATION 2 — User answered questions, no code yet → BUILD IMMEDIATELY. Start with ```html. No more questions before code.
SITUATION 3 — Image provided, no code yet → BUILD FROM IMAGE. No questions. Match the design.
SITUATION 4 — Code exists + user wants fix/change → PATCH ONLY. Read code. Change the minimum. Never rebuild.
SITUATION 5 — User says rebuild/start over/from scratch → FRESH BUILD allowed.
SITUATION 6 — User asks a question about the app → Answer conversationally, no code unless needed.

ALWAYS: Complete working code. No TODOs. No stubs. Every button does something real.
ON PATCH: Output the COMPLETE file. Change ONLY what was asked. Never restructure unrelated code.

## Personality — Partner Builder
You are a creative coding partner, not a robot. You genuinely care about whether things work.
- After building or fixing: ALWAYS check in. "Try it — does the play button work now? 🎮"
- Celebrate wins: "That came out clean! 🔥" not "Task completed."
- Be honest when uncertain: "Try it — if the physics feel off, tell me."
- Match user energy. Casual → casual. Technical → focused.
- Never end a fix without a check-in. Never end a build without 3 numbered next-step options.

## General response rules:
- Short greetings (hi, hello, hey) → respond warmly and briefly, ask what they need. Do NOT start responses with a greeting when the conversation is already in progress.
- NEVER prefix a response with a greeting or your name if the user already sent a substantive message
- If [REAL-TIME DATA] appears in the context, use it directly and accurately — NEVER say you don't have internet access when live data is present
- If [NO REAL-TIME DATA] appears in the context, honestly tell the user you couldn't fetch that information right now — do NOT make up or estimate weather, time, prices, scores, or any live data
- NEVER fabricate real-time information (weather, current time, stock prices, sports scores, news, etc.)
- You CAN generate images — NEVER tell users you cannot generate images
- Code execution IS built into this platform — you actively help write and run code
- For legal, medical, or financial topics: always recommend consulting a qualified professional
- Be helpful, direct, and conversational. Match the user's tone.
"""

# ---------------------------------------------------------------------------
# Lyrics specialist system prompt — injected when lyrics intent is detected
# ---------------------------------------------------------------------------
_LYRICS_SYSTEM_PROMPT = """\
You are a professional songwriter and lyricist with deep knowledge of every genre.
When writing song lyrics, always follow these rules:

## Notation conventions
- Things in ( ) are backup vocals, harmonies, or adlibs — e.g. (yeah), (uh huh), (ooh)
- Things in [ ] are section markers / production notes — e.g. [Intro], [Verse 1], [Pre-Chorus], [Chorus], [Bridge], [Outro], [Hook], [Breakdown], [Guitar Solo], [Drop], [Spoken], [Ad-lib section]
- Always label every section with [ ] markers so the structure is crystal clear

## Universal song structure rules
- Every song needs contrast — verses tell the story, chorus is the emotional peak
- The hook should be the most memorable, repeatable line(s)
- Bridge provides a shift in perspective, key, or mood
- Outro can mirror the intro or fade with a final ad-lib

## Genre structures and language guide

### Hip-Hop / Rap (English)
Structure: [Intro] → [Verse 1] → [Hook] → [Verse 2] → [Hook] → [Bridge] → [Hook] → [Outro]
- Verses: 16 bars, rhyme schemes (AABB, ABAB, or multisyllabic)
- Hook: 8 bars, catchy and simple, repeats 2–3x
- Use internal rhymes, wordplay, metaphors, punchlines
- Flow patterns: triplet flow, boom-bap 4/4, trap half-time
- (adlibs go here in parentheses — yea, ayy, uh, let's go)

### R&B / Soul (English)
Structure: [Intro] → [Verse 1] → [Pre-Chorus] → [Chorus] → [Verse 2] → [Pre-Chorus] → [Chorus] → [Bridge] → [Chorus] → [Outro]
- Smooth, melodic phrasing — lyrics follow the melody closely
- Pre-chorus builds tension before the release of the chorus
- Bridge: key change or emotional climax, often falsetto
- Backup vocals in ( ) add warmth: (oh oh), (yeah yeah), (mmm)

### Pop (English / Universal)
Structure: [Verse 1] → [Pre-Chorus] → [Chorus] → [Verse 2] → [Pre-Chorus] → [Chorus] → [Bridge] → [Chorus x2] → [Outro]
- Chorus is the title/hook — repeat it with slight variations
- Verses are conversational, bridge is the twist
- Keep lines short and punchy, easy to remember

### Trap / Drill (English)
Structure: [Intro] → [Hook] → [Verse 1] → [Hook] → [Verse 2] → [Hook] → [Outro]
- Hook comes FIRST in most trap songs
- Dark imagery, street narratives, flexing, survival themes
- Heavy use of adlibs: (gang), (slatt), (brrr), (on god)
- Melodic mumble sections vs sharp punchline verses

### Country (English)
Structure: [Verse 1] → [Chorus] → [Verse 2] → [Chorus] → [Bridge] → [Chorus] → [Outro]
- Storytelling is everything — each verse advances the narrative
- Chorus sums up the emotional truth of the story
- Common themes: home, heartbreak, trucks, small towns, faith, family
- [Steel Guitar Solo] or [Fiddle Break] as instrumental sections

### Rock / Alternative (English)
Structure: [Intro] → [Verse 1] → [Chorus] → [Verse 2] → [Chorus] → [Bridge] → [Guitar Solo] → [Chorus] → [Outro]
- Chorus is anthemic, verse is introspective
- Bridge often breaks the dynamic — quieter or heavier
- [Guitar Solo] or [Instrumental Break] are standard markers

### Reggaeton / Latin Trap (Spanish)
Structure: [Intro] → [Coro] → [Verso 1] → [Coro] → [Verso 2] → [Puente] → [Coro] → [Outro]
- Written in Spanish — section labels can be in Spanish: [Verso], [Coro], [Puente], [Intro], [Outro]
- Dembow rhythm drives the cadence of the lyrics
- Themes: party, romance, street life, flexing
- Adlibs in Spanish: (ey), (jaja), (dale), (fuego)

### Afrobeats / Afropop (English + Pidgin + Yoruba/Igbo phrases)
Structure: [Intro] → [Verse 1] → [Chorus] → [Verse 2] → [Chorus] → [Bridge] → [Chorus] → [Outro]
- Mix of English and local language phrases is authentic
- Chorus is highly melodic, call-and-response style
- Common Pidgin/expressions: "soro soke", "oya", "e choke", "wahala"
- Percussion-driven cadence — write lyrics with natural rhythmic bounce

### Amapiano / South African (Zulu / English / Tsotsitaal)
Structure: [Intro] → [Verse 1] → [Hook] → [Verse 2] → [Hook] → [Log Drum Break] → [Hook] → [Outro]
- Log drum sections are instrumental: mark as [Log Drum Break] or [Piano Break]
- Lyrics often bilingual — Zulu + English
- Laid-back, groove-focused delivery

### K-Pop (Korean, with some English hooks)
Structure: [Intro] → [Verse 1] → [Pre-Chorus] → [Chorus] → [Verse 2] → [Pre-Chorus] → [Chorus] → [Bridge / Rap Break] → [Chorus] → [Outro]
- Chorus often partially in English for global reach
- Rap break mid-song is a genre staple
- Precise syllabic matching to the melody
- Formation-aware — write for multiple members if applicable

### Dancehall (Jamaican Patois + English)
Structure: [Riddim Intro] → [Verse 1] → [Chorus] → [Verse 2] → [Chorus] → [Outro]
- Patois is authentic: "wah gwaan", "ting", "dutty", "badman", "nuh"
- Rhythmic flow follows the riddim pattern strictly
- Chorus (also called "hook" or "riddim hook") is bouncy and catchy

### Gospel / Worship (English)
Structure: [Intro] → [Verse 1] → [Chorus] → [Verse 2] → [Chorus] → [Bridge] → [Vamp / Spontaneous] → [Chorus] → [Outro]
- [Vamp] = repeated spontaneous worship section, often improvised
- Lyrics center on praise, testimony, scripture references
- Bridge is the emotional climax — builds to a peak
- Backup vocals in ( ) are call-and-response worship moments

### Bachata (Spanish — Dominican Republic)
Structure: [Intro] → [Verso 1] → [Coro] → [Verso 2] → [Coro] → [Mambo] → [Coro] → [Outro]
- Written in Spanish — raw, emotional, romantic or heartbreak themes
- [Mambo] = instrumental guitar / güira break section, can include call-response vocals
- Delivery is intimate, close, conversational — lyrics feel like whispers or confessions
- Common themes: love, jealousy, longing, betrayal, desire
- Adlibs: (ay), (amor), (mi vida), (oh oh oh)
- Lines often end with rhythmic syllables that match the guitar: "ay amor (ay)", "te quiero (te quiero)"

### Merengue (Spanish — Dominican Republic)
Structure: [Intro] → [Verso 1] → [Coro] → [Verso 2] → [Coro] → [Jaleo] → [Coro] → [Outro]
- Fast, upbeat, celebratory — 2/4 rhythm drives the phrasing
- [Jaleo] = freestyle improvised vocal section, often call-and-response with horns
- Lyrics are fun, playful, danceable — humor and flirting are common
- Short punchy lines that land on the beat: "ella baila, ella goza, ella mueve"
- Brass/accordion stabs reflected in lyric punches

### Salsa (Spanish — Cuban / Puerto Rican / Colombian roots)
Structure: [Intro] → [Verso 1] → [Coro] → [Verso 2] → [Coro] → [Montuno / Coro-Pregón] → [Mambo] → [Coro] → [Outro]
- [Montuno] = the heart of salsa — repeating coro while the lead singer improvises (pregón)
- [Pregón] = improvised shout lines over the coro loop, e.g. lead: "dime lo que tú quieres" / coro: (lo que yo quiero)"
- Themes: romance, street life, Afro-Caribbean pride, dancing, social commentary
- Clave rhythm (3-2 or 2-3) shapes syllable placement
- Adlibs: (eso es), (azúcar), (wepa), (pa' lante), (oye)

### Cumbia (Spanish — Colombian / Mexican / Central American)
Structure: [Intro] → [Verso 1] → [Coro] → [Verso 2] → [Coro] → [Instrumental Break] → [Coro] → [Outro]
- Roots in Colombian coast — spreads across Latin America with regional variations
- Medium tempo, hypnotic groove — lyrics match the steady rhythmic pulse
- Themes: celebration, folk stories, nostalgia, love, regional pride
- Colombian cumbia: poetic, Afro-Indigenous imagery
- Mexican cumbia: more festive, narco-corrido crossovers common
- Lines are rhythmically even, often syllabically matched to the beat
- Adlibs: (ay ay ay), (cumbia), (baila baila)

### Ballad / Power Ballad (English — universal)
Structure: [Intro] → [Verse 1] → [Chorus] → [Verse 2] → [Chorus] → [Bridge] → [Key Change Chorus] → [Outro]
- Slow, emotionally heavy — every line carries weight
- [Key Change Chorus] = the climactic final chorus, typically a half or whole step up
- Verses are vulnerable and narrative; chorus is the release
- Bridge is the emotional breaking point — often the most raw lines in the song
- Power Ballad variation: builds from soft verse to huge rock/orchestra chorus
- Themes: love, loss, longing, resilience, heartbreak
- No adlibs — let the vocals breathe. Harmonies in ( ) on chorus lifts

### Corrido / Regional Mexican (Spanish)
Structure: [Intro] → [Verso 1] → [Coro] → [Verso 2] → [Coro] → [Verso 3] → [Outro]
- Storytelling tradition — narrates real or dramatized events (heroes, outlaws, tragedies)
- Traditional corrido: 3+ verses, brass banda or guitarrón backing
- Narcocorrido / Corrido Tumbado: modern trap-influenced, dark themes, flex and loyalty
- First verse usually introduces the protagonist or setting
- Third verse often contains the resolution or moral
- Adlibs (corrido tumbado): (arriba), (puro sinaloa), (que viva), (ánimo)

### Vallenato (Spanish — Colombian)
Structure: [Intro] → [Verso 1] → [Coro] → [Verso 2] → [Coro] → [Piqueria / Acordeón Solo] → [Coro] → [Outro]
- [Piqueria] = accordion duel / improvised vocal challenge section
- Poetic, storytelling — love, nostalgia, place names, personal memory
- Four rhythms: paseo, merengue vallenato, puya, son — paseo is most common for lyrics
- Lyrics flow with the accordion melody closely
- Themes: romantic love, longing for home, nature, friendship

### Flamenco / Rumba Flamenca (Spanish — Andalusian)
Structure: [Introducción] → [Copla 1] → [Estribillo] → [Copla 2] → [Estribillo] → [Falseta / Solo de Guitarra] → [Estribillo] → [Cierre]
- [Copla] = verse (flamenco term), [Estribillo] = chorus, [Falseta] = guitar solo, [Cierre] = closing
- Deep emotional content — "duende" (raw soul) is everything
- Themes: sorrow (pena), passion, death, exile, love
- Short intense lines, often just 4 lines per copla
- Guttural exclamations are traditional: ¡Olé!, ¡Ay!, ¡Eso!, (jaleando)
- Rumba flamenca is faster and more festive — used in pop crossovers

### Bossa Nova / Samba (Portuguese — Brazilian)
Structure: [Intro] → [Verso A] → [Verso B] → [Refrão] → [Verso A] → [Verso B] → [Refrão] → [Coda]
- Written in Portuguese (Brazilian) — Bossa Nova: cool, intimate, jazzy
- Samba: celebratory, percussive, fast
- Bossa Nova lines are conversational, gentle, understated
- [Refrão] = chorus; [Coda] = ending section
- Themes: nature, Rio de Janeiro, longing (saudade), love, beauty
- Adlibs: (ai, ai), (oba), (saudade)

## Always follow the user's requested genre, theme, and language. If no genre is specified, ask or default to Pop structure. Match the authentic language, slang, and cultural feel of the genre.
"""

import re as _lyrics_re
_LYRICS_INTENT = _lyrics_re.compile(
    r"\b("
    r"writ(e|ing)|generat(e|ing)|creat(e|ing)|mak(e|ing)|giv(e|ing) me|show me|help (me )?(write|make|create)"
    r").{0,60}\b("
    r"song|lyrics?|verse|chorus|hook|bridge|rap|bars?|rhymes?|track|banger|anthem|flow|freestyle"
    r")\b"
    r"|"
    r"\b(song|lyrics?|verse|chorus|hook|bridge|rap|bars?)\b.{0,40}\b(about|for|on|called|titled|theme)\b"
    r"|"
    r"\b(write|make|create|pen).{0,30}\b(a |an )?(rap|song|verse|hook|chorus|bridge|banger|freestyle)\b",
    _lyrics_re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Real-time weather fetching (wttr.in — no API key required)
# ---------------------------------------------------------------------------

import re as _re

_WEATHER_PATTERNS = [
    _re.compile(r"what(?:'?s| is) the weather\s+(?:for|in|at)\s+(.+?)(?:\s+today|\s+tonight|\s+tomorrow|\?|$)", _re.I),
    _re.compile(r"how(?:'?s| is) the weather\s+(?:in|at|for)?\s*(.+?)(?:\s+today|\s+tonight|\?|$)", _re.I),
    _re.compile(r"weather\s+(?:for|in|at)\s+(.+?)(?:\s+today|\s+tonight|\s+tomorrow|\?|$)", _re.I),
    _re.compile(r"(?:forecast|temperature)\s+(?:for|in|at)\s+(.+?)(?:\s+today|\s+tonight|\?|$)", _re.I),
    _re.compile(r"whats the weather\s+(?:for|in|at)\s+(.+?)(?:\s+today|\s+tonight|\?|$)", _re.I),
    # Flexible: "weather ... for/in/at <location>" with arbitrary words between
    _re.compile(r"weather.{0,40}?(?:for|in|at)\s+([A-Za-z][A-Za-z\s,]{1,50})(?:\s+today|\s+tonight|\?|$|[,.])", _re.I),
    # "in <location>" near weather-related words
    _re.compile(r"(?:weather|temperature|forecast|time).{0,60}?\bin\s+([A-Za-z][A-Za-z\s,]{1,50})(?:\s+(?:right now|currently|today|now)|\?|$|[,.])", _re.I),
]


def _detect_weather_location(message: str) -> Optional[str]:
    """Return location string from a weather query, or None."""
    msg = message.strip()
    for pat in _WEATHER_PATTERNS:
        m = pat.search(msg)
        if m:
            loc = m.group(1).strip().rstrip("?.!,")
            if 1 < len(loc) < 60:
                return loc
    return None


_WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Moderate showers", 82: "Heavy showers",
    85: "Light snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm with hail",
}


async def _fetch_weather(location: str) -> Optional[str]:
    """Fetch current weather from Open-Meteo (free, no API key). Returns formatted string or None."""
    try:
        import httpx
        from datetime import datetime, timezone, timedelta

        # Step 1: Geocode the location
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location.replace(' ', '+')}&count=1&language=en&format=json"
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as _c:
            geo_r = await _c.get(geo_url, headers={"User-Agent": "MiniAssistant/1.0"})
        if geo_r.status_code != 200:
            return None
        geo_d = geo_r.json()
        results = geo_d.get("results")
        if not results:
            return None
        loc_info = results[0]
        lat  = loc_info["latitude"]
        lon  = loc_info["longitude"]
        name = loc_info.get("name", location)
        admin = loc_info.get("admin1", "")
        country = loc_info.get("country", "")
        loc_str = ", ".join(filter(None, [name, admin, country]))
        tz_name = loc_info.get("timezone", "UTC")

        # Step 2: Fetch weather
        wx_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
            f"wind_speed_10m,wind_direction_10m,weather_code,uv_index,visibility"
            f"&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone={tz_name}"
        )
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as _c:
            wx_r = await _c.get(wx_url, headers={"User-Agent": "MiniAssistant/1.0"})
        if wx_r.status_code != 200:
            return None
        wx_d = wx_r.json()
        cur  = wx_d.get("current", {})
        utc_offset_s = wx_d.get("utc_offset_seconds", 0)

        temp_f   = cur.get("temperature_2m", "?")
        feels_f  = cur.get("apparent_temperature", "?")
        humidity = cur.get("relative_humidity_2m", "?")
        wind_mph = cur.get("wind_speed_10m", "?")
        wind_deg = cur.get("wind_direction_10m", 0)
        wmo_code = cur.get("weather_code", -1)
        uv       = cur.get("uv_index", "?")
        vis_m    = cur.get("visibility", None)

        # Convert Fahrenheit to Celsius
        temp_c = round((float(temp_f) - 32) * 5 / 9, 1) if temp_f != "?" else "?"
        feels_c = round((float(feels_f) - 32) * 5 / 9, 1) if feels_f != "?" else "?"

        # Wind direction degrees → compass
        dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
        wind_dir = dirs[round(wind_deg / 22.5) % 16] if isinstance(wind_deg, (int, float)) else "?"

        # Visibility
        vis_str = f"{round(vis_m / 1000, 1)} km" if vis_m is not None else "?"

        desc = _WMO_CODES.get(wmo_code, f"Code {wmo_code}")

        # Local time at the queried location
        local_dt = datetime.now(timezone.utc) + timedelta(seconds=utc_offset_s)
        local_time_str = local_dt.strftime("%I:%M %p, %A %B %-d %Y")
        tz_offset_h = utc_offset_s // 3600
        tz_label = f"UTC{'+' if tz_offset_h >= 0 else ''}{tz_offset_h}"

        return (
            f"[REAL-TIME DATA from Open-Meteo]\n"
            f"Location: {loc_str}\n"
            f"Local time: {local_time_str} ({tz_label})\n"
            f"Condition: {desc}\n"
            f"Temperature: {temp_f}°F ({temp_c}°C)  |  Feels Like: {feels_f}°F ({feels_c}°C)\n"
            f"Humidity: {humidity}%  |  Wind: {wind_mph} mph {wind_dir}\n"
            f"UV Index: {uv}  |  Visibility: {vis_str}\n"
            f"[END REAL-TIME DATA]\n"
        )
    except Exception as _we:
        logger.warning("Weather fetch failed for '%s': %s", location, _we)
        return None


def _get_router():
    global _router_brain
    if _router_brain is None:
        from ..brains.router_brain import RouterBrain
        _router_brain = RouterBrain()
    return _router_brain


def _get_coding():
    global _coding_brain
    if _coding_brain is None:
        from ..brains.coding_brain import CodingBrain
        _coding_brain = CodingBrain()
    return _coding_brain


def _get_vision():
    global _vision_brain
    if _vision_brain is None:
        from ..brains.vision_brain import VisionBrain
        _vision_brain = VisionBrain()
    return _vision_brain


def _get_embed():
    global _embed_brain
    if _embed_brain is None:
        from ..brains.embed_brain import EmbedBrain
        _embed_brain = EmbedBrain()
    return _embed_brain


def _get_critic():
    global _critic_brain
    if _critic_brain is None:
        from ..brains.critic_brain import CriticBrain
        _critic_brain = CriticBrain()
    return _critic_brain


def _get_prompt_builder():
    global _prompt_builder
    if _prompt_builder is None:
        from ..services.prompt_builder import PromptBuilder
        _prompt_builder = PromptBuilder()
    return _prompt_builder


def _get_comfyui():
    global _comfyui_client
    if _comfyui_client is None:
        from ..services.comfyui_client import ComfyUIClient
        comfyui_url = os.environ.get("COMFYUI_URL", "http://localhost:8188")
        _comfyui_client = ComfyUIClient(base_url=comfyui_url)
    return _comfyui_client


def _get_ollama():
    global _ollama_client
    if _ollama_client is None:
        from ..services.ollama_client import OllamaClient
        _ollama_client = OllamaClient()
    return _ollama_client


def _load_registry() -> dict:
    import json as _json
    registry_path = Path(__file__).parent.parent / "config" / "model_registry.json"
    with open(registry_path) as f:
        return _json.load(f)


# ---------------------------------------------------------------------------
# Startup event
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Run availability check at startup and log the report."""
    logger.info("Mini Assistant Image System starting up...")
    try:
        from ..utils.startup_check import run_full_check, print_report
        report = await run_full_check()
        print_report(report)
    except Exception as exc:
        logger.warning("Startup check failed: %s", exc)

    # Pre-warm the two primary models so the first user request is fast.
    # Runs in the background — does not block startup.
    async def _warmup():
        import asyncio as _asyncio
        from ..services.ollama_client import OllamaClient as _OC, _model_name as _mn
        _client = _OC()
        for _role in ("router", "vision"):
            _model = _mn(_role)
            try:
                await _client.run_prompt(_model, "hi", timeout=300)
                logger.info("Warm-up OK: %s", _model)
            except Exception as _e:
                logger.warning("Warm-up failed for %s: %s", _model, _e)

    import asyncio as _asyncio
    _asyncio.ensure_future(_warmup())

    # Tier C retention purge — runs once at startup, non-blocking
    try:
        from ..privacy.retention_manager import schedule_background_purge as _purge
        _purge()
    except Exception as _exc:
        logger.warning("Retention purge schedule failed: %s", _exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/extract-text")
async def extract_text(file: UploadFile = File(...)):
    """Extract text from an uploaded PDF or plain-text file."""
    try:
        content = await file.read()
        filename = file.filename or ""

        if filename.lower().endswith(".pdf") or (file.content_type or "").startswith("application/pdf"):
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(content))
                text = "\n\n".join(
                    page.extract_text() or "" for page in reader.pages
                )
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"PDF parsing failed: {exc}")
        else:
            # Treat as plain text
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = content.decode("latin-1", errors="replace")

        text = text.strip()
        if not text:
            raise HTTPException(status_code=422, detail="No text could be extracted from the file.")

        # Cap at 50 000 chars to keep context manageable
        truncated = len(text) > 50000
        text = text[:50000]

        return {"text": text, "filename": filename, "chars": len(text), "truncated": truncated}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/observatory")
async def observatory():
    """
    Ceiling architecture: observability dashboard stats.
    Returns aggregate telemetry from the last 1000 brain calls.
    """
    try:
        from mini_assistant.observability import summary_stats, get_recent
        stats   = summary_stats()
        recent  = get_recent(20)
        return JSONResponse({"stats": stats, "recent_calls": recent})
    except Exception as exc:
        return JSONResponse({"error": str(exc), "stats": {}, "recent_calls": []})


@app.post("/api/orchestrate/analyze")
async def orchestrate_analyze(req: OrchestrationRequest):
    """
    Phase 1 Orchestration — Pre-execution Analysis

    Runs before any chat/builder execution to:
      1. Evaluate ask vs act
      2. Lock intent + normalize goal
      3. Estimate risk, confidence, and credit cost
      4. Return structured AnalysisResult for the frontend task card

    Fast path: simple conversational/chat messages return in <10ms.
    Full analysis (builder mode): ~20–50ms with no LLM calls.
    """
    import uuid as _uuid
    from ..orchestration.orchestrator import analyze as _orch_analyze, to_dict as _orch_to_dict

    session_id = req.session_id or str(_uuid.uuid4())
    history_raw = [{"role": m.role, "content": m.content} for m in (req.history or [])]

    try:
        result = _orch_analyze(
            message=req.message,
            session_id=session_id,
            mode=req.mode,
            history=history_raw,
            has_existing_code=req.has_existing_code,
            vibe_mode=req.vibe_mode,
        )
        return _orch_to_dict(result)
    except Exception as exc:
        logger.exception("[orchestrate/analyze] unexpected error: %s", exc)
        # Fail safe: return a minimal ACT result so the user is never blocked
        return {
            "decision": "act",
            "proceed_immediately": True,
            "intent_type": "chat",
            "normalized_goal": req.message,
            "mode": req.mode,
            "confidence": 0.75,
            "confidence_label": "High",
            "risk_level": "low",
            "risk_score": 0,
            "cost_min": 0,
            "cost_max": 1,
            "cost_label": "Low",
            "confidence_factors": [],
            "confidence_deductions": [],
            "risk_factors": [],
            "risk_mitigations": [],
            "clarification_q": None,
            "interpretations": [],
            "requires_checkpoint": False,
            "requires_approval": False,
            "contradiction_found": False,
            "ambiguity_score": 0.0,
            "constraints": [],
            "assumptions": [],
            "recommendation": None,
            "elapsed_ms": 0,
            "session_id": session_id,
        }


@app.get("/api/orchestrate/stream/{task_id}")
async def orchestrate_stream(task_id: str, request: Request):
    """
    Phase 2 — Live Execution Feed (SSE)

    Streams real-time task execution events as Server-Sent Events.
    Frontend connects here after receiving a task_id from the orchestrator.
    Events: task_started, step_started, step_completed, step_failed,
            checkpoint_created, approval_required, retry_started,
            task_completed, task_failed, task_cancelled.
    """
    from ..orchestration.live_updates import event_stream as _event_stream
    from starlette.responses import StreamingResponse as _SR

    async def _gen():
        async for chunk in _event_stream(task_id, timeout=300.0):
            if await request.is_disconnected():
                break
            yield chunk

    return _SR(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/creation/export")
async def creation_export(req: CreationExportRequest):
    """
    Creation Record Export

    Generates a structured, timestamped creation record for a project.
    Disclaimer is ALWAYS embedded — no conditionals.

    Returns:
      - JSON payload (default) or plain-text string (export_format="txt")
    """
    from .creation_record import build_export as _build_export
    from datetime import datetime, timezone as _tz

    history_raw = [{"role": m.role, "content": m.content} for m in (req.history or [])]
    created_at  = req.created_at or datetime.now(_tz.utc).isoformat()

    result = _build_export(
        project_id=req.project_id,
        project_title=req.project_title,
        created_at=created_at,
        history=history_raw,
        creator_name=req.creator_name,
        description=req.description,
        notes=req.notes,
        export_format=req.export_format,
    )

    if req.export_format == "txt":
        from starlette.responses import PlainTextResponse
        import re as _cr_re
        filename = _cr_re.sub(r"[^a-zA-Z0-9_\-]", "_", req.project_title)[:40] or "creation_record"
        return PlainTextResponse(
            content=result,
            headers={"Content-Disposition": f'attachment; filename="{filename}.txt"'},
        )

    return result


# ---------------------------------------------------------------------------
# User Settings endpoints
# ---------------------------------------------------------------------------

@app.get("/api/settings")
async def get_user_settings():
    """Return current user settings."""
    from .user_settings import get_settings as _get_settings
    return _get_settings()


@app.patch("/api/settings")
async def update_user_settings(body: dict):
    """
    Update one or more user settings.

    Body: { "ai_data_usage_mode": "private" | "improve_system" }
    """
    from .user_settings import update_settings as _update_settings
    try:
        updated = _update_settings(body)
        return updated
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# Privacy / Retention endpoints
# ---------------------------------------------------------------------------

@app.post("/api/privacy/purge")
async def privacy_purge():
    """
    Manually trigger a Tier C retention purge.

    Deletes analytics records older than 30 days.
    Returns counts of records kept and deleted per store.
    """
    from ..privacy.retention_manager import purge_all_tier_c as _purge
    import asyncio as _asyncio
    loop = _asyncio.get_running_loop()
    results = await loop.run_in_executor(None, _purge)
    total_deleted = sum(v["deleted"] for v in results.values())
    return {"purged": total_deleted, "stores": results}


@app.get("/api/health")
async def health_check():
    """Health check: reports DALL-E 3 / OpenAI API availability."""
    from ..services.dalle_client import DalleClient
    dalle_health = await DalleClient().health()
    openai_ok = dalle_health.get("status") == "ok"

    return {
        "status": "ok",
        "service": "mini-assistant-image-system",
        "image_provider": "dall-e-3",
        "openai": "connected" if openai_ok else "disconnected",
        "openai_detail": dalle_health.get("detail"),
    }


@app.post("/api/image/route")
async def route_only(req: RouteRequest):
    """
    Classify a prompt and return the routing decision without generating an image.
    Useful for debugging the router.
    """
    from ..utils.routing_guard import validate_route as guard_validate
    try:
        route_result = await _get_router().route(req.prompt)
        route_result = guard_validate(route_result)
        return {"route_result": route_result}
    except Exception as exc:
        logger.error("Route endpoint error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/api/image/generate/{session_id}", status_code=200)
async def cancel_generation(session_id: str):
    """Cancel an in-progress generation by session_id."""
    task = _active_generations.get(session_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"No active generation for session '{session_id}'")
    task.cancel()
    _active_generations.pop(session_id, None)
    logger.info("Generation cancelled: session_id=%s", session_id)
    return {"cancelled": True, "session_id": session_id}


@app.post("/api/image/generate")
async def generate_image(req: GenerateRequest, request: Request):
    """
    Image generation via DALL-E 3 (OpenAI API).
    1. Prompt safety validation.
    2. Generate via DALL-E 3 (standard or hd quality).
    3. Return image_base64 + metadata.
    """
    # Image generation never deducts credits — images and credits are separate systems.
    auth_header = request.headers.get("authorization")

    # ── Email verification gate ─────────────────────────────────────────────
    try:
        from mini_credits import _decode_bearer as _dec
        _payload = _dec(auth_header)
        if _payload:
            _uid = _payload.get("sub")
            _u = await db["users"].find_one({"id": _uid}, {"email_verified": 1}) if db else None
            if _u and not _u.get("email_verified", True):
                raise HTTPException(status_code=403, detail="email_not_verified")
    except HTTPException:
        raise
    except Exception:
        pass

    # ── Image limit gate ────────────────────────────────────────────────────
    try:
        from mini_credits import check_image_limit as _chk_img
        _img_ok, _img_used, _img_limit, _ = await _chk_img(auth_header)
        if not _img_ok:
            raise HTTPException(
                status_code=403,
                detail=f"image_limit_reached:{_img_used}/{_img_limit}",
            )
    except HTTPException:
        raise
    except Exception:
        pass

    from ..utils.prompt_safety import validate as ps_validate
    from ..services.dalle_client import DalleClient

    session_id = req.session_id or str(uuid.uuid4())
    start_time = time.perf_counter()

    # ---- Step 1: Prompt safety ----
    is_valid, clean_prompt, safety_error = ps_validate(req.prompt)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Prompt rejected: {safety_error}")
    prompt_warnings = []
    if clean_prompt != req.prompt:
        prompt_warnings.append("Prompt was sanitized (whitespace/control chars removed.")

    # ---- Step 2: DALL-E 3 generation ----
    quality = req.quality or "balanced"
    # Size: default square; portrait/landscape can be passed via override_width/height hint
    size = "1024x1024"
    if req.override_width and req.override_height:
        w, h = req.override_width, req.override_height
        if h > w:
            size = "1024x1792"
        elif w > h:
            size = "1792x1024"

    dalle = DalleClient()
    try:
        image_b64 = await dalle.generate(clean_prompt, quality=quality, size=size)
    except RuntimeError as exc:
        logger.error("DALL-E 3 generation failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.error("DALL-E 3 unexpected error: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Image generation error: {exc}")

    # ── Log image generation (no credit deduction) ──────────────────────────
    try:
        from mini_credits import log_image_generated as _log_img
        await _log_img(auth_header, request_id=req.request_id)
    except Exception:
        pass

    # ── Watermark for free-plan users ────────────────────────────────────────
    try:
        _wm_payload = None
        try:
            from mini_credits import _decode_bearer as _dec_wm
            _wm_payload = _dec_wm(auth_header)
        except Exception:
            pass
        _wm_uid  = (_wm_payload or {}).get("sub")
        _wm_user = await db["users"].find_one({"id": _wm_uid}, {"plan": 1}) if (db and _wm_uid) else None
        _wm_plan = (_wm_user or {}).get("plan", "free")
        if _wm_plan not in ("standard", "pro", "max"):
            image_b64 = _apply_watermark(image_b64)
    except Exception as _wm_e:
        logger.debug("Watermark check failed (non-fatal): %s", _wm_e)

    elapsed = (time.perf_counter() - start_time) * 1000
    return GenerateResponse(
        image_base64=image_b64,
        route_result={"provider": "dall-e-3", "quality": quality, "size": size},
        review=None,
        retry_used=False,
        critic_result=None,
        session_id=session_id,
        generation_time_ms=round(elapsed, 1),
        prompt_warnings=prompt_warnings,
    )

    # ---- dead code below kept for reference; remove after DALL-E is stable ----
    try:
        pb = _get_prompt_builder()
        prompts = await pb.build(clean_prompt, route_result)
        positive_prompt = prompts["positive"]
        negative_prompt = prompts["negative"]
        width = req.override_width or 0
        height = req.override_height or 0
        if not (width and height):
            width, height = pb.size_for_visual_mode(
                route_result.get("visual_mode", "portrait"), checkpoint_type, quality
            )
        steps = req.override_steps or pb.steps_for_quality(quality, checkpoint_type)
        cfg = req.override_cfg or pb.cfg_for_style(route_result.get("style_family", "anime"))
        seed = req.override_seed
    except Exception as exc:
        logger.error("PromptBuilder failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Prompt build error: {exc}")

    # Collect which overrides were applied
    overrides_applied: Dict[str, Any] = {}
    for field in ("checkpoint", "workflow", "width", "height", "steps", "cfg", "seed"):
        attr = f"override_{field}"
        val = getattr(req, attr, None)
        if val is not None:
            overrides_applied[field] = val

    plan = GenerationPlan(
        checkpoint=checkpoint_key,
        checkpoint_file=checkpoint_file,
        workflow=workflow_key,
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        steps=steps,
        cfg=cfg,
        seed=seed,
        quality=quality,
        overrides_applied=overrides_applied,
    )

    # ---- Step 5: Dry run — return plan without generating ----
    if req.dry_run:
        elapsed = (time.perf_counter() - start_time) * 1000
        return DryRunResponse(
            session_id=session_id,
            route_result=route_result,
            plan=plan,
            prompt_warnings=prompt_warnings,
        )

    # ---- Step 6: ComfyUI generation (with timeout + cancellation) ----
    comfyui = _get_comfyui()

    # ---- Step 6a: Build workflow based on ComfyUI routing mode ----
    from ..services.comfyui_router import WORKFLOW_GENERATE
    if comfy_decision.workflow == WORKFLOW_GENERATE or not any([reference_bytes, mask_bytes, pose_bytes, style_bytes]):
        # Standard text-to-image
        workflow = comfyui.build_standard_workflow(
            checkpoint=checkpoint_file,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            seed=seed,
        )
    else:
        # Reference-guided or edit/inpaint — load JSON workflow + upload images
        try:
            workflow = comfyui.load_workflow(comfy_decision.workflow)
            # Inject text params first
            workflow = comfyui.inject_params(workflow, {
                "checkpoint":       checkpoint_file,
                "positive_prompt":  positive_prompt,
                "negative_prompt":  negative_prompt,
                "steps":            steps,
                "cfg":              cfg,
                "seed":             seed if seed is not None else __import__("random").randint(0, 2**32 - 1),
                "denoise":          req.denoise_strength if req.denoise_strength is not None else 0.75,
            })

            # Upload images and inject filenames into LoadImage nodes
            # Primary reference image (reference mode) or init image (edit mode)
            primary_img = reference_bytes or pose_bytes or style_bytes
            if primary_img:
                stored_name = await comfyui.upload_image(primary_img, "reference_input.png")
                workflow = comfyui.inject_params(workflow, {"init_image_filename": stored_name})

            # Mask image (edit/inpaint mode)
            if mask_bytes:
                mask_name = await comfyui.upload_image(mask_bytes, "mask_input.png")
                workflow = comfyui.inject_params(workflow, {"mask_image_filename": mask_name})

        except Exception as exc:
            logger.error("Workflow load/inject failed (%s) — falling back to standard workflow", exc)
            workflow = comfyui.build_standard_workflow(
                checkpoint=checkpoint_file,
                positive_prompt=positive_prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                steps=steps,
                cfg=cfg,
                seed=seed,
            )

    image_bytes: Optional[bytes] = None
    review: Optional[dict] = None
    critic_result: Optional[dict] = None
    retry_used = False
    gen_start = time.perf_counter()

    try:
        gen_task = asyncio.ensure_future(comfyui.generate(workflow, timeout=300))
        _active_generations[session_id] = gen_task
        try:
            images = await gen_task
            image_bytes = images[0] if images else None
        except asyncio.CancelledError:
            logger.info("Generation cancelled: session_id=%s", session_id)
            raise HTTPException(status_code=499, detail="Generation cancelled by client")
        finally:
            _active_generations.pop(session_id, None)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ComfyUI generation failed: %s", exc, exc_info=True)
        gen_elapsed = (time.perf_counter() - gen_start) * 1000
        image_logger.log_comfyui_execution(
            session_id, checkpoint_key, workflow_key,
            width, height, steps, cfg, seed or -1,
            gen_elapsed, None, error=str(exc),
        )
        raise HTTPException(status_code=502, detail=f"ComfyUI error: {exc}")

    gen_elapsed = (time.perf_counter() - gen_start) * 1000
    image_logger.log_comfyui_execution(
        session_id, checkpoint_key, workflow_key,
        width, height, steps, cfg, seed or -1,
        gen_elapsed, None,
    )

    # ---- Step 7: Review (skip for fast quality) ----
    review_start = time.perf_counter()
    if image_bytes and quality != "fast":
        try:
            from ..services.image_reviewer import ImageReviewer
            reviewer = ImageReviewer()
            review = await reviewer.review_image(image_bytes, clean_prompt, route_result)
        except Exception as exc:
            logger.warning("Image review failed: %s", exc)
            review = None

    # ---- Step 8: Critic evaluation + single retry ----
    if review and image_bytes:
        try:
            critic = _get_critic()
            critic_result = await critic.evaluate(clean_prompt, route_result, review)

            if critic_result.get("should_retry"):
                adjusted = critic_result.get("adjusted_params", {})
                alt_checkpoint_key = critic_result.get("alt_checkpoint") or checkpoint_key
                try:
                    registry = _load_registry()
                    checkpoint_info_retry = registry["image_checkpoints"].get(alt_checkpoint_key, {})
                    retry_checkpoint_file = checkpoint_info_retry.get("file", checkpoint_file)
                except Exception:
                    retry_checkpoint_file = checkpoint_file

                retry_workflow = comfyui.build_standard_workflow(
                    checkpoint=retry_checkpoint_file,
                    positive_prompt=positive_prompt,
                    negative_prompt=negative_prompt,
                    width=width,
                    height=height,
                    steps=adjusted.get("steps", steps),
                    cfg=adjusted.get("cfg", cfg),
                    seed=adjusted.get("seed"),
                )

                retry_images = await comfyui.generate(retry_workflow, timeout=300)
                if retry_images:
                    image_bytes = retry_images[0]
                    retry_used = True
                    logger.info("Retry completed with checkpoint=%s", alt_checkpoint_key)
        except Exception as exc:
            logger.warning("Critic/retry failed: %s", exc)

    review_elapsed = (time.perf_counter() - review_start) * 1000
    quality_score = review.get("quality_score", 0.7) if review else 0.7
    image_logger.log_review_event(
        session_id, quality_score, retry_used,
        review.get("retry_reason") if review else None,
        critic_result.get("alt_checkpoint") if critic_result else None,
        2 if retry_used else 1,
        review_elapsed,
        None,
    )

    # ---- Step 9: Store successful route ----
    if image_bytes and quality_score >= 0.5:
        try:
            await _get_embed().store_successful_route(clean_prompt, route_result, quality_score)
        except Exception as exc:
            logger.warning("EmbedBrain store failed: %s", exc)

    # ---- Step 10: Save image + metadata sidecar ----
    out_path = None
    if image_bytes:
        try:
            out_path = metadata_writer.save_output_image(image_bytes, session_id, seed or -1)
            meta = metadata_writer.build_metadata(
                original_prompt=req.prompt,
                positive_prompt=positive_prompt,
                negative_prompt=negative_prompt,
                route=route_result,
                checkpoint=checkpoint_key,
                workflow=workflow_key,
                seed=seed or -1,
                width=width,
                height=height,
                steps=steps,
                cfg=cfg,
                quality=quality,
                review_result=review,
                session_id=session_id,
                generation_ms=(time.perf_counter() - start_time) * 1000,
            )
            metadata_writer.save_metadata(out_path, meta)
        except Exception as exc:
            logger.warning("Metadata/image save failed: %s", exc)

    elapsed = (time.perf_counter() - start_time) * 1000
    image_b64 = base64.b64encode(image_bytes).decode("utf-8") if image_bytes else None

    return GenerateResponse(
        image_base64=image_b64,
        route_result={**route_result, "comfyui_mode": comfy_decision.mode, "target_tab": comfy_decision.target_tab},
        review=review,
        retry_used=retry_used,
        critic_result=critic_result,
        session_id=session_id,
        generation_time_ms=round(elapsed, 1),
        prompt_warnings=prompt_warnings,
    )


@app.post("/api/image/analyze")
async def analyze_image(req: AnalyzeRequest, request: Request):
    """
    Analyse an image using the vision brain.

    Body: { image_base64: str, question?: str }
    """
    # Image analysis never deducts credits — images and credits are separate systems.

    try:
        image_bytes = base64.b64decode(req.image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    try:
        vision = _get_vision()
        answer = await vision.analyze(image_bytes, req.question or "Describe this image.")
        return {"answer": answer}
    except Exception as exc:
        logger.error("Vision analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ── Image-edit description cache (session_id → last GPT-4o description) ──────
# Capped at 200 entries; oldest entry evicted when full.
_edit_desc_cache: dict[str, str] = {}
_EDIT_DESC_CACHE_MAX = 200


def _route_edit_tier(
    etype: str,
    region: str,
    from_color: str | None,
    overlap_risk: bool,
) -> str:
    """
    Determine the processing tier for a single image-edit step.

    Returns one of: "semantic", "vision", "region_pil", "pil_global"

    Routing logic (evaluated top-down, first match wins):
    - skin/fur/body/complexion/tone in region    → "vision"
    - hair/eye/brow in region                    → "semantic"
    - clothing keywords in region                → "semantic"
    - color_change step AND no overlap risk      → "region_pil"  (fast, no API)
    - color_change step AND overlap risk         → "vision"
    - default                                    → "semantic"
    """
    r = (region or "").lower()

    _SKIN_RE = re.compile(
        r"\b(skin|fur|body|complexion|tone)\b", re.IGNORECASE
    )
    _HAIR_EYE_RE = re.compile(
        r"\b(hair|eye|eyes|brow|eyebrow)\b", re.IGNORECASE
    )
    _CLOTHING_RE = re.compile(
        r"\b(shirt|hoodie|jacket|pants|jeans|shoes|sneakers|boots|hat|cap|"
        r"vest|dress|outfit|coat|gloves|accessory|accessories)\b",
        re.IGNORECASE,
    )

    if _SKIN_RE.search(r):
        return "semantic"   # try gpt-image-1 edit first; fall back to vision on moderation
    if _HAIR_EYE_RE.search(r):
        return "semantic"
    if _CLOTHING_RE.search(r):
        return "semantic"
    if etype == "color_change":
        return "vision" if overlap_risk else "region_pil"
    return "semantic"


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    """
    Multi-purpose chat endpoint — Phase 2: Full Executive Hierarchy.

    Request flow:
      Command Parser  → slash command detection
      Planner         → intent + task list  (ALWAYS FIRST)
      CEO             → posture: mode, risk, priority
      Manager         → session context, normalization
      Supervisor      → task state tracking
      Brain           → image gen / coding / chat execution
      Critic          → reply validation
      Composer        → final response assembly

    Slash commands (/fix, /image, /code, etc.) override intent detection.
    Phase 2 adds CEO posture, Manager session context, and Supervisor task tracking.
    """
    from ..utils.prompt_safety import validate as ps_validate
    # Images never deduct credits — only deduct for text chat requests.
    if not getattr(req, "image_base64", None):
        try:
            from mini_credits import check_and_deduct as _deduct
            _ok, _remaining = await _deduct(request.headers.get("authorization"), cost=1)
            if not _ok:
                raise HTTPException(status_code=402, detail="out_of_credits")
        except HTTPException:
            raise
        except Exception:
            pass  # credit module unavailable — allow through

    session_id = req.session_id or str(uuid.uuid4())

    is_valid, clean_message, safety_error = ps_validate(req.message)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Message rejected: {safety_error}")

    # Decode user-attached image (Phase 5)
    attached_image_bytes: Optional[bytes] = None
    if req.image_base64:
        try:
            attached_image_bytes = base64.b64decode(req.image_base64)
        except Exception:
            logger.warning("Could not decode attached image_base64 — ignoring.")

    # ── Phase 1 Step 1: Command Parser ─────────────────────────────────────────
    phase1_plan        = None
    phase1_critic      = None
    parsed_cmd         = None
    effective_msg      = clean_message
    ceo_posture        = None
    manager_packet     = None
    supervisor_result  = None
    skill_match        = None
    reflection_record  = None
    parallel_result    = None
    mission_result     = None
    engineering_ctx    = None   # Phase 6
    memory_facts_stored = []    # Phase 6

    try:
        from mini_assistant.phase1.command_parser import parse as cmd_parse
        from mini_assistant.phase1.intent_planner import plan as make_plan
        from mini_assistant.phase1.critic import critique
        from mini_assistant.phase1.composer import compose as phase1_compose
        from mini_assistant.phase1.command_parser import help_text

        # Parse slash command (if any)
        parsed_cmd  = cmd_parse(clean_message)
        effective_msg = parsed_cmd.args if parsed_cmd.is_slash else clean_message

        # ── Phase 1 Step 2: Planner (ALWAYS RUNS FIRST) ────────────────────────
        # If an image is attached, route to edit / reference-generate / analysis
        import re as _re_intent
        # Edit keywords — modify the EXACT same image, preserve identity
        _EDIT_KW = _re_intent.compile(
            r"\b(change|edit|modify|fix|adjust|recolor|replace|remove|enhance|improve|"
            r"turn\s+(him|her|it|them|this|that)\b|make\s+(him|her|it|them|this|that)\b|"
            r"darker|brighter|lighter|redder|bluer|greener|purpler|"
            r"angrier|fiercer|stronger|calmer|sadder|happier|older|younger|"
            r"add\s+(?!a\s+new|another)|give\s+(?:him|her|it|them))\b",
            _re_intent.I,
        )
        # Reference-generate keywords — use image as style reference, create NEW image
        _REF_GEN_KW = _re_intent.compile(
            r"\b(draw|generate|create|recreate|render|design|reimagine|reinvent|"
            r"in the style of|inspired by|wearing|holding|show|put|place)\b",
            _re_intent.I,
        )
        from mini_assistant.phase1.command_parser import ParsedCommand as _PC, SLASH_COMMANDS as _SC
        if attached_image_bytes and not (parsed_cmd and parsed_cmd.is_slash):
            _wants_edit   = bool(_EDIT_KW.search(effective_msg))    if effective_msg else False
            _wants_refgen = bool(_REF_GEN_KW.search(effective_msg)) if effective_msg else False
            # Short prompt + image with no clear ref-gen keywords → treat as edit
            _short_prompt = len((effective_msg or "").strip()) < 80
            if _wants_edit or (_short_prompt and not _wants_refgen):
                # Modify the attached image — preserve identity
                logger.info("[MODEL ROUTER] image_edit detected (edit_kw=%s short=%s)", _wants_edit, _short_prompt)
                parsed_cmd = _PC(
                    raw=effective_msg,
                    command="image_edit",
                    args=effective_msg,
                    intent_override="image_edit",
                    is_slash=True,
                    is_known=True,
                    help_requested=False,
                )
            elif _wants_refgen:
                # Generate new image inspired by the reference
                logger.info("[MODEL ROUTER] image_reference_generate detected")
                parsed_cmd = _PC(
                    raw=effective_msg,
                    command="image",
                    args=effective_msg,
                    intent_override="image_reference_generate",
                    is_slash=True,
                    is_known=True,
                    help_requested=False,
                )
            else:
                # Pure analysis — describe the image
                parsed_cmd = _PC(
                    raw=effective_msg,
                    command="analyze",
                    args=effective_msg,
                    intent_override="image_analysis",
                    is_slash=True,
                    is_known=True,
                    help_requested=False,
                )

        phase1_plan = make_plan(
            message        = effective_msg,
            parsed_command = parsed_cmd,
            history        = req.history or [],
        )
        logger.info(
            "Planner → intent=%s confidence=%.2f method=%s ms=%.1f",
            phase1_plan.intent, phase1_plan.confidence,
            phase1_plan.routing_method, phase1_plan.planner_ms,
        )

        # /help shortcut — return command list without hitting any brain
        if parsed_cmd.help_requested:
            return phase1_compose(
                reply        = help_text(),
                plan         = phase1_plan,
                critic       = critique(help_text(), phase1_plan),
                session_id   = session_id,
                route_result = {},
            )

        # ── Phase 2 Step 1: CEO — set posture ──────────────────────────────────
        try:
            from mini_assistant.phase2.ceo import assess as ceo_assess
            ceo_posture = ceo_assess(phase1_plan, effective_msg)
            logger.info(
                "CEO → mode=%s risk=%s priority=%s ms=%.1f",
                ceo_posture.mode, ceo_posture.risk_posture,
                ceo_posture.priority, ceo_posture.ceo_ms,
            )
        except Exception as _ceo_err:
            logger.warning("CEO failed (%s) — using defaults.", _ceo_err)
            ceo_posture = None

        # ── Phase 2 Step 2: Manager — normalize + inject session context ───────
        try:
            from mini_assistant.phase2.manager import prepare as mgr_prepare
            history_list = [{"role": h.role, "content": h.content} for h in (req.history or [])]
            manager_packet = mgr_prepare(
                message    = effective_msg,
                session_id = session_id,
                plan       = phase1_plan,
                posture    = ceo_posture,
                history    = history_list,
            )
            logger.info(
                "Manager → turn=%d is_continuation=%s ceo_mode=%s ms=%.1f",
                manager_packet.session_context.get("turn_count", 0),
                manager_packet.is_continuation,
                manager_packet.ceo_mode,
                manager_packet.manager_ms,
            )
        except Exception as _mgr_err:
            logger.warning("Manager failed (%s) — skipping context injection.", _mgr_err)
            manager_packet = None

        # ── Phase 3 Step 1: Skill Selector ─────────────────────────────────────
        try:
            from mini_assistant.phase3.skill_selector import get_selector
            skill_match = get_selector().select(
                plan          = phase1_plan,
                message       = effective_msg,
                slash_command = parsed_cmd.command if parsed_cmd and parsed_cmd.is_slash else None,
            )
            if skill_match.matched:
                logger.info(
                    "SkillSelector matched: %s (conf=%.2f, %d steps) ms=%.1f",
                    skill_match.skill.name, skill_match.confidence,
                    len(skill_match.override_steps), skill_match.selector_ms,
                )
            else:
                logger.debug("SkillSelector: no match (ms=%.1f)", skill_match.selector_ms)
        except Exception as _ss_err:
            logger.warning("SkillSelector failed (%s) — continuing without skill.", _ss_err)
            skill_match = None

        # ── Phase 2 Step 3: Supervisor — sequential task state tracking ────────
        try:
            from mini_assistant.phase2.supervisor import Supervisor
            if manager_packet:
                supervisor = Supervisor(manager_packet)
                # If a skill matched, use its refined steps; otherwise use Planner's
                tasks_to_run = (
                    skill_match.override_steps
                    if skill_match and skill_match.matched and skill_match.override_steps
                    else phase1_plan.sequential_tasks
                )
                supervisor_result = supervisor.supervise(tasks_to_run)
                logger.info(
                    "Supervisor → %d/%d tasks completed, overall=%s ms=%.1f",
                    len(supervisor_result.completed_tasks),
                    len(supervisor_result.tasks),
                    supervisor_result.overall_state,
                    supervisor_result.supervisor_ms,
                )
            else:
                supervisor_result = None
        except Exception as _sup_err:
            logger.warning("Supervisor failed (%s) — continuing without task tracking.", _sup_err)
            supervisor_result = None

        # ── Phase 4 Step 1: Parallel Supervisor — wave-based async execution ───
        try:
            from mini_assistant.phase4.parallel_supervisor import ParallelSupervisor
            parallel_tasks = phase1_plan.parallel_tasks or []
            if parallel_tasks:
                par_sup = ParallelSupervisor()
                parallel_result = await par_sup.run(parallel_tasks)
                logger.info(
                    "ParallelSupervisor → %d tasks in %d waves, %.1f ms (gain=%.1fms)",
                    parallel_result.tasks_total,
                    len(parallel_result.waves),
                    parallel_result.total_ms,
                    parallel_result.parallel_gain,
                )
        except Exception as _par_err:
            logger.warning("ParallelSupervisor failed (%s) — non-fatal.", _par_err)
            parallel_result = None

    except Exception as _p1_err:
        logger.warning("Phase 1/2 pipeline failed (%s) — falling back to legacy routing.", _p1_err)
        phase1_plan = None
        ceo_posture = None
        manager_packet = None
        supervisor_result = None

    # ── Phase 1 Step 3: Execution Router ───────────────────────────────────────
    # Use Planner's execution_intent to drive the existing image_system router.
    # If Planner is unavailable, fall back to the RouterBrain as before.

    execution_intent = (
        phase1_plan.execution_intent if phase1_plan else None
    )
    route_result: dict = {}

    # For image generation, still run the RouterBrain to get checkpoint/workflow detail
    if execution_intent == "image_generation" or execution_intent is None:
        try:
            from ..utils.routing_guard import validate_route as guard_validate
            rr = await _get_router().route(effective_msg)
            rr = guard_validate(rr)
            route_result = rr if isinstance(rr, dict) else (rr.dict() if hasattr(rr, "dict") else {})
            if execution_intent is None:
                execution_intent = route_result.get("intent", "chat")
        except Exception as exc:
            logger.error("RouterBrain failed: %s", exc)
            route_result     = {"intent": "chat"}
            execution_intent = execution_intent or "chat"

    # ── Phase 9 Step 1: Self-Improvement Context Injection ──────────────────────
    phase9_ctx = None
    try:
        from mini_assistant.phase9.context_injector import get_injector
        phase9_ctx = get_injector().build(
            intent     = execution_intent or "chat",
            session_id = session_id,
        )
        if phase9_ctx.sources:
            logger.info(
                "Phase9Injector: lessons=%d memory=%d (%.1f ms)",
                phase9_ctx.lessons_used, phase9_ctx.memory_facts_used, phase9_ctx.assembly_ms,
            )
    except Exception as _p9_err:
        logger.debug("Phase9 context injection failed (non-fatal): %s", _p9_err)

    # ── Phase 6 Step 1: Engineering Assistant context assembly ──────────────────
    try:
        from mini_assistant.phase6.engineering_assistant import get_engineering_assistant
        engineering_ctx = get_engineering_assistant().build(
            intent     = phase1_plan.intent if phase1_plan else "normal_chat",
            message    = effective_msg,
            session_id = session_id,
        )
        if engineering_ctx.sources_used:
            logger.info(
                "EngineeringAssistant: %s (%.1f ms)",
                engineering_ctx.sources_used, engineering_ctx.assembly_ms,
            )
    except Exception as _eng_err:
        logger.debug("EngineeringAssistant failed (non-fatal): %s", _eng_err)
        engineering_ctx = None

    # ── Phase 1 Step 4: Brain Execution ────────────────────────────────────────
    reply = ""

    # ── Image limit gate (for all image-generating intents) ────────────────
    _is_img_intent = execution_intent in ("image_generation", "image_edit", "image_reference_generate")
    if _is_img_intent:
        _chat_auth = request.headers.get("authorization")
        try:
            from mini_credits import check_image_limit as _chk_img, _decode_bearer as _dec
            # Email verification check
            _pl = _dec(_chat_auth)
            if _pl:
                _u = await db["users"].find_one({"id": _pl.get("sub")}, {"email_verified": 1}) if db else None
                if _u and not _u.get("email_verified", True):
                    return {"reply": "Please verify your email before generating images.", "error": "email_not_verified"}
            # Image limit check
            _img_ok, _img_used, _img_limit_v, _ = await _chk_img(_chat_auth)
            if not _img_ok:
                return {
                    "reply": f"You've reached your image limit ({_img_used}/{_img_limit_v}). Upgrade to generate more.",
                    "error": "image_limit_reached",
                }
        except Exception:
            pass

    # Model: always Claude claude-sonnet-4-6 (no local Ollama)
    _active_model = "claude-sonnet-4-6"
    logger.info("[MODEL ROUTER] chat → Claude %s", _active_model)

    if execution_intent == "image_edit":
        logger.info("[MODEL ROUTER] image_edit")
        _edit_start = time.perf_counter()

        # ── Smart edit routing via GPT analyzer ──────────────────────────────
        # GPT breaks the request into ordered steps (color first, then structural).
        # Steps are chained: each step's output is the next step's input image.
        _edit_steps = None
        try:
            from mini_assistant.phase2.prompt_enhancer import analyze_edit_request
            _edit_steps = await analyze_edit_request(effective_msg.strip())
            logger.info("[MODEL ROUTER] analyze_edit_request → %d steps", len(_edit_steps) if _edit_steps else 0)
        except Exception as _ae:
            logger.warning("analyze_edit_request failed (%s) — using fallback routing", _ae)

        # If no steps from GPT, create a single fallback structural step
        if not _edit_steps:
            _edit_steps = [{"edit_type": "structural_edit", "final_instruction": None}]

        # ── Helper: build PIL mask from bounding box ──────────────────────────
        def _build_mask(img_bytes: bytes, mask_box: dict) -> bytes | None:
            try:
                import io as _io2
                from PIL import Image as _PILImg2
                _img2 = _PILImg2.open(_io2.BytesIO(img_bytes)).convert("RGBA")
                _W2, _H2 = _img2.size
                _mask2 = _PILImg2.new("RGBA", (_W2, _H2), (0, 0, 0, 255))
                _px2 = round(mask_box.get("left", 0) / 100 * _W2)
                _py2 = round(mask_box.get("top", 0) / 100 * _H2)
                _pw2 = round(mask_box.get("width", 100) / 100 * _W2)
                _ph2 = round(mask_box.get("height", 100) / 100 * _H2)
                _mpix = _mask2.load()
                for _my2 in range(_py2, min(_py2 + _ph2, _H2)):
                    for _mx2 in range(_px2, min(_px2 + _pw2, _W2)):
                        _mpix[_mx2, _my2] = (0, 0, 0, 0)
                _mbuf = _io2.BytesIO()
                _mask2.save(_mbuf, format="PNG")
                return _mbuf.getvalue()
            except Exception as _me:
                logger.warning("mask build failed: %s", _me)
                return None

        # ── 4-Tier pipeline ───────────────────────────────────────────────────
        from ..services.dalle_client import DalleClient
        _dalle = DalleClient()
        _current_bytes = attached_image_bytes   # updated after each step
        _current_b64: str | None = None
        _step_metadata: list[dict] = []

        for _step_i, _step in enumerate(_edit_steps):
            _etype        = _step.get("edit_type", "structural_edit")
            _from_color   = (_step.get("from_color") or "").lower().strip() or None
            _to_color     = (_step.get("to_color")   or "").lower().strip() or None
            _region_desc  = (_step.get("region_description") or "").lower()
            _mask_box     = _step.get("mask_box")
            _overlap_risk = bool(_step.get("color_overlap_risk", False))

            # Determine primary tier — honour analyzer hint if present, otherwise compute
            _analyzer_tier = _step.get("primary_tier") or ""
            _computed_tier = _route_edit_tier(_etype, _region_desc, _from_color, _overlap_risk)
            _primary_tier  = _analyzer_tier if _analyzer_tier in ("semantic", "vision", "region_pil", "pil_global") else _computed_tier

            logger.info(
                "[MODEL ROUTER] step %d/%d → etype=%s tier=%s from=%s to=%s overlap_risk=%s",
                _step_i + 1, len(_edit_steps), _etype, _primary_tier,
                _from_color, _to_color, _overlap_risk,
            )

            _step_meta = {"step": _step_i + 1, "tier": _primary_tier, "method_used": "unknown",
                          "confidence_score": 0.0, "notes": ""}
            _step_success = False

            # ── TIER 1: Semantic (gpt-image-1 edit) ──────────────────────────
            async def _try_tier1() -> bool:
                nonlocal _current_b64, _current_bytes
                _instr = _step.get("final_instruction")
                if not _instr:
                    try:
                        from mini_assistant.phase2.prompt_enhancer import enhance_edit_instruction
                        _instr = await enhance_edit_instruction(effective_msg.strip())
                    except Exception:
                        _instr = effective_msg.strip()

                _strict_prompt = (
                    f"Apply ONLY this change: {_instr}. "
                    "DO NOT modify clothing, accessories, background, pose, lighting, or identity. "
                    "Preserve everything else pixel-perfectly."
                )
                _msk = None
                if _current_bytes and _mask_box:
                    _msk = _build_mask(_current_bytes, _mask_box)
                try:
                    if _current_bytes:
                        _b64s = await _dalle.edit(_current_bytes, _strict_prompt, mask_bytes=_msk)
                    else:
                        _b64s = await _dalle.generate(_strict_prompt)
                    _current_b64   = _b64s
                    _current_bytes = base64.b64decode(_b64s)
                    _step_meta["method_used"]      = "semantic"
                    _step_meta["confidence_score"] = 0.9
                    logger.info("[MODEL ROUTER] step %d tier1/semantic OK", _step_i + 1)
                    return True
                except Exception as _t1e:
                    _is_mod = "moderation_blocked" in str(_t1e) or "safety system" in str(_t1e).lower()
                    logger.warning("step %d tier1/semantic failed (%s) is_moderation=%s", _step_i + 1, _t1e, _is_mod)
                    return False

            # ── TIER 2: Vision reconstruction ────────────────────────────────
            async def _try_tier2() -> bool:
                nonlocal _current_b64, _current_bytes
                if not (_from_color and _to_color and _current_bytes):
                    return False
                try:
                    _cached = _edit_desc_cache.get(session_id)
                    logger.info(
                        "[MODEL ROUTER] step %d tier2/vision %s→%s (cached_desc=%s)",
                        _step_i + 1, _from_color, _to_color, _cached is not None,
                    )
                    _b64s, _desc_used = await _dalle.describe_and_recolor(
                        _current_bytes, _from_color, _to_color,
                        region=_region_desc or "skin/fur",
                        cached_description=_cached,
                    )
                    # Cache the description for this session
                    if len(_edit_desc_cache) >= _EDIT_DESC_CACHE_MAX:
                        # Evict the oldest entry
                        _oldest = next(iter(_edit_desc_cache))
                        del _edit_desc_cache[_oldest]
                    _edit_desc_cache[session_id] = _desc_used

                    _current_b64   = _b64s
                    _current_bytes = base64.b64decode(_b64s)
                    _step_meta["method_used"]      = "vision"
                    _step_meta["confidence_score"] = 0.75
                    logger.info("[MODEL ROUTER] step %d tier2/vision OK", _step_i + 1)
                    return True
                except Exception as _t2e:
                    logger.warning("step %d tier2/vision failed (%s)", _step_i + 1, _t2e)
                    return False

            # ── TIER 3: Region-constrained PIL ───────────────────────────────
            async def _try_tier3() -> bool:
                nonlocal _current_b64, _current_bytes
                if not (_mask_box and _from_color and _to_color and _current_bytes):
                    return False
                try:
                    _b64s = _dalle.color_replace_region(
                        _current_bytes, _from_color, _to_color, _mask_box
                    )
                    if _b64s is None:
                        return False
                    _current_b64   = _b64s
                    _current_bytes = base64.b64decode(_b64s)
                    _step_meta["method_used"]      = "region_pil"
                    _step_meta["confidence_score"] = 0.5
                    logger.info("[MODEL ROUTER] step %d tier3/region_pil OK", _step_i + 1)
                    return True
                except Exception as _t3e:
                    logger.warning("step %d tier3/region_pil failed (%s)", _step_i + 1, _t3e)
                    return False

            # ── TIER 4: Global PIL (last resort) ─────────────────────────────
            async def _try_tier4() -> bool:
                nonlocal _current_b64, _current_bytes
                if not (_from_color and _to_color and _current_bytes):
                    return False
                try:
                    _b64s = _dalle.color_replace(_current_bytes, _from_color, _to_color)
                    if _b64s is None:
                        return False
                    _current_b64   = _b64s
                    _current_bytes = base64.b64decode(_b64s)
                    _step_meta["method_used"]      = "pil_global"
                    _step_meta["confidence_score"] = 0.2
                    _step_meta["notes"] = (
                        "Low-precision fallback. All pixels matching source color were replaced."
                    )
                    logger.warning(
                        "[MODEL ROUTER] step %d Low precision fallback: global PIL color_replace used",
                        _step_i + 1,
                    )
                    return True
                except Exception as _t4e:
                    logger.warning("step %d tier4/pil_global failed (%s)", _step_i + 1, _t4e)
                    return False

            # ── Dispatch based on primary tier, cascade on failure ────────────
            if _primary_tier == "semantic":
                _step_success = await _try_tier1()
                if not _step_success:
                    _step_success = await _try_tier2()
                if not _step_success:
                    _step_success = await _try_tier3()
                if not _step_success:
                    _step_success = await _try_tier4()

            elif _primary_tier == "vision":
                _step_success = await _try_tier2()
                if not _step_success:
                    _step_success = await _try_tier1()
                if not _step_success:
                    _step_success = await _try_tier3()
                if not _step_success:
                    _step_success = await _try_tier4()

            elif _primary_tier == "region_pil":
                _step_success = await _try_tier3()
                if not _step_success:
                    _step_success = await _try_tier4()
                if not _step_success:
                    _step_success = await _try_tier2()

            else:  # pil_global or unknown — try global PIL first, then escalate
                _step_success = await _try_tier4()
                if not _step_success:
                    _step_success = await _try_tier2()
                if not _step_success:
                    _step_success = await _try_tier1()

            _step_metadata.append(_step_meta)
            logger.info(
                "[MODEL ROUTER] step %d result: success=%s method=%s confidence=%.2f notes=%s",
                _step_i + 1, _step_success,
                _step_meta["method_used"], _step_meta["confidence_score"], _step_meta["notes"],
            )

            if not _step_success:
                if _current_b64 is None:
                    reply = "Image editing failed — all tiers exhausted."
                break

        _edit_elapsed_ms = round((time.perf_counter() - _edit_start) * 1000, 1)

        if _current_b64:
            try:
                from mini_credits import log_image_generated as _log_img
                await _log_img(request.headers.get("authorization"), request_id=getattr(req, "request_id", None))
            except Exception:
                pass
            return {
                "image_base64":      _current_b64,
                "reply":             "Image edited.",
                "intent":            "image_edit",
                "session_id":        session_id,
                "plan":              phase1_plan.to_dict() if phase1_plan else {},
                "method_used":       _step_metadata[-1]["method_used"] if _step_metadata else "unknown",
                "confidence_score":  min(s["confidence_score"] for s in _step_metadata) if _step_metadata else 0.0,
                "notes":             "; ".join(s["notes"] for s in _step_metadata if s.get("notes")),
                "route_result":      "image_edit",
                "generation_time_ms": _edit_elapsed_ms,
            }

    elif execution_intent == "image_generation":
        # ── PURE TEXT-TO-IMAGE: no reference image ────────────────────────────
        logger.info("[MODEL ROUTER] image_generation → DALL-E 3")
        try:
            from ..services.dalle_client import DalleClient
            # GPT-5.4 enriches the raw user prompt with art style, lighting,
            # composition, and quality modifiers before hitting DALL-E 3.
            try:
                from mini_assistant.phase2.prompt_enhancer import enhance_image_prompt
                _gen_prompt = await enhance_image_prompt(effective_msg)
            except Exception:
                _gen_prompt = effective_msg
            _dalle = DalleClient()
            _b64 = await _dalle.generate(_gen_prompt)
            try:
                from mini_credits import log_image_generated as _log_img
                await _log_img(request.headers.get("authorization"), request_id=getattr(req, "request_id", None))
            except Exception:
                pass
            return {
                "image_base64": _b64,
                "reply": "Image generated.",
                "intent": "image_generation",
                "session_id": session_id,
                "plan": phase1_plan.to_dict() if phase1_plan else {},
            }
        except Exception as exc:
            logger.error("DALL-E generation failed: %s", exc)
            reply = f"Image generation failed: {exc}"

    elif execution_intent == "image_reference_generate":
        # Analyze reference image with GPT-4o → build prompt → generate via DALL-E 3
        logger.info("[MODEL ROUTER] image_reference_generate → GPT-4o vision + DALL-E 3")
        try:
            vision = _get_vision()
            description = await vision.analyze(
                attached_image_bytes,
                "Describe this image in precise visual detail: subject appearance, "
                "colors, art style, lighting, composition, background. Be specific "
                "and comprehensive — this will be used as an image generation reference.",
            )
        except Exception as exc:
            description = "a character or scene"
            logger.warning("Vision describe failed: %s", exc)

        # GPT-5.4 fuses the vision description + user request into the
        # optimal DALL-E 3 prompt, preserving style while applying the request.
        try:
            from mini_assistant.phase2.prompt_enhancer import enhance_reference_prompt
            dalle_prompt = await enhance_reference_prompt(description, effective_msg)
        except Exception:
            dalle_prompt = (
                f"Reference image description: {description}\n\n"
                f"User request: {effective_msg}\n\n"
                "Generate a new image that fulfills the user request, visually inspired "
                "by the reference. Preserve the art style, color palette, and character "
                "design from the reference while applying the requested changes."
            )
        try:
            from ..services.dalle_client import DalleClient
            _dalle = DalleClient()
            _b64 = await _dalle.generate(dalle_prompt)
            try:
                from mini_credits import log_image_generated as _log_img
                await _log_img(request.headers.get("authorization"), request_id=getattr(req, "request_id", None))
            except Exception:
                pass
            return {
                "image_base64": _b64,
                "reply": "Image generated from reference.",
                "intent": "image_reference_generate",
                "session_id": session_id,
                "plan": phase1_plan.to_dict() if phase1_plan else {},
            }
        except Exception as exc:
            logger.error("DALL-E reference generation failed: %s", exc)
            reply = f"Image generation failed: {exc}"

    elif execution_intent == "image_analysis" or (execution_intent == "chat" and attached_image_bytes):
        # Pure image analysis — describe/answer questions about the attached image
        logger.info("[MODEL ROUTER] image_analysis → GPT-4o vision")
        try:
            vision = _get_vision()
            question = effective_msg or "Describe this image in detail."
            reply = await vision.analyze(attached_image_bytes, question)
        except Exception as exc:
            reply = f"Vision brain error: {exc}"

    elif execution_intent == "coding":
        try:
            # Inject engineering context prefix if available
            eng_prefix = (engineering_ctx.system_prefix if engineering_ctx else "")
            reply = await _get_coding().run(eng_prefix + effective_msg if eng_prefix else effective_msg)
        except Exception as exc:
            reply = f"Coding brain error: {exc}"

    elif execution_intent in ("tool_use", "code_runner", "shell"):
        # ── Phase 8: Tool Brain ─────────────────────────────────────────────
        # Parse "TOOL:<tool_name> CMD:<command>" pattern from message,
        # or route the raw message to shell_safe as a read-only shell command.
        try:
            from mini_assistant.phase8.tool_brain import tool_brain
            from mini_assistant.phase8.security_brain import evaluate_tool

            import re as _re
            _m = _re.search(r"TOOL:(\S+)\s+CMD:(.*)", effective_msg, _re.DOTALL)
            if _m:
                _tool_name = _m.group(1).strip()
                _command   = _m.group(2).strip()
            else:
                _tool_name = "shell_safe"
                _command   = effective_msg

            sec = evaluate_tool(_tool_name, _command)
            if sec.blocked:
                reply = f"⛔ Blocked: {'; '.join(sec.reasons)}"
            elif sec.requires_approval:
                from mini_assistant.phase8.approval_store import approval_store
                aid = approval_store.add_pending(
                    tool_name  = _tool_name,
                    command    = _command,
                    session_id = session_id,
                    risk_level = sec.risk_level,
                    reasons    = sec.reasons,
                )
                reply = (
                    f"⚠️ This action requires approval before it runs.\n\n"
                    f"**Tool:** `{_tool_name}`\n"
                    f"**Command:** `{_command}`\n"
                    f"**Risk:** {sec.risk_level}\n\n"
                    f"Approval ID: `{aid}`"
                )
            else:
                result = await tool_brain.execute(
                    tool_name       = _tool_name,
                    command         = _command,
                    session_id      = session_id,
                    auto_approve_safe = True,
                )
                if result.status == "success":
                    reply = f"```\n{result.output or '(no output)'}\n```"
                else:
                    reply = f"❌ Error (exit {result.exit_code}):\n```\n{result.error or result.output}\n```"
        except Exception as exc:
            reply = f"Tool brain error: {exc}"

    else:
        # General chat / research / planning / file_analysis / web_search — Claude claude-sonnet-4-6
        try:
            # Engineering context covers file_analysis + app_builder + code_runner
            system_prefix = engineering_ctx.system_prefix if engineering_ctx and engineering_ctx.system_prefix else ""
            if not system_prefix and phase1_plan and phase1_plan.intent == "file_analysis":
                try:
                    from mini_assistant.scanner import get_context
                    ctx = get_context()
                    feat_names = [f["feature"] for f in ctx.to_dict().get("feature_map", [])]
                    warnings   = ctx.to_dict().get("warnings", [])[:3]
                    system_prefix = (
                        f"[PROJECT CONTEXT — {len(feat_names)} features mapped. "
                        f"Key warnings: {'; '.join(warnings) if warnings else 'none'}]\n\n"
                    )
                except Exception:
                    pass

            # GPT-5.4 enriches the system context for complex coding/builder requests
            _gpt_code_ctx = ""
            if ceo_posture and ceo_posture.priority == "quality":
                try:
                    from mini_assistant.phase2.prompt_enhancer import enhance_code_context
                    _gpt_code_ctx = await enhance_code_context(
                        effective_msg, execution_intent or "chat"
                    ) or ""
                except Exception:
                    _gpt_code_ctx = ""

            # Build system prompt
            _sys_prompt = _MINI_SYSTEM_PROMPT
            if _LYRICS_INTENT.search(effective_msg):
                _sys_prompt = _MINI_SYSTEM_PROMPT + "\n\n" + _LYRICS_SYSTEM_PROMPT
            if _gpt_code_ctx:
                _sys_prompt = _sys_prompt + "\n\n[TASK CONTEXT — GPT-5.4 ANALYSIS]\n" + _gpt_code_ctx

            # Build conversation history for Claude (no system role in messages list)
            claude_msgs: list[dict] = []
            if req.history:
                for h in req.history[-10:]:
                    if h.role in ("user", "assistant") and h.content:
                        claude_msgs.append({"role": h.role, "content": h.content})

            # Real-time weather injection
            rt_context = ""
            weather_loc = _detect_weather_location(effective_msg)
            if weather_loc:
                weather_data = await _fetch_weather(weather_loc)
                if weather_data:
                    rt_context = (
                        f"{weather_data}\n"
                        "Use ONLY the live data above to answer the weather question accurately. "
                        "Do not say you lack internet access.\n\n"
                    )
                else:
                    rt_context = (
                        f"[NO REAL-TIME DATA] Weather fetch failed for '{weather_loc}'. "
                        "Tell the user you couldn't retrieve the weather right now — do NOT guess or make up any values.\n\n"
                    )

            # Prepend Phase 9 self-improvement context
            phase9_prefix = phase9_ctx.prefix if phase9_ctx else ""
            combined_prefix = rt_context + phase9_prefix + (system_prefix or "")
            user_content = (combined_prefix + effective_msg) if combined_prefix else effective_msg
            claude_msgs.append({"role": "user", "content": user_content})

            import anthropic as _am
            _ac = _am.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
            logger.info("[MODEL ROUTER] chat → Claude claude-sonnet-4-6")
            _resp = await _ac.messages.create(
                model      = "claude-sonnet-4-6",
                max_tokens = 4096,
                system     = _sys_prompt,
                messages   = claude_msgs,
            )
            reply = _resp.content[0].text
        except Exception as exc:
            reply = _friendly_error(exc)

    # ── Phase 2 QA Feedback Loop (runs before Critic when quality mode) ─────────
    # Only active when ENABLE_QA_LOOP=true + CEO priority==quality + code intent.
    # Fails silently — the original reply is always preserved on any error.
    if reply and phase1_plan is not None and ceo_posture is not None:
        try:
            from mini_assistant.phase2.qa import should_run_qa, review as qa_review
            if should_run_qa(execution_intent or "chat", ceo_posture.priority):
                _qa = await qa_review(request=effective_msg, output=reply)
                logger.info(
                    "QA loop | approved=%s issues=%d qa_ms=%.1f",
                    _qa["approved"], len(_qa["issues"]), _qa["qa_ms"],
                )
                if not _qa["approved"] and _qa["improved_output"]:
                    logger.info("QA loop | applying improved output (%d chars)", len(_qa["improved_output"]))
                    reply = _qa["improved_output"]
        except Exception as _qa_err:
            logger.warning("QA loop failed (non-fatal): %s", _qa_err)

    # ── Phase 1+2 Step 5: Critic + Composer ────────────────────────────────────
    if phase1_plan is not None:
        try:
            from mini_assistant.phase1.critic import critique
            from mini_assistant.phase1.composer import compose as phase1_compose
            critic_result = critique(reply, phase1_plan)

            # ── Phase 3 Step 2: Reflection (after Critic, before Composer) ─────
            try:
                from mini_assistant.phase3.reflection_layer import reflect
                reflection_record = reflect(
                    message     = effective_msg,
                    plan        = phase1_plan,
                    critic      = critic_result,
                    skill_match = skill_match,
                    reply       = reply,
                )
                logger.debug(
                    "Reflection logged=%s lesson=%s ms=%.1f",
                    reflection_record.logged,
                    reflection_record.lesson[:60],
                    reflection_record.reflection_ms,
                )
            except Exception as _ref_err:
                logger.warning("Reflection failed (non-fatal): %s", _ref_err)
                reflection_record = None

            # ── Phase 9 Step 2: Feed reflection lesson into LearningBrain ─────
            try:
                from mini_assistant.phase9.learning_brain import get_learning_brain
                if reflection_record and reflection_record.lesson:
                    get_learning_brain().record_reflection(
                        lesson       = reflection_record.lesson,
                        intent       = phase1_plan.intent if phase1_plan else "chat",
                        quality_score= getattr(reflection_record, "quality_score", 0.7),
                        success      = True,
                        source       = "reflection",
                    )
            except Exception as _lb_err:
                logger.debug("LearningBrain feed failed (non-fatal): %s", _lb_err)

            # ── Phase 6 Step 2: Session Memory extraction (after reply known) ───
            try:
                from mini_assistant.phase6.session_memory import get_memory
                memory_facts_stored = get_memory().extract_and_store(
                    message    = effective_msg,
                    reply      = reply,
                    session_id = session_id,
                    intent     = phase1_plan.intent if phase1_plan else "normal_chat",
                )
                if memory_facts_stored:
                    logger.info(
                        "SessionMemory: stored %d facts for session %s",
                        len(memory_facts_stored), session_id[:8],
                    )
            except Exception as _mem_err:
                logger.debug("SessionMemory extraction failed (non-fatal): %s", _mem_err)
                memory_facts_stored = []

            # ── Phase 4 Step 2: Mission Manager (after Reflection) ─────────────
            try:
                from mini_assistant.phase4.mission_manager import get_mission_manager
                mission_result = get_mission_manager().process(
                    message    = effective_msg,
                    plan       = phase1_plan,
                    critic     = critic_result,
                    session_id = session_id,
                )
                if mission_result.action != "none":
                    logger.info(
                        "MissionManager → action=%s mission=%s continuation=%s",
                        mission_result.action,
                        mission_result.mission.id[:8] if mission_result.mission else "—",
                        mission_result.is_continuation,
                    )
            except Exception as _mis_err:
                logger.warning("MissionManager failed (non-fatal): %s", _mis_err)
                mission_result = None

            response = phase1_compose(
                reply        = reply,
                plan         = phase1_plan,
                critic       = critic_result,
                session_id   = session_id,
                route_result = route_result,
            )
            # Enrich with Phase 2+3 executive metadata
            if ceo_posture:
                response["ceo"] = ceo_posture.to_dict()
            if manager_packet:
                response["manager"] = manager_packet.to_dict()
            if supervisor_result:
                response["supervisor"] = supervisor_result.to_dict()
            if skill_match:
                response["skill"] = skill_match.to_dict()
            if reflection_record:
                response["reflection"] = reflection_record.to_dict()
            if parallel_result:
                response["parallel"] = parallel_result.to_dict()
            if mission_result and mission_result.action != "none":
                response["mission"] = mission_result.to_dict()
            if engineering_ctx and engineering_ctx.sources_used:
                response["engineering"] = engineering_ctx.to_dict()
            if memory_facts_stored:
                response["memory_stored"] = [
                    {"key": f.key, "value": f.value, "confidence": f.confidence}
                    for f in memory_facts_stored
                ]
            if phase9_ctx and phase9_ctx.sources:
                response["self_improvement"] = phase9_ctx.to_dict()
            response["model_used"] = _active_model
            return response
        except Exception as _c_err:
            logger.warning("Phase 1+2 Critic/Composer failed (%s) — returning raw reply.", _c_err)

    # Legacy fallback response shape (Phase 1 unavailable)
    return {
        "reply":        reply,
        "intent":       execution_intent,
        "route_result": route_result,
        "session_id":   session_id,
    }


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """
    Streaming chat endpoint — returns SSE tokens for general chat.
    Each event: data: {"t": "<token>"}
    Final event: data: {"done": true, "meta": {...}}
    Image-gen intents signal: data: {"done": true, "meta": {"type": "image_redirect"}}
    """
    import json as _json

    # Images never deduct credits — only deduct for text chat requests.
    if not getattr(req, "image_base64", None):
        try:
            from mini_credits import check_and_deduct as _deduct
            _ok, _remaining = await _deduct(request.headers.get("authorization"), cost=1)
            if not _ok:
                raise HTTPException(status_code=402, detail="out_of_credits")
        except HTTPException:
            raise
        except Exception:
            pass

    session_id = req.session_id or str(uuid.uuid4())

    from ..utils.prompt_safety import validate as ps_validate
    is_valid, clean_message, safety_error = ps_validate(req.message)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Message rejected: {safety_error}")

    async def generate():
        # Yield an SSE keepalive immediately so Cloudflare doesn't timeout
        # the frontend connection while we wait for routing + Ollama.
        yield ": keepalive\n\n"

        effective_msg = clean_message
        phase1_plan = None
        execution_intent = "chat"

        # ── Persistent conversation store — load full server-side history ─────
        # This is the source of truth for all history checks below.
        # Falls back gracefully to req.history when the session file is empty/new.
        _stored_conv = load_conversation(session_id)

        def _history_source():
            """Return a list of objects with .role / .content from stored conv or req.history."""
            if _stored_conv:
                class _Msg:
                    __slots__ = ("role", "content")
                    def __init__(self, d):
                        self.role = d.get("role", "")
                        self.content = d.get("content", "")
                return [_Msg(m) for m in _stored_conv]
            return req.history or []

        _effective_history = _history_source()

        # ── Explicit chat_mode override (bypasses all intent detection) ──────
        # 'image' → force image generation (redirect to non-streaming endpoint)
        # 'build' → force app_builder (skip Q&A, build immediately)
        # 'chat'  → force plain chat/search, never image-gen or build
        if req.chat_mode == "image":
            yield f"data: {_json.dumps({'done': True, 'meta': {'type': 'image_redirect'}})}\n\n"
            return
        if req.chat_mode == "build":
            execution_intent = "app_builder"
            phase1_plan = None  # skip routing entirely
        if req.chat_mode == "chat":
            execution_intent = "chat"
            phase1_plan = None  # skip all intent routing

        # ── Phase 1 intent routing (fast regex, then LLM fallback) ──────────
        # Skip entirely when chat_mode forces the intent already
        if not req.chat_mode:
            try:
                from mini_assistant.phase1.command_parser import parse as cmd_parse
                from mini_assistant.phase1.intent_planner import (
                    plan as make_plan,
                    classify_intent_with_llm,
                    INTENT_TO_EXECUTION,
                )
                parsed_cmd = cmd_parse(clean_message)
                effective_msg = parsed_cmd.args if parsed_cmd.is_slash else clean_message
                phase1_plan = make_plan(
                    message=effective_msg,
                    parsed_command=parsed_cmd,
                    history=req.history or [],
                )
                execution_intent = phase1_plan.execution_intent or "chat"

                # LLM fallback: regex returned low-confidence normal_chat for a long
                # message — ask the model to classify properly
                if (
                    phase1_plan.intent == "normal_chat"
                    and phase1_plan.confidence <= 0.72
                    and len(effective_msg.strip()) > 60
                    and not (parsed_cmd and parsed_cmd.is_slash)
                ):
                    llm_intent = await classify_intent_with_llm(effective_msg)
                    if llm_intent != "normal_chat":
                        execution_intent = INTENT_TO_EXECUTION.get(llm_intent, "chat")
                        logger.info(
                            "Phase1 LLM override: %s → %s (exec: %s)",
                            phase1_plan.intent, llm_intent, execution_intent,
                        )
            except Exception as _e:
                logger.warning("Phase1 failed in stream endpoint: %s", _e)

        # Image intents can't stream meaningfully — signal redirect to non-streaming endpoint
        import re as _re_stream
        _EDIT_KW_STREAM = _re_stream.compile(
            r"\b(change|edit|modify|fix|adjust|recolor|replace|remove|enhance|improve|"
            r"turn\s+(?:him|her|it|them|this|that)\b|make\s+(?:him|her|it|them|this|that)\b|"
            r"darker|brighter|lighter|sharper|blurrier|warmer|cooler|saturate|desaturate|"
            r"add\s+(?!a\s+new|another)|give\s+(?:him|her|it|them)\b|"
            r"angrier|fiercer|stronger|glowing|dramatic|intense|powerful)\b",
            _re_stream.I,
        )
        _REF_GEN_KW_STREAM = _re_stream.compile(
            r"\b(draw|generate|create|recreate|render|design|reimagine|reinvent|"
            r"in the style of|inspired by|wearing|holding|show|put|place)\b",
            _re_stream.I,
        )
        _has_attached = bool(req.image_base64)
        if _has_attached:
            _msg_str = effective_msg or ""
            _edit_match    = bool(_EDIT_KW_STREAM.search(_msg_str))
            _ref_gen_match = bool(_REF_GEN_KW_STREAM.search(_msg_str))
            _short_prompt  = len(_msg_str.strip()) < 80
            # Ref-gen keywords (draw/create/generate/wearing…) → image_reference_generate
            if _ref_gen_match:
                execution_intent = "image_reference_generate"
            # Edit keywords OR short prompt with image → preserve identity, apply edit
            elif _edit_match or _short_prompt:
                execution_intent = "image_edit"
        # If we're in the middle of a build Q&A conversation, never image-redirect.
        # The user's answer to builder questions can look like an image prompt
        # ("modern style", "forest", "cartoon") — we must keep it in build flow.
        _build_convo_markers = ("ready to build", "build once", "```html", "what visual style",
                                "visual style", "app builder", "platform —", "obstacles —",
                                "difficulty —", "plain html", "react?")
        _in_build_conversation = any(
            h.role == "assistant" and any(kw in (h.content or "").lower() for kw in _build_convo_markers)
            for h in _effective_history
        )
        if _in_build_conversation:
            execution_intent = "app_builder"
        elif execution_intent in ("image_generation", "image_edit", "image_reference_generate") and req.chat_mode != "chat":
            yield f"data: {_json.dumps({'done': True, 'meta': {'type': 'image_redirect'}})}\n\n"
            return
        # In chat mode, fall back to plain chat if image/build intent was detected
        if req.chat_mode == "chat" and execution_intent in ("image_generation", "image_edit", "image_reference_generate", "app_builder"):
            execution_intent = "chat"

        # ── Model selection — always Claude claude-sonnet-4-6 ─────────────────
        _is_build_intent = execution_intent == "app_builder"

        # Vibe Code mode OR explicit build mode — skip all Q&A, build immediately
        # (never override chat mode with build intent)
        if (req.vibe_mode or req.chat_mode == "build") and not _is_build_intent and req.chat_mode != "chat":
            _is_build_intent = True
            execution_intent = "app_builder"  # so done-event intent is correct → auto-opens preview

        # Also detect build intent from history — follow-up messages in a build
        # conversation are often classified as "chat" by the router (e.g. "make it
        # a video uploader"), but they still need the coder model + build prompt.
        # Do NOT override chat or image mode — those explicitly opt out of building.
        if not _is_build_intent and _effective_history and req.chat_mode not in ("chat", "image"):
            _hist_contents = " ".join(h.content or "" for h in _effective_history)
            # If any previous assistant turn contains a code fence or raw HTML, we're in a build session
            _assistant_has_code = any(
                h.role == "assistant" and (
                    "```" in (h.content or "") or
                    "<!DOCTYPE" in (h.content or "") or
                    "<!doctype" in (h.content or "")
                )
                for h in _effective_history
            )
            # Or if the first user message was a build request
            _BUILD_KW = _re.compile(
                r"/build|build me|build it|create (a|an|the) (app|website|page|ui|component|dashboard)|"
                r"make (a|an) (web|html|react)|make it|do it|generate (a|an) (app|website|page)|"
                r"update it|add (a|an|the) (button|section|feature|page|component|form)|"
                r"can you (build|make|create|add|update)",
                _re.I,
            )
            _first_user = next((h for h in _effective_history if h.role == "user"), None)
            if _assistant_has_code or (_first_user and _BUILD_KW.search(_first_user.content or "")):
                _is_build_intent = True

        # Detect if the user pasted code (``` in their message or coding intent from router)
        _has_code_in_msg = "```" in effective_msg or execution_intent == "coding"
        # Also check if their message looks like a code question even without fences
        # Only treat as code if there are very explicit code signals — NOT broad phrases
        # that would match normal conversation ("how does", "why does", etc.)
        _CODE_ERRORS = _re.compile(
            r"\b(TypeError|SyntaxError|ImportError|NameError|AttributeError|KeyError|"
            r"IndexError|ValueError|RuntimeError|ModuleNotFoundError|stacktrace|traceback)\b",
            _re.I,
        )
        _is_code_intent = _has_code_in_msg or execution_intent == "coding" or bool(_CODE_ERRORS.search(effective_msg))

        # All tasks use Claude claude-sonnet-4-6 — no local models
        _active_model = "claude-sonnet-4-6"
        logger.info("[MODEL ROUTER] stream/%s → Claude %s", execution_intent, _active_model)

        # ── Real-time weather injection ───────────────────────────────────────
        rt_context = ""
        weather_loc = _detect_weather_location(effective_msg)
        if weather_loc:
            weather_data = await _fetch_weather(weather_loc)
            if weather_data:
                rt_context = (
                    f"{weather_data}\n"
                    "Use ONLY the live data above to answer the weather question accurately. "
                    "Do not say you lack internet access.\n\n"
                )
            else:
                rt_context = (
                    f"[NO REAL-TIME DATA] Weather fetch failed for '{weather_loc}'. "
                    "Tell the user you couldn't retrieve the weather right now — do NOT guess or make up any values.\n\n"
                )

        # ── Build message list ────────────────────────────────────────────────
        # Determine whether history already has a build-turn so we know where we are in the cycle.
        _build_history_turns = sum(1 for h in _effective_history if h.role == "assistant") if _is_build_intent else 0

        _has_images = bool(req.image_base64 or req.images_base64)
        # True if pipeline has already generated HTML code in a previous turn.
        # Match both fenced (```html) and raw (<!DOCTYPE html) output so PATCH MODE
        # triggers even when Claude previously skipped the fence.
        _has_prior_code = any(
            h.role == "assistant" and (
                "```html" in (h.content or "") or
                "<!DOCTYPE" in (h.content or "") or
                "<!doctype" in (h.content or "")
            )
            for h in _effective_history
        )
        if _is_build_intent:
            if not _has_images and not _has_prior_code and _build_history_turns == 0 and not req.vibe_mode:
                # First contact, no image, no prior code, not vibe mode — ask 3 questions then stop
                _build_mode_addendum = (
                    "\n\n## APP BUILDER — TURN 1\n"
                    "This is the FIRST message about building. Ask exactly 3 short, focused questions as a numbered list.\n"
                    "Good questions: visual style, must-have features, HTML vs React.\n"
                    "Bad questions: file sizes, fonts, pixel dimensions — you decide those.\n"
                    "End with: 'Ready to build once you answer!'\n"
                    "Do NOT produce any code yet.\n"
                )
            elif _has_images and not _has_prior_code:
                # Image provided — build immediately from the visual reference, no questions
                _build_mode_addendum = (
                    _APP_BUILDER_CODING_STANDARDS +
                    "\n\n## APP BUILDER — IMAGE-TO-CODE (MANDATORY IMMEDIATE BUILD)\n"
                    "The user has provided an image of the UI they want built. DO NOT ask any questions.\n"
                    "Your ONLY job is to replicate what you see in the image as a working app:\n"
                    "  1. Analyze the image — identify layout, colors, components, and interactions.\n"
                    "  2. Output the FULL working app as a single ```html code block (HTML + CSS + JS all inline).\n"
                    "  3. Match the visual design from the image as closely as possible.\n"
                    "  4. Apply the CODING STANDARDS above — CSS variables, real JS state, all interactions working.\n"
                    "  5. After the closing ```, write: 'Here\\'s what I built from your image! What would you like to change?\\n1. ...\\n2. ...\\n3. ...'\n\n"
                    "RULES:\n"
                    "- START your response with ```html — not with any words or questions.\n"
                    "- Every button, input, and control must be fully functional — no stubs, no TODOs.\n"
                    "- Make all design decisions yourself based on what you see in the image.\n"
                    "- NEVER ask clarifying questions when an image is provided. Just build it.\n"
                )
            elif not _has_prior_code:
                # User answered questions (no code yet) — now BUILD
                _build_mode_addendum = (
                    _APP_BUILDER_CODING_STANDARDS +
                    "\n\n## APP BUILDER — BUILD TURN\n"
                    "Structure your response in EXACTLY this order:\n\n"
                    "PART 1 — PLAN (output this first, before any code):\n"
                    "\U0001f4cb **Build Plan**\n"
                    "- **What:** [one sentence — what the app does]\n"
                    "- **Features:** [comma-separated list of key features you will build]\n"
                    "- **Style:** [visual style — e.g. dark neon, glassmorphism, retro arcade]\n"
                    "- **Tech:** Single-file HTML + embedded CSS + JS\n\n"
                    "PART 2 — THE CODE (immediately after the plan, no gap):\n"
                    "Output the FULL working app as a single ```html code block.\n"
                    "Apply the CODING STANDARDS above — CSS variables, real JS state, all interactions working.\n\n"
                    "PART 3 — SUMMARY (immediately after the closing ```):\n"
                    "\u2705 **Build complete!**\n\n"
                    "**What I built:** [2-3 sentence description of what was created]\n\n"
                    "**What you can do next:**\n"
                    "1. [specific, compelling feature to add]\n"
                    "2. [specific visual or UX improvement]\n"
                    "3. [specific gameplay/interaction enhancement]\n\n"
                    "\U0001f4a1 **Enhancement idea:** [one high-impact upgrade that would make this significantly better — be specific and enthusiastic]\n\n"
                    "RULES:\n"
                    "- Output PLAN → CODE → SUMMARY in that exact order — no exceptions.\n"
                    "- Every button, input, and control must be fully functional JavaScript.\n"
                    "- Include ALL CSS in <style> tags, ALL JS in <script> tags.\n"
                    "- Make all design decisions yourself — do NOT ask more questions.\n"
                )
            else:
                # User responded to follow-ups — update code then suggest next steps
                _build_mode_addendum = (
                    _APP_BUILDER_CODING_STANDARDS +
                    "\n\n## APP BUILDER — UPDATE TURN\n"
                    "Structure your response in EXACTLY this order:\n\n"
                    "PART 1 — The COMPLETE updated code (output first, no preamble):\n"
                    "```html block with the full updated app.\n\n"
                    "PART 2 — SUMMARY (immediately after the closing ```):\n"
                    "\u2705 **Updated!**\n\n"
                    "**What changed:** [1-2 sentences on what was added/fixed]\n\n"
                    "**What you can do next:**\n"
                    "1. [specific next feature]\n"
                    "2. [specific improvement]\n"
                    "3. [specific enhancement]\n\n"
                    "\U0001f4a1 **Enhancement idea:** [one compelling upgrade idea]\n\n"
                    "RULES:\n"
                    "- Start with ```html — never with words.\n"
                    "- Always output the ENTIRE file — never partial snippets.\n"
                    "- Every button and control must remain fully functional.\n"
                )
            _sys_prompt_stream = _MINI_SYSTEM_PROMPT + _build_mode_addendum
        elif _LYRICS_INTENT.search(effective_msg):
            _sys_prompt_stream = _MINI_SYSTEM_PROMPT + "\n\n" + _LYRICS_SYSTEM_PROMPT
        elif _is_code_intent:
            _sys_prompt_stream = _MINI_SYSTEM_PROMPT + _CODE_ASSISTANT_PROMPT
        else:
            _sys_prompt_stream = _MINI_SYSTEM_PROMPT
        history_msgs: list[dict] = [{"role": "system", "content": _sys_prompt_stream}]
        # Use stored conversation as source of truth; fall back to req.history when empty.
        _history_to_build = (
            trim_html_in_old_messages(_stored_conv) if _stored_conv
            else (req.history or [])
        )
        for h in _history_to_build:
            _hr = h.get("role") if isinstance(h, dict) else h.role
            _hc = h.get("content") if isinstance(h, dict) else h.content
            if _hr and _hc:
                history_msgs.append({"role": _hr, "content": _hc})
        user_content = (rt_context + effective_msg) if rt_context else effective_msg

        # ── Web search injection — fetch live results when intent is web_search ─
        if phase1_plan and phase1_plan.intent == "web_search" and not req.image_base64 and not req.images_base64:
            try:
                from mini_assistant.tools.docs_retriever import doc_aware_search, is_tech_query
                _is_tech = is_tech_query(effective_msg)
                if _is_tech:
                    # Tech query: local index → live official docs → web fallback
                    _doc_result = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: doc_aware_search(effective_msg, max_results=5)
                    )
                    _context = _doc_result.get("context_snippet", "")
                    _source  = _doc_result.get("source", "web_fallback")
                    _citations = _doc_result.get("citations", [])
                    if _context:
                        _cite_lines = "\n".join(
                            f"  [{i+1}] {c.get('title','')} — {c.get('url','')}"
                            for i, c in enumerate(_citations[:3]) if c.get("url")
                        )
                        _source_label = {
                            "local_index": "[LOCAL DOCS INDEX]",
                            "live_docs":   "[OFFICIAL DOCS]",
                            "web_fallback":"[WEB SEARCH]",
                        }.get(_source, "[WEB SEARCH]")
                        user_content = (
                            f"{_source_label} for: {effective_msg}\n\n"
                            f"{_context}\n\n"
                            + (f"Sources:\n{_cite_lines}\n\n" if _cite_lines else "")
                            + "Use ONLY the documentation above to answer accurately. "
                            "Cite the source when helpful. Do not say you lack internet access.\n\n"
                            f"{effective_msg}"
                        )
                else:
                    # Non-tech query: plain web search
                    from mini_assistant.tools.search import web_search as _plain_search
                    _ws_results = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: _plain_search(effective_msg, max_results=5)
                    )
                    if _ws_results:
                        _snippets = "\n".join(
                            f"[{i+1}] {r.get('title', '')}\n{r.get('body', '')}"
                            for i, r in enumerate(_ws_results[:5])
                        )
                        user_content = (
                            f"[WEB SEARCH RESULTS for: {effective_msg}]\n{_snippets}\n\n"
                            "Use the search results above to answer the user's question accurately. "
                            "Do not say you lack internet access.\n\n"
                            f"{effective_msg}"
                        )
            except Exception as _ws_err:
                logger.warning("Web search failed (non-fatal): %s", _ws_err)

        # Collect all attached images (multi-image support)
        # Compress each image to reduce payload size through Cloudflare tunnel.
        all_images = list(req.images_base64 or [])
        if req.image_base64 and req.image_base64 not in all_images:
            all_images.insert(0, req.image_base64)
        all_images = [_compress_image_b64(b64) for b64 in all_images]
        user_msg: dict = {"role": "user", "content": user_content}
        if all_images and not (_is_build_intent and not _has_prior_code):
            # Normal image analysis (not the image-to-code pipeline)
            user_msg["images"] = all_images
        history_msgs.append(user_msg)

        # ── Image-to-Code pipeline (Vision → Builder → Reviewer loop) ─────────
        # Trigger when: build intent + images attached + no HTML already generated.
        # This covers first-time image builds AND retries mid-conversation.

        # Extra heuristic: images + build/style keywords upgrade intent even if phase1
        # classified as image_analysis (e.g. user used /analyze but means "build like this").
        _IMAGE_BUILD_KW = _re.compile(
            r"\b(build|create|recreate|replicate|clone|design)\b"
            r"|same.{0,15}(style|theme|color|look|design)"
            r"|(style|theme|color|look|design).{0,15}(for|my)\b"
            r"|i.{0,10}want.{0,10}(this|same)",
            _re.I,
        )
        if all_images and not _is_build_intent and not _has_prior_code and _IMAGE_BUILD_KW.search(effective_msg):
            _is_build_intent = True
            execution_intent = "app_builder"

        _api_key_claude = os.environ.get("ANTHROPIC_API_KEY", "")
        _use_claude     = True  # Always use Claude — no local models
        reply_text      = ""

        # ── Save user message to persistent store ─────────────────────────────
        try:
            save_message(session_id, "user", effective_msg)
        except Exception as _sm_err:
            logger.warning("conversation_store: save_message(user) failed — %s", _sm_err)

        if _is_build_intent and all_images and not _has_prior_code:
            from .pipeline import image_to_code_pipeline
            async for _sse in image_to_code_pipeline(
                images=all_images,
                user_request=effective_msg,
                session_id=session_id,
            ):
                yield _sse
                # Accumulate reply text for session memory
                if _sse.startswith("data: "):
                    try:
                        _d = _json.loads(_sse[6:].split("\n")[0])
                        if "t" in _d:
                            reply_text += _d["t"]
                    except Exception:
                        pass

        elif _use_claude and (_is_build_intent or all_images or _is_code_intent):
            # ── Claude-powered stream ─────────────────────────────────────────
            # Routes: text builds, image analysis, code debugging → Claude API.
            # Local models stay for simple chat (cost control).

            # Convert history to Claude message format — send everything, full content.
            # Quality over token cost: Claude needs the full conversation + full code
            # to make accurate decisions. The 200k context window and extended thinking
            # budget handle it. Never truncate.
            _c_msgs = []
            _raw_history = [m for m in history_msgs if m.get("role") in ("user", "assistant") and m.get("content")]
            for _hm in _raw_history:
                _hr, _hc = _hm.get("role"), _hm.get("content", "")
                if _hc.strip():
                    _c_msgs.append({"role": _hr, "content": _hc})

            # Inject images into last user message as multipart content
            if all_images and _c_msgs and _c_msgs[-1]["role"] == "user":
                _img_parts = []
                for _b64 in all_images[:4]:
                    _mt = "image/png" if _b64.startswith("iVBOR") else "image/jpeg"
                    _img_parts.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": _mt, "data": _b64},
                    })
                _img_parts.append({"type": "text", "text": _c_msgs[-1]["content"]})
                _c_msgs[-1]["content"] = _img_parts

            # Pick system prompt based on what Claude is doing
            # ── Explicit rebuild requested (user said "rebuild", "start over", etc.) ──
            _REBUILD_KW = _re.compile(
                r"\b(rebuild|start (over|fresh|from scratch)|redo (it|everything|the (whole|entire))|"
                r"rewrite (it|everything|the (whole|entire))|make a (brand )?new (version|one)|"
                r"scrap (it|this)|throw (it|this) away|start (it )?again from)\b",
                _re.I,
            )
            _is_explicit_rebuild = bool(_REBUILD_KW.search(effective_msg))

            if _is_build_intent:
                if _has_prior_code and not _is_explicit_rebuild and not all_images:
                    # ── PATCH MODE — surgical fix, never rebuild ──────────────────
                    _c_sys = _kb_patch()
                elif all_images or req.vibe_mode or _is_explicit_rebuild:
                    # ── FRESH BUILD — image ref, vibe mode, or explicit rebuild ───
                    _c_sys = _kb_fresh_build()
                elif _build_history_turns == 0:
                    # ── REQUIREMENTS — first message, gather info before building ─
                    _c_sys = _kb_requirements()
                else:
                    # ── BUILD NOW — user answered requirements, build immediately ─
                    _c_sys = _kb_fresh_build()
            elif all_images:
                _c_sys = (
                    "You are a helpful AI assistant with strong vision capabilities. "
                    "Analyze images accurately. Describe colors precisely (use hex values when visible), "
                    "layout, text content, UI elements, and style. Be specific and technical."
                )
            else:  # code/fix intent
                _c_sys = (
                    "You are an expert software engineer and enthusiastic coding partner. "
                    "Read error messages carefully, identify root causes, and provide clear fixes. "
                    "After fixing: explain in plain English what was wrong and what you changed, "
                    "then end with 'Give it a try — does that fix it? 🎮' (adjust emoji to context). "
                    "Be warm and direct, like a senior dev pair-programming with a friend."
                )

            # ── Inject lesson memory + user prefs into build/patch prompts ───
            if _is_build_intent:
                if _LESSONS_LOADED:
                    _lessons_block = _lessons_for_prompt()
                    if _lessons_block:
                        _c_sys = _c_sys + _lessons_block
                if _USER_MEMORY_LOADED:
                    _prefs_block = _user_prefs_for_prompt()
                    if _prefs_block:
                        _c_sys = _c_sys + _prefs_block

            # ── Search Brain: scan all memory files for relevant context ─────────
            # Runs in parallel with prompt assembly (synchronous but <5ms on disk).
            # Fetches: user style prefs, session facts, bug patterns, past sessions.
            # Injects only what's relevant to this specific request — not everything.
            try:
                _search_block = _memory_search(effective_msg, session_id)
                if _search_block:
                    _c_sys = _c_sys + "\n\n" + _search_block
            except Exception as _sb_err:
                logger.debug("[SearchBrain] non-fatal: %s", _sb_err)

            # ── Patch mode: pin the CURRENT code + reinforce the patch rule ────────
            # Problem: _c_msgs only has the last 10 messages. If the HTML was built
            # more than 10 messages ago, Claude cannot see it and guesses from old context.
            # Fix: extract the latest HTML from the FULL req.history and inject it
            # explicitly right before the user's request so Claude always patches
            # the correct, up-to-date version.
            _is_patch_mode = (
                _is_build_intent
                and _has_prior_code
                and not _is_explicit_rebuild
                and not all_images
            )
            if _is_patch_mode and _c_msgs:
                # Extract latest HTML from full stored history (not the truncated 10-msg window)
                _latest_html = None
                for _ph in reversed(_effective_history):
                    if _ph.role == "assistant" and _ph.content:
                        _fence_m = _re.search(r'```html\s*\n([\s\S]+?)```', _ph.content)
                        if _fence_m:
                            _latest_html = _fence_m.group(1).strip()
                            break
                        _raw_m = _re.search(r'(<!DOCTYPE\s+html[\s\S]+)', _ph.content, _re.I)
                        if _raw_m:
                            _latest_html = _raw_m.group(1).strip()
                            break

                # Only inject if the code isn't already visible in the truncated context
                _code_visible = any(
                    "```html" in str(m.get("content", "")) or "<!DOCTYPE" in str(m.get("content", ""))
                    for m in _c_msgs
                )
                if _latest_html and not _code_visible:
                    # Pin current code immediately before the user's change request
                    _c_msgs.insert(-1, {
                        "role": "user",
                        "content": f"📌 CURRENT APP CODE — patch this exact version, nothing else:\n```html\n{_latest_html}\n```",
                    })
                    _c_msgs.insert(-1, {
                        "role": "assistant",
                        "content": "Current code loaded. I'll only change what you ask for.",
                    })

                _patch_stamp = (
                    "\U0001f6a8 PATCH MODE — CHANGE ONLY WHAT I ASKED FOR.\n"
                    "Do NOT touch anything else in the code. One change. That's it.\n\n"
                )
                last_msg = _c_msgs[-1]
                if isinstance(last_msg.get("content"), str):
                    _c_msgs[-1] = {**last_msg, "content": _patch_stamp + last_msg["content"]}
                elif isinstance(last_msg.get("content"), list):
                    for _part in last_msg["content"]:
                        if isinstance(_part, dict) and _part.get("type") == "text":
                            _part["text"] = _patch_stamp + _part["text"]
                            break

            try:
                import anthropic as _am_lib
                _ac = _am_lib.AsyncAnthropic(api_key=_api_key_claude)

                # ── Keep-alive pings while waiting for first token ────────────────
                # Railway drops SSE connections with no activity after ~30s.
                # Send invisible ping events every 8s until Claude starts streaming.
                _first_token_received = False

                async def _keepalive():
                    while not _first_token_received:
                        await asyncio.sleep(8)
                        if not _first_token_received:
                            yield f": ping\n\n"  # SSE comment — ignored by client, keeps TCP alive

                # Thinking budget scales with task complexity:
                # - Fresh builds: lighter budget (5k) — requirements already gathered,
                #   just build. Faster first token, still high quality.
                # - Patch/debug: full budget (16k) — needs deep reasoning to find
                #   root cause without breaking anything else.
                _is_patch_or_debug = _has_prior_code or _is_code_intent
                _think_budget = 16000 if _is_patch_or_debug else 5000
                _max_out = 24000 if _is_patch_or_debug else 14000

                async with _ac.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=_max_out,
                    thinking={"type": "enabled", "budget_tokens": _think_budget},
                    system=_c_sys,
                    messages=_c_msgs,
                    extra_headers={"anthropic-beta": "interleaved-thinking-2025-05-14"},
                ) as _cs:
                    _ping_task = asyncio.create_task(asyncio.sleep(0))  # dummy
                    _last_ping = asyncio.get_event_loop().time()
                    async for _ct in _cs.text_stream:
                        # Send a keep-alive ping if 8s have passed without a token
                        _now = asyncio.get_event_loop().time()
                        if _now - _last_ping > 8 and not _first_token_received:
                            yield f": ping\n\n"
                            _last_ping = _now
                        _first_token_received = True
                        reply_text += _ct
                        yield f"data: {_json.dumps({'t': _ct})}\n\n"
            except Exception as _ce:
                logger.warning("Claude stream failed: %s", _ce)
                _err_msg = f"⚠️ Claude hit an issue: {_ce}. Please try again.\n\n"
                yield f"data: {_json.dumps({'t': _err_msg})}\n\n"

            # ── Haiku Self-Review Quality Gate (fresh builds only) ────────────
            # Runs after builder streams, before done event. Catches bugs the
            # builder missed. Only on fresh builds — not patches, not vibe mode.
            _is_fresh_build_mode = (
                _is_build_intent
                and not _has_prior_code
                and not _is_explicit_rebuild
                and not getattr(req, 'vibe_mode', False)
                and _build_history_turns > 0   # user already answered requirements
            )
            if _is_fresh_build_mode and reply_text:
                # Extract HTML from builder's response
                _rev_fence = _re.search(r"```(?:html)?\s*\n([\s\S]+?)```", reply_text)
                _rev_raw   = _re.search(r"<!DOCTYPE\s+html", reply_text, _re.I)
                _rev_html  = None
                if _rev_fence:
                    _rev_html = _rev_fence.group(1).strip()
                elif _rev_raw:
                    _rev_html = reply_text[_rev_raw.start():].strip()

                if _rev_html:
                    _sr_scanning = _json.dumps({'t': '\n\n---\n\U0001f50d **Self-Review** scanning...\n\n'})
                    yield f"data: {_sr_scanning}\n\n"
                    try:
                        import anthropic as _rev_am
                        _rev_client = _rev_am.AsyncAnthropic(api_key=_api_key_claude)

                        # Non-streaming Haiku review — raised to 1024 tokens for thorough checks
                        _rev_content = "[USER REQUEST]\n" + effective_msg + "\n\n[GENERATED CODE]\n```html\n" + _rev_html + "\n```"
                        _rev_resp = await _rev_client.messages.create(
                            model="claude-haiku-4-5-20251001",
                            max_tokens=1024,
                            system=_kb_review() + """

## EXTENDED REVIEW CHECKS — VERIFY ALL OF THESE

### GAME/INTERACTIVE APP CHECKS
- Does the game actually START when loaded or when a start button is pressed?
- Do ALL buttons have working event listeners (not just onclick="undefined")?
- Is the game loop running and updating the display every frame/tick?
- Do keyboard controls have `if (e.repeat) return;` as first line?
- Is score/lives/timer updating in the DOM (not just in a variable)?
- Does restart reset ALL state (not just some)?
- Are setInterval/setTimeout IDs stored so they can be cleared on restart?

### FATAL BUG CHECKS
- Any querySelector that could return null crashing on .addEventListener?
- Any variable used before it's declared?
- Any infinite loop (while(true) without a break path)?
- Canvas: is ctx = canvas.getContext('2d') actually called?

If ANY of these fail: FAIL with SCORE below 70.
If all pass: PASS.
""",
                            messages=[{"role": "user", "content": _rev_content}],
                        )
                        _rev_text = _rev_resp.content[0].text.strip()
                        _rev_pass = bool(_re.match(r'^PASS\b', _rev_text, _re.I))

                        if _rev_pass:
                            _sr_ok = _json.dumps({'t': '\u2705 Reviewed \u2014 all good!\n'})
                            yield f"data: {_sr_ok}\n\n"
                        else:
                            _rev_score_m = _re.search(r'SCORE:\s*(\d+)', _rev_text, _re.I)
                            _rev_score = int(_rev_score_m.group(1)) if _rev_score_m else 50
                            logger.info("[SelfReview] score=%s — running fix pass", _rev_score)
                            _sr_fixing = _json.dumps({'t': '\u26a0\ufe0f Score ' + str(_rev_score) + '/100 \u2014 fixing issues...\n\n'})
                            yield f"data: {_sr_fixing}\n\n"

                            # One streaming fix pass with Sonnet
                            _fix_sys = _kb_patch() + "\n\n## YOUR TASK: FIX ALL REVIEWER ISSUES\nFix every issue listed. Output the complete fixed HTML file starting with ```html."
                            _fix_user = (
                                "[REVIEWER ISSUES \u2014 FIX ALL]\n" + _rev_text + "\n\n"
                                "[CODE TO FIX]\n```html\n" + _rev_html + "\n```\n\n"
                                "Fix every issue. Output the complete corrected file."
                            )
                            try:
                                async with _rev_client.messages.stream(
                                    model="claude-sonnet-4-6",
                                    max_tokens=16000,
                                    thinking={"type": "enabled", "budget_tokens": 8000},
                                    system=_fix_sys,
                                    messages=[{"role": "user", "content": _fix_user}],
                                    extra_headers={"anthropic-beta": "interleaved-thinking-2025-05-14"},
                                ) as _fix_stream:
                                    _fix_last_ping = asyncio.get_event_loop().time()
                                    async for _fix_tok in _fix_stream.text_stream:
                                        _fix_now = asyncio.get_event_loop().time()
                                        if _fix_now - _fix_last_ping > 8:
                                            yield ": ping\n\n"
                                            _fix_last_ping = _fix_now
                                        reply_text += _fix_tok
                                        yield f"data: {_json.dumps({'t': _fix_tok})}\n\n"
                                _sr_done = _json.dumps({'t': '\n\n\u2705 Fixed and ready!\n'})
                                yield f"data: {_sr_done}\n\n"
                            except Exception as _fix_err:
                                logger.warning("[SelfReview] fix pass failed (non-fatal): %s", _fix_err)
                    except Exception as _rev_err:
                        logger.debug("[SelfReview] review failed (non-fatal): %s", _rev_err)

        else:
            # ── Claude stream — all chat/planning/research ─────────────────────
            # Build Claude-format messages (no system role in messages list)
            _c_msgs_plain = []
            for _hm in history_msgs:
                _hr, _hc = _hm.get("role"), _hm.get("content", "")
                if _hr in ("user", "assistant") and _hc:
                    _c_msgs_plain.append({"role": _hr, "content": _hc})

            logger.info("[MODEL ROUTER] chat/stream → Claude claude-sonnet-4-6")
            try:
                import anthropic as _am_plain
                _ac_plain = _am_plain.AsyncAnthropic(api_key=_api_key_claude)
                async with _ac_plain.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=8192,
                    system=_sys_prompt_stream,
                    messages=_c_msgs_plain,
                ) as _cs_plain:
                    _plain_last_ping = asyncio.get_event_loop().time()
                    async for _ct in _cs_plain.text_stream:
                        _plain_now = asyncio.get_event_loop().time()
                        if _plain_now - _plain_last_ping > 8:
                            yield f": ping\n\n"
                            _plain_last_ping = _plain_now
                        reply_text += _ct
                        yield f"data: {_json.dumps({'t': _ct})}\n\n"
            except Exception as _plain_err:
                err = _friendly_error(_plain_err)
                reply_text = err
                yield f"data: {_json.dumps({'t': err})}\n\n"

        # ── Save assistant reply to persistent store (non-fatal) ─────────────
        if reply_text:
            try:
                save_message(session_id, "assistant", reply_text)
            except Exception as _sm_err:
                logger.warning("conversation_store: save_message(assistant) failed — %s", _sm_err)

        # ── Observability: log this brain call (non-fatal) ────────────────────
        try:
            from mini_assistant.observability import BrainCall, record as _obs_record
            _obs_record(BrainCall(
                brain=execution_intent,
                model=_active_model,
                task=effective_msg[:80],
                session_id=session_id,
                tokens_out=len(reply_text.split()),
                outcome="success" if reply_text else "fail",
            ))
        except Exception:
            pass

        # ── Post-processing: session memory (non-fatal) ───────────────────────
        memory_facts_stored = []
        try:
            from mini_assistant.phase6.session_memory import get_memory
            memory_facts_stored = get_memory().extract_and_store(
                message=effective_msg,
                reply=reply_text,
                session_id=session_id,
                intent=phase1_plan.intent if phase1_plan else "normal_chat",
            )
        except Exception:
            pass

        # ── Post-processing: user preference learning (non-fatal) ─────────────
        if _USER_MEMORY_LOADED and reply_text:
            try:
                _update_user_prefs(
                    message=effective_msg,
                    reply=reply_text,
                    intent=execution_intent,
                    was_build=bool(_is_build_intent and not _has_prior_code),
                    was_fix=bool(_is_build_intent and _has_prior_code),
                )
            except Exception:
                pass

        # ── Guarantee Mini Assistant AI branding in every built app ──────────
        _BRAND_TAG = (
            '<div style="position:fixed;bottom:10px;right:12px;font-family:sans-serif;'
            'font-size:10px;color:rgba(255,255,255,0.25);letter-spacing:0.05em;'
            'pointer-events:none;z-index:9999;user-select:none;">'
            'Built with <span style="color:rgba(255,255,255,0.4);font-weight:600;">'
            'Mini Assistant AI</span></div>'
        )
        if _is_build_intent and reply_text and '</body>' in reply_text and _BRAND_TAG not in reply_text:
            reply_text = reply_text.replace('</body>', _BRAND_TAG + '\n</body>', 1)

        # ── Final done event with metadata ────────────────────────────────────
        meta = {
            "reply": reply_text,
            "session_id": session_id,
            "model_used": _active_model,
            "route_result": {"intent": execution_intent},
            "memory_stored": [
                {"key": f.key, "value": f.value, "confidence": f.confidence}
                for f in memory_facts_stored
            ] if memory_facts_stored else [],
        }
        yield f"data: {_json.dumps({'done': True, 'meta': meta})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            # Tell Chrome not to upgrade this SSE endpoint to QUIC/HTTP3.
            # Railway uses HTTP/3 by default which drops long-lived SSE connections
            # with ERR_QUIC_PROTOCOL_ERROR. Alt-Svc: clear disables QUIC for this origin.
            "Alt-Svc": "clear",
        },
    )


@app.post("/api/chat/compare")
async def chat_compare(req: ChatRequest, request: Request):
    """
    Run the same message through two models in parallel and return both replies.
    Used by the frontend every 10 responses to let the user pick their preferred model output.
    """
    try:
        from mini_credits import check_and_deduct as _deduct
        _ok, _remaining = await _deduct(request.headers.get("authorization"), action_type="chat_compare")
        if not _ok:
            raise HTTPException(status_code=402, detail="out_of_credits")
    except HTTPException:
        raise
    except Exception:
        pass

    import json as _json

    session_id = req.session_id or str(uuid.uuid4())

    from ..utils.prompt_safety import validate as ps_validate
    is_valid, clean_message, safety_error = ps_validate(req.message)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Message rejected: {safety_error}")

    from ..services.ollama_client import _model_name as _reg_model_name
    model_a = _reg_model_name("router")           # qwen3:14b  — primary
    model_b = _reg_model_name("router_fallback")  # qwen2.5:7b — faster fallback

    # ── Build shared message list ─────────────────────────────────────────────
    from mini_assistant.phase1.command_parser import parse as cmd_parse
    try:
        parsed_cmd = cmd_parse(clean_message)
        effective_msg = parsed_cmd.args if parsed_cmd.is_slash else clean_message
    except Exception:
        effective_msg = clean_message

    _sys_prompt = _MINI_SYSTEM_PROMPT
    if _LYRICS_INTENT.search(effective_msg):
        _sys_prompt = _MINI_SYSTEM_PROMPT + "\n\n" + _LYRICS_SYSTEM_PROMPT

    history_msgs: list[dict] = [{"role": "system", "content": _sys_prompt}]
    if req.history:
        for h in req.history[-10:]:
            history_msgs.append({"role": h.role, "content": h.content})
    history_msgs.append({"role": "user", "content": effective_msg})

    # ── Run both models concurrently ──────────────────────────────────────────
    async def _collect(model_name: str) -> str:
        reply = ""
        try:
            ollama_client = _get_ollama()
            async for token in ollama_client.run_chat_stream(
                model=model_name,
                messages=history_msgs,
                temperature=0.7,
            ):
                reply += token
        except Exception as exc:
            reply = f"[{model_name} error: {exc}]"
        return reply

    reply_a, reply_b = await asyncio.gather(_collect(model_a), _collect(model_b))

    return {
        "reply_a": reply_a,
        "model_a": model_a,
        "reply_b": reply_b,
        "model_b": model_b,
    }


@app.post("/api/chat/summarize")
async def chat_summarize(req: SummarizeRequest):
    """
    Summarize a list of messages into a concise bullet-point recap.
    Called automatically by the frontend when a conversation exceeds the compact threshold.
    Returns { summary: "..." }
    """
    if not req.messages:
        return {"summary": ""}

    from ..services.ollama_client import _model_name as _reg_model_name
    ollama_client = _get_ollama()

    history_text = "\n".join(
        f"{m.role.upper()}: {m.content}" for m in req.messages if m.content
    )
    prompt = (
        "Summarize the following conversation in 4-6 concise bullet points. "
        "Capture: key topics discussed, decisions made, code written, user preferences, and any important context. "
        "Preserve specific technical details like filenames, variable names, or URLs. "
        "Write the summary so another AI can pick up the conversation seamlessly.\n\n"
        f"{history_text}"
    )

    try:
        summary = await ollama_client.run_prompt(
            model=_reg_model_name("router"),
            prompt=prompt,
            temperature=0.3,
        )
    except Exception:
        # Non-fatal — return empty so the frontend silently skips compaction
        return {"summary": ""}

    return {"summary": summary}


@app.get("/api/models/status")
async def models_status():
    """Check which Ollama models are available locally."""
    ollama = _get_ollama()
    try:
        available = await ollama.list_models()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Ollama unreachable: {exc}")

    try:
        registry = _load_registry()
        required_models = {k: v["model"] for k, v in registry["ollama_models"].items()}
    except Exception:
        required_models = {}

    status = {}
    for role, model_name in required_models.items():
        normalised = {m.split(":")[0] for m in available} | set(available)
        status[role] = {
            "model": model_name,
            "available": model_name in normalised or model_name.split(":")[0] in normalised,
        }

    return {"available_models": available, "required_status": status}


@app.post("/api/models/pull")
async def pull_models(req: PullModelsRequest):
    """Pull missing Ollama models. This is a long-running operation."""
    ollama = _get_ollama()
    results = {}
    for model in req.models:
        try:
            await ollama.ensure_models([model])
            results[model] = "pulled"
        except Exception as exc:
            results[model] = f"error: {exc}"
    return {"results": results}


# ---------------------------------------------------------------------------
# Document text extraction
# ---------------------------------------------------------------------------

@app.post("/api/extract-text")
async def extract_text(file: UploadFile = File(...)):
    """
    Extract plain text from an uploaded document (PDF, TXT, MD, CSV).
    Returns { text, chars, truncated }.
    """
    MAX_CHARS = 50_000
    content = await file.read()
    filename = (file.filename or "").lower()

    if filename.endswith(".pdf"):
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=content, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
        except ImportError:
            try:
                from pdfminer.high_level import extract_text as _pdf_extract
                import io as _io
                text = _pdf_extract(_io.BytesIO(content))
            except ImportError:
                raise HTTPException(status_code=422, detail="PDF extraction unavailable — install PyMuPDF or pdfminer.six on the server.")
    else:
        text = content.decode("utf-8", errors="replace")

    truncated = len(text) > MAX_CHARS
    text = text[:MAX_CHARS]
    return {"text": text, "chars": len(text), "truncated": truncated}


# ---------------------------------------------------------------------------
# Code execution
# ---------------------------------------------------------------------------
from pydantic import BaseModel

class ExecuteRequest(BaseModel):
    code: str
    language: str = "python"


@app.post("/api/execute")
async def execute_code(req: ExecuteRequest):
    """
    Execute Python code in a sandboxed subprocess (10-second timeout).
    Returns { output, error, exit_code }.
    """
    import subprocess
    import sys as _sys

    if req.language.lower() not in ("python", "python3"):
        raise HTTPException(status_code=400, detail="Only Python execution is currently supported.")

    if not req.code.strip():
        return {"output": "", "error": "", "exit_code": 0}

    def _run():
        try:
            return subprocess.run(
                [_sys.executable, "-c", req.code],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            return None

    try:
        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _run),
            timeout=12.0,
        )
    except asyncio.TimeoutError:
        return {"output": "", "error": "Execution timed out (10s limit).", "exit_code": -1}

    if result is None:
        return {"output": "", "error": "Execution timed out (10s limit).", "exit_code": -1}

    return {
        "output": result.stdout,
        "error": result.stderr,
        "exit_code": result.returncode,
    }


# ---------------------------------------------------------------------------
# Follow-up suggestions
# ---------------------------------------------------------------------------

class SuggestionsRequest(BaseModel):
    message: str
    reply: str


# ---------------------------------------------------------------------------
# Auto-Fix endpoint — one pass of autonomous bug detection + patching
# ---------------------------------------------------------------------------
@app.post("/api/autofix/stream")
async def autofix_stream(req: AutoFixRequest, request: Request):
    """
    One autonomous bug-fix pass. Streams Claude's analysis + patched code.
    Done event includes { all_clear: bool }.
    Injects: lesson memory (past bug patterns) + DOM snapshot (live inspector).
    """
    import json as _json
    import re as _re

    _api_key_claude = os.environ.get("ANTHROPIC_API_KEY", "")
    if not _api_key_claude:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not set")

    # Build system prompt: base + lessons learned from past sessions
    _base_system = _kb_debug_agent()
    _lessons_block = _lessons_for_prompt()  # empty string if no lessons yet
    _autofix_system = _base_system + _lessons_block

    # Build user message: errors + DOM snapshot + code
    error_block = ""
    if req.errors:
        unique_errors = list(dict.fromkeys(req.errors))[:10]  # dedupe, cap at 10
        error_block = "\n\n## JavaScript Errors From Running App\n" + "\n".join(f"- {e}" for e in unique_errors)
    else:
        error_block = "\n\n## JavaScript Errors From Running App\nNone captured — check for silent/visual bugs."

    dom_block = ""
    if req.dom_report and req.dom_report.strip():
        dom_block = f"\n\n## DOM Snapshot (live runtime state)\n{req.dom_report.strip()}"

    user_msg = (
        f"## Auto-Debug Pass {req.iteration}\n\n"
        f"Analyse and fix all bugs in this app.{error_block}{dom_block}\n\n"
        f"## Current App Code\n```html\n{req.html}\n```"
    )

    async def _generate():
        import anthropic as _am
        _ac = _am.AsyncAnthropic(api_key=_api_key_claude)
        reply = ""
        _first = False

        try:
            async with _ac.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=24000,
                thinking={"type": "enabled", "budget_tokens": 16000},
                system=_autofix_system,
                messages=[{"role": "user", "content": user_msg}],
                extra_headers={"anthropic-beta": "interleaved-thinking-2025-05-14"},
            ) as _cs:
                async for _ct in _cs.text_stream:
                    _first = True
                    reply += _ct
                    yield f"data: {_json.dumps({'t': _ct})}\n\n"

            all_clear = bool(_re.search(r'✅\s*ALL CLEAR', reply))

            # Save bug patterns to lesson memory for future sessions
            if not all_clear and _LESSONS_LOADED:
                try:
                    lessons = _extract_lessons(reply)
                    for lesson in lessons:
                        _save_lesson(lesson["pattern"], lesson["root_cause"], lesson["fix"])
                except Exception as _le:
                    logger.debug("[LessonMemory] extraction failed (non-fatal): %s", _le)

            # Save build pattern when app passes clean — shared across all users
            if all_clear and req.iteration == 1:
                try:
                    from ..brains.build_patterns import extract_and_save as _save_build_pattern
                    _save_build_pattern(req.html, session_id=req.session_id)
                except Exception as _bp_err:
                    logger.debug("[BuildPatterns] non-fatal: %s", _bp_err)

            yield f"data: {_json.dumps({'done': True, 'meta': {'all_clear': all_clear, 'reply': reply}})}\n\n"

        except Exception as exc:
            err = _friendly_error(exc)
            yield f"data: {_json.dumps({'done': True, 'meta': {'all_clear': False, 'error': err}})}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    })


# ---------------------------------------------------------------------------
# Visual QA review — screenshot → Claude vision → patch if broken
# ---------------------------------------------------------------------------

@app.post("/api/visual_review")
async def visual_review(req: VisualReviewRequest):
    """
    Accepts a JPEG screenshot of the rendered app + its source HTML.
    Claude vision inspects it for visual problems (overflow, blank areas,
    layout breaks, content cut off) and returns a patched HTML if needed.
    """
    import re as _re

    _api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not _api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not set")

    system_prompt = """\
You are a visual QA engineer for web apps. You will be shown a screenshot of a rendered web app and its source HTML.

Your ONLY job: identify layout/fitting problems visible in the screenshot.

STRICT RULES — VIOLATIONS WILL BREAK THE USER'S APP:
- NEVER rewrite, rebuild, or replace the app. NEVER change ANY game logic, content, features, or text.
- NEVER change what type of app it is. A game stays a game. A calculator stays a calculator.
- You may ONLY add or modify CSS (sizing, overflow, transform, scale, flex/grid layout).
- If you output HTML, it must be the EXACT original HTML with ONLY a <style> block added or modified.

If the app looks GOOD (visible, playable, content fits) → respond with EXACTLY: ALL_CLEAR

If there are real visual problems (overflow, blank screen, canvas too large, content cut off):
→ Output ONLY a CSS block to inject, inside ```css ... ``` fences.
→ Nothing else. No HTML. No explanation. Just the CSS.

Do not explain. Do not add commentary. Just ALL_CLEAR or a ```css block."""

    user_content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": req.screenshot_base64,
            },
        },
        {
            "type": "text",
            "text": f"## App Screenshot\nAnalyse the screenshot above for visual problems.\n\n## Source HTML\n```html\n{req.html[:40000]}\n```",
        },
    ]

    try:
        import anthropic as _am
        _ac = _am.AsyncAnthropic(api_key=_api_key)
        resp = await _ac.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=16000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        reply = resp.content[0].text.strip() if resp.content else ""

        if reply.startswith("ALL_CLEAR"):
            return {"all_clear": True, "issues": None, "fixed_html": None}

        # Extract fixed HTML if provided
        fence = _re.search(r"```html\s*\n([\s\S]+?)```", reply)
        fixed_html = fence.group(1).strip() if fence else None

        issues = reply.replace(f"```html\n{fixed_html}\n```", "").strip() if fixed_html else reply

        return {
            "all_clear": False,
            "issues": issues[:500] if issues else "Visual issues detected",
            "fixed_html": fixed_html,
        }

    except Exception as exc:
        logger.error("[VisualReview] error: %s", exc)
        return {"all_clear": True, "issues": None, "fixed_html": None}  # fail open


# ---------------------------------------------------------------------------
# Share store — persist shared apps to disk
# ---------------------------------------------------------------------------
import json as _share_json

_SHARES_FILE = Path(__file__).parent.parent.parent / "memory_store" / "shares.json"
_THUMBNAILS_FILE = Path(__file__).parent.parent.parent / "memory_store" / "thumbnails.json"
_shares: Dict[str, str] = {}
_thumbnails: Dict[str, str] = {}  # share_id → base64 JPEG thumbnail

def _load_shares():
    global _shares, _thumbnails
    try:
        if _SHARES_FILE.exists():
            _shares = _share_json.loads(_SHARES_FILE.read_text(encoding="utf-8"))
    except Exception:
        _shares = {}
    try:
        if _THUMBNAILS_FILE.exists():
            _thumbnails = _share_json.loads(_THUMBNAILS_FILE.read_text(encoding="utf-8"))
    except Exception:
        _thumbnails = {}

def _save_shares():
    try:
        _SHARES_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SHARES_FILE.write_text(_share_json.dumps(_shares), encoding="utf-8")
    except Exception as e:
        logger.warning("Could not persist shares: %s", e)

def _save_thumbnails():
    try:
        _THUMBNAILS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _THUMBNAILS_FILE.write_text(_share_json.dumps(_thumbnails), encoding="utf-8")
    except Exception as e:
        logger.warning("Could not persist thumbnails: %s", e)

_load_shares()

_SHARE_BANNER = """
<div id="__ma_share_banner" style="
  position:fixed;bottom:0;left:0;right:0;
  background:linear-gradient(135deg,#0f111a,#1a1d2e);
  border-top:1px solid rgba(99,102,241,0.25);
  display:flex;align-items:center;justify-content:center;gap:10px;
  padding:8px 16px;z-index:99999;font-family:sans-serif;
">
  <span style="font-size:11px;color:rgba(255,255,255,0.45);">Built with</span>
  <span style="font-size:12px;font-weight:700;
    background:linear-gradient(90deg,#818cf8,#a78bfa);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
    Mini Assistant AI
  </span>
  <a href="https://miniassistantai.com" target="_blank"
     style="font-size:10px;color:rgba(99,102,241,0.7);text-decoration:none;
     border:1px solid rgba(99,102,241,0.3);border-radius:99px;padding:2px 10px;
     transition:opacity .2s;" onmouseover="this.style.opacity='.7'" onmouseout="this.style.opacity='1'">
    Build yours →
  </a>
</div>
<style>#__ma_share_banner+*,body{padding-bottom:44px!important}</style>
"""


@app.post("/api/share")
async def share_app(req: ShareRequest, request: Request):
    """Store an app's HTML and return a public share URL."""
    share_id = str(uuid.uuid4())[:8]
    _shares[share_id] = req.html
    _save_shares()
    if req.thumbnail_base64:
        _thumbnails[share_id] = req.thumbnail_base64
        _save_thumbnails()

    # Build share URL — account for /image-api mount prefix
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    share_url = f"{scheme}://{host}/image-api/s/{share_id}"
    return {"id": share_id, "url": share_url}


@app.get("/s/{share_id}")
async def view_shared_app(share_id: str):
    """Serve a shared app as a full HTML page with a Mini Assistant AI banner."""
    from fastapi.responses import HTMLResponse
    html = _shares.get(share_id)
    if not html:
        # Try reloading from disk in case server restarted
        _load_shares()
        html = _shares.get(share_id)
    if not html:
        raise HTTPException(status_code=404, detail="Shared app not found or expired.")

    # Inject banner before </body> (or at end)
    if "</body>" in html:
        html = html.replace("</body>", _SHARE_BANNER + "</body>", 1)
    else:
        html = html + _SHARE_BANNER

    return HTMLResponse(content=html, status_code=200)


# ---------------------------------------------------------------------------
# Community showcase store + endpoints
# ---------------------------------------------------------------------------
_COMMUNITY_FILE = Path(__file__).parent.parent.parent / "memory_store" / "community.json"
_community: list = []

def _load_community():
    global _community
    try:
        if _COMMUNITY_FILE.exists():
            _community = _share_json.loads(_COMMUNITY_FILE.read_text(encoding="utf-8"))
    except Exception:
        _community = []

def _save_community():
    try:
        _COMMUNITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _COMMUNITY_FILE.write_text(_share_json.dumps(_community), encoding="utf-8")
    except Exception as e:
        logger.warning("Could not persist community: %s", e)

_load_community()


@app.post("/api/community")
async def add_to_community(req: CommunityRequest, request: Request):
    """Add a shared app to the community showcase."""
    # Verify the share_id actually exists
    if req.share_id not in _shares:
        _load_shares()
    if req.share_id not in _shares:
        raise HTTPException(status_code=404, detail="Share not found.")

    # Deduplicate — don't add same share_id twice
    if any(e.get("share_id") == req.share_id for e in _community):
        return {"ok": True, "duplicate": True}

    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    play_url = f"{scheme}://{host}/image-api/s/{req.share_id}"

    entry = {
        "id": str(uuid.uuid4())[:8],
        "share_id": req.share_id,
        "title": req.title[:80],
        "author_name": req.author_name[:40],
        "timestamp": int(time.time()),
        "play_url": play_url,
        "thumbnail": _thumbnails.get(req.share_id),  # base64 JPEG, may be None
    }
    _community.insert(0, entry)  # newest first
    _community[:] = _community[:200]  # cap at 200
    _save_community()
    return {"ok": True, "id": entry["id"]}


@app.get("/api/community")
async def get_community():
    """Return the community showcase list."""
    return {"apps": _community}


# ---------------------------------------------------------------------------
# Session Memory / Lessons endpoints
# ---------------------------------------------------------------------------

@app.get("/api/userprefs")
async def get_user_prefs():
    """Return the learned user preference profile."""
    try:
        from ..brains.user_memory import load_prefs
        return load_prefs()
    except Exception as e:
        logger.warning("UserPrefs read error: %s", e)
        return {}


@app.get("/api/memory")
async def get_all_memory():
    """Return all learned memory facts across all sessions."""
    try:
        from mini_assistant.phase6.session_memory import get_memory
        mem = get_memory()
        facts = [
            f.to_dict()
            for facts_list in mem._store.values()
            for f in facts_list
        ]
        facts.sort(key=lambda f: f.get("updated_at", ""), reverse=True)
        return {"facts": facts}
    except Exception as e:
        logger.warning("Memory read error: %s", e)
        return {"facts": []}


@app.delete("/api/memory/{fact_id}")
async def delete_memory_fact(fact_id: str):
    """Delete a specific memory fact by ID."""
    try:
        from mini_assistant.phase6.session_memory import get_memory
        mem = get_memory()
        # Search all sessions for this fact
        for sid, facts_list in mem._store.items():
            if any(f.id == fact_id for f in facts_list):
                deleted = mem.delete_fact(sid, fact_id)
                if deleted:
                    return {"ok": True}
        raise HTTPException(status_code=404, detail="Fact not found.")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Memory delete error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/suggestions")
async def chat_suggestions(req: SuggestionsRequest):
    """
    Generate 3 short follow-up questions based on the last exchange.
    Returns { suggestions: ["...", "...", "..."] }.
    """
    from ..services.ollama_client import _model_name as _reg_model_name
    ollama_client = _get_ollama()

    prompt = (
        f"User asked: {req.message[:400]}\n\n"
        f"Assistant replied: {req.reply[:400]}\n\n"
        "Write exactly 3 short follow-up questions the user might ask next. "
        "One per line, no numbers, no bullets, no punctuation at end, under 60 chars each."
    )

    try:
        raw = await ollama_client.run_prompt(
            model=_reg_model_name("router_fallback"),
            prompt=prompt,
            temperature=0.8,
            timeout=25,
        )
        lines = [l.strip().lstrip("0123456789.-) ") for l in raw.strip().split("\n") if l.strip()]
        suggestions = [l for l in lines if 5 < len(l) < 120][:3]
        return {"suggestions": suggestions}
    except Exception as exc:
        logger.warning("Suggestions failed: %s", exc)
        return {"suggestions": []}
