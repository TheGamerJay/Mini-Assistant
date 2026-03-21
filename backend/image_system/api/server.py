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
from fastapi.responses import JSONResponse, StreamingResponse

from .models import (
    GenerateRequest,
    GenerateResponse,
    GenerationPlan,
    DryRunResponse,
    RouteRequest,
    AnalyzeRequest,
    ChatRequest,
    SummarizeRequest,
    PullModelsRequest,
    ModelStatusResponse,
    ErrorResponse,
)

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

_CORS_DEFAULTS = ",".join([
    "https://mini-assistant-production.up.railway.app",
    "https://www.miniassistantai.com",
    "https://miniassistantai.com",
    "https://ai.miniassistantai.com",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://localhost:8080",
])
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", _CORS_DEFAULTS).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Phase 10: Production middleware stack
# ---------------------------------------------------------------------------
try:
    from mini_assistant.phase10.request_tracer  import attach_tracer
    from mini_assistant.phase10.rate_limiter    import attach_rate_limiter
    from mini_assistant.phase10.auth_middleware import attach_auth
    attach_tracer(app)
    attach_rate_limiter(app)
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

## App / UI building — 3-question cycle (CRITICAL — follow exactly):
Building follows a strict cycle. Never deviate from it.

TURN 1 — FIRST BUILD REQUEST (text only, no image):
  Ask exactly 3 short, focused questions as a numbered list. No more, no less.
  Good: visual style/colors, must-have features, HTML vs React preference.
  Bad: file sizes, fonts, pixel dimensions — decide those yourself.
  End with: "Ready to build once you answer!"

