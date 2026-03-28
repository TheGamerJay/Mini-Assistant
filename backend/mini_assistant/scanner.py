"""
scanner.py — Phase 0 · Project Context Scanner
───────────────────────────────────────────────
Walks the Mini Assistant codebase and produces a structured snapshot of:

  • detected tech stack
  • frontend / backend roots
  • probable entrypoints
  • feature-to-file map  (chat, upload, image gen, mic, builder, memory, …)
  • duplicate-risk register  (files that implement the same concern)
  • architecture warnings

The scanner is purely filesystem-based — no LLM calls, no external services.
It runs in milliseconds and is safe to call on every request if needed.

Consumers (Planner, Manager, Critic) import ``get_context()`` directly, or
reach it via the REST endpoint  GET /api/project/context.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# ── Resolve project root ──────────────────────────────────────────────────────
# scanner.py lives at  backend/mini_assistant/scanner.py
# project root is two levels up
_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parent.parent.parent   # …/Mini Assistant/

BACKEND_ROOT  = PROJECT_ROOT / "backend"
FRONTEND_ROOT = PROJECT_ROOT / "frontend" / "src"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _rel(p: Path) -> str:
    """Return a path relative to PROJECT_ROOT, forward-slash separated."""
    try:
        return p.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _exists(rel: str) -> bool:
    return (PROJECT_ROOT / rel).exists()


def _file_size(rel: str) -> int:
    p = PROJECT_ROOT / rel
    return p.stat().st_size if p.exists() else 0


def _find(root: Path, glob: str, max_depth: int = 10) -> list[str]:
    """Glob under *root* and return relative paths (PROJECT_ROOT-relative)."""
    if not root.exists():
        return []
    results: list[str] = []
    for p in root.rglob(glob):
        # honour max_depth (count path segments below root)
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if len(rel.parts) > max_depth:
            continue
        results.append(_rel(p))
    return sorted(results)


def _grep_first(rel: str, pattern: str) -> bool:
    """Return True if *pattern* appears in the file at *rel*."""
    p = PROJECT_ROOT / rel
    if not p.exists():
        return False
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
        return bool(re.search(pattern, text))
    except OSError:
        return False


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class FeatureFiles:
    """Canonical file list for one product feature."""
    feature: str
    description: str
    files: list[str] = field(default_factory=list)
    status: str = "present"          # present | partial | missing


@dataclass
class DuplicateRisk:
    """Two or more files that implement the same concern."""
    concern: str
    files: list[str]
    severity: str                    # high | medium | low
    recommendation: str


@dataclass
class ProjectContext:
    """Full structured snapshot returned by get_context()."""
    scanned_at: str
    project_root: str
    stack: dict[str, Any]
    frontend_root: str
    backend_root: str
    entrypoints: list[str]
    feature_map: list[FeatureFiles]
    duplicate_risks: list[DuplicateRisk]
    warnings: list[str]
    file_counts: dict[str, int]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ── Stack detection ───────────────────────────────────────────────────────────

def _detect_stack() -> dict[str, Any]:
    pkg = PROJECT_ROOT / "frontend" / "package.json"
    req = BACKEND_ROOT / "requirements.txt"

    frontend_fw = "React"
    frontend_builder = "Craco"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if "next" in deps:
                frontend_fw = "Next.js"
            elif "vite" in deps:
                frontend_builder = "Vite"
            react_ver = deps.get("react", "unknown")
        except Exception:
            react_ver = "unknown"
    else:
        react_ver = "unknown"
        deps = {}

    backend_fw = "FastAPI"
    python_ver = "3.11"

    has_mongo    = _exists("backend/requirements.txt") and _grep_first("backend/requirements.txt", r"motor|pymongo")
    has_postgres = _grep_first("backend/requirements.txt", r"asyncpg|psycopg")
    has_redis    = _grep_first("backend/requirements.txt", r"redis")
    has_ollama   = _grep_first("backend/requirements.txt", r"ollama")
    has_whisper  = _grep_first("backend/requirements.txt", r"faster.whisper|whisper")
    has_image_system = _exists("backend/image_system")

    databases = []
    if has_mongo:    databases.append("MongoDB")
    if has_postgres: databases.append("PostgreSQL")
    if has_redis:    databases.append("Redis")

    return {
        "frontend": f"{frontend_fw} {react_ver}",
        "frontend_build": frontend_builder,
        "frontend_css": "Tailwind CSS" if "tailwindcss" in deps else "CSS",
        "backend": backend_fw,
        "python": python_ver,
        "databases": databases,
        "llm_runtime": "Ollama" if has_ollama else "unknown",
        "speech_to_text": "faster-whisper" if has_whisper else "none",
        "image_gen": "DALL-E" if has_image_system else "none",
        "deployment": "Railway / Docker" if _exists("Dockerfile") else "unknown",
    }


# ── Entrypoints ───────────────────────────────────────────────────────────────

def _detect_entrypoints() -> list[str]:
    candidates = [
        "backend/server.py",
        "backend/mini_assistant/main.py",
        "backend/image_system/api/server.py",
        "frontend/src/index.js",
        "frontend/src/App.js",
        "Dockerfile",
        "railway.toml",
        "nixpacks.toml",
        "start.sh",
        "setup.sh",
    ]
    return [c for c in candidates if _exists(c)]


# ── Feature map ───────────────────────────────────────────────────────────────

def _build_feature_map() -> list[FeatureFiles]:
    features: list[FeatureFiles] = []

    # ── 1. Chat routing ───────────────────────────────────────────────────────
    chat_files = [f for f in [
        "backend/image_system/api/server.py",       # primary /api/chat endpoint
        "backend/mini_assistant/router.py",          # 8-matcher intent router
        "backend/agents.py",                         # legacy brain router
        "backend/mini_assistant/planner.py",         # task planner
        "frontend/src/api/client.js",                # api.chat()
        "frontend/src/hooks/useChat.js",             # useChat hook
        "frontend/src/pages/ChatPage.js",            # main chat UI
        "frontend/src/components/ChatMessage.js",    # message renderer
        "frontend/src/components/ChatInput.js",      # input area
    ] if _exists(f)]
    features.append(FeatureFiles(
        feature="chat_routing",
        description="End-to-end chat flow: input → router → brain → response",
        files=chat_files,
        status="present",
    ))

    # ── 2. Image generation ───────────────────────────────────────────────────
    img_gen_files = [f for f in [
        "backend/image_system/api/server.py",           # /api/image/generate
        "backend/image_system/brains/router_brain.py",  # router brain
        "backend/image_system/services/dalle_client.py",
        "backend/image_system/services/prompt_builder.py",
        "backend/image_system/services/image_reviewer.py",
        "backend/mini_assistant/tools/image_gen.py",    # ← DUPLICATE RISK
        "frontend/src/pages/ImagePage.js",
        "frontend/src/components/ImageCard.js",
    ] if _exists(f)]
    features.append(FeatureFiles(
        feature="image_generation",
        description="DALL-E 3 powered image generation pipeline",
        files=img_gen_files,
        status="present",
    ))

    # ── 3. Image analysis / vision ───────────────────────────────────────────
    vision_files = [f for f in [
        "backend/image_system/api/server.py",           # /api/image/analyze
        "backend/image_system/brains/vision_brain.py",
        "backend/mini_assistant/brains/vision.py",      # ← DUPLICATE RISK
    ] if _exists(f)]
    features.append(FeatureFiles(
        feature="image_analysis",
        description="Vision brain for analyzing uploaded images / screenshots",
        files=vision_files,
        status="present",
    ))

    # ── 4. Upload system ─────────────────────────────────────────────────────
    upload_files = [f for f in [
        "frontend/src/components/ChatInput.js",         # file picker + base64
        "backend/server.py",                            # /voice/stt FormData upload
        "backend/image_system/api/server.py",           # analyze endpoint accepts base64
    ] if _exists(f)]
    features.append(FeatureFiles(
        feature="upload",
        description="File and image upload handling",
        files=upload_files,
        status="present",
    ))

    # ── 5. Microphone / speech ───────────────────────────────────────────────
    mic_files = [f for f in [
        "frontend/src/components/Voice/VoiceControl.js",
        "backend/server.py",    # /voice/stt + /voice/tts
    ] if _exists(f)]
    features.append(FeatureFiles(
        feature="mic_speech",
        description="Microphone recording → Whisper STT → text insertion",
        files=mic_files,
        status="present" if mic_files else "missing",
    ))

    # ── 6. App builder ───────────────────────────────────────────────────────
    builder_files = [f for f in [
        "frontend/src/components/AppBuilder/AppBuilder.js",
        "backend/server.py",    # /api/app-builder/* routes
        "frontend/src/utils/projectTree.js",
    ] if _exists(f)]
    features.append(FeatureFiles(
        feature="app_builder",
        description="AI-driven coach → build → edit → export web app generator",
        files=builder_files,
        status="present",
    ))

    # ── 7. Session / memory ──────────────────────────────────────────────────
    memory_files = [f for f in [
        "backend/mini_assistant/memory/conversation_memory.py",
        "backend/mini_assistant/memory/long_term_memory.py",
        "backend/mini_assistant/memory/vector_store.py",
        "backend/mini_assistant/memory/solution_memory.py",
        "frontend/src/context/AppContext.js",
        "frontend/src/hooks/usePersist.js",
    ] if _exists(f)]
    features.append(FeatureFiles(
        feature="session_memory",
        description="Conversation ring-buffer, long-term JSON store, vector RAG, solution cache",
        files=memory_files,
        status="present",
    ))

    # ── 8. Tool registry ─────────────────────────────────────────────────────
    tool_files = [f for f in [
        "frontend/src/App.js",          # TOOL_PAGES map
        "frontend/src/layout/Sidebar.js",
        "frontend/src/layout/MainPanel.js",
        "backend/mini_assistant/swarm/tool_brain.py",
    ] if _exists(f)]
    features.append(FeatureFiles(
        feature="tool_registry",
        description="Frontend tool dispatch (TOOL_PAGES) and sidebar navigation",
        files=tool_files,
        status="present",
    ))

    # ── 9. Slash commands ────────────────────────────────────────────────────
    slash_files = [f for f in [
        "frontend/src/components/ChatInput.js",   # no parser yet — placeholder
    ] if _exists(f)]
    # Confirm whether a slash parser actually exists
    has_slash = _grep_first("frontend/src/components/ChatInput.js", r"startsWith\(['\"]\/")
    features.append(FeatureFiles(
        feature="slash_commands",
        description="Slash-command parser for forced intent routing (/fix, /build, /image …)",
        files=slash_files if has_slash else [],
        status="partial" if has_slash else "missing",
    ))

    # ── 10. Planner ──────────────────────────────────────────────────────────
    planner_files = [f for f in [
        "backend/mini_assistant/planner.py",
        "backend/mini_assistant/executor.py",
        "backend/mini_assistant/swarm/planner_agent.py",
    ] if _exists(f)]
    features.append(FeatureFiles(
        feature="planner",
        description="Task planning: breaks requests into ordered / parallel steps",
        files=planner_files,
        status="present" if planner_files else "missing",
    ))

    # ── 11. Swarm orchestration ──────────────────────────────────────────────
    swarm_files = _find(BACKEND_ROOT / "mini_assistant" / "swarm", "*.py")
    features.append(FeatureFiles(
        feature="swarm_orchestration",
        description="Multi-agent swarm: manager → specialist agents → parallel execution",
        files=swarm_files,
        status="present" if swarm_files else "missing",
    ))

    # ── 12. Web search ───────────────────────────────────────────────────────
    search_files = [f for f in [
        "backend/mini_assistant/tools/search.py",
        "backend/server.py",                        # /api/search/web
        "frontend/src/components/Search/WebSearch.js",
    ] if _exists(f)]
    features.append(FeatureFiles(
        feature="web_search",
        description="DuckDuckGo-powered web search tool",
        files=search_files,
        status="present" if search_files else "missing",
    ))

    # ── 13. Self-improvement / reflection ────────────────────────────────────
    reflection_files = _find(BACKEND_ROOT / "mini_assistant" / "self_improvement", "*.py")
    features.append(FeatureFiles(
        feature="self_improvement",
        description="Repair loop, reflection, test generation, code review",
        files=reflection_files,
        status="present" if reflection_files else "missing",
    ))

    # ── 14. Config / environment ─────────────────────────────────────────────
    config_files = [f for f in [
        "backend/.env",
        "backend/mini_assistant/config.py",
        "frontend/.env",
        "frontend/.env.local",
        "frontend/.env.production",
        "backend/requirements.txt",
        "frontend/package.json",
        "Dockerfile",
        "railway.toml",
        "nixpacks.toml",
    ] if _exists(f)]
    features.append(FeatureFiles(
        feature="config_environment",
        description="Environment variables, model config, dependency manifests, deployment config",
        files=config_files,
        status="present",
    ))

    return features


# ── Duplicate-risk register ───────────────────────────────────────────────────

def _detect_duplicate_risks() -> list[DuplicateRisk]:
    risks: list[DuplicateRisk] = []

    # 1. Chat routing
    has_router  = _exists("backend/mini_assistant/router.py")
    has_agents  = _exists("backend/agents.py")
    if has_router and has_agents:
        risks.append(DuplicateRisk(
            concern="Chat intent routing",
            files=["backend/mini_assistant/router.py", "backend/agents.py"],
            severity="high",
            recommendation=(
                "agents.py appears to be an older routing layer. "
                "Verify it is not called from server.py for the same code path as "
                "mini_assistant/router.py. Consolidate into one router before Phase 1."
            ),
        ))

    # 2. Chat UI components
    has_chat_page  = _exists("frontend/src/pages/ChatPage.js")
    has_chat_iface = _exists("frontend/src/components/ChatInterface.js")
    has_legacy_chat = _exists("frontend/src/components/Chat/ChatInterface.js")
    legacy = [f for f in [
        "frontend/src/components/ChatInterface.js",
        "frontend/src/components/Chat/ChatInterface.js",
    ] if _exists(f)]
    if has_chat_page and legacy:
        risks.append(DuplicateRisk(
            concern="Chat UI component",
            files=["frontend/src/pages/ChatPage.js"] + legacy,
            severity="medium",
            recommendation=(
                "ChatPage.js is the active chat UI. "
                "The ChatInterface.js files are legacy and should not receive new features. "
                "Consider removing them to prevent confusion."
            ),
        ))

    # 3. Image generation paths
    has_image_api = _exists("backend/image_system/api/server.py")
    has_image_tool = _exists("backend/mini_assistant/tools/image_gen.py")
    if has_image_api and has_image_tool:
        risks.append(DuplicateRisk(
            concern="Image generation implementation",
            files=[
                "backend/image_system/api/server.py",
                "backend/mini_assistant/tools/image_gen.py",
            ],
            severity="high",
            recommendation=(
                "Two separate image generation paths exist. "
                "mini_assistant/tools/image_gen.py should delegate to the image_system API "
                "rather than calling DALL-E directly. Unify before adding new generation features."
            ),
        ))

    # 4. Brain implementations split across 3 locations
    brains_core   = list((BACKEND_ROOT / "mini_assistant" / "brains").glob("*.py")) if (BACKEND_ROOT / "mini_assistant" / "brains").exists() else []
    brains_swarm  = list((BACKEND_ROOT / "mini_assistant" / "swarm").glob("*_agent.py")) if (BACKEND_ROOT / "mini_assistant" / "swarm").exists() else []
    brains_image  = list((BACKEND_ROOT / "image_system" / "brains").glob("*.py")) if (BACKEND_ROOT / "image_system" / "brains").exists() else []
    if brains_core and brains_swarm:
        risks.append(DuplicateRisk(
            concern="Brain / agent implementations",
            files=[
                "backend/mini_assistant/brains/  (single-agent brains)",
                "backend/mini_assistant/swarm/*_agent.py  (swarm agents)",
                "backend/image_system/brains/  (image-system brains)",
            ],
            severity="medium",
            recommendation=(
                "Brain logic is split across 3 directories. "
                "When adding new specialist brains (Planner, CEO, Critic, etc.) "
                "place them in mini_assistant/brains/ and register them in the router. "
                "Do NOT create a 4th brain location."
            ),
        ))

    # 5. Vision brain split
    has_vision_image  = _exists("backend/image_system/brains/vision_brain.py")
    has_vision_core   = _exists("backend/mini_assistant/brains/vision.py")
    if has_vision_image and has_vision_core:
        risks.append(DuplicateRisk(
            concern="Vision brain duplication",
            files=[
                "backend/image_system/brains/vision_brain.py",
                "backend/mini_assistant/brains/vision.py",
            ],
            severity="medium",
            recommendation=(
                "Two vision brain implementations exist. "
                "image_system/brains/vision_brain.py is the active one (called from /api/image/analyze). "
                "mini_assistant/brains/vision.py should proxy to it or be merged."
            ),
        ))

    # 6. Project tree conversion logic
    has_server_pt    = _grep_first("backend/server.py", r"_pt_flat_to_tree|_pt_file_node")
    has_frontend_pt  = _exists("frontend/src/utils/projectTree.js")
    if has_server_pt and has_frontend_pt:
        risks.append(DuplicateRisk(
            concern="Project tree conversion logic",
            files=[
                "backend/server.py  (_pt_* helper functions)",
                "frontend/src/utils/projectTree.js",
            ],
            severity="low",
            recommendation=(
                "V1↔V2 project format conversion exists in both backend Python and frontend JS. "
                "Keep them in sync when changing project schema. "
                "Long-term: move conversion to backend only."
            ),
        ))

    # 7. Memory system fragmentation
    memory_layers = [f for f in [
        "backend/mini_assistant/memory/conversation_memory.py",
        "backend/mini_assistant/memory/long_term_memory.py",
        "backend/mini_assistant/memory/vector_store.py",
        "backend/mini_assistant/memory/solution_memory.py",
    ] if _exists(f)]
    if len(memory_layers) >= 3:
        risks.append(DuplicateRisk(
            concern="Memory system fragmentation",
            files=memory_layers,
            severity="low",
            recommendation=(
                "4 separate memory layers exist with no shared access interface. "
                "Phase 2+ should wire a MemoryBrain facade that queries all layers consistently. "
                "Do not add a 5th layer — extend the existing ones."
            ),
        ))

    return risks


# ── Warnings ─────────────────────────────────────────────────────────────────

def _build_warnings(
    feature_map: list[FeatureFiles],
    risks: list[DuplicateRisk],
) -> list[str]:
    warnings: list[str] = []

    # Slash commands missing
    slash = next((f for f in feature_map if f.feature == "slash_commands"), None)
    if slash and slash.status == "missing":
        warnings.append(
            "MISSING: Slash command parser not implemented. "
            "ChatInput.js needs a /command prefix detector before Phase 1 routing works."
        )

    # No CEO / Manager / Supervisor yet
    for module, label in [
        ("backend/mini_assistant/ceo.py",      "CEO Layer"),
        ("backend/mini_assistant/manager.py",  "Manager Layer"),
        ("backend/mini_assistant/supervisor.py","Supervisor Layer"),
        ("backend/mini_assistant/critic.py",   "Critic Layer"),
        ("backend/mini_assistant/composer.py", "Response Composer"),
        ("backend/mini_assistant/skills",      "Skill Library"),
    ]:
        if not _exists(module):
            warnings.append(f"NOT YET BUILT: {label} ({module})")

    # High-severity risks
    for r in risks:
        if r.severity == "high":
            warnings.append(f"HIGH RISK — {r.concern}: {r.recommendation}")

    # Check if planner is actually wired into chat flow
    planner_used_in_chat = _grep_first(
        "backend/image_system/api/server.py", r"from.*planner|import.*planner|planner\.plan"
    )
    if not planner_used_in_chat:
        warnings.append(
            "Planner is NOT wired into the chat endpoint. "
            "mini_assistant/planner.py exists but /api/chat bypasses it. "
            "Phase 1 must wire Planner as mandatory first step."
        )

    return warnings


# ── File counts ───────────────────────────────────────────────────────────────

def _count_files() -> dict[str, int]:
    counts: dict[str, int] = {}
    for label, root, pattern in [
        ("backend_py",      BACKEND_ROOT,  "*.py"),
        ("frontend_js_jsx", FRONTEND_ROOT, "*.js"),
        ("frontend_jsx",    FRONTEND_ROOT, "*.jsx"),
        ("frontend_ts",     FRONTEND_ROOT, "*.ts"),
        ("frontend_tsx",    FRONTEND_ROOT, "*.tsx"),
    ]:
        counts[label] = len(_find(root, pattern))
    return counts


# ── Public API ────────────────────────────────────────────────────────────────

def get_context() -> ProjectContext:
    """
    Scan the project and return a ProjectContext snapshot.

    Returns:
        ProjectContext — structured dict-serialisable snapshot.

    Example::
        from mini_assistant.scanner import get_context
        ctx = get_context()
        print(ctx.to_json())
    """
    t0 = time.perf_counter()

    stack        = _detect_stack()
    entrypoints  = _detect_entrypoints()
    feature_map  = _build_feature_map()
    dup_risks    = _detect_duplicate_risks()
    warnings     = _build_warnings(feature_map, dup_risks)
    file_counts  = _count_files()

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    ctx = ProjectContext(
        scanned_at=f"{__import__('datetime').datetime.utcnow().isoformat()}Z  (scan took {elapsed_ms} ms)",
        project_root=str(PROJECT_ROOT),
        stack=stack,
        frontend_root=_rel(FRONTEND_ROOT),
        backend_root=_rel(BACKEND_ROOT),
        entrypoints=entrypoints,
        feature_map=feature_map,
        duplicate_risks=dup_risks,
        warnings=warnings,
        file_counts=file_counts,
    )
    return ctx


# ── CLI smoke-test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ctx = get_context()
    print(ctx.to_json())