import os

# ─── Ollama endpoints ────────────────────────────────────────────────────────
# Override OLLAMA_HOST to point at a remote/cloud Ollama gateway if needed.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# ─── Brain model assignment ───────────────────────────────────────────────────
# Each brain can be overridden via environment variable.
# "cloud" suffix models require an Ollama-compatible proxy (e.g. LiteLLM).
MODELS = {
    "router":   os.getenv("ROUTER_MODEL",   "qwen3:30b"),
    "coder":    os.getenv("CODER_MODEL",    "qwen3-coder:480b-cloud"),
    "vision":   os.getenv("VISION_MODEL",   "qwen3-vl:235b-cloud"),
    "research": os.getenv("RESEARCH_MODEL", "deepseek-v3:671b-cloud"),
    "fast":     os.getenv("FAST_MODEL",     "gemma3:4b"),
    # Always-available fallback when the primary model is not pulled locally
    "fallback": os.getenv("FALLBACK_MODEL", "qwen2.5:3b"),
}

# ─── Task type labels used by the router ─────────────────────────────────────
TASK_TYPES = [
    "coding",       # write / debug / explain code
    "vision",       # describe image, read screenshot
    "research",     # deep analysis, long-form reasoning
    "search",       # internet lookup
    "image_gen",    # generate an image
    "computer",     # control mouse / keyboard / GUI
    "memory",       # learn from / query documents
    "fast",         # quick factual or conversational response
]

# ─── Tool configuration ───────────────────────────────────────────────────────
# Web search
SEARCH_ENGINE   = os.getenv("SEARCH_ENGINE", "duckduckgo")   # or "tavily" / "brave"
TAVILY_API_KEY  = os.getenv("TAVILY_API_KEY", "")
BRAVE_API_KEY   = os.getenv("BRAVE_API_KEY", "")

# Image generation  (AUTOMATIC1111 or ComfyUI)
SD_HOST         = os.getenv("SD_HOST", "http://localhost:7860")
SD_BACKEND      = os.getenv("SD_BACKEND", "auto1111")         # or "comfyui"

# Code execution sandbox
CODE_TIMEOUT    = int(os.getenv("CODE_TIMEOUT", "15"))        # seconds
CODE_MAX_OUTPUT = int(os.getenv("CODE_MAX_OUTPUT", "4096"))   # chars

# ─── Memory / RAG ────────────────────────────────────────────────────────────
VECTOR_STORE_PATH = os.getenv("VECTOR_STORE_PATH", "./memory_store")
EMBED_MODEL       = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
RAG_TOP_K         = int(os.getenv("RAG_TOP_K", "5"))
