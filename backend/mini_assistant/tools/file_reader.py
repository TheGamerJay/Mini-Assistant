"""
file_reader.py – File & Folder Reader Tool
────────────────────────────────────────────
Read project files and documents for ingestion into context or memory.

Supports: .txt, .md, .py, .js, .ts, .jsx, .tsx, .json, .yaml, .yml,
          .html, .css, .env, .toml, .sh, .pdf
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Extensions treated as plain text
_TEXT_EXTS = {
    ".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx",
    ".json", ".yaml", ".yml", ".html", ".css", ".env",
    ".toml", ".sh", ".bat", ".cfg", ".ini", ".rst",
    ".sql", ".graphql", ".proto", ".xml", ".csv",
}

# Files / dirs to skip when reading a whole folder
_SKIP_DIRS  = {"node_modules", ".git", "__pycache__", ".venv", "venv",
               "dist", "build", ".next", ".nuxt", "coverage"}
_SKIP_FILES = {".DS_Store", "Thumbs.db", "package-lock.json", "yarn.lock"}

MAX_FILE_CHARS = 20_000   # per-file character cap
MAX_DIR_CHARS  = 60_000   # total cap when reading a directory


# ─── Single-file reader ───────────────────────────────────────────────────────

def read_file(file_path: str) -> str:
    """
    Read a single file and return its content as a string.

    Returns an error string (not an exception) if the file cannot be read.
    """
    path = Path(file_path)
    if not path.exists():
        return f"[Error] File not found: {file_path}"
    if not path.is_file():
        return f"[Error] Not a file: {file_path}"

    ext = path.suffix.lower()

    # PDF support
    if ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text[:MAX_FILE_CHARS]
        except ImportError:
            return "[Error] pypdf not installed. Run: pip install pypdf"
        except Exception as exc:
            return f"[Error] PDF read failed: {exc}"

    if ext not in _TEXT_EXTS and ext != "":
        return f"[Skipped] Unsupported file type: {ext}"

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS] + f"\n\n[Truncated – {len(content):,} chars total]"
        return content
    except Exception as exc:
        return f"[Error] Could not read {file_path}: {exc}"


# ─── Directory reader ─────────────────────────────────────────────────────────

def read_directory(
    dir_path: str,
    include_content: bool = True,
    max_depth: int = 3,
) -> str:
    """
    Read all supported text files in a directory recursively.

    Returns a formatted string with file paths and (optionally) content.
    """
    root = Path(dir_path)
    if not root.exists():
        return f"[Error] Directory not found: {dir_path}"
    if not root.is_dir():
        return read_file(dir_path)   # treat as file

    parts: list[str] = [f"# Project: {root.name}\n"]
    total_chars = 0

    def _walk(current: Path, depth: int):
        nonlocal total_chars
        if depth > max_depth or total_chars >= MAX_DIR_CHARS:
            return
        try:
            entries = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return

        for entry in entries:
            if entry.name in _SKIP_FILES:
                continue
            if entry.is_dir():
                if entry.name in _SKIP_DIRS:
                    continue
                parts.append(f"\n## {entry.relative_to(root)}/\n")
                _walk(entry, depth + 1)
            elif entry.is_file():
                rel = entry.relative_to(root)
                if not include_content:
                    parts.append(f"  - {rel}\n")
                    continue
                ext = entry.suffix.lower()
                if ext not in _TEXT_EXTS and ext != ".pdf":
                    parts.append(f"  - {rel}  [binary/unsupported]\n")
                    continue
                content = read_file(str(entry))
                block = f"\n### {rel}\n```{ext.lstrip('.')}\n{content}\n```\n"
                if total_chars + len(block) > MAX_DIR_CHARS:
                    parts.append(f"\n[Truncated – directory too large]\n")
                    return
                parts.append(block)
                total_chars += len(block)

    _walk(root, depth=0)
    return "".join(parts)


# ─── Smart dispatcher ─────────────────────────────────────────────────────────

def read_path(path: str, include_content: bool = True) -> str:
    """
    Auto-detect whether path is a file or directory and read accordingly.
    """
    p = Path(path)
    if p.is_dir():
        return read_directory(path, include_content=include_content)
    return read_file(path)


# ─── File listing only ────────────────────────────────────────────────────────

def list_files(dir_path: str, max_depth: int = 3) -> list[dict]:
    """
    Return a list of file metadata dicts without reading content.

    Each dict: {path, name, extension, size_bytes, is_dir}
    """
    root = Path(dir_path)
    if not root.exists():
        return []

    results = []

    def _walk(current: Path, depth: int):
        if depth > max_depth:
            return
        try:
            for entry in sorted(current.iterdir(), key=lambda p: p.name):
                if entry.name in _SKIP_FILES or entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    if entry.name in _SKIP_DIRS:
                        continue
                    results.append({
                        "path": str(entry),
                        "name": entry.name,
                        "extension": "",
                        "size_bytes": 0,
                        "is_dir": True,
                    })
                    _walk(entry, depth + 1)
                else:
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        size = 0
                    results.append({
                        "path": str(entry),
                        "name": entry.name,
                        "extension": entry.suffix.lower(),
                        "size_bytes": size,
                        "is_dir": False,
                    })
        except PermissionError:
            pass

    _walk(root, depth=0)
    return results


# ─── In-file search ───────────────────────────────────────────────────────────

def search_in_files(dir_path: str, query: str, max_results: int = 20) -> list[dict]:
    """
    Simple grep-style text search across all supported files in a directory.

    Returns list of {file, line_number, line} dicts.
    """
    root = Path(dir_path)
    if not root.exists():
        return []

    query_lower = query.lower()
    results: list[dict] = []

    for item in list_files(dir_path):
        if item["is_dir"] or item["extension"] not in _TEXT_EXTS:
            continue
        try:
            lines = Path(item["path"]).read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines, 1):
                if query_lower in line.lower():
                    results.append({
                        "file":        item["path"],
                        "line_number": i,
                        "line":        line.strip(),
                    })
                    if len(results) >= max_results:
                        return results
        except Exception:
            continue

    return results
