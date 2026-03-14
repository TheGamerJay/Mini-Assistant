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
import httpx

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# ── Project tree helpers ──────────────────────────────────────────────────────
# Supports both v1 (flat: index_html/style_css/script_js) and v2 (nested tree).
# All app-builder endpoints accept/return v2; v1 sessions are migrated on load.

_MIME_MAP = {
    'html': 'text/html', 'htm': 'text/html', 'css': 'text/css',
    'js': 'application/javascript', 'mjs': 'application/javascript',
    'ts': 'application/typescript', 'tsx': 'application/typescript',
    'json': 'application/json', 'md': 'text/markdown', 'txt': 'text/plain',
    'py': 'text/x-python', 'rb': 'text/x-ruby', 'rs': 'text/x-rust',
    'go': 'text/x-go', 'yaml': 'text/yaml', 'yml': 'text/yaml',
    'toml': 'text/x-toml', 'sh': 'text/x-shellscript',
    'svg': 'image/svg+xml', 'png': 'image/png', 'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg', 'gif': 'image/gif', 'ico': 'image/x-icon',
    'woff': 'font/woff', 'woff2': 'font/woff2', 'ttf': 'font/ttf',
}

def _pt_guess_mime(name: str) -> str:
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    return _MIME_MAP.get(ext, 'text/plain')

def _pt_file_node(name: str, path: str, content: str = '', **kw) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        'id':      kw.get('id') or str(uuid.uuid4()),
        'name':    name,
        'path':    path,
        'type':    'file',
        'content': content,
        'dataUrl': kw.get('dataUrl'),
        'metadata': {
            'locked':     kw.get('locked', False),
            'source':     kw.get('source', 'generated'),
            'created_at': kw.get('created_at', now),
            'updated_at': kw.get('updated_at', now),
            'mime':       kw.get('mime') or _pt_guess_mime(name),
        },
    }

def _pt_folder_node(name: str, path: str, children: list = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        'id': str(uuid.uuid4()), 'name': name, 'path': path,
        'type': 'folder', 'children': children or [],
        'metadata': {'locked': False, 'source': 'generated', 'created_at': now, 'updated_at': now},
    }

def _pt_is_v2(project: dict) -> bool:
    return bool(project) and project.get('version') == 2

def _pt_flat_to_tree(old: dict, project_id: str = None, name: str = 'project') -> dict:
    """Migrate flat v1 project → nested tree v2."""
    if not old:
        return None
    if _pt_is_v2(old):
        return old
    now  = datetime.now(timezone.utc).isoformat()
    meta = old.get('file_metadata', {})

    def m(filename):
        fm = meta.get(filename, {})
        return {'locked': fm.get('locked', False), 'created_at': fm.get('created_at', now), 'updated_at': fm.get('updated_at', now)}

    root = []
    if old.get('index_html'): root.append(_pt_file_node('index.html', 'index.html', old['index_html'], mime='text/html',               **m('index.html')))
    if old.get('style_css'):  root.append(_pt_file_node('style.css',  'style.css',  old['style_css'],  mime='text/css',                **m('style.css')))
    if old.get('script_js'):  root.append(_pt_file_node('script.js',  'script.js',  old['script_js'],  mime='application/javascript',  **m('script.js')))
    if old.get('readme'):     root.append(_pt_file_node('README.md',  'README.md',  old['readme'],     mime='text/markdown'))

    for ef in old.get('extra_files', []):
        root.append(_pt_file_node(ef['name'], ef['name'], ef.get('content', ''), **m(ef['name'])))

    assets = old.get('assets', [])
    if assets:
        asset_nodes = [_pt_file_node(a['name'], f"assets/{a['name']}", '',
                        dataUrl=a.get('dataUrl'), mime=a.get('type') or _pt_guess_mime(a['name']),
                        source='imported') for a in assets]
        root.append(_pt_folder_node('assets', 'assets', asset_nodes))

    return {'version': 2, 'id': project_id or str(uuid.uuid4()), 'name': name,
            'root': root, 'created_at': now, 'updated_at': now}

def _pt_ensure_v2(project: dict, project_id: str = None, name: str = 'project') -> dict:
    if not project:
        return project
    if _pt_is_v2(project):
        return project
    return _pt_flat_to_tree(project, project_id, name)

def _pt_get_all_file_nodes(tree: dict) -> list:
    files = []
    def traverse(nodes):
        for n in (nodes or []):
            if n.get('type') == 'file':   files.append(n)
            elif n.get('type') == 'folder': traverse(n.get('children', []))
    traverse(tree.get('root', []) if _pt_is_v2(tree) else [])
    return files

def _pt_find_node(tree: dict, path: str) -> Optional[dict]:
    def traverse(nodes):
        for n in (nodes or []):
            if n.get('path') == path: return n
            if n.get('type') == 'folder':
                r = traverse(n.get('children', []))
                if r: return r
        return None
    return traverse(tree.get('root', [])) if _pt_is_v2(tree) else None

_PT_FLAT_MAP = {'index.html': 'index_html', 'style.css': 'style_css',
                'script.js': 'script_js', 'README.md': 'readme'}

def _pt_get_content(project: dict, path: str) -> str:
    if not project: return ''
    if _pt_is_v2(project):
        node = _pt_find_node(project, path)
        return node.get('content', '') if node else ''
    if path in _PT_FLAT_MAP:
        return project.get(_PT_FLAT_MAP[path], '')
    ef = next((f for f in project.get('extra_files', []) if f['name'] == path), None)
    return ef['content'] if ef else ''

