from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File
from agents import run_agent_pipeline
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import json
import asyncio
from ollama import Client
from faster_whisper import WhisperModel
from gtts import gTTS
from duckduckgo_search import DDGS
import tempfile
import subprocess

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ.get('MONGO_URL', '')
if mongo_url:
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ.get('DB_NAME', 'mini_assistant')]
else:
    logging.warning("MONGO_URL not set – MongoDB features will be unavailable")
    client = None
    db = None


def _require_db():
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured (MONGO_URL env var not set)")

app = FastAPI()
api_router = APIRouter(prefix="/api")

# Default model for basic endpoints (override with FAST_MODEL env var)
_default_model = os.environ.get('FAST_MODEL', 'glm-4.7:cloud')

# Initialize Ollama client using OLLAMA_HOST / OLLAMA_API_KEY env vars
_ollama_host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
_ollama_api_key = os.environ.get('OLLAMA_API_KEY', '')
_ollama_headers = {"Authorization": f"Bearer {_ollama_api_key}"} if _ollama_api_key else {}

try:
    ollama_client = Client(host=_ollama_host, headers=_ollama_headers)
    print(f"✓ Ollama client initialised (host={_ollama_host})")
except Exception as e:
    print(f"✗ Failed to initialise Ollama client: {e}")
    ollama_client = None

# Initialize Whisper model for STT (lazy loading)
whisper_model = None

# Models
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: str = _default_model
    stream: bool = False
    system_override: Optional[str] = None  # custom system prompt (e.g. coach mode)

class ChatResponse(BaseModel):
    response: str
    model: str

class WebSearchRequest(BaseModel):
    query: str
    max_results: int = 5

class WebSearchResult(BaseModel):
    title: str
    url: str
    body: str

class FileListRequest(BaseModel):
    path: str = "/app"

class FileReadRequest(BaseModel):
    path: str

class FileWriteRequest(BaseModel):
    path: str
    content: str

class CommandRequest(BaseModel):
    command: str
    allowlist: List[str] = ["ls", "pwd", "cat", "echo", "grep", "find", "wc", "head", "tail"]

class ProjectProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    path: str
    description: Optional[str] = None
    commands: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ProjectProfileCreate(BaseModel):
    name: str
    path: str
    description: Optional[str] = None
    commands: List[str] = []

class STTRequest(BaseModel):
    audio_data: str

class TTSRequest(BaseModel):
    text: str
    lang: str = "en"

class ImageGenRequest(BaseModel):
    prompt: str
    model: str = "stable-diffusion"

class FixLoopRequest(BaseModel):
    command: str
    error_output: str

class CodeSearchRequest(BaseModel):
    query: str
    path: str = "/app"
    max_results: int = 5

# Chat endpoint
# Strong triggers: topic-based, always worth searching
_STRONG_TRIGGERS = [
    "where to buy", "where can i buy", "find me", "search for", "look up",
    "amazon", "ebay", "shop", "purchase", "release date", "new model",
    "news about", "price of", "how much is", "how much does",
    "latest news", "current price", "best deal", "in stock",
]
# Weak triggers: only trigger if message has enough substance (> 6 words)
_WEAK_TRIGGERS = [
    "latest", "current", "recently", "2024", "2025", "2026", "today",
    "news", "price", "available", "review", "specs", "vs", "compare",
]

def _should_search(text: str) -> bool:
    lower = text.lower().strip()
    # Skip very short conversational messages
    words = lower.split()
    if len(words) < 4:
        return False
    if any(trigger in lower for trigger in _STRONG_TRIGGERS):
        return True
    # Weak triggers require a longer, more substantive message
    if len(words) >= 6 and any(trigger in lower for trigger in _WEAK_TRIGGERS):
        return True
    return False

def _run_web_search(query: str, max_results: int = 5) -> str:
    # Try Tavily first (most reliable on cloud IPs)
    tavily_key = os.environ.get("TAVILY_API_KEY", "")
    if tavily_key:
        try:
            import requests as _req
            resp = _req.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "max_results": max_results},
                timeout=10,
            )
            data = resp.json()
            results = data.get("results", [])
            if results:
                lines = [
                    "=== LIVE WEB SEARCH RESULTS (treat as ground truth, ignore your training data) ===",
                    f"Query: {query}",
                ]
                for i, r in enumerate(results, 1):
                    lines.append(f"{i}. Title: {r.get('title', '')}")
                    lines.append(f"   URL: {r.get('url', '')}")
                    lines.append(f"   Summary: {r.get('content', '')[:250]}")
                lines.append("=== END OF SEARCH RESULTS — use the URLs above directly in your response ===")
                return "\n".join(lines)
        except Exception as e:
            print(f"[TAVILY ERROR] {e}")

    # Fallback: DuckDuckGo with multiple backends
    for backend in ("lite", "html", "auto"):
        try:
            ddgs = DDGS(timeout=15)
            results = list(ddgs.text(query, max_results=max_results, backend=backend))
            if results:
                lines = [
                    "=== LIVE WEB SEARCH RESULTS (treat as ground truth, ignore your training data) ===",
                    f"Query: {query}",
                ]
                for i, r in enumerate(results, 1):
                    lines.append(f"{i}. Title: {r.get('title', '')}")
                    lines.append(f"   URL: {r.get('href', '')}")
                    lines.append(f"   Summary: {r.get('body', '')[:250]}")
                lines.append("=== END OF SEARCH RESULTS — use the URLs above directly in your response ===")
                return "\n".join(lines)
        except Exception as e:
            print(f"[DDGS {backend} ERROR] {e}")
    return ""

def _auto_select_model(message: str, has_search_context: bool = False) -> str:
    """Pick the best model based on what the user is asking."""
    lower = message.lower().strip()

    # Coding / technical work → devstral
    code_keywords = [
        'code', 'function', 'class', 'debug', 'error', 'bug', 'fix',
        'script', 'python', 'javascript', 'typescript', 'sql', 'api',
        'build', 'implement', 'write a', 'create a', 'refactor',
        'deploy', 'docker', 'git', 'test', 'unit test', 'endpoint',
    ]
    if any(k in lower for k in code_keywords):
        return _default_model

    # Deep research / analysis / long-form → glm-5
    deep_keywords = [
        'explain', 'analyze', 'compare', 'research', 'summarize',
        'architecture', 'design', 'strategy', 'best practice',
        'difference between', 'pros and cons', 'how does', 'why does',
        'recommend', 'evaluate',
    ]
    if any(k in lower for k in deep_keywords) or has_search_context:
        return 'glm-5:cloud'

    # Default: fast, capable general chat
    return 'minimax-m2.1:cloud'


@api_router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available. Please ensure Ollama is running on localhost:11434")

    try:
        from datetime import date as _date
        today = _date.today().strftime("%B %d, %Y")
        default_system = (
            f"You are Mini Assistant, a helpful AI assistant. Today's date is {today}. "
            "Never mention that you are GLM, Z.ai, or any other underlying model. Always refer to yourself as Mini Assistant. "
            "CRITICAL: When web search results are provided in this conversation, you MUST use them as your primary source of truth — "
            "they are live, real-time data and are always more accurate than your training knowledge. "
            "Never say a product does not exist or is unreleased if search results show it available. "
            "Always extract and share the actual URLs from the search results. "
            "Format every link as markdown: [title](url) so it is clickable. "
            "If search results contain product links, list them directly — do not make up or paraphrase URLs."
        )
        system_content = request.system_override if request.system_override else default_system
        system_prompt = {"role": "system", "content": system_content}
        messages = [system_prompt] + [{"role": msg.role, "content": msg.content} for msg in request.messages]

        # Auto web search: if the last user message looks like a search query, fetch live results
        last_user = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
        has_search = False
        if last_user and _should_search(last_user):
            search_context = await asyncio.get_event_loop().run_in_executor(None, _run_web_search, last_user)
            if search_context:
                has_search = True
                print(f"[CHAT] Injecting web search context for: {last_user[:80]}")
                messages.insert(-1, {"role": "system", "content": search_context})

        # Resolve model: auto-select if not explicitly chosen
        resolved_model = (
            _auto_select_model(last_user, has_search_context=has_search)
            if request.model == "auto"
            else request.model
        )
        print(f"[CHAT] model={resolved_model} (requested={request.model})")

        if request.stream:
            response_text = ""
            stream = ollama_client.chat(model=resolved_model, messages=messages, stream=True)
            for chunk in stream:
                if 'message' in chunk and 'content' in chunk['message']:
                    response_text += chunk['message']['content']
        else:
            response = ollama_client.chat(model=resolved_model, messages=messages)
            response_text = response['message']['content']

        return ChatResponse(response=response_text, model=resolved_model)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")

