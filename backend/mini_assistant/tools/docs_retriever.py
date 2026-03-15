"""
docs_retriever.py — Local documentation index retrieval
────────────────────────────────────────────────────────
Searches a JSON-based local docs index built by docs_indexer.py.
Uses BM25-style keyword scoring — no heavy ML deps required.

Priority chain:
  1. Local index (fast, offline)
  2. Doc-aware live web search (online, official domains first)
  3. Generic DuckDuckGo fallback
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent.parent
INDEX_DIR  = _HERE / "data" / "docs_index"
CACHE_DIR  = _HERE / "data" / "docs_cache"

INDEX_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Official doc domain map ────────────────────────────────────────────────────
# Maps keyword → (display_name, [domains_to_search])
DOC_DOMAIN_MAP: dict[str, tuple[str, list[str]]] = {
    "python":      ("Python",      ["docs.python.org", "pypi.org"]),
    "javascript":  ("JavaScript",  ["developer.mozilla.org", "nodejs.org"]),
    "mdn":         ("MDN",         ["developer.mozilla.org"]),
    "node":        ("Node.js",     ["nodejs.org"]),
    "react":       ("React",       ["react.dev"]),
    "fastapi":     ("FastAPI",     ["fastapi.tiangolo.com"]),
    "flask":       ("Flask",       ["flask.palletsprojects.com"]),
    "stripe":      ("Stripe",      ["docs.stripe.com"]),
    "postgresql":  ("PostgreSQL",  ["postgresql.org/docs"]),
    "postgres":    ("PostgreSQL",  ["postgresql.org/docs"]),
    "github":      ("GitHub",      ["docs.github.com"]),
    "cloudflare":  ("Cloudflare",  ["developers.cloudflare.com"]),
    "ollama":      ("Ollama",      ["ollama.com", "github.com/ollama/ollama"]),
    "comfyui":     ("ComfyUI",     ["github.com/comfyanonymous/ComfyUI"]),
    "railway":     ("Railway",     ["docs.railway.com"]),
    "tailwind":    ("Tailwind",    ["tailwindcss.com/docs"]),
    "typescript":  ("TypeScript",  ["typescriptlang.org/docs"]),
    "docker":      ("Docker",      ["docs.docker.com"]),
    "mongodb":     ("MongoDB",     ["mongodb.com/docs"]),
    "redis":       ("Redis",       ["redis.io/docs"]),
    "nextjs":      ("Next.js",     ["nextjs.org/docs"]),
    "vite":        ("Vite",        ["vitejs.dev/guide"]),
    "pydantic":    ("Pydantic",    ["docs.pydantic.dev"]),
    "sqlalchemy":  ("SQLAlchemy",  ["docs.sqlalchemy.org"]),
    "celery":      ("Celery",      ["docs.celeryproject.org"]),
    "openai":      ("OpenAI",      ["platform.openai.com/docs"]),
    "anthropic":   ("Anthropic",   ["docs.anthropic.com"]),
}

# Reputable technical sources (used as fallback preference)
REPUTABLE_DOMAINS = {
    "stackoverflow.com", "github.com", "medium.com", "dev.to",
    "realpython.com", "css-tricks.com", "web.dev", "freecodecamp.org",
    "digitalocean.com/community", "smashingmagazine.com",
}

# ── Tech query detection ───────────────────────────────────────────────────────
_TECH_PATTERNS = re.compile(
    r"\b("
    r"how (to|do|does|can|should)|"
    r"what (is|are|does)|"
    r"why (is|does|am|are)|"
    r"error|exception|traceback|"
    r"install|import|require|configure|setup|deploy|"
    r"api|sdk|endpoint|request|response|"
    r"function|method|class|module|package|library|"
    r"syntax|parameter|argument|return|async|await|"
    r"debug|fix|solve|issue|problem|"
    r"docs?|documentation|reference|example"
    r")\b",
    re.IGNORECASE,
)

_LANG_PATTERNS = re.compile(
    "|".join(re.escape(k) for k in DOC_DOMAIN_MAP),
    re.IGNORECASE,
)


def is_tech_query(text: str) -> bool:
    """Return True if the query looks like a technical/coding question."""
    return bool(_TECH_PATTERNS.search(text)) or bool(_LANG_PATTERNS.search(text))


def detect_tech_domains(text: str) -> list[tuple[str, list[str]]]:
    """
    Return list of (display_name, [domains]) for any tech keywords found in text.
    """
    found: dict[str, tuple[str, list[str]]] = {}
    for kw, (name, domains) in DOC_DOMAIN_MAP.items():
        if re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE):
            found[name] = (name, domains)
    return list(found.values())


# ── BM25-style local index search ─────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]{2,}", text.lower())


def _build_query_terms(query: str) -> set[str]:
    return set(_tokenize(query))


class LocalDocsIndex:
    """Loads and searches the JSON-based local docs index."""

    def __init__(self):
        self._chunks: list[dict] = []      # [{text, source, library, title, url}]
        self._tf: list[dict[str, float]] = []   # term frequency per chunk
        self._df: dict[str, int] = defaultdict(int)  # doc freq per term
        self._loaded = False
        self._load_time: float = 0.0

    def _load(self):
        if self._loaded and (time.time() - self._load_time) < 300:
            return  # cached for 5 minutes
        self._chunks = []
        self._tf = []
        self._df = defaultdict(int)
        for idx_file in INDEX_DIR.glob("*.json"):
            try:
                with open(idx_file, encoding="utf-8") as f:
                    entries = json.load(f)
                for entry in entries:
                    tokens = _tokenize(entry.get("text", ""))
                    if not tokens:
                        continue
                    tf: dict[str, float] = defaultdict(float)
                    for t in tokens:
                        tf[t] += 1
                    total = len(tokens)
                    for t in tf:
                        tf[t] /= total
                        self._df[t] += 1
                    self._chunks.append(entry)
                    self._tf.append(dict(tf))
            except Exception as exc:
                logger.warning("Failed to load index %s: %s", idx_file, exc)
        self._loaded = True
        self._load_time = time.time()
        logger.info("Local docs index loaded: %d chunks from %s", len(self._chunks), INDEX_DIR)

    def search(self, query: str, top_k: int = 3, min_score: float = 0.01) -> list[dict]:
        """
        BM25-style search. Returns top_k chunks with score >= min_score.
        Each result: {text, source, library, title, url, score}
        """
        self._load()
        if not self._chunks:
            return []

        terms = _build_query_terms(query)
        N = len(self._chunks)
        k1, b, avg_dl = 1.5, 0.75, 200.0

        scores: list[tuple[float, int]] = []
        for i, (chunk, tf) in enumerate(zip(self._chunks, self._tf)):
            dl = sum(tf.values()) * avg_dl  # approximate doc length
            score = 0.0
            for term in terms:
                if term not in tf:
                    continue
                df = self._df.get(term, 0)
                idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
                tf_val = tf[term]
                score += idf * (tf_val * (k1 + 1)) / (tf_val + k1 * (1 - b + b * dl / avg_dl))
            if score >= min_score:
                scores.append((score, i))

        scores.sort(reverse=True)
        results = []
        for score, i in scores[:top_k]:
            entry = dict(self._chunks[i])
            entry["score"] = round(score, 4)
            results.append(entry)
        return results


# Singleton
_local_index = LocalDocsIndex()


def search_local_docs(query: str, top_k: int = 3) -> list[dict]:
    """Search the local docs index. Returns [] if index is empty."""
    try:
        return _local_index.search(query, top_k=top_k)
    except Exception as exc:
        logger.warning("Local docs search failed: %s", exc)
        return []


# ── Page fetch + clean + chunk ─────────────────────────────────────────────────

_PAGE_CACHE: dict[str, tuple[float, str]] = {}   # url → (timestamp, text)
_PAGE_CACHE_TTL = 3600  # 1 hour


def _fetch_page_text(url: str) -> Optional[str]:
    """Fetch a web page and return cleaned main-content text."""
    now = time.time()
    cached = _PAGE_CACHE.get(url)
    if cached and (now - cached[0]) < _PAGE_CACHE_TTL:
        return cached[1]

    # Check disk cache
    cache_key = re.sub(r"[^\w]", "_", url)[:120]
    cache_file = CACHE_DIR / f"{cache_key}.txt"
    if cache_file.exists() and (now - cache_file.stat().st_mtime) < _PAGE_CACHE_TTL:
        text = cache_file.read_text(encoding="utf-8", errors="ignore")
        _PAGE_CACHE[url] = (cache_file.stat().st_mtime, text)
        return text

    try:
        import httpx
        headers = {"User-Agent": "MiniAssistant/1.0 (documentation reader)"}
        resp = httpx.get(url, headers=headers, timeout=10.0, follow_redirects=True)
        if resp.status_code != 200:
            return None
        html = resp.text
    except Exception as exc:
        logger.debug("Page fetch failed %s: %s", url, exc)
        return None

    text = _clean_html(html)
    if len(text) < 100:
        return None

    # Store caches
    _PAGE_CACHE[url] = (now, text)
    try:
        cache_file.write_text(text, encoding="utf-8")
    except Exception:
        pass
    return text


def _clean_html(html: str) -> str:
    """Strip HTML tags and boilerplate, return clean readable text."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        # Remove nav/sidebar/footer/scripts/styles
        for tag in soup(["nav", "header", "footer", "aside", "script", "style",
                          "noscript", "form", "button", "iframe", "figure"]):
            tag.decompose()
        # Also remove elements with sidebar/nav class names
        for tag in soup.find_all(class_=re.compile(r"nav|sidebar|footer|menu|cookie|banner|ad", re.I)):
            tag.decompose()
        # Try to find main content area
        main = (soup.find("main") or soup.find("article") or
                soup.find(id=re.compile(r"content|main|docs|article", re.I)) or
                soup.find(class_=re.compile(r"content|main|docs|article", re.I)) or
                soup.body)
        if main:
            text = main.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)
    except ImportError:
        # Fallback: strip tags with regex
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&[a-z]+;", " ", text)

    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks by character count."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        # Try to break at a sentence boundary
        if end < len(text):
            last_break = max(chunk.rfind(". "), chunk.rfind("\n"))
            if last_break > chunk_size // 2:
                chunk = chunk[:last_break + 1]
        chunks.append(chunk.strip())
        start += len(chunk) - overlap
        if start <= 0:
            break
    return [c for c in chunks if len(c) > 50]


