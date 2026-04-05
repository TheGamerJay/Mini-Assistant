"""
modules/github_brain.py — GitHub / Repo Inspection Brain.

CEO delegates ALL repo/file inspection here.
This brain reads, walks, and analyzes code. CEO never reads files directly.

Input (via decision dict):
  - github_url : str   GitHub repo URL (https://github.com/owner/repo)
  - branch     : str   optional, auto-detected if omitted
  - focus      : str   what the user wants to do — used to prioritise files
  - api_key_gh : str   optional GitHub token for private repos / higher rate limit

Output:
  {
    "type":                      "repo_inspection",
    "status":                    "success" | "error",
    "error":                     str,                   # only on error
    "project_type":              str,
    "tech_stack":                [str],
    "entry_points":              [str],
    "relevant_files":            [{"path": str, "purpose": str, "snippet": str}],
    "existing_features":         [str],
    "duplicate_candidates":      [{"concern": str, "files": [str]}],
    "recommended_patch_targets": [str],
    "file_tree_summary":         str,
    "notes":                     [str],
  }

Rules:
- Uses GitHub REST API — no git binary required
- Never calls LLM — pure filesystem/API analysis
- Returns structured report to CEO only
- CEO decides what to inject into Planner / Builder
- Never reads .env files, secrets, or binary files
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

import httpx

log = logging.getLogger("ceo_router.modules.github_brain")

# ── Files we always try to fetch ─────────────────────────────────────────────
_ANCHOR_FILES = [
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "README.md",
    "next.config.js",
    "vite.config.js",
    "vite.config.ts",
    "tsconfig.json",
    "tailwind.config.js",
    "tailwind.config.ts",
]

# ── Directories to index for entry points and features ───────────────────────
_SRC_DIRS = [
    "src/pages", "src/components", "src/routes", "src/api",
    "pages", "components", "routes", "api", "controllers",
    "app", "lib", "utils", "services", "models", "middleware",
]

# ── File extensions we will read ─────────────────────────────────────────────
_READABLE_EXTS = {
    ".js", ".jsx", ".ts", ".tsx", ".py", ".go", ".rs",
    ".json", ".toml", ".yaml", ".yml", ".md", ".env.example",
    ".html", ".css", ".sql",
}

# ── Paths/names to always skip ────────────────────────────────────────────────
_SKIP_PATHS = {
    "node_modules", ".git", "dist", "build", "__pycache__",
    ".next", ".nuxt", ".cache", "coverage", ".pytest_cache",
    "venv", ".venv", "env", ".env", "vendor",
}
_SKIP_FILES = {
    ".env", ".env.local", ".env.production", ".env.development",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock",
}

# ── Feature keyword patterns ──────────────────────────────────────────────────
_FEATURE_PATTERNS: dict[str, list[str]] = {
    "authentication":   ["auth", "login", "logout", "session", "jwt", "token", "oauth", "passport"],
    "routing":          ["router", "routes", "navigation", "middleware"],
    "database":         ["db", "database", "model", "schema", "prisma", "mongoose", "sqlalchemy", "motor"],
    "state_management": ["store", "redux", "zustand", "context", "recoil"],
    "api_layer":        ["api", "endpoint", "controller", "service", "fetch", "axios"],
    "ui_components":    ["component", "page", "layout", "modal", "form", "button"],
    "testing":          ["test", "spec", "jest", "pytest", "vitest"],
    "deployment":       ["dockerfile", "docker-compose", "railway", "vercel", ".github/workflows"],
    "payment":          ["stripe", "payment", "checkout", "billing"],
    "realtime":         ["socket", "websocket", "sse", "realtime"],
    "file_upload":      ["upload", "multer", "s3", "storage", "bucket"],
}

_GITHUB_API = "https://api.github.com"


# ---------------------------------------------------------------------------
# Public entry point (called by brain_router → CEO only)
# ---------------------------------------------------------------------------

async def execute(
    decision: dict[str, Any],
    memory:   dict[str, Any],
    _web:     dict[str, Any],
) -> dict[str, Any]:
    """
    Inspect a GitHub repo and return a structured report.
    CEO calls this. CEO receives the report. CEO decides what to do next.
    """
    github_url = decision.get("github_url") or decision.get("message", "")
    branch     = decision.get("branch", "")
    focus      = decision.get("focus", decision.get("message", ""))
    token      = decision.get("api_key_gh", "")

    owner, repo, detected_branch = _parse_url(github_url)
    if not owner or not repo:
        return _error(f"Could not parse GitHub URL: {github_url}")

    if not branch:
        branch = detected_branch or "main"

    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        # ── 1. Resolve default branch if not specified ───────────────────────
        if not detected_branch:
            branch = await _get_default_branch(client, owner, repo, branch)

        # ── 2. Fetch full recursive file tree ────────────────────────────────
        tree = await _get_tree(client, owner, repo, branch)
        if tree is None:
            return _error(f"Could not fetch file tree for {owner}/{repo}@{branch}")

        # ── 3. Select files to read ──────────────────────────────────────────
        to_read = _select_files(tree, focus)

        # ── 4. Fetch file contents (in parallel, capped) ─────────────────────
        contents = await _fetch_files(client, owner, repo, branch, to_read[:22])

        # ── 5. Analyse and build report ──────────────────────────────────────
        return _build_report(owner, repo, branch, tree, contents, focus)


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

def _parse_url(url: str) -> tuple[str, str, str]:
    """
    Parse a GitHub URL and return (owner, repo, branch).
    branch is empty string when not present in URL.
    Handles:
      https://github.com/owner/repo
      https://github.com/owner/repo/tree/branch
      https://github.com/owner/repo/tree/branch/path
    Also accepts plain "owner/repo" strings.
    """
    # Extract from full URL
    m = re.search(
        r"github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?(?:/tree/([^/\s]+))?(?:/|$|\s)",
        url,
    )
    if m:
        return m.group(1), m.group(2), m.group(3) or ""

    # Plain "owner/repo"
    m2 = re.match(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$", url.strip())
    if m2:
        return m2.group(1), m2.group(2), ""

    return "", "", ""


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

async def _get_default_branch(
    client: httpx.AsyncClient, owner: str, repo: str, fallback: str
) -> str:
    try:
        r = await client.get(f"{_GITHUB_API}/repos/{owner}/{repo}")
        if r.status_code == 200:
            return r.json().get("default_branch", fallback)
    except Exception:
        pass
    return fallback


async def _get_tree(
    client: httpx.AsyncClient, owner: str, repo: str, branch: str
) -> list[dict] | None:
    """Fetch the full recursive tree. Falls back to master if main fails."""
    for br in [branch, "master", "main", "develop"]:
        try:
            r = await client.get(
                f"{_GITHUB_API}/repos/{owner}/{repo}/git/trees/{br}",
                params={"recursive": "1"},
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("tree", [])
        except Exception:
            continue
    return None


async def _fetch_files(
    client:  httpx.AsyncClient,
    owner:   str,
    repo:    str,
    branch:  str,
    paths:   list[str],
) -> dict[str, str]:
    """
    Fetch file contents from GitHub API.
    Returns {path: text_content}.
    Silently skips files that fail or are binary.
    """
    results: dict[str, str] = {}
    import asyncio

    async def _fetch_one(path: str) -> tuple[str, str]:
        try:
            r = await client.get(
                f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
                params={"ref": branch},
            )
            if r.status_code != 200:
                return path, ""
            data = r.json()
            if isinstance(data, list):  # directory
                return path, ""
            encoded = data.get("content", "")
            if not encoded:
                return path, ""
            raw = base64.b64decode(encoded).decode("utf-8", errors="ignore")
            return path, raw
        except Exception:
            return path, ""

    tasks = [_fetch_one(p) for p in paths]
    for coro in asyncio.as_completed(tasks):
        path, content = await coro
        if content:
            results[path] = content
    return results


# ---------------------------------------------------------------------------
# File selection
# ---------------------------------------------------------------------------

def _select_files(tree: list[dict], focus: str) -> list[str]:
    """
    Choose up to 22 files to read, prioritised by:
    1. Anchor files (package.json, requirements.txt, etc.)
    2. Files matching focus keywords
    3. Entry points
    4. Source directory samples
    """
    blobs = [
        item["path"] for item in tree
        if item.get("type") == "blob"
        and not _should_skip(item["path"])
        and _is_readable(item["path"])
    ]

    focus_kws = set(re.findall(r"\w+", focus.lower()))

    anchors   = [p for p in blobs if _basename(p).lower() in {a.lower() for a in _ANCHOR_FILES}]
    focused   = [p for p in blobs if p not in anchors and _path_matches_focus(p, focus_kws)]
    entry_pts = [p for p in blobs if p not in anchors and p not in focused and _is_entry_point(p)]
    rest      = [p for p in blobs if p not in anchors and p not in focused and p not in entry_pts]

    selected: list[str] = []
    selected.extend(anchors[:8])
    selected.extend(focused[:8])
    selected.extend(entry_pts[:4])
    selected.extend(rest[:4])
    return selected[:22]


def _should_skip(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    if any(p in _SKIP_PATHS for p in parts):
        return True
    if _basename(path) in _SKIP_FILES:
        return True
    return False


def _is_readable(path: str) -> bool:
    ext = _ext(path)
    return ext in _READABLE_EXTS or _basename(path) in _ANCHOR_FILES


def _is_entry_point(path: str) -> bool:
    name = _basename(path).lower()
    return name in {
        "index.js", "index.ts", "index.jsx", "index.tsx",
        "main.js", "main.ts", "main.py", "app.js", "app.ts",
        "app.py", "server.py", "server.js", "server.ts",
        "app.jsx", "app.tsx",
    }


def _path_matches_focus(path: str, focus_kws: set[str]) -> bool:
    path_lower = path.lower()
    stop = {"the", "a", "an", "to", "for", "and", "or", "my", "i", "it", "is", "in", "on"}
    relevant = focus_kws - stop
    return any(kw in path_lower for kw in relevant if len(kw) > 2)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def _build_report(
    owner:    str,
    repo:     str,
    branch:   str,
    tree:     list[dict],
    contents: dict[str, str],
    focus:    str,
) -> dict[str, Any]:
    blob_paths = [
        item["path"] for item in tree
        if item.get("type") == "blob" and not _should_skip(item["path"])
    ]
    dir_paths = [
        item["path"] for item in tree if item.get("type") == "tree"
    ]

    tech_stack   = _detect_stack(contents)
    project_type = _detect_project_type(tech_stack, blob_paths)
    features     = _detect_features(blob_paths, contents)
    entry_points = _find_entry_points(blob_paths)
    duplicates   = _find_duplicates(blob_paths, features)
    patch_targets = _recommend_patch_targets(blob_paths, focus, features)
    file_summary  = _summarise_tree(blob_paths, dir_paths)

    relevant_files = []
    for path, text in contents.items():
        purpose  = _infer_purpose(path, text)
        snippet  = text[:300].strip() if text else ""
        relevant_files.append({"path": path, "purpose": purpose, "snippet": snippet})

    notes = []
    if len(blob_paths) > 500:
        notes.append(f"Large repo ({len(blob_paths)} files) — only the most relevant files were inspected.")
    if not tech_stack:
        notes.append("Could not detect tech stack — verify package files exist.")

    log.info(
        "github_brain: scanned %s/%s@%s — %d blobs, %d files read, %d features",
        owner, repo, branch, len(blob_paths), len(contents), len(features),
    )

    return {
        "type":                      "repo_inspection",
        "status":                    "success",
        "repo":                      f"{owner}/{repo}",
        "branch":                    branch,
        "project_type":              project_type,
        "tech_stack":                tech_stack,
        "entry_points":              entry_points[:10],
        "relevant_files":            relevant_files,
        "existing_features":         features,
        "duplicate_candidates":      duplicates,
        "recommended_patch_targets": patch_targets[:8],
        "file_tree_summary":         file_summary,
        "notes":                     notes,
    }


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def _detect_stack(contents: dict[str, str]) -> list[str]:
    stack: list[str] = []

    pkg = contents.get("package.json", "")
    if pkg:
        try:
            import json
            data = json.loads(pkg)
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if "react" in deps:         stack.append("React")
            if "next" in deps:          stack.append("Next.js")
            if "vue" in deps:           stack.append("Vue")
            if "svelte" in deps:        stack.append("Svelte")
            if "express" in deps:       stack.append("Express")
            if "fastify" in deps:       stack.append("Fastify")
            if "tailwindcss" in deps:   stack.append("Tailwind CSS")
            if "typescript" in deps or "@types/node" in deps:
                stack.append("TypeScript")
            if "prisma" in deps:        stack.append("Prisma")
            if "mongoose" in deps:      stack.append("Mongoose / MongoDB")
            if "stripe" in deps:        stack.append("Stripe")
            if "socket.io" in deps:     stack.append("Socket.io")
        except Exception:
            pass

    req = contents.get("requirements.txt", "")
    if req:
        if re.search(r"fastapi", req, re.I):    stack.append("FastAPI")
        if re.search(r"flask",   req, re.I):    stack.append("Flask")
        if re.search(r"django",  req, re.I):    stack.append("Django")
        if re.search(r"motor|pymongo", req, re.I): stack.append("MongoDB (Python)")
        if re.search(r"sqlalchemy",    req, re.I): stack.append("SQLAlchemy")
        if re.search(r"anthropic",     req, re.I): stack.append("Anthropic SDK")
        if re.search(r"openai",        req, re.I): stack.append("OpenAI SDK")
        if not any("Python" in s for s in stack):
            stack.append("Python")

    if contents.get("Cargo.toml"):  stack.append("Rust")
    if contents.get("go.mod"):      stack.append("Go")

    return list(dict.fromkeys(stack))  # deduplicate, preserve order


def _detect_project_type(stack: list[str], paths: list[str]) -> str:
    has_frontend = any(s in stack for s in ["React", "Next.js", "Vue", "Svelte"])
    has_backend  = any(s in stack for s in ["FastAPI", "Flask", "Django", "Express", "Fastify", "Go", "Rust", "Python"])
    path_str = " ".join(paths).lower()

    if has_frontend and has_backend:
        return "full-stack web application"
    if has_frontend:
        return "frontend web application"
    if has_backend:
        return "backend / API service"
    if "next.config" in path_str:
        return "Next.js application"
    if any(p.endswith(".py") for p in paths):
        return "Python project"
    return "unknown project type"


def _detect_features(paths: list[str], contents: dict[str, str]) -> list[str]:
    found: list[str] = []
    all_text = " ".join(paths).lower() + " " + " ".join(v.lower()[:500] for v in contents.values())
    for feature, keywords in _FEATURE_PATTERNS.items():
        if any(kw in all_text for kw in keywords):
            found.append(feature)
    return found


def _find_entry_points(paths: list[str]) -> list[str]:
    return [p for p in paths if _is_entry_point(p)]


def _find_duplicates(paths: list[str], features: list[str]) -> list[dict]:
    dupes: list[dict] = []
    for feature, keywords in _FEATURE_PATTERNS.items():
        if feature not in features:
            continue
        matching = [p for p in paths if any(kw in p.lower() for kw in keywords)]
        if len(matching) >= 3:
            dupes.append({
                "concern": feature,
                "files":   matching[:6],
            })
    return dupes


def _recommend_patch_targets(paths: list[str], focus: str, features: list[str]) -> list[str]:
    focus_kws = set(re.findall(r"\w+", focus.lower())) - {"the", "a", "an", "to", "fix", "add", "update", "my"}
    targets = [p for p in paths if _path_matches_focus(p, focus_kws)]
    return targets[:8]


def _summarise_tree(blobs: list[str], dirs: list[str]) -> str:
    top_dirs = sorted({p.split("/")[0] for p in dirs if "/" not in p and p not in _SKIP_PATHS})
    return (
        f"{len(blobs)} files across {len(dirs)} directories. "
        f"Top-level: {', '.join(top_dirs[:12]) or 'root only'}."
    )


def _infer_purpose(path: str, content: str) -> str:
    name = _basename(path).lower()
    content_lower = content.lower()[:500]

    if name == "package.json":           return "Frontend dependencies & scripts"
    if name == "requirements.txt":       return "Python dependencies"
    if name == "readme.md":              return "Project documentation"
    if "auth" in name or "login" in name: return "Authentication logic"
    if "route" in name or "router" in name: return "Routing"
    if "model" in name or "schema" in name: return "Data model / schema"
    if "db" in name or "database" in name:  return "Database configuration"
    if "config" in name:                 return "Configuration"
    if "test" in name or "spec" in name: return "Tests"
    if "component" in path.lower():      return "UI component"
    if "page" in path.lower():           return "Page / view"
    if "api" in path.lower():            return "API endpoint"
    if "middleware" in path.lower():     return "Middleware"
    if "util" in name or "helper" in name: return "Utility / helper"
    if "stripe" in content_lower or "payment" in content_lower: return "Payment processing"
    if "socket" in content_lower:        return "Real-time / WebSocket"
    return "Source file"


# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------

def _basename(path: str) -> str:
    return path.replace("\\", "/").split("/")[-1]


def _ext(path: str) -> str:
    name = _basename(path)
    if "." in name:
        return "." + name.rsplit(".", 1)[-1].lower()
    return ""


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------

def _error(message: str) -> dict[str, Any]:
    log.warning("github_brain: %s", message)
    return {
        "type":   "repo_inspection",
        "status": "error",
        "error":  message,
        "project_type":              "unknown",
        "tech_stack":                [],
        "entry_points":              [],
        "relevant_files":            [],
        "existing_features":         [],
        "duplicate_candidates":      [],
        "recommended_patch_targets": [],
        "file_tree_summary":         "",
        "notes":                     [message],
    }