TURN 1 — FIRST BUILD REQUEST WITH IMAGE:
  The user provided a screenshot or mockup. DO NOT ask questions. Build immediately.
  Replicate the UI from the image as a working HTML/CSS/JS app. Start with ```html.

TURN 2 — USER ANSWERS TURN 1:
  Build the complete working app immediately. Zero questions before the code.
  Make all remaining decisions yourself with sensible defaults.
  After the code, ask exactly 3 follow-up questions about what to improve/add/change.
  Format: "Here's what I built! What would you like next?\n1. ...\n2. ...\n3. ..."

TURN 3+ — USER RESPONDS TO FOLLOW-UPS:
  Update the code based on their feedback, then ask 3 more follow-up questions.
  Repeat this build → 3 questions → build cycle until the user says they're done.

ALWAYS:
- Complete, working code. No TODOs, stubs, or placeholders ever.
- On updates, modify existing code in-place. Never restart unless explicitly asked.
- Make opinionated decisions for anything the user didn't specify.

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


@app.get("/api/health")
async def health_check():
    """Health check: reports ComfyUI connectivity and checkpoint availability."""
    comfyui_url = os.environ.get("COMFYUI_URL", "http://localhost:8188")
    comfyui_ok = False
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient() as _client:
            r = await _client.get(f"{comfyui_url}/system_stats", timeout=3.0)
            comfyui_ok = r.status_code == 200
    except Exception:
        pass

    # Check for installed checkpoints
    checkpoints_dir = Path(os.environ.get(
        "COMFYUI_CHECKPOINTS_DIR",
        "C:/Users/jaaye/ai-panels/ComfyUI/models/checkpoints"
    ))
    checkpoint_files = []
    checkpoints_ok = False
    if checkpoints_dir.exists():
        checkpoint_files = [f.name for f in checkpoints_dir.iterdir()
                            if f.suffix in (".safetensors", ".ckpt", ".pt")]
        checkpoints_ok = len(checkpoint_files) > 0

    status = {
        "status": "ok",
        "service": "mini-assistant-image-system",
        "comfyui": "connected" if comfyui_ok else "disconnected",
        "checkpoints": {
            "available": checkpoints_ok,
            "count": len(checkpoint_files),
            "message": None if checkpoints_ok else "No checkpoint models found. Place .safetensors files in ComfyUI/models/checkpoints/",
        },
    }
    return status


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
async def generate_image(req: GenerateRequest):
    """
    Full image generation pipeline:
    1. Prompt safety validation.
    2. RouterBrain classifies the request (with routing_guard confidence + compatibility checks).
    3. Apply any manual overrides.
    4. If dry_run, return the plan without generating.
    5. PromptBuilder crafts positive + negative prompts.
    6. ComfyUIClient generates the image (with timeout + cancellation).
    7. ImageReviewer scores the result (unless quality=='fast').
    8. CriticBrain evaluates; retries once if warranted.
    9. EmbedBrain stores successful routes for memory.
    10. Metadata sidecar saved beside the output image.
    """
    from ..utils.prompt_safety import validate as ps_validate
    from ..utils.routing_guard import validate_route as guard_validate
    from ..utils import image_logger, metadata_writer

    session_id = req.session_id or str(uuid.uuid4())
    start_time = time.perf_counter()

    # ---- Step 1: Prompt safety ----
    is_valid, clean_prompt, safety_error = ps_validate(req.prompt)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Prompt rejected: {safety_error}")
    prompt_warnings = []
    if clean_prompt != req.prompt:
        prompt_warnings.append("Prompt was sanitized (whitespace/control chars removed).")

    # ---- Step 2: Route ----
    reference_bytes = None
    mask_bytes      = None
    pose_bytes      = None
    style_bytes     = None
    if req.reference_image_base64:
        try:
            reference_bytes = base64.b64decode(req.reference_image_base64)
        except Exception:
            logger.warning("Could not decode reference_image_base64")
    if req.mask_image_base64:
        try:
            mask_bytes = base64.b64decode(req.mask_image_base64)
        except Exception:
            logger.warning("Could not decode mask_image_base64")
    if req.pose_image_base64:
        try:
            pose_bytes = base64.b64decode(req.pose_image_base64)
        except Exception:
            logger.warning("Could not decode pose_image_base64")
    if req.style_image_base64:
        try:
            style_bytes = base64.b64decode(req.style_image_base64)
        except Exception:
            logger.warning("Could not decode style_image_base64")

    try:
        route_result = await _get_router().route(clean_prompt, reference_image=reference_bytes)
        route_result = guard_validate(route_result)
    except Exception as exc:
        logger.error("Routing failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Routing error: {exc}")

    # Log routing decision
    elapsed_route = (time.perf_counter() - start_time) * 1000
    image_logger.log_router_decision(clean_prompt, route_result, elapsed_route, session_id)

    if route_result.get("_low_confidence_warning"):
        prompt_warnings.append(route_result["_low_confidence_warning"])
    if route_result.get("_compatibility_warning"):
        prompt_warnings.append(route_result["_compatibility_warning"])

    intent = route_result.get("intent", "chat")

    # ---- Step 2b: ComfyUI mode routing (Phase 7) ----
    from ..services.comfyui_router import route_image_request as _comfy_route
    comfy_decision = _comfy_route(
        prompt=clean_prompt,
        reference_image=req.reference_image_base64,
        mask_image=req.mask_image_base64,
        pose_image=req.pose_image_base64,
        style_image=req.style_image_base64,
    )
    logger.info(
        "ComfyUI route: mode=%s target_tab=%s reason=%s",
        comfy_decision.mode, comfy_decision.target_tab, comfy_decision.reason,
    )

    # ---- Step 3: Non-image intents ----
    if intent in ("chat", "planning"):
        ollama = _get_ollama()
        try:
            from ..services.ollama_client import _model_name
            reply = await ollama.run_prompt(
                model=_model_name("router"),
                prompt=clean_prompt,
                temperature=0.7,
            )
        except Exception as exc:
            reply = _friendly_error(exc)

        elapsed = (time.perf_counter() - start_time) * 1000
        return GenerateResponse(
            image_base64=None,
            route_result={**route_result, "text_reply": reply},
            review=None,
            retry_used=False,
            critic_result=None,
            session_id=session_id,
            generation_time_ms=round(elapsed, 1),
            prompt_warnings=prompt_warnings,
        )

    if intent == "coding":
        coding = _get_coding()
        try:
            reply = await coding.run(clean_prompt)
        except Exception as exc:
            reply = f"Coding brain error: {exc}"

        elapsed = (time.perf_counter() - start_time) * 1000
        return GenerateResponse(
            image_base64=None,
            route_result={**route_result, "text_reply": reply},
            review=None,
            retry_used=False,
            critic_result=None,
            session_id=session_id,
            generation_time_ms=round(elapsed, 1),
            prompt_warnings=prompt_warnings,
        )

    # ---- Step 4: Image generation setup ----
    # Apply checkpoint/workflow overrides
    checkpoint_key = req.override_checkpoint or route_result.get("selected_checkpoint", "anime_general")
    workflow_key = req.override_workflow or route_result.get("selected_workflow", "anime_general")
    quality = req.quality or "balanced"

    # Load checkpoint file from registry
    try:
        registry = _load_registry()
        checkpoint_info = registry["image_checkpoints"].get(checkpoint_key, {})
        checkpoint_file = checkpoint_info.get("file", f"{checkpoint_key}.safetensors")
        checkpoint_type = checkpoint_info.get("type", "SD1.5")
    except Exception:
        checkpoint_file = f"{checkpoint_key}.safetensors"
        checkpoint_type = "SD1.5"

    # Build prompts
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
async def analyze_image(req: AnalyzeRequest):
    """
    Analyse an image using the vision brain.

    Body: { image_base64: str, question?: str }
    """
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


@app.post("/api/chat")
async def chat(req: ChatRequest):
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
        # If an image is attached, force image_analysis intent regardless of text
        from mini_assistant.phase1.command_parser import ParsedCommand as _PC, SLASH_COMMANDS as _SC
        if attached_image_bytes and not (parsed_cmd and parsed_cmd.is_slash):
            # Synthesise a /analyze slash command so Planner locks to image_analysis
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

    # Model override from request (Phase 6 model selector)
    from ..services.ollama_client import _model_name as _reg_model_name
    _active_model = req.preferred_model or os.environ.get("FAST_MODEL") or _reg_model_name("router")

    if execution_intent in ("image_generation", "image_edit"):
        gen_req = GenerateRequest(prompt=effective_msg, session_id=session_id)
        image_response = await generate_image(gen_req)
        # Image generation returns its own response — inject plan metadata and return
        if isinstance(image_response, dict):
            image_response["plan"]         = phase1_plan.to_dict() if phase1_plan else {}
            image_response["intent"]       = "image_generate"
            image_response["slash_command"]= parsed_cmd.command if parsed_cmd and parsed_cmd.is_slash else None
        return image_response

    elif execution_intent == "image_analysis" or (execution_intent == "chat" and attached_image_bytes):
        # User attached an image — route to vision brain
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
        # General chat / research / planning / file_analysis / web_search
        try:
            ollama_client = _get_ollama()

            # Engineering context covers file_analysis + app_builder + code_runner
            # Fall back to legacy project context for plain file_analysis without engineering ctx
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

            # System message always first — inject lyrics specialist prompt if needed
            _sys_prompt = _MINI_SYSTEM_PROMPT
            if _LYRICS_INTENT.search(effective_msg):
                _sys_prompt = _MINI_SYSTEM_PROMPT + "\n\n" + _LYRICS_SYSTEM_PROMPT
            history_msgs: list[dict] = [{"role": "system", "content": _sys_prompt}]
            if req.history:
                for h in req.history[-10:]:
                    history_msgs.append({"role": h.role, "content": h.content})

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

            # Prepend Phase 9 self-improvement context (lessons + long-term memory)
            phase9_prefix = phase9_ctx.prefix if phase9_ctx else ""
            combined_prefix = rt_context + phase9_prefix + (system_prefix or "")
            user_content = (combined_prefix + effective_msg) if combined_prefix else effective_msg
            history_msgs.append({"role": "user", "content": user_content})

            reply = await ollama_client.run_chat(
                model       = _active_model,
                messages    = history_msgs,
                temperature = 0.7,
            )
        except Exception as exc:
            reply = _friendly_error(exc)

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
async def chat_stream(req: ChatRequest):
    """
    Streaming chat endpoint — returns SSE tokens for general chat.
    Each event: data: {"t": "<token>"}
    Final event: data: {"done": true, "meta": {...}}
    Image-gen intents signal: data: {"done": true, "meta": {"type": "image_redirect"}}
    """
    import json as _json

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

        # ── Phase 1 intent routing (fast, non-blocking) ──────────────────────
        try:
            from mini_assistant.phase1.command_parser import parse as cmd_parse
            from mini_assistant.phase1.intent_planner import plan as make_plan
            parsed_cmd = cmd_parse(clean_message)
            effective_msg = parsed_cmd.args if parsed_cmd.is_slash else clean_message
            phase1_plan = make_plan(
                message=effective_msg,
                parsed_command=parsed_cmd,
                history=req.history or [],
            )
            execution_intent = phase1_plan.execution_intent or "chat"
        except Exception as _e:
            logger.warning("Phase1 failed in stream endpoint: %s", _e)

        # Image / coding intents can't stream meaningfully — signal redirect
        if execution_intent in ("image_generation", "image_edit"):
            yield f"data: {_json.dumps({'done': True, 'meta': {'type': 'image_redirect'}})}\n\n"
            return

        # ── Model selection ───────────────────────────────────────────────────
        from ..services.ollama_client import _model_name as _reg_model_name
        _is_build_intent = execution_intent == "app_builder"

        # Vibe Code mode — user toggled ⚡ in the UI, skip all Q&A, build immediately
        if req.vibe_mode and not _is_build_intent:
            _is_build_intent = True
            execution_intent = "app_builder"  # so done-event intent is correct → auto-opens preview

        # Also detect build intent from history — follow-up messages in a build
        # conversation are often classified as "chat" by the router (e.g. "make it
        # a video uploader"), but they still need the coder model + build prompt.
        if not _is_build_intent and req.history:
            _hist_contents = " ".join(h.content or "" for h in req.history)
            # If any previous assistant turn contains a code fence, we're in a build session
            _assistant_has_code = any(
                h.role == "assistant" and "```" in (h.content or "")
                for h in req.history
            )
            # Or if the first user message was a build request
            _BUILD_KW = _re.compile(
                r"/build|build me|build it|create (a|an|the) (app|website|page|ui|component|dashboard)|"
                r"make (a|an) (web|html|react)|make it|do it|generate (a|an) (app|website|page)|"
                r"update it|add (a|an|the) (button|section|feature|page|component|form)|"
                r"can you (build|make|create|add|update)",
                _re.I,
            )
            _first_user = next((h for h in req.history if h.role == "user"), None)
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

        if _is_build_intent:
            # App building: use deepseek-coder. Keepalive loop above handles
            # the model-load wait so Cloudflare won't drop the connection.
            _active_model = _reg_model_name("coder")
        elif _is_code_intent and not req.preferred_model:
            # Explicit code paste or error: use deepseek-coder.
            # User initiated this intentionally so the load wait is acceptable.
            _active_model = _reg_model_name("coder")
        else:
            _active_model = req.preferred_model or os.environ.get("FAST_MODEL") or _reg_model_name("router")

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
        _build_history_turns = sum(1 for h in (req.history or []) if h.role == "assistant") if _is_build_intent else 0

        _has_images = bool(req.image_base64 or req.images_base64)
        # True if pipeline has already generated HTML code in a previous turn
        _has_prior_code = any(
            h.role == "assistant" and "```html" in (h.content or "")
            for h in (req.history or [])
        )
        if _is_build_intent:
            if not _has_images and not _has_prior_code and _build_history_turns == 0:
                # First contact, no image, no prior code — ask 3 questions then stop
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
                    "\n\n## APP BUILDER — BUILD TURN (MANDATORY CODE OUTPUT)\n"
                    "CRITICAL: You MUST output a complete, working code block RIGHT NOW. No exceptions.\n"
                    "The user answered your questions. Your ONLY job in this response is:\n"
                    "  1. Output the FULL working app as a single ```html code block (HTML + CSS + JS all inline).\n"
                    "  2. Apply the CODING STANDARDS above — CSS variables, flexbox layouts, real JS state, transitions, empty states, etc.\n"
                    "  3. The code block MUST come FIRST before any other text.\n"
                    "  4. After the closing ``` of the code block, write exactly:\n"
                    "     'Here\\'s what I built! What would you like next?\\n1. ...\\n2. ...\\n3. ...'\n\n"
                    "RULES:\n"
                    "- Output format: ```html\\n<!DOCTYPE html>\\n...\\n```  (mandatory)\n"
                    "- Every button, input, and control must be fully functional JavaScript — no stubs, no TODOs.\n"
                    "- Include ALL CSS inline in <style> tags, ALL JS inline in <script> tags.\n"
                    "- Make all design decisions yourself — do NOT ask more questions before writing code.\n"
                    "- If you write anything except code first, you have FAILED. Start your response with ```html\n"
                )
            else:
                # User responded to follow-ups — update code then ask 3 more
                _build_mode_addendum = (
                    _APP_BUILDER_CODING_STANDARDS +
                    "\n\n## APP BUILDER — UPDATE TURN (MANDATORY CODE OUTPUT)\n"
                    "CRITICAL: Output the COMPLETE updated code block FIRST. No exceptions.\n"
                    "  1. Output the full updated app as a single ```html code block.\n"
                    "  2. Maintain the CODING STANDARDS — preserve CSS variables, clean state management, all working interactions.\n"
                    "  3. The code block MUST come FIRST before any other text.\n"
                    "  4. After the closing ```, write: 'Updated! What would you like next?\\n1. ...\\n2. ...\\n3. ...'\n\n"
                    "RULES:\n"
                    "- Always output the ENTIRE file — never partial diffs or snippets.\n"
                    "- Every button and control must remain fully functional. No TODOs, no stubs.\n"
                    "- Start your response with ```html — not with words.\n"
                )
            _sys_prompt_stream = _MINI_SYSTEM_PROMPT + _build_mode_addendum
        elif _LYRICS_INTENT.search(effective_msg):
            _sys_prompt_stream = _MINI_SYSTEM_PROMPT + "\n\n" + _LYRICS_SYSTEM_PROMPT
        elif _is_code_intent:
            _sys_prompt_stream = _MINI_SYSTEM_PROMPT + _CODE_ASSISTANT_PROMPT
        else:
            _sys_prompt_stream = _MINI_SYSTEM_PROMPT
        history_msgs: list[dict] = [{"role": "system", "content": _sys_prompt_stream}]
        if req.history:
            for h in req.history[-10:]:
                history_msgs.append({"role": h.role, "content": h.content})
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
            if not req.preferred_model:
                _active_model = _reg_model_name("vision")
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
        _use_claude     = bool(_api_key_claude)
        reply_text      = ""
        ollama_client   = _get_ollama()

        if _is_build_intent and all_images and not _has_prior_code:
            from .pipeline import image_to_code_pipeline
            async for _sse in image_to_code_pipeline(
                images=all_images,
                user_request=effective_msg,
                ollama_client=ollama_client,
                vision_model=_reg_model_name("vision"),
                builder_model=_reg_model_name("coder"),
                reviewer_model=_reg_model_name("router"),
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

            # Convert history to Claude message format (filter system msgs)
            _c_msgs = []
            for _hm in history_msgs:
                _hr, _hc = _hm.get("role"), _hm.get("content", "")
                if _hr in ("user", "assistant") and _hc:
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
            if _is_build_intent:
                _c_sys = (
                    _APP_BUILDER_CODING_STANDARDS +
                    "\n\n## BUILD IMMEDIATELY\n"
                    "Build the complete working app right now from the user's description. "
                    "No questions. Output the full HTML/CSS/JS as a single ```html code block. "
                    "After the closing ``` write: "
                    "'Here\\'s what I built! What would you like to change?\\n1. ...\\n2. ...\\n3. ...'"
                )
            elif all_images:
                _c_sys = (
                    "You are a helpful AI assistant with strong vision capabilities. "
                    "Analyze images accurately. Describe colors precisely (use hex values when visible), "
                    "layout, text content, UI elements, and style. Be specific and technical."
                )
            else:  # code intent
                _c_sys = (
                    "You are an expert software engineer and debugger. "
                    "Read error messages carefully, identify root causes, and provide clear fixes. "
                    "Show corrected code with explanation of what was wrong and why the fix works."
                )

            try:
                import anthropic as _am_lib
                _ac = _am_lib.AsyncAnthropic(api_key=_api_key_claude)
                async with _ac.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=8192,
                    system=_c_sys,
                    messages=_c_msgs,
                ) as _cs:
                    async for _ct in _cs.text_stream:
                        reply_text += _ct
                        yield f"data: {_json.dumps({'t': _ct})}\n\n"
            except Exception as _ce:
                logger.warning("Claude stream failed, falling back to Ollama: %s", _ce)
                _err_msg = f"⚠️ Claude unavailable: {_ce}. Retrying with local model...\n\n"
                yield f"data: {_json.dumps({'t': _err_msg})}\n\n"
                # Fall through isn't possible in elif — emit error and continue to done event

        else:
            # ── Local Ollama stream ───────────────────────────────────────────
            # Simple chat stays local — free, fast enough for conversation.
            # Complex tasks (builds, vision, code) routed to Claude above.
            _fallback_model = _reg_model_name("router")
            _model_to_try = _active_model
            for _attempt in range(2):  # Try primary model first, fall back to router on model error
                try:
                    _stream = ollama_client.run_chat_stream(
                        model=_model_to_try,
                        messages=history_msgs,
                        temperature=0.7,
                    )
                    _aiter = _stream.__aiter__()
                    # Use ensure_future to wrap the coroutine in a Task, then shield the Task.
                    # A Task can be shielded multiple times across keepalive timeouts;
                    # a raw coroutine cannot — re-shielding it raises RuntimeError.
                    _next_task = asyncio.ensure_future(_aiter.__anext__())
                    while True:
                        try:
                            token = await asyncio.wait_for(asyncio.shield(_next_task), timeout=3.0)
                            reply_text += token
                            yield f"data: {_json.dumps({'t': token})}\n\n"
                            _next_task = asyncio.ensure_future(_aiter.__anext__())
                        except asyncio.TimeoutError:
                            # No token yet — keepalive ping, same Task still running
                            yield ": keepalive\n\n"
                        except StopAsyncIteration:
                            break
                    break  # success — don't retry
                except Exception as exc:
                    _exc_s = str(exc).lower()
                    _is_model_err = any(kw in _exc_s for kw in ("not found", "pull", "404", "no such", "unknown model"))
                    if _attempt == 0 and _is_model_err and _model_to_try != _fallback_model:
                        logger.warning("Model %s unavailable, falling back to %s: %s", _model_to_try, _fallback_model, exc)
                        _model_to_try = _fallback_model
                        continue  # retry with fallback router model
                    err = _friendly_error(exc)
                yield f"data: {_json.dumps({'t': err})}\n\n"
                reply_text = err

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
async def chat_compare(req: ChatRequest):
    """
    Run the same message through two models in parallel and return both replies.
    Used by the frontend every 10 responses to let the user pick their preferred model output.
    """
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