def _rank_chunks(chunks: list[str], query: str, top_k: int = 2) -> list[str]:
    """Rank text chunks by keyword overlap with query. Returns top_k."""
    terms = _build_query_terms(query)
    if not terms:
        return chunks[:top_k]
    scored = []
    for chunk in chunks:
        chunk_terms = set(_tokenize(chunk))
        overlap = len(terms & chunk_terms)
        scored.append((overlap, chunk))
    scored.sort(reverse=True)
    return [c for _, c in scored[:top_k]]


# ── Doc-aware live search ──────────────────────────────────────────────────────

def _build_doc_biased_query(query: str, domains: list[str]) -> str:
    """Append site: operators to bias search toward official docs."""
    if not domains:
        return query
    site_ops = " OR ".join(f"site:{d}" for d in domains[:4])
    return f"{query} ({site_ops})"


def _is_official_domain(url: str, domains: list[str]) -> bool:
    return any(d in url for d in domains)


def doc_aware_search(query: str, max_results: int = 5) -> dict:
    """
    Full doc-aware search pipeline.

    Returns:
        {
          "source": "local_index" | "live_docs" | "web_fallback",
          "results": [{"title", "url", "body", "library"?, "score"?}],
          "context_snippet": str,   # best chunk(s) for context injection
          "citations": [{"title", "url", "library"}],
        }
    """
    from .search import web_search as _plain_web_search

    tech_domains = detect_tech_domains(query)
    all_official_domains = [d for _, domains in tech_domains for d in domains]

    # ── Step 1: local index ──────────────────────────────────────────────────
    local_hits = search_local_docs(query, top_k=3)
    if local_hits and local_hits[0].get("score", 0) >= 0.05:
        context_chunks = [h["text"] for h in local_hits]
        ranked = _rank_chunks(context_chunks, query, top_k=2)
        citations = [{"title": h.get("title", ""), "url": h.get("url", ""), "library": h.get("library", "")} for h in local_hits]
        return {
            "source": "local_index",
            "results": local_hits,
            "context_snippet": "\n\n---\n\n".join(ranked),
            "citations": citations,
        }

    # ── Step 2: live official docs search + fetch ────────────────────────────
    if all_official_domains:
        doc_query = _build_doc_biased_query(query, all_official_domains)
        try:
            live_results = _plain_web_search(doc_query, max_results=max_results)
        except Exception as exc:
            logger.warning("Doc-biased search failed: %s", exc)
            live_results = []

        # Find results from official domains
        official_hits = [r for r in live_results if _is_official_domain(r.get("url", ""), all_official_domains)]

        if official_hits:
            # Try to fetch and extract the best official page
            best = official_hits[0]
            page_text = _fetch_page_text(best["url"])
            if page_text:
                chunks = _chunk_text(page_text)
                top_chunks = _rank_chunks(chunks, query, top_k=2)
                citations = [{"title": r.get("title", ""), "url": r.get("url", ""), "library": ""} for r in official_hits[:3]]
                for pair in tech_domains:
                    name, domains = pair
                    if any(d in best["url"] for d in domains):
                        citations[0]["library"] = name
                        break
                return {
                    "source": "live_docs",
                    "results": official_hits,
                    "context_snippet": "\n\n---\n\n".join(top_chunks),
                    "citations": citations,
                }

            # Fallback: use snippets from official results
            snippets = [f"{r['title']}\n{r['body']}" for r in official_hits]
            return {
                "source": "live_docs",
                "results": official_hits,
                "context_snippet": "\n\n".join(snippets[:3]),
                "citations": [{"title": r.get("title", ""), "url": r.get("url", ""), "library": ""} for r in official_hits[:3]],
            }

    # ── Step 3: generic web fallback (prefer reputable domains) ─────────────
    try:
        generic_results = _plain_web_search(query, max_results=max_results)
    except Exception as exc:
        logger.warning("Generic search failed: %s", exc)
        generic_results = []

    # Sort to prefer reputable domains
    def _domain_score(r: dict) -> int:
        url = r.get("url", "")
        return 1 if any(d in url for d in REPUTABLE_DOMAINS) else 0

    generic_results.sort(key=_domain_score, reverse=True)

    snippets = [f"{r.get('title','')}\n{r.get('body','')}" for r in generic_results]
    return {
        "source": "web_fallback",
        "results": generic_results,
        "context_snippet": "\n\n".join(snippets[:4]),
        "citations": [{"title": r.get("title", ""), "url": r.get("url", ""), "library": ""} for r in generic_results[:3]],
    }