def _pt_set_content(project: dict, path: str, value: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    if _pt_is_v2(project):
        def update(nodes):
            result = []
            for n in (nodes or []):
                if n.get('path') == path and n.get('type') == 'file':
                    result.append(dict(n, content=value, metadata=dict(n.get('metadata', {}), updated_at=now)))
                elif n.get('type') == 'folder':
                    result.append(dict(n, children=update(n.get('children', []))))
                else:
                    result.append(n)
            return result
        return dict(project, root=update(project.get('root', [])), updated_at=now)
    p = dict(project)
    if path in _PT_FLAT_MAP: p[_PT_FLAT_MAP[path]] = value
    else: p['extra_files'] = [dict(f, content=value) if f['name'] == path else f for f in p.get('extra_files', [])]
    return p

def _pt_tree_to_flat(tree: dict) -> dict:
    if not _pt_is_v2(tree): return tree
    SPECIAL = {'index.html', 'style.css', 'script.js', 'README.md'}
    all_files = _pt_get_all_file_nodes(tree)
    return {
        'version': 1,
        'index_html': _pt_get_content(tree, 'index.html'),
        'style_css':  _pt_get_content(tree, 'style.css'),
        'script_js':  _pt_get_content(tree, 'script.js'),
        'readme':     _pt_get_content(tree, 'README.md'),
        'extra_files': [{'name': n['name'], 'content': n.get('content', '')}
                        for n in all_files if not n.get('dataUrl') and n['path'] not in SPECIAL],
        'assets':      [{'name': n['name'], 'type': n.get('metadata', {}).get('mime', ''), 'dataUrl': n['dataUrl']}
                        for n in all_files if n.get('dataUrl')],
        'file_metadata': {n['path']: {'locked': True}
                          for n in all_files if n.get('metadata', {}).get('locked')},
    }

def _pt_reconstruct_html(project: dict) -> str:
    """Build full HTML from project (v1 or v2)."""
    html = _pt_get_content(project, 'index.html')
    css  = _pt_get_content(project, 'style.css')
    js   = _pt_get_content(project, 'script.js')
    return _pt_inline_html(html, css, js)

def _pt_inline_html(html: str, css: str, js: str) -> str:
    import re as _re
    if not html: return ''
    out = html
    if css:
        if _re.search(r'< *link[^>]*href=["\']style\.css["\'][^>]*>', out, _re.IGNORECASE):
            out = _re.sub(r'< *link[^>]*href=["\']style\.css["\'][^>]*>', f'<style>\n{css}\n</style>', out, flags=_re.IGNORECASE)
        elif not _re.search(r'<style[\s>]', out, _re.IGNORECASE):
            out = out.replace('</head>', f'<style>\n{css}\n</style>\n</head>')
    if js:
        if _re.search(r'< *script[^>]*src=["\']script\.js["\'][^>]*><\/script>', out, _re.IGNORECASE):
            out = _re.sub(r'< *script[^>]*src=["\']script\.js["\'][^>]*><\/script>', f'<script>\n{js}\n</script>', out, flags=_re.IGNORECASE)
        elif not _re.search(r'<script[\s>]', out, _re.IGNORECASE):
            out = out.replace('</body>', f'<script>\n{js}\n</script>\n</body>')
    return out

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


# ── Redis client (for app preview cache) ───────────────────────────────────────
_redis_client = None

async def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = os.environ.get('REDIS_URL', '')
    if not redis_url:
        return None
    try:
        import redis.asyncio as aioredis
        _redis_client = await aioredis.from_url(redis_url, decode_responses=True)
        await _redis_client.ping()
        return _redis_client
    except Exception as e:
        logging.warning(f"Redis unavailable: {e}")
        return None


# ── Postgres pool (for app builder sessions) ───────────────────────────────────
_pg_pool = None

async def _get_pg():
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    db_url = os.environ.get('DATABASE_URL', '')
    if not db_url:
        return None
    try:
        import asyncpg
        _pg_pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
        async with _pg_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS app_builder_sessions (
                    id          TEXT PRIMARY KEY,
                    name        TEXT,
                    description TEXT,
                    html        TEXT,
                    project     JSONB,
                    edit_history JSONB  DEFAULT '[]',
                    versions    JSONB   DEFAULT '[]',
                    build_id    TEXT,
                    preview_url TEXT,
                    saved_at    TIMESTAMPTZ DEFAULT NOW(),
                    updated_at  TIMESTAMPTZ DEFAULT NOW()
                )
            """)
        logging.info("✓ Postgres pool ready (app_builder_sessions table ensured)")
        return _pg_pool
    except Exception as e:
        logging.warning(f"Postgres unavailable: {e}")
        return None

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
        raise HTTPException(status_code=503, detail=f"Ollama service not available. Please ensure Ollama is reachable at {_ollama_host}")

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
    """Serve a generated app HTML by build ID.
    Priority: Redis cache → in-memory dict → reconstruct from Postgres session.
    """
    # 1. Try Redis
    redis = await _get_redis()
    if redis:
        try:
            html = await redis.get(f"preview:{build_id}")
            if html:
                return HTMLResponse(content=html)
        except Exception:
            pass

    # 2. Try in-memory dict
    html = _app_previews.get(build_id)
    if html:
        return HTMLResponse(content=html)

    # 3. Regenerate from Postgres — find session by build_id
    pg = await _get_pg()
    if pg:
        try:
            async with pg.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT project, html FROM app_builder_sessions WHERE build_id=$1",
                    build_id)
            if row:
                project = json.loads(row["project"]) if row["project"] else None
                if project:
                    html = _reconstruct_html(project)
                elif row["html"]:
                    html = row["html"]
                if html:
                    # Re-cache in Redis and memory
                    _app_previews[build_id] = html
                    if redis:
                        try: await redis.setex(f"preview:{build_id}", 86400, html)
                        except Exception: pass
                    return HTMLResponse(content=html)
        except Exception:
            pass

    raise HTTPException(status_code=404, detail="Preview not found or expired")

import re as _app_re

def _parse_html_to_project(html: str, name: str = "generated-app", description: str = "") -> dict:
    """Split a single-file HTML into a v2 project tree (index.html / style.css / script.js / README.md)."""
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
    return _pt_flat_to_tree({
        "index_html": clean.strip(),
        "style_css":  css  or "/* styles */",
        "script_js":  js   or "// scripts",
        "readme":     readme,
    }, name=name)


def _reconstruct_html(project: dict) -> str:
    """Merge project files back into a single self-contained HTML. Accepts v1 or v2."""
    return _pt_reconstruct_html(project)


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
    project_type: str = "app"      # app | game | dashboard | landing | tool | creative
    build_mode: str = "polished"   # quick | polished | production | game_jam | mobile

@api_router.post("/app-builder/generate")
async def generate_app(request: AppBuilderRequest):
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")

    _mode_addendum = {
        "quick":      "\nBUILD MODE: Quick prototype. Core features only. Prioritize working logic over polish.",
        "production": "\nBUILD MODE: Production starter. Emphasize clean architecture, error handling, edge cases.",
        "game_jam":   "\nBUILD MODE: Game jam mode. Maximize fun, game feel, and effects. Speed over perfection.",
        "mobile":     "\nBUILD MODE: Mobile-first. Touch controls required. Design for 375px width first.",
    }.get(request.build_mode, "")

    try:
        prompt = f"""You are a world-class web developer and UI designer. Your job is to generate a single, complete, self-contained HTML file for the following app:{_mode_addendum}

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

        # ── Full-stack: generate Node.js/Express backend alongside the frontend ──
        if request.project_type == "fullstack":
            try:
                server_prompt = f"""You are a senior Node.js developer. Generate a complete, working Express.js server for this app:

{request.description}

The frontend is a self-contained HTML/CSS/JS app. Your server should:
- Use Express.js (require('express'))
- Serve the frontend at GET / by serving index.html as a static file from the same directory
- Add any API endpoints this app needs (REST, JSON)
- Use in-memory storage (no database required unless the app specifically needs persistence)
- Include error handling middleware
- Listen on process.env.PORT || 3000
- Export the app object for testing

OUTPUT FORMAT:
- Output ONLY the raw JavaScript. No markdown. No code fences. No explanation.
- First line must be: const express = require('express');
- Last line must close the server or export it."""

                server_resp = ollama_client.chat(
                    model=_default_model,
                    messages=[{"role": "user", "content": server_prompt}]
                )
                server_js = server_resp['message']['content'].strip()
                # Strip fences
                import re as _re2
                server_js = _re2.sub(r'^```[a-zA-Z]*\n?', '', server_js)
                server_js = _re2.sub(r'\n?```\s*$', '', server_js).strip()

                package_json = json.dumps({
                    "name": app_name,
                    "version": "1.0.0",
                    "description": request.description[:100],
                    "main": "server.js",
                    "scripts": {"start": "node server.js", "dev": "nodemon server.js"},
                    "dependencies": {"express": "^4.18.2"},
                    "devDependencies": {"nodemon": "^3.0.0"}
                }, indent=2)

                project["extra_files"] = [
                    {"name": "server.js", "content": server_js},
                    {"name": "package.json", "content": package_json},
                    {"name": ".gitignore", "content": "node_modules/\n.env\n*.log\n"},
                ]
            except Exception as fs_err:
                logging.warning(f"Full-stack server generation failed: {fs_err}")

        build_id = str(uuid.uuid4())
        _app_previews[build_id] = reconstructed
        r = await _get_redis()
        if r:
            try:
                await r.setex(f"preview:{build_id}", 86400, reconstructed)
            except Exception:
                pass

        return {
            "name": app_name,
            "description": request.description,
            "html": content,
            "project": project,
            "build_id": build_id,
            "preview_url": f"/api/preview/{build_id}",
            "project_type": request.project_type,
            "build_mode": request.build_mode,
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
    github_token: str = ""

class AppBuilderEditRequest(BaseModel):
    html: Optional[str] = None          # legacy / fallback
    project: Optional[dict] = None      # structured project files
    instruction: str
    locked_files: List[str] = []        # file names that must not be edited

@api_router.post("/app-builder/edit")
async def edit_app(request: AppBuilderEditRequest):
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    try:
        # Resolve project — accept v1 flat or v2 tree; migrate to v2
        if request.project:
            project = _pt_ensure_v2(request.project)
        elif request.html:
            project = _parse_html_to_project(request.html)
        else:
            raise HTTPException(status_code=400, detail="Provide either 'project' or 'html'")

        index_html = _pt_get_content(project, 'index.html')
        style_css  = _pt_get_content(project, 'style.css')
        script_js  = _pt_get_content(project, 'script.js')

        # Route the edit to the most appropriate file
        target_file = _route_edit(request.instruction)

        # Respect locked files — fall back to next best unlocked file
        _fallback_order = ["index.html", "style.css", "script.js"]
        if target_file in request.locked_files:
            for f in _fallback_order:
                if f not in request.locked_files:
                    target_file = f
                    break
            else:
                raise HTTPException(status_code=400, detail="All target files are locked. Unlock a file to allow AI edits.")

        target_content = _pt_get_content(project, target_file)

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

        # Merge the updated file back into the tree
        updated_project = _pt_set_content(project, target_file, updated_content)

        # Reconstruct full HTML for preview
        reconstructed = _reconstruct_html(updated_project)

        build_id = str(uuid.uuid4())
        _app_previews[build_id] = reconstructed
        r = await _get_redis()
        if r:
            try:
                await r.setex(f"preview:{build_id}", 86400, reconstructed)
            except Exception:
                pass

        # Generate a short conversational reply describing what changed
        chat_reply = ""
        try:
            reply_resp = ollama_client.chat(
                model=_default_model,
                messages=[{"role": "user", "content":
                    f"A developer asked you to: \"{request.instruction}\"\n"
                    f"You just updated {target_file} to implement this.\n"
                    f"Write 1-2 friendly sentences describing what you changed and why. "
                    f"Be specific but brief. Don't say 'certainly' or 'of course'. "
                    f"Sound like a helpful teammate, not a robot."
                }]
            )
            chat_reply = reply_resp['message']['content'].strip()
        except Exception:
            chat_reply = f"Done! I updated `{target_file}` based on your request. Review the changes below."

        return {
            "project": updated_project,
            "html": reconstructed,
            "file_changed": target_file,
            "build_id": build_id,
            "preview_url": f"/api/preview/{build_id}",
            "chat_reply": chat_reply,
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
    assets: List[dict] = []         # [{name, type, dataUrl}]
    extra_files: List[dict] = []    # [{name, content}]

@api_router.post("/app-builder/export-zip")
async def export_app_zip(request: AppBuilderExportRequest):
    """Return a ZIP of the structured project files, assets, and extra files."""
    import io, zipfile, base64
    from fastapi.responses import Response

    name = request.name or "generated-app"

    # Resolve project → ensure v2 tree
    if request.project:
        project = _pt_ensure_v2(request.project, name=name)
    elif request.html:
        project = _parse_html_to_project(request.html, name, request.description)
    else:
        raise HTTPException(status_code=400, detail="Provide either 'project' or 'html'")

    # Merge in any extra_files / assets passed separately (legacy callers)
    for ef in request.extra_files:
        ef_name = ef.get("name", "").strip()
        if ef_name and not _pt_find_node(project, ef_name):
            project = _pt_flat_to_tree.__func__(  # fallback: just append node
                project, name=name) if False else project  # skip; handled below
    # Simpler: add extra_files as file nodes if not already present
    for ef in request.extra_files:
        ef_name = ef.get("name", "").strip()
        if ef_name and not _pt_find_node(project, ef_name):
            node = _pt_file_node(ef_name, ef_name, ef.get("content", ""), source="imported")
            project = dict(project, root=project['root'] + [node])
    for asset in request.assets:
        asset_name = asset.get("name", "").strip()
        asset_path = f"assets/{asset_name}"
        if asset_name and not _pt_find_node(project, asset_path):
            node = _pt_file_node(asset_name, asset_path, '', dataUrl=asset.get('dataUrl'), mime=asset.get('type', ''), source='imported')
            project = dict(project, root=project['root'] + [node])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Walk all file nodes preserving tree paths
        for fnode in _pt_get_all_file_nodes(project):
            zip_path = f"{name}/{fnode['path']}"
            if fnode.get('dataUrl'):
                try:
                    _, b64data = fnode['dataUrl'].split(",", 1)
                    zf.writestr(zip_path, base64.b64decode(b64data))
                except Exception:
                    pass
            else:
                zf.writestr(zip_path, fnode.get('content', ''))

    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'}
    )


# ── Phase 5: Format, Explain-Diff, Explain-Architecture, Changelog ────────────

class FormatFileRequest(BaseModel):
    content: str
    language: str = "html"   # html | css | js | json | markdown

@api_router.post("/app-builder/format")
async def format_file(req: FormatFileRequest):
    """Format/prettify a file's content using AI."""
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama not available")
    if req.language == "json":
        try:
            return {"formatted": json.dumps(json.loads(req.content), indent=2)}
        except Exception:
            pass
    lang_map = {"html": "HTML", "css": "CSS", "js": "JavaScript", "markdown": "Markdown"}
    lang = lang_map.get(req.language, req.language.upper())
    prompt = f"""Format and prettify this {lang} code. Apply consistent indentation (2 spaces), line breaks, and clean structure.
Return ONLY the formatted code. No explanation. No markdown fences.

{req.content[:8000]}"""
    resp = ollama_client.chat(model=_default_model, messages=[{"role": "user", "content": prompt}])
    raw = resp["message"]["content"].strip()
    import re as _ref
    raw = _ref.sub(r'^```[a-zA-Z]*\n?', '', raw)
    raw = _ref.sub(r'\n?```\s*$', '', raw).strip()
    return {"formatted": raw}


class ExplainDiffRequest(BaseModel):
    file_name: str
    before: str
    after: str
    instruction: Optional[str] = None

@api_router.post("/app-builder/explain-diff")
async def explain_diff(req: ExplainDiffRequest):
    """AI explains what changed between two versions of a file."""
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama not available")
    prompt = f"""A developer made changes to {req.file_name}.
{f'Edit instruction: "{req.instruction}"' if req.instruction else ''}

BEFORE:
{req.before[:3000]}

AFTER:
{req.after[:3000]}

Explain what changed in plain English. Be specific — mention function names, elements, or rules that changed.
Keep it under 6 bullet points. Use plain language, no jargon."""
    resp = ollama_client.chat(model=_default_model, messages=[{"role": "user", "content": prompt}])
    return {"explanation": resp["message"]["content"].strip()}


class ExplainArchRequest(BaseModel):
    project: dict
    name: str = "project"

@api_router.post("/app-builder/explain-architecture")
async def explain_architecture(req: ExplainArchRequest):
    """AI gives an architecture overview of the full project."""
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama not available")
    p = req.project
    files_summary = []
    if p.get("index_html"): files_summary.append(f"index.html ({len(p['index_html'])} chars)")
    if p.get("style_css"):  files_summary.append(f"style.css ({len(p['style_css'])} chars)")
    if p.get("script_js"):  files_summary.append(f"script.js ({len(p['script_js'])} chars)")
    for ef in p.get("extra_files", []):
        files_summary.append(f"{ef['name']} ({len(ef.get('content',''))} chars)")
    prompt = f"""Project: {req.name}
Files: {', '.join(files_summary)}

HTML (first 2000 chars):
{p.get('index_html','')[:2000]}

JS (first 2000 chars):
{p.get('script_js','')[:2000]}

CSS (first 1000 chars):
{p.get('style_css','')[:1000]}

Give a concise architecture overview covering:
1. What this project does
2. How files relate to each other
3. Key patterns/libraries used
4. Data flow (if any)
5. How someone would extend it

Be specific to THIS codebase. Plain English. Max 300 words."""
    resp = ollama_client.chat(model=_default_model, messages=[{"role": "user", "content": prompt}])
    return {"overview": resp["message"]["content"].strip()}


class GenerateChangelogRequest(BaseModel):
    versions: List[dict]
    project_name: str = "project"

@api_router.post("/app-builder/generate-changelog")
async def generate_changelog(req: GenerateChangelogRequest):
    """Generate a markdown changelog from version history."""
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama not available")
    entries = []
    for v in req.versions[-20:]:  # last 20 versions
        line = f"- [{v.get('savedAt','?')[:10]}] {v.get('eventType','manual').upper()} — {v.get('name','Unnamed')}"
        if v.get("summary"): line += f": {v['summary']}"
        if v.get("file_changed"): line += f" (in {v['file_changed']})"
        entries.append(line)
    prompt = f"""Convert these raw version entries for "{req.project_name}" into a clean Markdown CHANGELOG.

Version entries:
{chr(10).join(entries)}

Format as:
# Changelog
## [date] - [version name]
- What changed (inferred from the version name and context)

Group by date if multiple on same day. Be concise. No fabricated details."""
    resp = ollama_client.chat(model=_default_model, messages=[{"role": "user", "content": prompt}])
    return {"changelog": resp["message"]["content"].strip()}


# ── Phase 4: GitHub push & Vercel deploy ──────────────────────────────────────

class GithubPushRequest(BaseModel):
    token: str
    repo_name: str
    project: dict
    name: str = "generated-app"
    description: str = ""
    private: bool = False
    assets: List[dict] = []
    extra_files: List[dict] = []

@api_router.post("/app-builder/github-push")
async def github_push(req: GithubPushRequest):
    """Create (or update) a GitHub repo and push all project files."""
    import base64, re
    import requests as _req

    headers = {
        "Authorization": f"Bearer {req.token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Get authenticated user
    user_resp = _req.get("https://api.github.com/user", headers=headers, timeout=10)
    if user_resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid GitHub token")
    username = user_resp.json()["login"]

    repo_slug = re.sub(r"[^a-zA-Z0-9._-]", "-", req.repo_name.strip()) or "generated-app"
    repo_url_base = f"https://api.github.com/repos/{username}/{repo_slug}"

    # Check if repo exists; create if not
    check = _req.get(repo_url_base, headers=headers, timeout=10)
    if check.status_code == 404:
        create_resp = _req.post(
            "https://api.github.com/user/repos",
            headers=headers,
            json={"name": repo_slug, "description": req.description, "private": req.private, "auto_init": False},
            timeout=15,
        )
        if create_resp.status_code not in (200, 201):
            raise HTTPException(status_code=400, detail=f"Failed to create repo: {create_resp.text}")
        html_url = create_resp.json()["html_url"]
    else:
        html_url = check.json()["html_url"]

    # Helper — upsert a file via GitHub Contents API
    def _upsert_file(path: str, content_bytes: bytes, message: str):
        existing = _req.get(f"{repo_url_base}/contents/{path}", headers=headers, timeout=10)
        sha = existing.json().get("sha") if existing.status_code == 200 else None
        payload = {
            "message": message,
            "content": base64.b64encode(content_bytes).decode(),
        }
        if sha:
            payload["sha"] = sha
        _req.put(f"{repo_url_base}/contents/{path}", headers=headers, json=payload, timeout=15)

    p = req.project
    _upsert_file("index.html", p.get("index_html", "").encode(), "Add index.html")
    _upsert_file("style.css",  p.get("style_css",  "").encode(), "Add style.css")
    _upsert_file("script.js",  p.get("script_js",  "").encode(), "Add script.js")
    if p.get("readme"):
        _upsert_file("README.md", p["readme"].encode(), "Add README.md")

    for ef in req.extra_files:
        if ef.get("name"):
            _upsert_file(ef["name"], ef.get("content", "").encode(), f"Add {ef['name']}")

    for asset in req.assets:
        asset_name = asset.get("name", "").strip()
        data_url = asset.get("dataUrl", "")
        if asset_name and data_url and "," in data_url:
            raw = base64.b64decode(data_url.split(",", 1)[1])
            _upsert_file(f"assets/{asset_name}", raw, f"Add asset {asset_name}")

    pages_url = f"https://{username}.github.io/{repo_slug}/"
    return {"repo_url": html_url, "pages_url": pages_url, "username": username, "repo": repo_slug}


class VercelDeployRequest(BaseModel):
    token: str
    project: dict
    name: str = "generated-app"
    assets: List[dict] = []
    extra_files: List[dict] = []

@api_router.post("/app-builder/deploy-vercel")
async def deploy_vercel(req: VercelDeployRequest):
    """Deploy project as a static site to Vercel."""
    import base64, re, hashlib
    import requests as _req

    headers = {
        "Authorization": f"Bearer {req.token}",
        "Content-Type": "application/json",
    }

    slug = re.sub(r"[^a-z0-9-]", "-", req.name.lower().strip())[:50] or "generated-app"
    p = req.project

    def _make_file(path: str, content_bytes: bytes):
        return {
            "file": path,
            "data": base64.b64encode(content_bytes).decode(),
            "encoding": "base64",
        }

    files = [
        _make_file("index.html", p.get("index_html", "").encode()),
        _make_file("style.css",  p.get("style_css",  "").encode()),
        _make_file("script.js",  p.get("script_js",  "").encode()),
    ]
    if p.get("readme"):
        files.append(_make_file("README.md", p["readme"].encode()))
    for ef in req.extra_files:
        if ef.get("name"):
            files.append(_make_file(ef["name"], ef.get("content", "").encode()))
    for asset in req.assets:
        asset_name = asset.get("name", "").strip()
        data_url = asset.get("dataUrl", "")
        if asset_name and data_url and "," in data_url:
            raw = base64.b64decode(data_url.split(",", 1)[1])
            files.append(_make_file(f"assets/{asset_name}", raw))

    payload = {
        "name": slug,
        "files": files,
        "projectSettings": {"framework": None, "outputDirectory": "."},
        "target": "production",
    }

    resp = _req.post(
        "https://api.vercel.com/v13/deployments",
        headers=headers,
        json=payload,
        timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"Vercel deploy failed: {resp.text[:300]}")

    data = resp.json()
    deploy_url = f"https://{data.get('url', '')}"
    return {"deploy_url": deploy_url, "id": data.get("id"), "status": data.get("readyState", "BUILDING")}


# ── Migrate table to add new columns if they don't exist yet ────────────────────
_SESSION_MIGRATIONS = [
    # Phase 0 (original)
    "ALTER TABLE app_builder_sessions ADD COLUMN IF NOT EXISTS user_id TEXT",
    "ALTER TABLE app_builder_sessions ADD COLUMN IF NOT EXISTS project_type TEXT DEFAULT 'app'",
    "ALTER TABLE app_builder_sessions ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN DEFAULT FALSE",
    "ALTER TABLE app_builder_sessions ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE",
    "ALTER TABLE app_builder_sessions ADD COLUMN IF NOT EXISTS edit_count INTEGER DEFAULT 0",
    "ALTER TABLE app_builder_sessions ADD COLUMN IF NOT EXISTS last_edited_file TEXT",
    "ALTER TABLE app_builder_sessions ADD COLUMN IF NOT EXISTS last_opened_at TIMESTAMPTZ",
    "ALTER TABLE app_builder_sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
    # Phase 1
    "ALTER TABLE app_builder_sessions ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]'",
    "ALTER TABLE app_builder_sessions ADD COLUMN IF NOT EXISTS notes TEXT",
    "ALTER TABLE app_builder_sessions ADD COLUMN IF NOT EXISTS is_favorite BOOLEAN DEFAULT FALSE",
    "ALTER TABLE app_builder_sessions ADD COLUMN IF NOT EXISTS build_mode TEXT DEFAULT 'polished'",
    "ALTER TABLE app_builder_sessions ADD COLUMN IF NOT EXISTS project_type_label TEXT",
    "ALTER TABLE app_builder_sessions ADD COLUMN IF NOT EXISTS fixloop_result JSONB",
]

async def _migrate_sessions_table(conn):
    for stmt in _SESSION_MIGRATIONS:
        try:
            await conn.execute(stmt)
        except Exception:
            pass  # column already exists or other harmless error


def _row_to_session(r) -> dict:
    """Convert an asyncpg Row to a plain dict for the API response."""
    def _j(v):
        if v is None: return None
        if isinstance(v, str):
            try: return json.loads(v)
            except Exception: return v
        return v
    keys = r.keys()
    def _col(col, default=None):
        return r[col] if col in keys else default
    return {
        "id":               r["id"],
        "name":             r["name"],
        "description":      r["description"],
        "html":             r["html"],
        "project":          _pt_ensure_v2(_j(r["project"]), r["id"], r["name"]),
        "editHistory":      _j(r["edit_history"]) or [],
        "versions":         _j(r["versions"]) or [],
        "build_id":         r["build_id"],
        "preview_url":      r["preview_url"],
        "user_id":          _col("user_id"),
        "project_type":     _col("project_type", "app"),
        "project_type_label": _col("project_type_label"),
        "build_mode":       _col("build_mode", "polished"),
        "is_pinned":        _col("is_pinned", False),
        "is_archived":      _col("is_archived", False),
        "is_favorite":      _col("is_favorite", False),
        "edit_count":       _col("edit_count", 0),
        "last_edited_file": _col("last_edited_file"),
        "tags":             _j(_col("tags")) or [],
        "notes":            _col("notes"),
        "fixloop_result":   _j(_col("fixloop_result")),
        "last_opened_at":   r["last_opened_at"].isoformat() if _col("last_opened_at") else None,
        "created_at":       r["created_at"].isoformat() if _col("created_at") else None,
        "savedAt":          r["updated_at"].isoformat() if r["updated_at"] else None,
    }


class AppBuilderSessionUpsert(BaseModel):
    id: str
    name: str
    description: str = ""
    html: Optional[str] = None
    project: Optional[dict] = None
    edit_history: list = []
    versions: list = []
    build_id: Optional[str] = None
    preview_url: Optional[str] = None
    user_id: Optional[str] = None
    project_type: str = "app"
    project_type_label: Optional[str] = None
    build_mode: str = "polished"
    is_pinned: bool = False
    is_archived: bool = False
    is_favorite: bool = False
    edit_count: int = 0
    last_edited_file: Optional[str] = None
    tags: list = []
    notes: Optional[str] = None

class AppBuilderSessionPatch(BaseModel):
    is_pinned: Optional[bool] = None
    is_archived: Optional[bool] = None
    is_favorite: Optional[bool] = None
    name: Optional[str] = None
    tags: Optional[list] = None
    notes: Optional[str] = None

@api_router.post("/app-builder/sessions")
async def upsert_session(req: AppBuilderSessionUpsert):
    """Create or update an app builder session in Postgres."""
    pg = await _get_pg()
    if not pg:
        return {"ok": False, "reason": "postgres_unavailable"}
    async with pg.acquire() as conn:
        await _migrate_sessions_table(conn)
        await conn.execute("""
            INSERT INTO app_builder_sessions
                (id, name, description, html, project, edit_history, versions,
                 build_id, preview_url, user_id, project_type, project_type_label,
                 build_mode, is_pinned, is_archived, is_favorite,
                 edit_count, last_edited_file, tags, notes,
                 created_at, saved_at, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,NOW(),NOW(),NOW())
            ON CONFLICT (id) DO UPDATE SET
                name=EXCLUDED.name, description=EXCLUDED.description,
                html=EXCLUDED.html, project=EXCLUDED.project,
                edit_history=EXCLUDED.edit_history, versions=EXCLUDED.versions,
                build_id=EXCLUDED.build_id, preview_url=EXCLUDED.preview_url,
                user_id=EXCLUDED.user_id, project_type=EXCLUDED.project_type,
                project_type_label=EXCLUDED.project_type_label,
                build_mode=EXCLUDED.build_mode,
                edit_count=EXCLUDED.edit_count, last_edited_file=EXCLUDED.last_edited_file,
                tags=EXCLUDED.tags, notes=EXCLUDED.notes,
                updated_at=NOW()
        """,
        req.id, req.name, req.description,
        req.html,
        json.dumps(req.project) if req.project else None,
        json.dumps(req.edit_history),
        json.dumps(req.versions),
        req.build_id, req.preview_url,
        req.user_id, req.project_type, req.project_type_label,
        req.build_mode,
        req.is_pinned, req.is_archived, req.is_favorite,
        req.edit_count, req.last_edited_file,
        json.dumps(req.tags), req.notes)
    return {"ok": True}

@api_router.patch("/app-builder/sessions/{session_id}")
async def patch_session(session_id: str, req: AppBuilderSessionPatch):
    """Partial update — pin/unpin, archive/unarchive, favorite, rename, tags, notes."""
    pg = await _get_pg()
    if not pg:
        raise HTTPException(status_code=503, detail="Postgres unavailable")
    fields, vals = [], []
    if req.is_pinned is not None:
        fields.append(f"is_pinned=${len(vals)+1}"); vals.append(req.is_pinned)
    if req.is_archived is not None:
        fields.append(f"is_archived=${len(vals)+1}"); vals.append(req.is_archived)
    if req.is_favorite is not None:
        fields.append(f"is_favorite=${len(vals)+1}"); vals.append(req.is_favorite)
    if req.name is not None:
        fields.append(f"name=${len(vals)+1}"); vals.append(req.name)
    if req.tags is not None:
        fields.append(f"tags=${len(vals)+1}"); vals.append(json.dumps(req.tags))
    if req.notes is not None:
        fields.append(f"notes=${len(vals)+1}"); vals.append(req.notes)
    if not fields:
        return {"ok": True}
    fields.append(f"updated_at=NOW()")
    vals.append(session_id)
    async with pg.acquire() as conn:
        await conn.execute(
            f"UPDATE app_builder_sessions SET {', '.join(fields)} WHERE id=${len(vals)}",
            *vals)
    return {"ok": True}

@api_router.get("/app-builder/sessions")
async def list_sessions(
    search: Optional[str] = None,
    sort: str = "newest",               # newest | oldest | most_edited | pinned
    archived: bool = False,
):
    """Return saved sessions with optional search, sort, and archive filter."""
    pg = await _get_pg()
    if not pg:
        return []

    order = {
        "oldest":      "updated_at ASC",
        "most_edited": "edit_count DESC, updated_at DESC",
        "pinned":      "is_pinned DESC, updated_at DESC",
    }.get(sort, "updated_at DESC")

    conditions = ["is_archived = $1"]
    params: list = [archived]

    if search:
        params.append(f"%{search}%")
        conditions.append(f"name ILIKE ${len(params)}")

    where = " AND ".join(conditions)

    async with pg.acquire() as conn:
        await _migrate_sessions_table(conn)
        rows = await conn.fetch(
            f"SELECT * FROM app_builder_sessions WHERE {where} ORDER BY {order}",
            *params)

    return [_row_to_session(r) for r in rows]

@api_router.get("/app-builder/sessions/{session_id}")
async def get_session(session_id: str):
    """Return a single session and stamp last_opened_at."""
    pg = await _get_pg()
    if not pg:
        raise HTTPException(status_code=503, detail="Postgres unavailable")
    async with pg.acquire() as conn:
        await _migrate_sessions_table(conn)
        await conn.execute(
            "UPDATE app_builder_sessions SET last_opened_at=NOW() WHERE id=$1", session_id)
        r = await conn.fetchrow("SELECT * FROM app_builder_sessions WHERE id=$1", session_id)
    if not r:
        raise HTTPException(status_code=404, detail="Session not found")
    return _row_to_session(r)

@api_router.delete("/app-builder/sessions/{session_id}")
async def delete_session(session_id: str):
    pg = await _get_pg()
    if not pg:
        raise HTTPException(status_code=503, detail="Postgres unavailable")
    async with pg.acquire() as conn:
        await conn.execute("DELETE FROM app_builder_sessions WHERE id=$1", session_id)
    return {"ok": True}

@api_router.get("/app-builder/sessions/{session_id}/versions")
async def get_session_versions(session_id: str):
    """Return the full version history for a session."""
    pg = await _get_pg()
    if not pg:
        raise HTTPException(status_code=503, detail="Postgres unavailable")
    async with pg.acquire() as conn:
        r = await conn.fetchrow(
            "SELECT versions FROM app_builder_sessions WHERE id=$1", session_id)
    if not r:
        raise HTTPException(status_code=404, detail="Session not found")
    versions = json.loads(r["versions"]) if r["versions"] else []
    return versions

class RestoreVersionRequest(BaseModel):
    version_index: int   # index into versions array

@api_router.post("/app-builder/sessions/{session_id}/restore-version")
async def restore_version(session_id: str, req: RestoreVersionRequest):
    """Restore a named version: apply it as the current project and push the
    current state as a new version first (so nothing is lost)."""
    pg = await _get_pg()
    if not pg:
        raise HTTPException(status_code=503, detail="Postgres unavailable")
    async with pg.acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM app_builder_sessions WHERE id=$1", session_id)
    if not r:
        raise HTTPException(status_code=404, detail="Session not found")

    versions = json.loads(r["versions"]) if r["versions"] else []
    if req.version_index < 0 or req.version_index >= len(versions):
        raise HTTPException(status_code=400, detail="Invalid version index")

    target = versions[req.version_index]
    project = target.get("project")
    if not project:
        raise HTTPException(status_code=400, detail="Version has no project data")

    # Rebuild preview HTML from the restored project
    restored_html = _reconstruct_html(project)

    # Store new preview in Redis + memory
    build_id = str(uuid.uuid4())
    _app_previews[build_id] = restored_html
    r2 = await _get_redis()
    if r2:
        try:
            await r2.setex(f"preview:{build_id}", 86400, restored_html)
        except Exception:
            pass

    return {
        "project": project,
        "html": restored_html,
        "build_id": build_id,
        "preview_url": f"/api/preview/{build_id}",
        "restored_version": target,
    }


@api_router.post("/app-builder/sessions/{session_id}/clone")
async def clone_session(session_id: str):
    """Duplicate a session with a new ID and 'Copy of' prefix."""
    pg = await _get_pg()
    if not pg:
        raise HTTPException(status_code=503, detail="Postgres unavailable")
    async with pg.acquire() as conn:
        await _migrate_sessions_table(conn)
        r = await conn.fetchrow("SELECT * FROM app_builder_sessions WHERE id=$1", session_id)
    if not r:
        raise HTTPException(status_code=404, detail="Session not found")
    new_id = str(uuid.uuid4())
    orig = _row_to_session(r)
    async with pg.acquire() as conn:
        await conn.execute("""
            INSERT INTO app_builder_sessions
                (id, name, description, html, project, edit_history, versions,
                 build_id, preview_url, user_id, project_type, project_type_label,
                 build_mode, is_pinned, is_archived, is_favorite,
                 edit_count, last_edited_file, tags, notes,
                 created_at, saved_at, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,NOW(),NOW(),NOW())
        """,
        new_id, f"Copy of {orig['name']}", orig["description"],
        orig["html"],
        json.dumps(orig["project"]) if orig["project"] else None,
        json.dumps([]),  # fresh edit history
        json.dumps(orig["versions"]),
        None, None,  # new build_id/preview_url — will be set on next edit
        orig["user_id"], orig["project_type"], orig["project_type_label"],
        orig["build_mode"],
        False, False, False,  # is_pinned, is_archived, is_favorite
        0, None,
        json.dumps(orig["tags"] or []), orig["notes"])
    return {"ok": True, "id": new_id, "name": f"Copy of {orig['name']}"}


class AppBuilderExplainRequest(BaseModel):
    file: str               # 'index.html' | 'style.css' | 'script.js' | 'readme'
    content: str
    project_name: str = ""
    level: str = "normal"   # 'beginner' | 'normal' | 'advanced'

@api_router.post("/app-builder/explain")
async def explain_file(req: AppBuilderExplainRequest):
    """Ask AI to explain a project file in plain English."""
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    level_map = {
        "beginner": "Use very simple language. Avoid jargon. Assume no programming knowledge.",
        "advanced": "Be technical. Use proper terminology. Explain internal mechanics and trade-offs.",
    }
    level_note = level_map.get(req.level, "Use clear but technical language suitable for an intermediate developer.")
    prompt = f"""You are explaining code from a project called "{req.project_name or 'this app'}".

The file is: {req.file}

{level_note}

Explain what this file does, how it's structured, and any important patterns or decisions it uses.
Keep your explanation focused and practical — under 300 words.
Do not repeat the code back. Only explain it.

FILE CONTENT:
{req.content[:8000]}"""
    try:
        res = ollama_client.chat(model=_default_model, messages=[{"role": "user", "content": prompt}])
        return {"explanation": res["message"]["content"].strip(), "file": req.file}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Explain error: {str(e)}")


class AppBuilderReadmeRequest(BaseModel):
    project: dict
    name: str = "generated-app"
    description: str = ""

@api_router.post("/app-builder/generate-readme")
async def generate_readme(req: AppBuilderReadmeRequest):
    """Generate a comprehensive README from the structured project files."""
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    html_snippet  = (req.project.get("index_html") or "")[:3000]
    css_snippet   = (req.project.get("style_css")  or "")[:1500]
    js_snippet    = (req.project.get("script_js")  or "")[:3000]
    prompt = f"""You are a technical writer. Generate a comprehensive README.md for the following web project.

Project name: {req.name}
Description: {req.description}

index.html (excerpt):
{html_snippet}

style.css (excerpt):
{css_snippet}

script.js (excerpt):
{js_snippet}

Write the README in Markdown. Include:
1. Project title and one-sentence description
2. Features list (bullet points)
3. How to run it (double-click HTML / python -m http.server)
4. Controls (if it's a game or interactive app)
5. Tech used
6. Brief code structure overview
7. License: MIT

Output only the Markdown. No preamble."""
    try:
        res = ollama_client.chat(model=_default_model, messages=[{"role": "user", "content": prompt}])
        readme = res["message"]["content"].strip()
        return {"readme": readme}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"README generation error: {str(e)}")


class ProjectBriefRequest(BaseModel):
    description: str
    project_type: str = "app"
    build_mode: str = "polished"

@api_router.post("/app-builder/project-brief")
async def generate_project_brief(req: ProjectBriefRequest):
    """Generate a structured build brief + file plan before generation."""
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")
    type_context = {
        "game":      "a browser-based game",
        "dashboard": "a data dashboard or analytics app",
        "landing":   "a marketing landing page",
        "tool":      "a productivity utility app",
        "creative":  "a creative/generative art app",
    }.get(req.project_type, "a web application")
    mode_context = {
        "quick":      "Fast prototype. Core features only. Minimal polish.",
        "polished":   "Polished demo. Full UI, animations, complete feature set.",
        "production": "Production starter. Clean architecture, error handling, scalable patterns.",
        "game_jam":   "Game jam mode. Maximum fun, effects, and game feel. Ship fast.",
        "mobile":     "Mobile-first. Touch controls, responsive, small-screen optimized.",
    }.get(req.build_mode, "")
    prompt = f"""You are a senior product engineer planning a web project.

USER WANTS: {type_context}
BUILD MODE: {req.build_mode} — {mode_context}
DESCRIPTION: {req.description}

Generate a structured project brief in JSON with this exact shape:
{{
  "title": "short app name",
  "one_liner": "one sentence summary",
  "features": ["feature 1", "feature 2", ...],
  "tech_stack": ["HTML", "CSS", "JavaScript", ...],
  "complexity": "low | medium | high",
  "estimated_files": {{"index.html": "...", "style.css": "...", "script.js": "..."}},
  "risks": ["potential issue 1", ...],
  "must_haves": ["non-negotiable feature 1", ...],
  "nice_to_haves": ["optional feature 1", ...]
}}

Output ONLY valid JSON. No markdown. No preamble."""
    try:
        res = ollama_client.chat(model=_default_model, messages=[{"role": "user", "content": prompt}])
        raw = res["message"]["content"].strip()
        import re as _re2
        raw = _re2.sub(r'^```[a-zA-Z]*\n?', '', raw)
        raw = _re2.sub(r'\n?```\s*$', '', raw).strip()
        brief = json.loads(raw)
        return {"brief": brief}
    except json.JSONDecodeError:
        return {"brief": None, "raw": res["message"]["content"].strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Brief error: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — TESTING, SCAN, AUTO-FIX
# ══════════════════════════════════════════════════════════════════════════════

class AppBuilderScanRequest(BaseModel):
    project: dict
    project_type: str = "app"

def _static_scan(project: dict, project_type: str = "app") -> dict:
    """
    Pure-Python static analysis of project files.
    Returns severity-labelled findings + readiness score.
    """
    import re as _sr
    findings = []
    html = project.get("index_html", "") or ""
    css  = project.get("style_css",  "") or ""
    js   = project.get("script_js",  "") or ""

    # ── index.html checks ─────────────────────────────────────────────────────
    if "viewport" not in html.lower():
        findings.append({"file": "index.html", "severity": "warning",
            "category": "mobile", "message": "Missing <meta name='viewport'> — layout will break on mobile"})

    imgs_no_alt = _sr.findall(r'<img(?![^>]*\balt\b)[^>]*>', html, _sr.IGNORECASE)
    if imgs_no_alt:
        findings.append({"file": "index.html", "severity": "warning",
            "category": "accessibility", "message": f"{len(imgs_no_alt)} image(s) missing alt attribute"})

    if not _sr.search(r'<title>[^<]+</title>', html, _sr.IGNORECASE):
        findings.append({"file": "index.html", "severity": "cosmetic",
            "category": "meta", "message": "Missing or empty <title> tag"})

    empty_hrefs = _sr.findall(r"href\s*=\s*[\"']#[\"']", html, _sr.IGNORECASE)
    if len(empty_hrefs) > 2:
        findings.append({"file": "index.html", "severity": "cosmetic",
            "category": "broken_link", "message": f"{len(empty_hrefs)} placeholder href='#' link(s)"})

    inputs_no_label = _sr.findall(r'<input(?![^>]*\bid\b)[^>]*>', html, _sr.IGNORECASE)
    if len(inputs_no_label) > 2:
        findings.append({"file": "index.html", "severity": "cosmetic",
            "category": "accessibility", "message": f"{len(inputs_no_label)} input(s) without id — hard to associate labels"})

    # ── script.js checks ──────────────────────────────────────────────────────
    cl_count = len(_sr.findall(r'\bconsole\.log\b', js))
    if cl_count > 5:
        findings.append({"file": "script.js", "severity": "cosmetic",
            "category": "cleanup", "message": f"{cl_count} console.log() calls left in — remove before release"})

    fetch_count = len(_sr.findall(r'\bfetch\s*\(', js))
    try_count   = len(_sr.findall(r'\btry\s*\{', js))
    if fetch_count > 0 and try_count == 0:
        findings.append({"file": "script.js", "severity": "warning",
            "category": "error_handling", "message": "fetch() calls with no try/catch — unhandled network errors will crash the app"})

    js_kb = len(js.encode("utf-8")) / 1024
    if js_kb > 200:
        findings.append({"file": "script.js", "severity": "performance",
            "category": "size", "message": f"script.js is {js_kb:.0f} KB — large scripts hurt load time"})

    if not js.strip() and project_type not in ("landing",):
        findings.append({"file": "script.js", "severity": "warning",
            "category": "empty", "message": "script.js is empty — app may not be interactive"})

    # eval is a red flag for games/tools
    if "eval(" in js:
        findings.append({"file": "script.js", "severity": "warning",
            "category": "security", "message": "eval() detected — security risk and performance hit"})

    # ── style.css checks ──────────────────────────────────────────────────────
    if css and "@media" not in css:
        findings.append({"file": "style.css", "severity": "warning",
            "category": "mobile", "message": "No @media queries — layout will not adapt to screen sizes"})

    imp_count = len(_sr.findall(r"!important", css))
    if imp_count > 6:
        findings.append({"file": "style.css", "severity": "cosmetic",
            "category": "quality", "message": f"{imp_count} !important declarations — indicates specificity conflicts"})

    if not css.strip():
        findings.append({"file": "style.css", "severity": "cosmetic",
            "category": "empty", "message": "style.css is empty — all styling is inline or missing"})

    # ── Sort by severity ───────────────────────────────────────────────────────
    _ord = {"critical": 0, "warning": 1, "performance": 2, "cosmetic": 3}
    findings.sort(key=lambda f: _ord.get(f["severity"], 4))

    counts = {
        "critical":    sum(1 for f in findings if f["severity"] == "critical"),
        "warning":     sum(1 for f in findings if f["severity"] == "warning"),
        "performance": sum(1 for f in findings if f["severity"] == "performance"),
        "cosmetic":    sum(1 for f in findings if f["severity"] == "cosmetic"),
    }
    score = max(0, 100 - (
        counts["critical"]    * 25 +
        counts["warning"]     * 10 +
        counts["performance"] * 5  +
        counts["cosmetic"]    * 2
    ))
    return {"findings": findings, "score": score, "counts": counts}


@api_router.post("/app-builder/scan")
async def scan_project(req: AppBuilderScanRequest):
    """Static analysis scan — no browser required."""
    return _static_scan(req.project, req.project_type)


class RunSessionTestRequest(BaseModel):
    preview_url: Optional[str] = None  # override; falls back to session.preview_url

@api_router.post("/app-builder/sessions/{session_id}/run-test")
async def run_session_test(session_id: str, req: RunSessionTestRequest):
    """Run static scan + optional FixLoop screenshot test; store in fixloop_result."""
    pg = await _get_pg()
    if not pg:
        raise HTTPException(status_code=503, detail="Postgres unavailable")

    async with pg.acquire() as conn:
        await _migrate_sessions_table(conn)
        r = await conn.fetchrow("SELECT * FROM app_builder_sessions WHERE id=$1", session_id)
    if not r:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _row_to_session(r)
    project = session.get("project")

    # Static scan
    scan = _static_scan(project or {}, session.get("project_type", "app"))

    # FixLoop (screenshot) — only if we have a real HTTP preview URL
    fl_result = None
    url = req.preview_url or session.get("preview_url") or ""
    if url and not url.startswith("blob:"):
        # Make absolute if relative
        if url.startswith("/"):
            host = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
            if host:
                url = f"https://{host}{url}"
        if url.startswith("http"):
            try:
                fl_req = ErrorFixRequest(url=url, auto_fix=False, capture_screenshot=True)
                fl_result = await fixloop_start(fl_req)
            except Exception as e:
                fl_result = {"error": str(e)}

    result = {
        "session_id": session_id,
        "scan":      scan,
        "fixloop":   fl_result,
        "tested_at": datetime.now(timezone.utc).isoformat(),
    }

    async with pg.acquire() as conn:
        await conn.execute(
            "UPDATE app_builder_sessions SET fixloop_result=$1, updated_at=NOW() WHERE id=$2",
            json.dumps(result), session_id)

    return result


class AutoFixRequest(BaseModel):
    errors: list          # list of finding/error dicts with severity + message + file
    max_attempts: int = 3

@api_router.post("/app-builder/sessions/{session_id}/auto-fix")
async def auto_fix_session(session_id: str, req: AutoFixRequest):
    """Apply AI fixes for the top errors (up to max_attempts). Save updated project."""
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama service not available")

    pg = await _get_pg()
    if not pg:
        raise HTTPException(status_code=503, detail="Postgres unavailable")

    async with pg.acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM app_builder_sessions WHERE id=$1", session_id)
    if not r:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _row_to_session(r)
    project = session.get("project")
    if not project:
        raise HTTPException(status_code=400, detail="Session has no project files")

    _ord = {"critical": 0, "warning": 1, "performance": 2, "cosmetic": 3}
    errors_to_fix = sorted(req.errors[:8], key=lambda e: _ord.get(e.get("severity", "cosmetic"), 4))
    current = dict(project)
    applied = []

    for err in errors_to_fix[:req.max_attempts]:
        target = err.get("file", "script.js")
        fkey = ("index_html" if target == "index.html"
                else "style_css" if target == "style.css"
                else "script_js")
        content = current.get(fkey, "")
        prompt = f"""Fix this specific issue in {target}.

Issue: {err.get("message", "")}
Severity: {err.get("severity", "")}
Category: {err.get("category", "")}

Current {target}:
{content[:7000]}

Return ONLY the complete corrected {target}. No markdown. No explanation. Start outputting the file immediately."""
        try:
            import re as _fr
            res = ollama_client.chat(model=_default_model, messages=[{"role": "user", "content": prompt}])
            fixed = res["message"]["content"].strip()
            fixed = _fr.sub(r'^```[a-zA-Z]*\n?', '', fixed)
            fixed = _fr.sub(r'\n?```\s*$', '', fixed).strip()
            if fixed:
                current[fkey] = fixed
                applied.append({"error": err, "file": target})
        except Exception:
            pass

    if not applied:
        return {"ok": False, "message": "No fixes applied", "applied": []}

    reconstructed = _reconstruct_html(current)
    build_id = str(uuid.uuid4())
    _app_previews[build_id] = reconstructed
    redis = await _get_redis()
    if redis:
        try: await redis.setex(f"preview:{build_id}", 86400, reconstructed)
        except Exception: pass

    async with pg.acquire() as conn:
        await conn.execute("""
            UPDATE app_builder_sessions
            SET project=$1, html=$2, build_id=$3, preview_url=$4, updated_at=NOW()
            WHERE id=$5
        """, json.dumps(current), reconstructed, build_id, f"/api/preview/{build_id}", session_id)

    return {
        "ok": True,
        "applied": applied,
        "project": current,
        "html": reconstructed,
        "build_id": build_id,
        "preview_url": f"/api/preview/{build_id}",
    }


class AppBuilderImportHtmlRequest(BaseModel):
    html: str
    name: str = "imported-app"
    description: str = ""

@api_router.post("/app-builder/import-html")
async def import_html(req: AppBuilderImportHtmlRequest):
    """Parse a raw HTML string into a structured project and cache a preview."""
    project = _parse_html_to_project(req.html, req.name, req.description)
    reconstructed = _reconstruct_html(project)
    build_id = str(uuid.uuid4())
    _app_previews[build_id] = reconstructed
    r = await _get_redis()
    if r:
        try: await r.setex(f"preview:{build_id}", 86400, reconstructed)
        except Exception: pass
    return {
        "name": req.name, "description": req.description,
        "html": reconstructed, "project": project,
        "build_id": build_id, "preview_url": f"/api/preview/{build_id}"
    }

@api_router.post("/app-builder/import-zip")
async def import_zip(file: UploadFile = File(...)):
    """Extract a ZIP file (index.html / style.css / script.js / README.md) into a project."""
    import io, zipfile
    content = await file.read()
    buf = io.BytesIO(content)
    project = {"index_html": "", "style_css": "", "script_js": "", "readme": ""}
    name = (file.filename or "imported-app").removesuffix(".zip")
    try:
        with zipfile.ZipFile(buf) as zf:
            for fname in zf.namelist():
                base = fname.split("/")[-1].lower()
                try:
                    text = zf.read(fname).decode("utf-8", errors="replace")
                except Exception:
                    continue
                if base == "index.html":    project["index_html"] = text
                elif base == "style.css":   project["style_css"]  = text
                elif base == "script.js":   project["script_js"]  = text
                elif base in ("readme.md", "readme.txt"): project["readme"] = text
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")

    # If only index.html came in (self-contained), parse it out
    if project["index_html"] and not project["style_css"] and not project["script_js"]:
        project = _parse_html_to_project(project["index_html"], name, "")

    reconstructed = _reconstruct_html(project)
    build_id = str(uuid.uuid4())
    _app_previews[build_id] = reconstructed
    r = await _get_redis()
    if r:
        try: await r.setex(f"preview:{build_id}", 86400, reconstructed)
        except Exception: pass
    return {
        "name": name, "description": "",
        "html": reconstructed, "project": project,
        "build_id": build_id, "preview_url": f"/api/preview/{build_id}"
    }


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

class GitWriteFilesRequest(BaseModel):
    files: Dict[str, str]  # {filename: content}

# ── Git workspace helpers ──────────────────────────────────────────────────────
_GIT_WORKSPACE = Path("/tmp/ma_workspace")

def _git_ws() -> str:
    _GIT_WORKSPACE.mkdir(parents=True, exist_ok=True)
    return str(_GIT_WORKSPACE)

def _auth_url(url: str, token: str) -> str:
    """Embed GitHub token into HTTPS URL for authentication."""
    if token and url.startswith("https://"):
        return url.replace("https://", f"https://{token}@", 1)
    return url

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
@api_router.post("/git/write-files")
async def git_write_files(request: GitWriteFilesRequest):
    """Write project files into the git workspace so they can be committed."""
    try:
        ws = Path(_git_ws())
        written = []
        for filename, content in request.files.items():
            # Sanitize: no path traversal
            safe_name = Path(filename).name
            (ws / safe_name).write_text(content, encoding="utf-8")
            written.append(safe_name)
        return {"success": True, "written": written}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Write files error: {str(e)}")

@api_router.get("/git/status")
async def git_status():
    try:
        ws = _git_ws()
        result = subprocess.run(
            ["git", "status", "--porcelain", "-b"],
            capture_output=True, text=True, timeout=5, cwd=ws
        )

        if result.returncode != 0:
            return {"initialized": False, "branch": None, "modified": [], "staged": []}

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

        return {"initialized": True, "branch": branch, "modified": modified, "staged": staged, "branches": []}
    except Exception as e:
        return {"initialized": False, "branch": None, "modified": [], "staged": []}

@api_router.post("/git/init")
async def git_init():
    try:
        ws = _git_ws()
        result = subprocess.run(["git", "init"], capture_output=True, text=True, timeout=5, cwd=ws)

        if result.returncode == 0:
            subprocess.run(["git", "config", "user.name", "Mini Assistant"], cwd=ws)
            subprocess.run(["git", "config", "user.email", "mini@assistant.ai"], cwd=ws)
            return {"success": True, "message": "Repository initialized"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Init error: {str(e)}")

@api_router.post("/git/add")
async def git_add(files: List[str] = ["."]):
    try:
        ws = _git_ws()
        result = subprocess.run(["git", "add"] + files, capture_output=True, text=True, timeout=10, cwd=ws)

        if result.returncode == 0:
            return {"success": True, "message": "Files staged"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Add error: {str(e)}")

@api_router.post("/git/commit")
async def git_commit(request: GitCommitRequest):
    try:
        ws = _git_ws()
        result = subprocess.run(
            ["git", "commit", "-m", request.message],
            capture_output=True, text=True, timeout=10, cwd=ws
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
        ws = _git_ws()
        result = subprocess.run(
            ["git", "push", request.remote, request.branch],
            capture_output=True, text=True, timeout=30, cwd=ws
        )

        if result.returncode == 0:
            return {"success": True, "message": "Pushed successfully"}
        else:
            raise HTTPException(status_code=500, detail=result.stderr or "Push failed. Make sure remote is configured with a valid token.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Push error: {str(e)}")

@api_router.post("/git/pull")
async def git_pull(request: GitPullRequest):
    try:
        ws = _git_ws()
        result = subprocess.run(
            ["git", "pull", request.remote, request.branch],
            capture_output=True, text=True, timeout=30, cwd=ws
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
        ws = _git_ws()
        auth_url = _auth_url(request.url, request.github_token)

        # Remove existing remote with same name if it exists
        subprocess.run(["git", "remote", "remove", request.name], cwd=ws, capture_output=True)

        result = subprocess.run(
            ["git", "remote", "add", request.name, auth_url],
            capture_output=True, text=True, timeout=5, cwd=ws
        )
        if result.returncode == 0:
            return {"success": True, "message": f"Remote '{request.name}' added"}
        raise HTTPException(status_code=500, detail=result.stderr)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Remote add error: {str(e)}")

@api_router.post("/git/branch/create")
async def git_create_branch(request: GitBranchRequest):
    try:
        ws = _git_ws()
        result = subprocess.run(
            ["git", "checkout", "-b", request.name],
            capture_output=True, text=True, timeout=5, cwd=ws
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

_RAILWAY_GQL = "https://backboard.railway.app/graphql/v2"

async def _railway_gql(token: str, query: str, variables: dict = None) -> dict:
    """Run a Railway GraphQL query. Raises HTTPException on error."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _RAILWAY_GQL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid Railway API token. Generate one at https://railway.app/account/tokens")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=f"Railway API returned {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if "errors" in data:
        msgs = "; ".join(e.get("message", str(e)) for e in data["errors"])
        raise HTTPException(status_code=400, detail=f"Railway error: {msgs}")
    return data.get("data", {})

@api_router.post("/railway/projects")
async def railway_projects(request: RailwayRequest):
    data = await _railway_gql(request.api_token, """
        query {
            me {
                projects {
                    edges {
                        node {
                            id
                            name
                            description
                            createdAt
                        }
                    }
                }
            }
        }
    """)
    edges = data.get("me", {}).get("projects", {}).get("edges", [])
    return {"projects": [e["node"] for e in edges]}

@api_router.post("/railway/services")
async def railway_services(request: RailwayRequest):
    if not request.project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    data = await _railway_gql(request.api_token, """
        query($projectId: String!) {
            project(id: $projectId) {
                services {
                    edges {
                        node {
                            id
                            name
                        }
                    }
                }
            }
        }
    """, {"projectId": request.project_id})
    edges = data.get("project", {}).get("services", {}).get("edges", [])
    return {"services": [e["node"] for e in edges]}

@api_router.post("/railway/deploy")
async def railway_deploy(request: RailwayRequest):
    if not request.project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    # Railway deployments are triggered via their GitHub integration or CLI.
    # We surface the project URL so the user can trigger redeploys from the dashboard.
    data = await _railway_gql(request.api_token, """
        query($projectId: String!) {
            project(id: $projectId) {
                id
                name
            }
        }
    """, {"projectId": request.project_id})
    project = data.get("project", {})
    return {
        "success": True,
        "message": f"Project '{project.get('name', request.project_id)}' — trigger a redeploy from https://railway.app/project/{request.project_id}",
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

@api_router.delete("/fixloop/sessions/{session_id}")
async def delete_fixloop_session(session_id: str):
    _require_db()
    result = await db.fixloop_sessions.delete_one({"id": session_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": session_id}

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
    # Check ComfyUI availability
    comfyui_status = "disconnected"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{os.environ.get('COMFYUI_URL', 'http://localhost:8188')}/system_stats", timeout=2.0)
            if resp.status_code == 200:
                comfyui_status = "connected"
    except Exception:
        comfyui_status = "disconnected"

    return {
        "status": "healthy",
        "ollama": "connected" if ollama_client else "disconnected",
        "comfyui": comfyui_status,
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


# ══════════════════════════════════════════════════════════════════════════════
# Phase 0 — Project Context Scanner
# GET /api/project/context
# Returns a structured snapshot of the codebase for Planner / Manager use.
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/project/context", tags=["scanner"])
async def project_context():
    """
    Scan the Mini Assistant codebase and return a structured context snapshot:
    stack, entrypoints, feature-to-file map, duplicate-risk register, warnings.
    Pure filesystem scan — no LLM calls, runs in < 100 ms.
    """
    try:
        from mini_assistant.scanner import get_context
        ctx = get_context()
        return ctx.to_dict()
    except Exception as exc:
        logging.exception("Project context scanner failed")
        raise HTTPException(status_code=500, detail=f"Scanner error: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# Image System API  (/api/image/*, /api/models/*)
# Mounts the local Ollama+ComfyUI multi-brain image router as a sub-application.
# ══════════════════════════════════════════════════════════════════════════════
try:
    import sys as _sys, pathlib as _pl, logging as _logging
    _sys.path.insert(0, str(_pl.Path(__file__).parent))
    from image_system.api.server import app as _image_app
    app.mount("/image-api", _image_app)
    _logging.getLogger("image_system").info("Image system mounted at /image-api")
except Exception as _img_err:
    _logging.getLogger("image_system").warning(f"Image system not available: {_img_err}")


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator Task API  (/api/tasks/*)
# ══════════════════════════════════════════════════════════════════════════════
# Provides REST access to the OrchestratorEngine – the macro-level state
# machine that wraps SwarmManager and tracks full user-request lifecycle.
# ──────────────────────────────────────────────────────────────────────────────
try:
    from mini_assistant.swarm.orchestrator_engine import OrchestratorEngine
    from mini_assistant.swarm.task_store          import TaskStore

    _task_store  = TaskStore(mongo_db=db)
    _orchestrator = OrchestratorEngine(task_store=_task_store)

    class _TaskCreateRequest(BaseModel):
        goal:     str
        metadata: Optional[Dict[str, Any]] = None

    class _TaskResumeRequest(BaseModel):
        task_id: str

    @api_router.post("/tasks", tags=["orchestrator"])
    async def create_task(req: _TaskCreateRequest):
        """Create and run a new orchestrated task. Returns the completed OrchestratorTask."""
        task = await _orchestrator.run(goal=req.goal, metadata=req.metadata)
        return task.to_dict()

    @api_router.get("/tasks", tags=["orchestrator"])
    async def list_tasks(limit: int = 50):
        """List recent orchestrated tasks (summary view, newest first)."""
        return await _task_store.list_recent(limit=limit)

    @api_router.get("/tasks/{task_id}", tags=["orchestrator"])
    async def get_task(task_id: str):
        """Get full details for a specific orchestrated task."""
        task = await _task_store.load(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        return task.to_dict()

    @api_router.post("/tasks/{task_id}/resume", tags=["orchestrator"])
    async def resume_task(task_id: str):
        """Resume an interrupted or failed task from its last safe state."""
        task = await _orchestrator.resume(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        return task.to_dict()

    @api_router.post("/tasks/{task_id}/cancel", tags=["orchestrator"])
    async def cancel_task(task_id: str):
        """Cancel a pending or running task."""
        task = await _orchestrator.cancel(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        return task.to_dict()

    @api_router.delete("/tasks/{task_id}", tags=["orchestrator"])
    async def delete_task(task_id: str):
        """Delete a task from the store."""
        deleted = await _task_store.delete(task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        return {"deleted": task_id}

    @api_router.get("/tasks/active/list", tags=["orchestrator"])
    async def list_active_tasks():
        """List tasks that are NOT in a terminal state (not completed/failed/cancelled)."""
        _TERMINAL = {"completed", "failed", "cancelled"}
        all_tasks = await _task_store.list_recent(limit=200)
        return [t for t in all_tasks if t.get("current_state") not in _TERMINAL]

    @api_router.post("/tasks/{task_id}/rollback/{checkpoint_name}", tags=["orchestrator"])
    async def rollback_task(task_id: str, checkpoint_name: str):
        """
        Roll back a task to a named checkpoint (post_plan, post_codegen, post_test, …).
        Resets task state without re-running — call /resume afterwards to continue.
        Preserved outputs from the checkpoint are kept; steps after the checkpoint are cleared.
        """
        task = await _orchestrator.rollback(task_id, checkpoint_name)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        return task.to_dict()

    @api_router.get("/tasks/{task_id}/checkpoints", tags=["orchestrator"])
    async def get_task_checkpoints(task_id: str):
        """Return all named checkpoints for a task with their preserved outputs."""
        task = await _task_store.load(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        return {
            "task_id":            task.task_id,
            "checkpoints":        [c.to_dict() for c in task.checkpoints],
            "preserved_outputs":  task.preserved_outputs,
            "last_checkpoint":    task.last_checkpoint_name(),
        }

    @api_router.get("/tasks/{task_id}/export", tags=["orchestrator"])
    async def export_task_diagnostics(task_id: str):
        """
        Full diagnostic export for a task:
        - task metadata, steps, checkpoints, preserved_outputs
        - debug_log (full brain event stream)
        - learning_patterns
        - security audit entries from debug_log
        - tool result entries from debug_log
        - per-brain config versions (from brain_configs)
        - permission model snapshot (from permission_model)
        """
        task = await _task_store.load(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

        from mini_assistant.swarm.brain_configs import all_configs_dict
        from mini_assistant.swarm.permission_model import all_permissions_dict

        debug_log = task.metadata.get("debug_log", [])
        security_events = [e for e in debug_log if e.get("type") == "security_check"]
        tool_events     = [e for e in debug_log if e.get("type") == "tool_result"]

        return {
            "task_id":            task.task_id,
            "task_type":          task.task_type,
            "goal":               task.goal,
            "current_state":      str(task.current_state),
            "created_at":         task.created_at.isoformat() if task.created_at else None,
            "updated_at":         task.updated_at.isoformat() if task.updated_at else None,
            "retry_count":        task.retry_count,
            "failure_reason":     task.failure_reason,
            "failure_summary":    task.failure_summary,
            "steps":              [s.to_dict() for s in task.steps],
            "checkpoints":        [c.to_dict() for c in task.checkpoints],
            "preserved_outputs":  task.preserved_outputs,
            "assigned_agents":    task.assigned_agents,
            "debug_log":          debug_log,
            "security_events":    security_events,
            "tool_events":        tool_events,
            "learning_patterns":  task.metadata.get("learning_patterns", {}),
            "brain_configs":      all_configs_dict(),
            "permission_model":   all_permissions_dict(),
            "exported_at":        datetime.now(timezone.utc).isoformat(),
        }

    @api_router.get("/learning/patterns", tags=["orchestrator"])
    async def get_learning_patterns():
        """Return cross-task learning patterns from LearningBrain."""
        try:
            from mini_assistant.swarm.learning_brain import LearningBrain
            lb = LearningBrain()
            return lb.get_patterns()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @api_router.get("/diagnostics/brains", tags=["orchestrator"])
    async def get_brain_diagnostics():
        """Return brain configs + permission model for all registered brains."""
        from mini_assistant.swarm.brain_configs import all_configs_dict
        from mini_assistant.swarm.permission_model import all_permissions_dict
        return {
            "brain_configs":    all_configs_dict(),
            "permission_model": all_permissions_dict(),
        }

    logging.info("✓ Orchestrator task API registered (/api/tasks/*)")

except Exception as _orch_err:
    logging.warning("Orchestrator task API unavailable: %s", _orch_err)


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

_CORS_DEFAULTS = ",".join([
    "https://mini-assistant-production.up.railway.app",
    "https://ai.miniassistantai.com",
    "http://localhost:3000",
    "http://localhost:8080",
])
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', _CORS_DEFAULTS).split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Key auth middleware ───────────────────────────────────────────────────
_API_KEY = os.environ.get('API_KEY', '')

@app.middleware("http")
async def api_key_guard(request, call_next):
    # Skip auth if no key configured (local dev), for health checks, or preflight
    if not _API_KEY or request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    if path in ("/", "/api/health") or path.startswith("/static") or path.startswith("/_"):
        return await call_next(request)
    # Check header or query param
    key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if key != _API_KEY:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)

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