# Voice endpoints
@api_router.post("/voice/stt")
async def speech_to_text(file: UploadFile = File(...)):
    global whisper_model
    try:
        if whisper_model is None:
            whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        segments, info = whisper_model.transcribe(tmp_path, language="en")
        transcription = " ".join([segment.text for segment in segments])
        
        os.unlink(tmp_path)
        return {"transcription": transcription, "language": info.language}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT error: {str(e)}")

@api_router.post("/voice/tts")
async def text_to_speech(request: TTSRequest):
    try:
        tts = gTTS(text=request.text, lang=request.lang, slow=False)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tts.save(tmp.name)
            tmp_path = tmp.name
        
        def iter_file():
            with open(tmp_path, "rb") as f:
                yield from f
            os.unlink(tmp_path)
        
        return StreamingResponse(iter_file(), media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)}")

# Web search endpoint
@api_router.post("/search/web", response_model=List[WebSearchResult])
async def web_search(request: WebSearchRequest):
    print(f"[SEARCH] Query: '{request.query}' (max: {request.max_results})")

    # Try Tavily first (most reliable on cloud IPs)
    tavily_key = os.environ.get("TAVILY_API_KEY", "")
    if tavily_key:
        try:
            import requests as _req
            resp = _req.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": request.query, "max_results": request.max_results},
                timeout=10,
            )
            data = resp.json()
            tv_results = data.get("results", [])
            if tv_results:
                print(f"[SEARCH] Tavily returned {len(tv_results)} results")
                return [WebSearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    body=r.get("content", "")
                ) for r in tv_results]
        except Exception as e:
            print(f"[TAVILY ERROR] {e}")

    # Fallback: DuckDuckGo with multiple backends
    last_error = "No results found. DuckDuckGo may be blocking this server's IP. Add a TAVILY_API_KEY env var for reliable search."
    for backend in ("lite", "html", "auto"):
        try:
            ddgs = DDGS(timeout=15)
            results = list(ddgs.text(request.query, max_results=request.max_results, backend=backend))
            if results:
                print(f"[SEARCH] DDGS({backend}) returned {len(results)} results")
                return [WebSearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    body=r.get("body", "")
                ) for r in results]
        except Exception as e:
            last_error = str(e)
            print(f"[DDGS {backend} ERROR] {e}")

    raise HTTPException(status_code=503, detail=last_error)

