import os

# ─── Service endpoints ───────────────────────────────────────────────────────
LOCAL_AI  = os.getenv("LOCAL_AI",  "http://localhost:8000")   # FastAPI brain backend

# ─── AI API keys ─────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")

# ─── Assistant execution mode ─────────────────────────────────────────────────
# "single" – classic single-agent pipeline (router → planner → executor)
# "swarm"  – multi-agent swarm (manager → specialist agents run in parallel)
# Can be overridden per-request via chat(mode="swarm") or by env variable.
ASSISTANT_MODE = os.getenv("ASSISTANT_MODE", "single")

# ─── Brain model assignment ───────────────────────────────────────────────────
# Each brain can be overridden via environment variable.
# "cloud" suffix models require an Ollama-compatible proxy (e.g. LiteLLM).
MODELS = {
    "router":   os.getenv("ROUTER_MODEL",   "glm-4.7:cloud"),
    "coder":    os.getenv("CODER_MODEL",    "qwen3-coder:480b-cloud"),
    "vision":   os.getenv("VISION_MODEL",   "qwen3-vl:235b-cloud"),
    "research": os.getenv("RESEARCH_MODEL", "deepseek-v3:671b-cloud"),
    "fast":     os.getenv("FAST_MODEL",     "glm-4.7:cloud"),
    "fallback": os.getenv("FALLBACK_MODEL", "minimax-m2.1:cloud"),
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

# Image generation — uses OpenAI DALL-E 3 via OPENAI_API_KEY

# Code execution sandbox
CODE_TIMEOUT    = int(os.getenv("CODE_TIMEOUT", "15"))        # seconds
CODE_MAX_OUTPUT = int(os.getenv("CODE_MAX_OUTPUT", "4096"))   # chars

# ─── Memory / RAG ────────────────────────────────────────────────────────────
VECTOR_STORE_PATH     = os.getenv("VECTOR_STORE_PATH",     "./memory_store")
EMBED_MODEL           = os.getenv("EMBED_MODEL",           "all-MiniLM-L6-v2")
RAG_TOP_K             = int(os.getenv("RAG_TOP_K",         "5"))
LONG_TERM_MEMORY_PATH = os.getenv("LONG_TERM_MEMORY_PATH", "./memory_store/long_term.json")
SOLUTION_MEMORY_PATH  = os.getenv("SOLUTION_MEMORY_PATH",  "./memory_store/solutions.json")
REFLECTION_LOG_PATH   = os.getenv("REFLECTION_LOG_PATH",   "./memory_store/reflections.json")

# ─── Self-improvement ────────────────────────────────────────────────────────
# Maximum repair attempts before giving up and returning best-effort output
REPAIR_MAX_RETRIES    = int(os.getenv("REPAIR_MAX_RETRIES", "3"))

# Set to "0" to disable automatic test generation for coding tasks
AUTO_TEST_ENABLED     = os.getenv("AUTO_TEST_ENABLED", "1") == "1"

# Safety mode for computer control: "auto" | "confirm" | "dry-run"
COMPUTER_SAFETY_MODE  = os.getenv("COMPUTER_SAFETY_MODE", "confirm")

# ─── Swarm agent model assignment ────────────────────────────────────────────
# Each agent independently calls its assigned Ollama model.
# Override any via environment variable.
AGENT_MODELS = {
    "manager":      os.getenv("MANAGER_MODEL",       "glm-4.7:cloud"),
    "planner":      os.getenv("PLANNER_AGENT_MODEL", "glm-4.7:cloud"),
    "research":     os.getenv("RESEARCH_AGENT_MODEL","deepseek-v3:671b-cloud"),
    "coding":       os.getenv("CODING_AGENT_MODEL",  "qwen3-coder:480b-cloud"),
    "debug":        os.getenv("DEBUG_AGENT_MODEL",   "qwen3-coder:480b-cloud"),
    "tester":       os.getenv("TESTER_AGENT_MODEL",  "minimax-m2.1:cloud"),
    "file_analyst": os.getenv("FILE_ANALYST_MODEL",  "glm-4.7:cloud"),
    "vision":       os.getenv("VISION_AGENT_MODEL",  "qwen3-vl:235b-cloud"),
}

# Number of parallel workers in the swarm execution loop
SWARM_MAX_WORKERS = int(os.getenv("SWARM_MAX_WORKERS", "4"))