# File operations
@api_router.post("/files/list")
async def list_files(request: FileListRequest):
    try:
        path = Path(request.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Path not found")
        
        items = []
        for item in path.iterdir():
            items.append({
                "name": item.name,
                "path": str(item),
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else 0
            })
        
        return {"items": sorted(items, key=lambda x: (not x['is_dir'], x['name']))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List error: {str(e)}")

@api_router.post("/files/read")
async def read_file(request: FileReadRequest):
    try:
        path = Path(request.path)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        
        content = path.read_text()
        return {"content": content, "path": str(path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Read error: {str(e)}")

@api_router.post("/files/write")
async def write_file(request: FileWriteRequest):
    try:
        path = Path(request.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(request.content)
        return {"success": True, "path": str(path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Write error: {str(e)}")

# Command execution
@api_router.post("/commands/execute")
async def execute_command(request: CommandRequest):
    cmd_parts = request.command.strip().split()
    if not cmd_parts:
        raise HTTPException(status_code=400, detail="Empty command")
    
    base_cmd = cmd_parts[0]
    if base_cmd not in request.allowlist:
        raise HTTPException(status_code=403, detail=f"Command '{base_cmd}' not in allowlist")
    
    try:
        result = subprocess.run(
            request.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd="/app"
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Command timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")

# Project Profiles
@api_router.get("/profiles", response_model=List[ProjectProfile])
async def get_profiles():
    _require_db()
    profiles = await db.profiles.find({}, {"_id": 0}).to_list(1000)
    for profile in profiles:
        if isinstance(profile.get('created_at'), str):
            profile['created_at'] = datetime.fromisoformat(profile['created_at'])
    return profiles

@api_router.post("/profiles", response_model=ProjectProfile)
async def create_profile(input: ProjectProfileCreate):
    _require_db()
    profile_dict = input.model_dump()
    profile_obj = ProjectProfile(**profile_dict)
    
    doc = profile_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.profiles.insert_one(doc)
    return profile_obj

@api_router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    _require_db()
    result = await db.profiles.delete_one({"id": profile_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"success": True}

# Image generation placeholder
@api_router.post("/images/generate")
async def generate_image(request: ImageGenRequest):
    return {
        "success": False,
        "message": "Image generation requires local Stable Diffusion setup. Please install and configure ComfyUI or Automatic1111.",
        "prompt": request.prompt
    }

# FixLoop - Error analysis
@api_router.post("/fixloop/analyze")
async def analyze_error(request: FixLoopRequest):
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    
    try:
        prompt = f"""Analyze this command error and suggest a fix:

Command: {request.command}
Error Output: {request.error_output}

Provide:
1. Root cause analysis
2. Suggested fix (exact command or code change)
3. Explanation"""
        
        response = ollama_client.chat(
            model=_default_model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return {
            "analysis": response['message']['content'],
            "command": request.command
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")

# App Builder
# In-memory preview store: maps build_id -> html string
# (persists for the lifetime of the server process)
_app_previews: dict = {}

@api_router.get("/preview/{build_id}", response_class=HTMLResponse)
async def serve_app_preview(build_id: str):
    """Serve a generated app HTML by build ID — navigable by FixLoop and browsers."""
    html = _app_previews.get(build_id)
    if not html:
        raise HTTPException(status_code=404, detail="Preview not found or expired")
    return HTMLResponse(content=html)

import re as _app_re

def _parse_html_to_project(html: str, name: str = "generated-app", description: str = "") -> dict:
    """Split a single-file HTML into index.html / style.css / script.js."""
    # Extract <style> blocks
    css_blocks = _app_re.findall(r'<style[^>]*>(.*?)</style>', html, _app_re.DOTALL | _app_re.IGNORECASE)
    css = "\n\n".join(b.strip() for b in css_blocks)
    clean = _app_re.sub(r'<style[^>]*>.*?</style>', '', html, flags=_app_re.DOTALL | _app_re.IGNORECASE)

    # Extract inline <script> blocks (skip src= scripts)
    js_blocks = _app_re.findall(r'<script(?![^>]*\bsrc\b)[^>]*>(.*?)</script>', html, _app_re.DOTALL | _app_re.IGNORECASE)
    js = "\n\n".join(b.strip() for b in js_blocks)
    clean = _app_re.sub(r'<script(?![^>]*\bsrc\b)[^>]*>.*?</script>', '', clean, flags=_app_re.DOTALL | _app_re.IGNORECASE)

    # Inject external file references
    link = '<link rel="stylesheet" href="style.css">'
    scr  = '<script src="script.js"></script>'
    if '</head>' in clean:
        clean = clean.replace('</head>', f'  {link}\n</head>', 1)
        clean = clean.replace('</body>', f'  {scr}\n</body>', 1)
    else:
        clean = f'{link}\n{clean}\n{scr}'

    readme = f"""# {name}

{description}

## How to run

**Option 1 — Open directly:**
Double-click `index.html`. It opens in your browser with no server needed.

**Option 2 — Local server:**
```bash
python -m http.server 8080   # then visit http://localhost:8080
npx serve .                  # Node.js alternative
```

## Structure
```
{name}/
├── index.html   # Markup
├── style.css    # Styles
├── script.js    # Logic
└── README.md
```
_Generated by Mini Assistant App Builder_
"""
    return {
        "index_html": clean.strip(),
        "style_css":  css  or "/* styles */",
        "script_js":  js   or "// scripts",
        "readme":     readme,
    }


def _reconstruct_html(project: dict) -> str:
    """Merge structured project files back into a single self-contained HTML."""
    html = project.get("index_html", "")
    css  = project.get("style_css", "")
    js   = project.get("script_js", "")
    html = html.replace('<link rel="stylesheet" href="style.css">', f'<style>{css}</style>', 1)
    html = html.replace('<script src="script.js"></script>',        f'<script>{js}</script>',  1)
    # Fallback: if the placeholders weren't there, just inline at end
    if f'<style>{css}</style>' not in html and css.strip():
        html = html.replace('</head>', f'<style>{css}</style>\n</head>', 1)
    if f'<script>{js}</script>' not in html and js.strip():
        html = html.replace('</body>', f'<script>{js}</script>\n</body>', 1)
    return html


def _route_edit(instruction: str) -> str:
    """Decide which project file an edit instruction targets."""
    lower = instruction.lower()
    js_kw    = ['function','logic','bug','error','not work','doesn\'t work','click','event',
                'game','score','animation','api','fetch','javascript',' js ','feature',
                'behavior','fix','crash','speed','performance','collision','physics','movement',
                'jump','attack','sound','audio','timer','loop','canvas']
    style_kw = ['color','font','size','background','border','margin','padding','style','css',
                'design','visual','spacing','shadow','gradient','responsive','dark','light',
                'theme','opacity','transition','hover','radius','flex','grid','width','height']
    html_kw  = ['button','text','title','heading','content','html','element','section','nav',
                'footer','header','menu','link','image','input','form','placeholder','label',
                'paragraph','div','layout structure']

    js_s = sum(1 for k in js_kw    if k in lower)
    st_s = sum(1 for k in style_kw if k in lower)
    ht_s = sum(1 for k in html_kw  if k in lower)

    if js_s >= st_s and js_s >= ht_s:
        return "script.js"
    if st_s >= ht_s:
        return "style.css"
    return "index.html"


class AppBuilderRequest(BaseModel):
    description: str
    framework: str = "react"

@api_router.post("/app-builder/generate")
async def generate_app(request: AppBuilderRequest):
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    
    try:
        prompt = f"""You are a world-class web developer and UI designer. Your job is to generate a single, complete, self-contained HTML file for the following app:

{request.description}

--- OUTPUT FORMAT (NON-NEGOTIABLE) ---
- Output ONLY the raw HTML file. Nothing else.
- No markdown. No code fences. No explanation. No preamble. No commentary after.
- The VERY FIRST character of your response must be < (the start of <!DOCTYPE html>).
- The VERY LAST character must be > (the end of </html>).
- Never truncate. Never use placeholders like "// add logic here" or "TODO". Write every single line of real, working code.

--- TECHNICAL REQUIREMENTS ---
- Everything must be inline: all CSS inside <style>, all JavaScript inside <script>.
- No external files. Self-contained means it works when you double-click the .html file offline.
- You MAY use CDN links ONLY for well-known essential libraries (Three.js, Chart.js, Tone.js). Prefer inline when possible.
- Use modern JavaScript (ES6+), Canvas API, Web Audio API, localStorage wherever they improve the app.
- Handle edge cases gracefully. The app must never crash or freeze.

--- QUALITY STANDARDS ---
VISUAL DESIGN:
- Dark, premium aesthetic. Rich gradients, subtle glassmorphism, smooth drop shadows.
- Consistent color palette. Every interactive element has hover/active states with CSS transitions.
- UI should look like a polished commercial product, not a demo or homework assignment.
- Fully responsive: works on mobile, tablet, desktop. Use CSS Grid or Flexbox.

FOR GAMES:
- Proper game loop using requestAnimationFrame. Target 60fps.
- Physics: gravity, collision detection, momentum, friction as appropriate.
- Particle effects for impacts, explosions, pickups, deaths, level-ups.
- Sound effects via Web Audio API (synthesized tones, no external audio files).
- Keyboard controls (WASD/arrows/space) AND on-screen touch buttons for mobile.
- Score system with high score persisted in localStorage.
- Progressive difficulty that scales over time.
- Start screen with title and instructions. Game over screen with score and restart.
- Rich game feel: screen shake on hits, flash effects, combo counters.

FOR UTILITY APPS:
- Every button and control must be fully functional, no stubs.
- Auto-save to localStorage so data persists across sessions.
- Keyboard shortcuts for common actions.
- Styled error/success messages for user feedback.
- Subtle animations for state transitions (fade, slide).

FOR DATA/VISUALIZATION APPS:
- Pre-populate with realistic demo data so the app looks alive on first open.
- Animate chart renders and data transitions.
- Interactive controls (filters, sliders, date pickers) that actually work.

--- CHECKLIST (verify before outputting) ---
[x] App fully implements everything described in the request
[x] Every button, input, and control is functional
[x] Visual design is polished and consistent
[x] Code is complete with no TODOs, truncation, or placeholders
[x] Response starts with <!DOCTYPE html> and ends with </html>

Now generate the complete HTML file:"""

        response = ollama_client.chat(
            model=_default_model,
            messages=[{"role": "user", "content": prompt}]
        )

        content = response['message']['content'].strip()

        # Strip markdown fences if the model added them (handles ```html, ```htm, ``` etc.)
        import re as _re
        content = _re.sub(r'^```[a-zA-Z]*\n?', '', content)
        content = _re.sub(r'\n?```\s*$', '', content)
        content = content.strip()
        # Ensure it starts with a proper doctype
        if not content.lower().startswith('<!doctype') and '<!doctype' in content.lower():
            content = content[content.lower().find('<!doctype'):]

        # Derive a simple app name from the description
        name_words = request.description.split()[:4]
        app_name = "-".join(w.lower() for w in name_words if w.isalpha()) or "generated-app"

        # Parse into structured project files
        project = _parse_html_to_project(content, app_name, request.description)
        # Reconstruct full HTML (inlined) for preview cache
        reconstructed = _reconstruct_html(project)

        build_id = str(uuid.uuid4())
        _app_previews[build_id] = reconstructed

        return {
            "name": app_name,
            "description": request.description,
            "html": content,        # original for backward compat
            "project": project,     # structured files
            "build_id": build_id,
            "preview_url": f"/api/preview/{build_id}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation error: {str(e)}")

# Code Review
class CodeReviewRequest(BaseModel):
    code: str
    language: str = "javascript"

class GitRemoteRequest(BaseModel):
    name: str
    url: str

class AppBuilderEditRequest(BaseModel):
    html: Optional[str] = None          # legacy / fallback
    project: Optional[dict] = None      # structured project files
    instruction: str

@api_router.post("/app-builder/edit")
async def edit_app(request: AppBuilderEditRequest):
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    try:
        # Resolve project — accept structured or fall back to parsing raw HTML
        if request.project:
            project = request.project
        elif request.html:
            project = _parse_html_to_project(request.html)
        else:
            raise HTTPException(status_code=400, detail="Provide either 'project' or 'html'")

        index_html = project.get("index_html", "")
        style_css  = project.get("style_css", "")
        script_js  = project.get("script_js", "")

        # Route the edit to the most appropriate file
        target_file = _route_edit(request.instruction)

        file_map = {
            "index.html": index_html,
            "style.css":  style_css,
            "script.js":  script_js,
        }
        target_content = file_map[target_file]

        prompt = f"""You are editing a specific file inside a multi-file web project.

Here are all project files for context:

--- index.html ---
{index_html}

--- style.css ---
{style_css}

--- script.js ---
{script_js}

The file you must edit is: {target_file}

USER'S CHANGE REQUEST:
{request.instruction}

--- RULES ---
- Return ONLY the complete updated content of {target_file}.
- No markdown. No code fences. No explanation before or after.
- Return the FULL file — never truncate.
- Keep everything that was not changed exactly as it was.
- If the user reports a bug, fix the root cause — do not comment it out.
- Layout/content changes → index.html
- Visual/design changes → style.css
- Logic/behavior/game changes → script.js

Now output the updated {target_file}:"""

        response = ollama_client.chat(
            model=_default_model,
            messages=[{"role": "user", "content": prompt}]
        )

        updated_content = response['message']['content'].strip()
        # Strip markdown fences
        updated_content = _app_re.sub(r'^```[a-zA-Z]*\n?', '', updated_content)
        updated_content = _app_re.sub(r'\n?```\s*$', '', updated_content)
        updated_content = updated_content.strip()

        # Merge the updated file back into the project
        updated_project = dict(project)
        if target_file == "index.html":
            updated_project["index_html"] = updated_content
        elif target_file == "style.css":
            updated_project["style_css"] = updated_content
        elif target_file == "script.js":
            updated_project["script_js"] = updated_content

        # Reconstruct full HTML for preview
        reconstructed = _reconstruct_html(updated_project)

        build_id = str(uuid.uuid4())
        _app_previews[build_id] = reconstructed

        return {
            "project": updated_project,
            "html": reconstructed,
            "file_changed": target_file,
            "build_id": build_id,
            "preview_url": f"/api/preview/{build_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Edit error: {str(e)}")


class AppBuilderExportRequest(BaseModel):
    html: Optional[str] = None      # legacy single-file
    project: Optional[dict] = None  # structured project (preferred)
    name: str = "generated-app"
    description: str = ""

@api_router.post("/app-builder/export-zip")
async def export_app_zip(request: AppBuilderExportRequest):
    """Return a ZIP of the structured project files."""
    import io, zipfile
    from fastapi.responses import Response

    name = request.name or "generated-app"

    # Resolve project — structured preferred, fall back to parsing HTML
    if request.project:
        project = request.project
        # Ensure readme is present
        if not project.get("readme"):
            project["readme"] = _parse_html_to_project("", name, request.description)["readme"]
    elif request.html:
        project = _parse_html_to_project(request.html, name, request.description)
    else:
        raise HTTPException(status_code=400, detail="Provide either 'project' or 'html'")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{name}/index.html", project.get("index_html", "").strip())
        zf.writestr(f"{name}/style.css",  project.get("style_css",  "/* styles */"))
        zf.writestr(f"{name}/script.js",  project.get("script_js",  "// scripts"))
        zf.writestr(f"{name}/README.md",  project.get("readme",     ""))
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'}
    )


class GitCommitRequest(BaseModel):
    message: str

class GitPushRequest(BaseModel):
    remote: str = "origin"
    branch: str = "main"

class GitPullRequest(BaseModel):
    remote: str = "origin"
    branch: str = "main"

class GitBranchRequest(BaseModel):
    name: str

class CodeRunRequest(BaseModel):
    code: str
    language: str = "python"
    timeout: int = 10

class APITestRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: Dict[str, str] = {}
    body: Optional[str] = None

class PackageInstallRequest(BaseModel):
    package: str
    type: str = "npm"

class EnvVarRequest(BaseModel):
    type: str
    variables: List[Dict[str, str]] = []

class SnippetCreate(BaseModel):
    title: str
    code: str
    language: str = "javascript"
    tags: Optional[str] = None

@api_router.post("/code-review/analyze")
async def review_code(request: CodeReviewRequest):
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    
    try:
        prompt = f"""Review this {request.language} code and provide:

1. Issues found (errors, warnings, best practices)
2. Security vulnerabilities
3. Performance improvements
4. Fixed/improved version of the code

Code:
```{request.language}
{request.code}
```

Format response as JSON:
{{
  "issues": [
    {{"severity": "error|warning|info", "title": "...", "description": "...", "line": 0, "suggestion": "..."}},
    ...
  ],
  "summary": "Overall assessment...",
  "fixed_code": "Fixed version of the code..."
}}"""
        
        response = ollama_client.chat(
            model=_default_model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response['message']['content']
        try:
            # Extract JSON from markdown code blocks if present
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                content = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.find("```") + 3
                json_end = content.find("```", json_start)
                content = content[json_start:json_end].strip()
            
            analysis = json.loads(content)
        except:
            # If JSON parsing fails, create structured response from text
            analysis = {
                "issues": [{
                    "severity": "info",
                    "title": "Analysis Complete",
                    "description": content[:500],
                    "suggestion": "Review the full analysis"
                }],
                "summary": content,
                "fixed_code": ""
            }
        
        return {"analysis": analysis, "fixed_code": analysis.get("fixed_code", "")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review error: {str(e)}")

# Git Integration
@api_router.get("/git/status")
async def git_status():
    try:
        result = subprocess.run(
            "cd /app && git status --porcelain -b",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        # Check if git repo exists
        if result.returncode != 0:
            return {
                "initialized": False,
                "branch": None,
                "modified": [],
                "staged": []
            }
        
        lines = result.stdout.strip().split('\n')
        branch = lines[0].split('/')[-1] if lines else 'main'
        
        modified = []
        staged = []
        for line in lines[1:]:
            if line:
                status = line[:2]
                filename = line[3:]
                if 'M' in status or '?' in status:
                    modified.append(filename)
                if status[0] in ['A', 'M', 'D']:
                    staged.append(filename)
        
        return {
            "initialized": True,
            "branch": branch,
            "modified": modified,
            "staged": staged,
            "branches": []
        }
    except Exception as e:
        return {
            "initialized": False,
            "branch": None,
            "modified": [],
            "staged": []
        }

@api_router.post("/git/init")
async def git_init():
    try:
        result = subprocess.run(
            "cd /app && git init",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # Configure git user
            subprocess.run("cd /app && git config user.name 'Mini Assistant'", shell=True)
            subprocess.run("cd /app && git config user.email 'mini@assistant.ai'", shell=True)
            return {"success": True, "message": "Repository initialized"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Init error: {str(e)}")

@api_router.post("/git/add")
async def git_add(files: List[str] = ["."])  :
    try:
        file_list = " ".join(files)
        result = subprocess.run(
            f"cd /app && git add {file_list}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return {"success": True, "message": "Files staged"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Add error: {str(e)}")

@api_router.post("/git/commit")
async def git_commit(request: GitCommitRequest):
    try:
        result = subprocess.run(
            f'cd /app && git commit -m "{request.message}"',
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 or "nothing to commit" in result.stdout:
            return {"success": True, "message": "Changes committed"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr or result.stdout)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Commit error: {str(e)}")

@api_router.post("/git/push")
async def git_push(request: GitPushRequest):
    try:
        result = subprocess.run(
            f"cd /app && git push {request.remote} {request.branch}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return {"success": True, "message": "Pushed successfully"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr or "Push failed. Make sure remote is configured and you have permissions.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Push error: {str(e)}")

@api_router.post("/git/pull")
async def git_pull(request: GitPullRequest):
    try:
        result = subprocess.run(
            f"cd /app && git pull {request.remote} {request.branch}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return {"success": True, "message": "Pulled successfully"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr or "Pull failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pull error: {str(e)}")

@api_router.post("/git/remote/add")
async def git_add_remote(request: GitRemoteRequest):
    try:
        result = subprocess.run(
            f"cd /app && git remote add {request.name} {request.url}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            return {"success": True, "message": f"Remote '{request.name}' added"}
        else:
            # Try removing and re-adding if already exists
            subprocess.run(f"cd /app && git remote remove {request.name}", shell=True, capture_output=True)
            result = subprocess.run(
                f"cd /app && git remote add {request.name} {request.url}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return {"success": True, "message": f"Remote '{request.name}' updated"}
            raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Remote add error: {str(e)}")

@api_router.post("/git/branch/create")
async def git_create_branch(request: GitBranchRequest):
    try:
        result = subprocess.run(
            f"cd /app && git checkout -b {request.name}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            return {"success": True, "message": f"Branch '{request.name}' created"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Branch create error: {str(e)}")

# Code Runner
@api_router.post("/code-runner/execute")
async def execute_code(request: CodeRunRequest):
    try:
        if request.language == "python":
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(request.code)
                temp_file = f.name
            
            result = subprocess.run(
                f"python3 {temp_file}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=request.timeout
            )
            os.unlink(temp_file)
            
        elif request.language in ["javascript", "nodejs"]:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(request.code)
                temp_file = f.name
            
            result = subprocess.run(
                f"node {temp_file}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=request.timeout
            )
            os.unlink(temp_file)
        else:
            raise HTTPException(status_code=400, detail="Unsupported language")
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Execution timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")

# API Tester
@api_router.post("/api-tester/request")
async def test_api(request: APITestRequest):
    try:
        import requests as req_lib
        
        method = request.method.upper()
        headers = request.headers or {}
        
        if method == "GET":
            response = req_lib.get(request.url, headers=headers, timeout=10)
        elif method == "POST":
            body_data = json.loads(request.body) if request.body else None
            response = req_lib.post(request.url, json=body_data, headers=headers, timeout=10)
        elif method == "PUT":
            body_data = json.loads(request.body) if request.body else None
            response = req_lib.put(request.url, json=body_data, headers=headers, timeout=10)
        elif method == "PATCH":
            body_data = json.loads(request.body) if request.body else None
            response = req_lib.patch(request.url, json=body_data, headers=headers, timeout=10)
        elif method == "DELETE":
            response = req_lib.delete(request.url, headers=headers, timeout=10)
        else:
            raise HTTPException(status_code=400, detail="Unsupported method")
        
        try:
            response_data = response.json()
        except:
            response_data = response.text
        
        return {
            "status": response.status_code,
            "headers": dict(response.headers),
            "data": response_data
        }
    except req_lib.exceptions.Timeout:
        raise HTTPException(status_code=408, detail="Request timeout")
    except req_lib.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API test error: {str(e)}")

# Package Manager
@api_router.get("/packages/list")
async def list_packages(type: str = "npm"):
    try:
        if type == "npm":
            result = subprocess.run(
                "cd /app/frontend && npm list --depth=0 --json",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                packages = [{"name": k, "version": v.get("version")} for k, v in data.get("dependencies", {}).items()]
                return {"packages": packages}
        elif type == "pip":
            result = subprocess.run(
                "pip list --format=json",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                return {"packages": packages}
        
        return {"packages": []}
    except Exception as e:
        return {"packages": []}

@api_router.post("/packages/install")
async def install_package(request: PackageInstallRequest):
    try:
        if request.type == "npm":
            result = subprocess.run(
                f"cd /app/frontend && yarn add {request.package}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
        elif request.type == "pip":
            result = subprocess.run(
                f"pip install {request.package} && pip freeze > /app/backend/requirements.txt",
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid package type")
        
        if result.returncode == 0:
            return {"success": True, "message": f"{request.package} installed"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Install error: {str(e)}")

@api_router.post("/packages/uninstall")
async def uninstall_package(request: PackageInstallRequest):
    try:
        if request.type == "npm":
            result = subprocess.run(
                f"cd /app/frontend && yarn remove {request.package}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
        elif request.type == "pip":
            result = subprocess.run(
                f"pip uninstall -y {request.package} && pip freeze > /app/backend/requirements.txt",
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid package type")
        
        if result.returncode == 0:
            return {"success": True, "message": f"{request.package} uninstalled"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Uninstall error: {str(e)}")

# Environment Manager
@api_router.get("/env/read")
async def read_env(type: str = "frontend"):
    try:
        env_path = "/app/frontend/.env" if type == "frontend" else "/app/backend/.env"
        if not Path(env_path).exists():
            return {"variables": []}
        
        variables = []
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    variables.append({"id": len(variables), "key": key, "value": value})
        
        return {"variables": variables}
    except Exception as e:
        return {"variables": []}

@api_router.post("/env/write")
async def write_env(request: EnvVarRequest):
    try:
        env_path = "/app/frontend/.env" if request.type == "frontend" else "/app/backend/.env"
        
        with open(env_path, 'w') as f:
            for var in request.variables:
                if var.get('key'):
                    f.write(f"{var['key']}={var.get('value', '')}\\n")
        
        return {"success": True, "message": "Environment variables saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Write error: {str(e)}")

# Snippet Library
@api_router.get("/snippets/list")
async def list_snippets():
    _require_db()
    snippets = await db.snippets.find({}, {"_id": 0}).to_list(1000)
    return {"snippets": snippets}

@api_router.post("/snippets/create")
async def create_snippet(snippet: SnippetCreate):
    _require_db()
    snippet_dict = snippet.model_dump()
    snippet_dict["id"] = str(uuid.uuid4())
    snippet_dict["created_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.snippets.insert_one(snippet_dict)
    return {"success": True, "id": snippet_dict["id"]}

@api_router.delete("/snippets/delete/{snippet_id}")
async def delete_snippet(snippet_id: str):
    _require_db()
    result = await db.snippets.delete_one({"id": snippet_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Snippet not found")
    return {"success": True}

# Conversation Summarization
class SummarizeRequest(BaseModel):
    messages: List[ChatMessage]
    model: str = _default_model

@api_router.post("/chat/summarize")
async def summarize_conversation(request: SummarizeRequest):
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    
    try:
        conversation_text = "\n".join([f"{msg.role}: {msg.content}" for msg in request.messages])
        
        summary_prompt = f"""Please provide a concise summary of this conversation. Include:
1. Key topics discussed
2. Important decisions or conclusions
3. Any action items mentioned

Conversation:
{conversation_text}

Summary:"""
        
        response = ollama_client.chat(
            model=request.model,
            messages=[{"role": "user", "content": summary_prompt}]
        )
        
        return {"summary": response['message']['content']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization error: {str(e)}")

# Security Scanner
class SecurityScanRequest(BaseModel):
    code: str

@api_router.post("/security/scan")
async def security_scan(request: SecurityScanRequest):
    vulnerabilities = []
    code = request.code
    
    # Check for common security issues
    security_patterns = [
        {"pattern": "eval(", "title": "Dangerous eval() usage", "severity": "critical", "description": "eval() can execute arbitrary code", "fix": "Use safer alternatives like JSON.parse()"},
        {"pattern": "exec(", "title": "Dangerous exec() usage", "severity": "critical", "description": "exec() can execute arbitrary system commands", "fix": "Use subprocess with proper input validation"},
        {"pattern": "dangerouslySetInnerHTML", "title": "XSS Risk", "severity": "high", "description": "May allow XSS attacks", "fix": "Sanitize HTML content before rendering"},
        {"pattern": "password", "title": "Hardcoded Password", "severity": "high", "description": "Password found in code", "fix": "Use environment variables for secrets"},
        {"pattern": "api_key", "title": "Exposed API Key", "severity": "high", "description": "API key found in code", "fix": "Use environment variables"},
        {"pattern": "secret", "title": "Potential Secret Exposure", "severity": "medium", "description": "Secret keyword found", "fix": "Review and secure sensitive data"},
        {"pattern": "http://", "title": "Insecure HTTP", "severity": "medium", "description": "Using HTTP instead of HTTPS", "fix": "Use HTTPS for secure communication"},
        {"pattern": "SELECT * FROM", "title": "SQL Injection Risk", "severity": "high", "description": "Raw SQL query detected", "fix": "Use parameterized queries"},
        {"pattern": "pickle.load", "title": "Unsafe Deserialization", "severity": "critical", "description": "Pickle can execute arbitrary code", "fix": "Use safer formats like JSON"},
        {"pattern": "shell=True", "title": "Shell Injection Risk", "severity": "high", "description": "subprocess with shell=True is risky", "fix": "Use shell=False with argument list"},
    ]
    
    for i, line in enumerate(code.split('\n'), 1):
        for pattern in security_patterns:
            if pattern["pattern"].lower() in line.lower():
                vulnerabilities.append({
                    "line": i,
                    "code": line.strip(),
                    **{k: v for k, v in pattern.items() if k != "pattern"}
                })
    
    return {"vulnerabilities": vulnerabilities, "scanned_lines": len(code.split('\n'))}

# Deployment
class DeployRequest(BaseModel):
    platform: str
    project_path: str = "/app"

@api_router.post("/deploy/start")
async def start_deployment(request: DeployRequest):
    # Mock deployment - in real scenario, this would integrate with Vercel/Netlify/Railway APIs
    return {
        "status": "initiated",
        "platform": request.platform,
        "message": f"Deployment to {request.platform} would be initiated here. Configure your {request.platform} API token to enable real deployments.",
        "url": f"https://your-app.{request.platform}.app"
    }

# Docker Management (Mock - requires Docker to be available)
@api_router.get("/docker/containers")
async def list_docker_containers():
    try:
        result = subprocess.run(
            "docker ps -a --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}'",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        containers = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split('|')
                if len(parts) >= 4:
                    containers.append({
                        "id": parts[0],
                        "name": parts[1],
                        "image": parts[2],
                        "status": "running" if "Up" in parts[3] else "stopped"
                    })
        
        return {"containers": containers}
    except Exception as e:
        return {"containers": [], "error": str(e)}

@api_router.post("/docker/start/{container_id}")
async def start_docker_container(container_id: str):
    try:
        result = subprocess.run(
            f"docker start {container_id}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        return {"success": result.returncode == 0, "output": result.stdout}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/docker/stop/{container_id}")
async def stop_docker_container(container_id: str):
    try:
        result = subprocess.run(
            f"docker stop {container_id}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        return {"success": result.returncode == 0, "output": result.stdout}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Performance Monitor
@api_router.get("/monitor/performance")
async def get_performance_metrics():
    try:
        import psutil
        
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        boot_time = psutil.boot_time()
        
        uptime_seconds = datetime.now().timestamp() - boot_time
        hours, remainder = divmod(int(uptime_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"
        
        return {
            "cpu": round(cpu_percent, 1),
            "memory": round(memory.percent, 1),
            "disk": round(disk.percent, 1),
            "uptime": uptime_str
        }
    except ImportError:
        return {
            "cpu": 0,
            "memory": 0,
            "disk": 0,
            "uptime": "N/A",
            "error": "psutil not installed"
        }

# Codebase search
@api_router.post("/search/codebase")
async def search_codebase(request: CodeSearchRequest):
    try:
        result = subprocess.run(
            f"grep -r -n '{request.query}' {request.path} --include='*.py' --include='*.js' --include='*.jsx' --include='*.ts' --include='*.tsx' | head -n {request.max_results}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        results = []
        for line in result.stdout.split('\n'):
            if line.strip():
                parts = line.split(':', 2)
                if len(parts) >= 3:
                    results.append({
                        "file": parts[0],
                        "line": parts[1],
                        "content": parts[2]
                    })
        
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")

# ==================== PostgreSQL Integration ====================
class PostgresConnectRequest(BaseModel):
    connection_string: str

class PostgresQueryRequest(BaseModel):
    connection_string: str
    query: str

postgres_pool = None

@api_router.post("/postgres/connect")
async def postgres_connect(request: PostgresConnectRequest):
    try:
        import asyncpg
        conn = await asyncpg.connect(request.connection_string)
        version = await conn.fetchval('SELECT version()')
        await conn.close()
        return {"connected": True, "version": version}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PostgreSQL connection failed: {str(e)}")

@api_router.post("/postgres/query")
async def postgres_query(request: PostgresQueryRequest):
    try:
        import asyncpg
        conn = await asyncpg.connect(request.connection_string)
        
        # Check if it's a SELECT query
        is_select = request.query.strip().upper().startswith('SELECT')
        
        if is_select:
            rows = await conn.fetch(request.query)
            columns = list(rows[0].keys()) if rows else []
            data = [dict(row) for row in rows]
            await conn.close()
            return {"columns": columns, "data": data, "rowCount": len(data)}
        else:
            result = await conn.execute(request.query)
            await conn.close()
            return {"result": result, "rowCount": 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query error: {str(e)}")

@api_router.post("/postgres/tables")
async def postgres_tables(request: PostgresConnectRequest):
    try:
        import asyncpg
        conn = await asyncpg.connect(request.connection_string)
        rows = await conn.fetch("""
            SELECT table_name, table_schema 
            FROM information_schema.tables 
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
        """)
        await conn.close()
        return {"tables": [{"name": r['table_name'], "schema": r['table_schema']} for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list tables: {str(e)}")

@api_router.post("/postgres/schema")
async def postgres_schema(request: PostgresQueryRequest):
    try:
        import asyncpg
        conn = await asyncpg.connect(request.connection_string)
        # request.query contains table name
        rows = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = $1
            ORDER BY ordinal_position
        """, request.query)
        await conn.close()
        return {"columns": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schema error: {str(e)}")

# ==================== Redis Integration ====================
class RedisConnectRequest(BaseModel):
    host: str = "localhost"
    port: int = 6379
    password: Optional[str] = None
    db: int = 0

class RedisCommandRequest(BaseModel):
    host: str
    port: int = 6379
    password: Optional[str] = None
    db: int = 0
    command: str
    args: List[str] = []

@api_router.post("/redis/connect")
async def redis_connect(request: RedisConnectRequest):
    try:
        import redis.asyncio as redis
        r = redis.Redis(
            host=request.host, 
            port=request.port, 
            password=request.password, 
            db=request.db,
            decode_responses=True
        )
        info = await r.info()
        await r.close()
        return {
            "connected": True, 
            "version": info.get('redis_version'),
            "used_memory": info.get('used_memory_human'),
            "connected_clients": info.get('connected_clients')
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis connection failed: {str(e)}")

@api_router.post("/redis/keys")
async def redis_keys(request: RedisConnectRequest):
    try:
        import redis.asyncio as redis
        r = redis.Redis(
            host=request.host, 
            port=request.port, 
            password=request.password, 
            db=request.db,
            decode_responses=True
        )
        keys = await r.keys('*')
        # Get types for each key
        key_data = []
        for key in keys[:100]:  # Limit to 100 keys
            key_type = await r.type(key)
            ttl = await r.ttl(key)
            key_data.append({"key": key, "type": key_type, "ttl": ttl})
        await r.close()
        return {"keys": key_data, "total": len(keys)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list keys: {str(e)}")

@api_router.post("/redis/get")
async def redis_get(request: RedisCommandRequest):
    try:
        import redis.asyncio as redis
        r = redis.Redis(
            host=request.host, 
            port=request.port, 
            password=request.password, 
            db=request.db,
            decode_responses=True
        )
        key = request.args[0] if request.args else ""
        key_type = await r.type(key)
        
        value = None
        if key_type == 'string':
            value = await r.get(key)
        elif key_type == 'list':
            value = await r.lrange(key, 0, -1)
        elif key_type == 'set':
            value = list(await r.smembers(key))
        elif key_type == 'hash':
            value = await r.hgetall(key)
        elif key_type == 'zset':
            value = await r.zrange(key, 0, -1, withscores=True)
        
        await r.close()
        return {"key": key, "type": key_type, "value": value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis get error: {str(e)}")

@api_router.post("/redis/set")
async def redis_set(request: RedisCommandRequest):
    try:
        import redis.asyncio as redis
        r = redis.Redis(
            host=request.host, 
            port=request.port, 
            password=request.password, 
            db=request.db,
            decode_responses=True
        )
        key = request.args[0] if len(request.args) > 0 else ""
        value = request.args[1] if len(request.args) > 1 else ""
        await r.set(key, value)
        await r.close()
        return {"success": True, "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis set error: {str(e)}")

@api_router.post("/redis/delete")
async def redis_delete(request: RedisCommandRequest):
    try:
        import redis.asyncio as redis
        r = redis.Redis(
            host=request.host, 
            port=request.port, 
            password=request.password, 
            db=request.db,
            decode_responses=True
        )
        key = request.args[0] if request.args else ""
        result = await r.delete(key)
        await r.close()
        return {"success": result > 0, "deleted": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis delete error: {str(e)}")

# ==================== Railway Integration ====================
class RailwayRequest(BaseModel):
    api_token: str
    project_id: Optional[str] = None

@api_router.post("/railway/projects")
async def railway_projects(request: RailwayRequest):
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://backboard.railway.app/graphql/v2",
                headers={
                    "Authorization": f"Bearer {request.api_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "query": """
                        query {
                            me {
                                projects {
                                    edges {
                                        node {
                                            id
                                            name
                                            description
                                            createdAt
                                            environments {
                                                edges {
                                                    node {
                                                        id
                                                        name
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    """
                }
            ) as resp:
                data = await resp.json()
                if 'errors' in data:
                    raise HTTPException(status_code=400, detail=data['errors'][0]['message'])
                projects = data.get('data', {}).get('me', {}).get('projects', {}).get('edges', [])
                return {"projects": [p['node'] for p in projects]}
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=500, detail=f"Railway API error: {str(e)}")

@api_router.post("/railway/services")
async def railway_services(request: RailwayRequest):
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://backboard.railway.app/graphql/v2",
                headers={
                    "Authorization": f"Bearer {request.api_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "query": """
                        query($projectId: String!) {
                            project(id: $projectId) {
                                services {
                                    edges {
                                        node {
                                            id
                                            name
                                            icon
                                        }
                                    }
                                }
                            }
                        }
                    """,
                    "variables": {"projectId": request.project_id}
                }
            ) as resp:
                data = await resp.json()
                if 'errors' in data:
                    raise HTTPException(status_code=400, detail=data['errors'][0]['message'])
                services = data.get('data', {}).get('project', {}).get('services', {}).get('edges', [])
                return {"services": [s['node'] for s in services]}
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=500, detail=f"Railway API error: {str(e)}")

@api_router.post("/railway/deploy")
async def railway_deploy(request: RailwayRequest):
    # Trigger a deployment via Railway API
    return {
        "status": "Deploy triggered",
        "message": "Use Railway CLI or GitHub integration for automatic deployments",
        "docs": "https://docs.railway.app/guides/github-autodeploys"
    }

# ==================== Auto Error Fix (FixLoop with Screenshots) ====================
class ErrorFixRequest(BaseModel):
    url: str
    error_description: Optional[str] = None
    auto_fix: bool = True
    model: str = _default_model
    capture_screenshot: bool = True

class FixLoopSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    screenshots: List[str] = []
    errors: List[Dict] = []
    fixes_applied: List[Dict] = []
    status: str = "running"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Screenshot storage directory
SCREENSHOT_DIR = ROOT_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

async def capture_page_screenshot(url: str, session_id: str) -> Dict:
    """Capture a screenshot of a webpage using Playwright"""
    # Blob URLs are browser-side memory objects and cannot be navigated by the server.
    if url.startswith("blob:"):
        return {
            "success": False,
            "error": (
                "Blob URL detected. Blob URLs are browser-memory objects and cannot be "
                "opened server-side. Use the App Builder's built-in Edit conversation to "
                "test and fix generated apps, or open them in a full tab and submit their "
                "preview URL instead."
            ),
            "console_logs": [],
            "page_errors": [],
            "blob_url": True
        }

    try:
        from playwright.async_api import async_playwright

        screenshot_path = SCREENSHOT_DIR / f"{session_id}.png"
        console_logs = []
        page_errors = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1920, "height": 1080})
            page = await context.new_page()

            # Capture console logs
            page.on("console", lambda msg: console_logs.append({
                "type": msg.type,
                "text": msg.text,
                "location": str(msg.location) if msg.location else None
            }))

            # Capture page errors
            page.on("pageerror", lambda err: page_errors.append({
                "type": "PageError",
                "message": str(err),
                "severity": "critical"
            }))

            try:
                # Navigate to URL
                response = await page.goto(url, timeout=30000, wait_until="networkidle")
                
                # Wait a bit for any dynamic content
                await page.wait_for_timeout(2000)
                
                # Take screenshot
                await page.screenshot(path=str(screenshot_path), full_page=False)
                
                # Get HTTP status
                status_code = response.status if response else 0
                
                await browser.close()
                
                return {
                    "success": True,
                    "screenshot_path": str(screenshot_path),
                    "screenshot_filename": f"{session_id}.png",
                    "status_code": status_code,
                    "console_logs": console_logs[-20:],  # Last 20 logs
                    "page_errors": page_errors
                }
            except Exception as nav_error:
                # Still try to take a screenshot of the error state
                try:
                    await page.screenshot(path=str(screenshot_path), full_page=False)
                except:
                    pass
                await browser.close()
                
                return {
                    "success": False,
                    "screenshot_path": str(screenshot_path) if screenshot_path.exists() else None,
                    "screenshot_filename": f"{session_id}.png" if screenshot_path.exists() else None,
                    "error": str(nav_error),
                    "console_logs": console_logs[-20:],
                    "page_errors": page_errors
                }
    except Exception as e:
        return {
            "success": False,
            "error": f"Screenshot capture failed: {str(e)}",
            "console_logs": [],
            "page_errors": []
        }

@api_router.post("/fixloop/start")
async def fixloop_start(request: ErrorFixRequest):
    try:
        import aiohttp
        import base64
        
        session_id = str(uuid.uuid4())
        errors_found = []
        screenshot_data = None
        console_errors = []
        
        # Capture screenshot if enabled
        if request.capture_screenshot:
            screenshot_result = await capture_page_screenshot(request.url, session_id)
            
            if screenshot_result.get("screenshot_path"):
                screenshot_data = {
                    "filename": screenshot_result.get("screenshot_filename"),
                    "url": f"/api/fixloop/screenshot/{session_id}"
                }
            
            # Extract errors from console logs
            for log in screenshot_result.get("console_logs", []):
                if log["type"] in ["error", "warning"]:
                    console_errors.append({
                        "type": f"Console {log['type'].title()}",
                        "message": log["text"][:500],  # Limit message length
                        "severity": "high" if log["type"] == "error" else "medium"
                    })
            
            # Add page errors
            errors_found.extend(screenshot_result.get("page_errors", []))
            
            # Check HTTP status
            status_code = screenshot_result.get("status_code", 0)
            if status_code >= 400:
                errors_found.append({
                    "type": "HTTP Error",
                    "message": f"HTTP {status_code}",
                    "severity": "high" if status_code >= 500 else "medium"
                })
            
            # Add console errors
            errors_found.extend(console_errors[:10])  # Limit to 10 console errors
            
            if not screenshot_result.get("success") and screenshot_result.get("error"):
                errors_found.append({
                    "type": "Navigation Error",
                    "message": screenshot_result.get("error"),
                    "severity": "critical"
                })
        else:
            # Fallback to HTTP fetch without screenshot
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(request.url, timeout=10) as resp:
                        status_code = resp.status
                        content = await resp.text()
                        
                        if status_code >= 400:
                            errors_found.append({
                                "type": "HTTP Error",
                                "message": f"HTTP {status_code}",
                                "severity": "high" if status_code >= 500 else "medium"
                            })
                        
                        # Check for error patterns in content
                        error_patterns = [
                            ("TypeError:", "JavaScript TypeError"),
                            ("ReferenceError:", "JavaScript ReferenceError"),
                            ("SyntaxError:", "JavaScript SyntaxError"),
                            ("Cannot read property", "Null Reference Error"),
                            ("undefined is not", "Undefined Error"),
                            ("Uncaught", "Uncaught Exception"),
                            ("Error:", "General Error"),
                            ("failed to compile", "Compilation Error"),
                            ("Module not found", "Module Not Found"),
                        ]
                        
                        for pattern, error_type in error_patterns:
                            if pattern.lower() in content.lower():
                                errors_found.append({
                                    "type": error_type,
                                    "pattern": pattern,
                                    "severity": "high"
                                })
            except Exception as fetch_error:
                errors_found.append({
                    "type": "Connection Error",
                    "message": str(fetch_error),
                    "severity": "critical"
                })
        
        # Store session in DB
        fixloop_session = {
            "id": session_id,
            "url": request.url,
            "errors": errors_found,
            "screenshot": screenshot_data,
            "status": "analyzed",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        if db is not None:
            await db.fixloop_sessions.insert_one(fixloop_session)
        
        # If errors found and auto_fix enabled, try to generate fixes
        suggested_fixes = []
        if errors_found and request.auto_fix and ollama_client:
            try:
                fix_prompt = f"""Analyze these errors from a web app and suggest specific fixes.

URL: {request.url}
Errors found:
{json.dumps(errors_found, indent=2)}

{f"Additional context: {request.error_description}" if request.error_description else ""}

For each error, provide:
1. Which file it most likely belongs to (index.html, style.css, or script.js)
2. What the root cause is
3. The exact code fix (show a before/after snippet if possible)

Format as a numbered list. Be specific — do not give generic advice."""

                response = ollama_client.chat(
                    model=request.model,
                    messages=[{"role": "user", "content": fix_prompt}]
                )
                suggested_fixes = [{"suggestion": response['message']['content']}]
            except:
                pass
        
        return {
            "session_id": session_id,
            "url": request.url,
            "errors": errors_found,
            "screenshot": screenshot_data,
            "suggested_fixes": suggested_fixes,
            "status": "completed"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FixLoop error: {str(e)}")

@api_router.get("/fixloop/screenshot/{session_id}")
async def get_fixloop_screenshot(session_id: str):
    """Serve the screenshot image for a FixLoop session"""
    screenshot_path = SCREENSHOT_DIR / f"{session_id}.png"
    if not screenshot_path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(screenshot_path, media_type="image/png")

@api_router.get("/fixloop/sessions")
async def fixloop_sessions():
    _require_db()
    sessions = await db.fixloop_sessions.find({}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    return {"sessions": sessions}

# ==================== Tester Agent ====================
class TestRequest(BaseModel):
    url: str
    test_type: str = "smoke"  # smoke, functional, api, e2e
    endpoints: List[str] = []
    assertions: List[Dict] = []
    model: str = _default_model

class TestCase(BaseModel):
    name: str
    type: str
    endpoint: Optional[str] = None
    method: str = "GET"
    expected_status: int = 200
    body: Optional[Dict] = None
    assertions: List[str] = []

@api_router.post("/tester/run")
async def tester_run(request: TestRequest):
    try:
        import aiohttp
        
        test_results = []
        
        # Basic smoke test - check if URL is accessible
        if request.test_type in ["smoke", "e2e"]:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(request.url, timeout=10) as resp:
                        test_results.append({
                            "name": "Smoke Test - URL Accessible",
                            "status": "PASS" if resp.status == 200 else "FAIL",
                            "details": f"HTTP {resp.status}",
                            "duration": "< 1s"
                        })
            except Exception as e:
                test_results.append({
                    "name": "Smoke Test - URL Accessible",
                    "status": "FAIL",
                    "details": str(e),
                    "duration": "N/A"
                })
        
        # API endpoint tests
        if request.test_type in ["api", "functional", "e2e"] and request.endpoints:
            async with aiohttp.ClientSession() as session:
                for endpoint in request.endpoints:
                    full_url = f"{request.url.rstrip('/')}{endpoint}"
                    try:
                        async with session.get(full_url, timeout=10) as resp:
                            test_results.append({
                                "name": f"API Test - {endpoint}",
                                "status": "PASS" if resp.status < 400 else "FAIL",
                                "details": f"HTTP {resp.status}",
                                "endpoint": endpoint
                            })
                    except Exception as e:
                        test_results.append({
                            "name": f"API Test - {endpoint}",
                            "status": "FAIL",
                            "details": str(e),
                            "endpoint": endpoint
                        })
        
        # Generate AI-powered test suggestions
        ai_suggestions = []
        if ollama_client:
            try:
                suggest_prompt = f"""Based on this URL and test results, suggest additional test cases:

URL: {request.url}
Test Type: {request.test_type}
Current Results: {json.dumps(test_results, indent=2)}

Suggest 3-5 specific test cases that would improve coverage. Format as a numbered list."""

                response = ollama_client.chat(
                    model=request.model,
                    messages=[{"role": "user", "content": suggest_prompt}]
                )
                ai_suggestions = response['message']['content']
            except:
                pass
        
        # Calculate summary
        passed = sum(1 for t in test_results if t['status'] == 'PASS')
        failed = sum(1 for t in test_results if t['status'] == 'FAIL')
        
        # Store test run
        test_run = {
            "id": str(uuid.uuid4()),
            "url": request.url,
            "test_type": request.test_type,
            "results": test_results,
            "summary": {"passed": passed, "failed": failed, "total": len(test_results)},
            "ai_suggestions": ai_suggestions,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        if db is not None:
            await db.test_runs.insert_one(test_run)
        
        return {
            "test_run_id": test_run["id"],
            "url": request.url,
            "results": test_results,
            "summary": {"passed": passed, "failed": failed, "total": len(test_results)},
            "ai_suggestions": ai_suggestions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tester error: {str(e)}")

@api_router.post("/tester/generate")
async def tester_generate_tests(request: TestRequest):
    """Generate test cases using AI"""
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama not available")
    
    try:
        prompt = f"""Generate comprehensive test cases for this application:

URL: {request.url}
Test Type: {request.test_type}
Endpoints to test: {json.dumps(request.endpoints) if request.endpoints else "Auto-detect"}

Generate a JSON array of test cases with this structure:
[
  {{
    "name": "Test name",
    "type": "smoke|api|functional|e2e",
    "endpoint": "/api/example",
    "method": "GET|POST|PUT|DELETE",
    "expected_status": 200,
    "assertions": ["Response contains X", "Status is 200"]
  }}
]

Generate 5-10 realistic test cases."""

        response = ollama_client.chat(
            model=request.model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return {"generated_tests": response['message']['content']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test generation error: {str(e)}")

@api_router.get("/tester/history")
async def tester_history():
    _require_db()
    runs = await db.test_runs.find({}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    return {"test_runs": runs}

# Health check
@api_router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "ollama": "connected" if ollama_client else "disconnected",
        "whisper": "loaded" if whisper_model else "not_loaded"
    }

# ==================== Multi-Brain Assistant API ====================
try:
    from mini_assistant import MiniAssistant
    from mini_assistant.router import route as _route_msg, get_registered_matchers
    _MINI_ASSISTANT_OK = True
except ImportError as _import_err:
    logger.error(
        "DEPENDENCY ERROR: mini_assistant failed to import: %s. "
        "Ensure all packages in requirements.txt are installed.",
        _import_err,
    )
    MiniAssistant = None  # type: ignore[assignment,misc]
    _route_msg = None  # type: ignore[assignment]
    get_registered_matchers = lambda: []  # type: ignore[assignment]
    _MINI_ASSISTANT_OK = False

_assistant: "MiniAssistant | None" = None


def _get_assistant() -> "MiniAssistant":
    if not _MINI_ASSISTANT_OK:
        raise HTTPException(
            status_code=503,
            detail=(
                "Mini Assistant is unavailable: a required dependency failed to import. "
                "Check the server logs for the exact missing package."
            ),
        )
    global _assistant
    if _assistant is None:
        _assistant = MiniAssistant()
    return _assistant


class AssistantChatRequest(BaseModel):
    message: str
    images: List[str] = []
    history: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}
    mode: Optional[str] = None  # "single" | "swarm" – overrides server default


class AssistantLearnTextRequest(BaseModel):
    text: str
    source: str = "manual"


class AssistantLearnFileRequest(BaseModel):
    file_path: str


@api_router.post("/assistant/chat")
async def assistant_chat(request: AssistantChatRequest):
    try:
        assistant = _get_assistant()
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: assistant.chat(
                message=request.message,
                images=request.images or [],
                history=request.history or [],
                metadata=request.metadata or {},
                mode=request.mode,
            ),
        )
        return {
            "reply":           response.text,
            "brain":           response.brain,
            "task":            response.task,
            "model":           response.model,
            "routing_method":  response.routing_method,
            "tests_passed":    response.tests_passed,
            "tests_run":       response.tests_run,
            "review_passed":   response.review_passed,
            "review_score":    response.review_score,
            "repair_attempts": response.repair_attempts,
        }
    except Exception as exc:
        logger.exception("assistant_chat failed")
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post("/assistant/learn/text")
async def assistant_learn_text(request: AssistantLearnTextRequest):
    try:
        assistant = _get_assistant()
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: assistant.learn_text(request.text, source=request.source),
        )
        return {"success": True, "chunks_added": result.get("chunks", 0)}
    except Exception as exc:
        logger.exception("assistant_learn_text failed")
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post("/assistant/learn/file")
async def assistant_learn_file(request: AssistantLearnFileRequest):
    try:
        assistant = _get_assistant()
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: assistant.learn_file(request.file_path),
        )
        return {"success": True, "chunks_added": result.get("chunks", 0)}
    except Exception as exc:
        logger.exception("assistant_learn_file failed")
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get("/assistant/memory/search")
async def assistant_memory_search(q: str, top_k: int = 5):
    try:
        assistant = _get_assistant()
        results = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: assistant.memory_search(q, top_k=top_k),
        )
        return {"results": results}
    except Exception as exc:
        logger.exception("assistant_memory_search failed")
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get("/assistant/route/info")
async def assistant_route_info(message: str):
    try:
        result = _route_msg(message)
        return {
            "brain": result.brain,
            "task": result.task,
            "model": result.model,
            "routing_method": result.routing_method,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get("/assistant/matchers")
async def assistant_matchers():
    matchers = get_registered_matchers()
    return {
        "matchers": [
            {"name": type(m).__name__, "priority": m.priority}
            for m in matchers
        ]
    }


@api_router.get("/assistant/status")
async def assistant_status():
    try:
        return _get_assistant().status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get("/assistant/solutions")
async def assistant_solutions(q: str = "", top_k: int = 10):
    try:
        assistant = _get_assistant()
        if q:
            return {"solutions": assistant.find_solutions(q, top_k=top_k)}
        return {"solutions": assistant._solutions.all_solutions()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get("/assistant/reflections")
async def assistant_reflections(n: int = 20):
    try:
        return {"reflections": _get_assistant().recent_reflections(n)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class StoreFactRequest(BaseModel):
    key: str
    value: Any


@api_router.post("/assistant/facts")
async def assistant_store_fact(request: StoreFactRequest):
    try:
        _get_assistant().store_fact(request.key, request.value)
        return {"success": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get("/assistant/facts")
async def assistant_get_facts():
    try:
        return {"facts": _get_assistant()._long_term.all_facts()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



# ── Mode endpoints ────────────────────────────────────────────────────────────

class SetModeRequest(BaseModel):
    mode: str  # "single" | "swarm"


@api_router.get("/assistant/mode")
async def get_assistant_mode():
    """Return the current assistant execution mode."""
    try:
        assistant = _get_assistant()
        return {"mode": assistant.mode}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post("/assistant/mode")
async def set_assistant_mode(request: SetModeRequest):
    """Switch the assistant execution mode at runtime."""
    if request.mode not in ("single", "swarm"):
        raise HTTPException(status_code=400, detail="mode must be 'single' or 'swarm'")
    try:
        assistant = _get_assistant()
        assistant.set_mode(request.mode)
        return {"mode": assistant.mode}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Swarm endpoints ───────────────────────────────────────────────────────────

class SwarmRunRequest(BaseModel):
    request: str
    mode: Optional[str] = None  # ignored – always runs swarm pipeline


@api_router.post("/swarm/run")
async def swarm_run(body: SwarmRunRequest):
    """Run a request directly through the full swarm pipeline."""
    try:
        assistant = _get_assistant()
        swarm_result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: assistant._get_swarm().run(body.request),
        )
        return {
            "run_id":           swarm_result.run_id,
            "success":          swarm_result.success,
            "final_output":     swarm_result.final_output,
            "summary":          swarm_result.summary,
            "errors":           swarm_result.errors,
            "duration_seconds": swarm_result.duration_seconds,
            "tasks": [
                {
                    "id":             t.id,
                    "description":    t.description,
                    "type":           t.type,
                    "assigned_agent": t.assigned_agent,
                    "status":         t.status,
                }
                for t in swarm_result.tasks
            ],
        }
    except Exception as exc:
        logger.exception("swarm_run failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ── Agent Pipeline ────────────────────────────────────────────────────────────
class AgentRunRequest(BaseModel):
    task: str

@api_router.post("/agent/run")
async def agent_run(request: AgentRunRequest):
    """Stream multi-brain agent pipeline execution via SSE."""
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama not available")

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_update(ctx):
        loop.call_soon_threadsafe(queue.put_nowait, ctx.to_dict())

    async def generate():
        pipeline_task = asyncio.create_task(
            run_agent_pipeline(request.task, ollama_client, on_update)
        )
        try:
            while True:
                try:
                    update = await asyncio.wait_for(queue.get(), timeout=2.0)
                    yield f"data: {json.dumps(update)}\n\n"
                    if update.get("status") in ("done", "failed"):
                        break
                except asyncio.TimeoutError:
                    if pipeline_task.done():
                        try:
                            ctx = pipeline_task.result()
                            yield f"data: {json.dumps(ctx.to_dict())}\n\n"
                        except Exception as e:
                            yield f"data: {json.dumps({'status': 'failed', 'errors': str(e)})}\n\n"
                        break
                    yield f"data: {json.dumps({'status': 'thinking'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'status': 'failed', 'errors': str(e)})}\n\n"
        finally:
            if not pipeline_task.done():
                pipeline_task.cancel()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


app.include_router(api_router)

# Serve React frontend static files if the build directory exists
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir / "static")), name="static-assets")

    # Serve root-level public assets (Logo.png, favicon, etc.) before the catch-all
    @app.get("/Logo.png")
    async def serve_logo():
        logo = _static_dir / "Logo.png"
        if logo.exists():
            return FileResponse(str(logo), media_type="image/png")
        raise HTTPException(status_code=404, detail="Logo not found")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        index = _static_dir / "index.html"
        return FileResponse(str(index))

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    if client is not None:
        client.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)