"""
docs_indexer.py — Local documentation index builder
─────────────────────────────────────────────────────
Crawls official documentation pages and stores a searchable local index
in backend/mini_assistant/data/docs_index/<library>.json

Run as a script:
    python -m mini_assistant.tools.docs_indexer --libs python react fastapi
    python -m mini_assistant.tools.docs_indexer --all

Each entry in the index:
    {
      "library": "React",
      "title":   "Hooks Overview",
      "url":     "https://react.dev/reference/react",
      "text":    "<cleaned chunk text>",
      "source":  "react.dev",
    }
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent.parent
INDEX_DIR = _HERE / "data" / "docs_index"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

# ── Seed URLs for each library ─────────────────────────────────────────────────
# Each value is a list of high-value documentation pages to index.
# Add more URLs per library to expand coverage.
SEED_URLS: dict[str, list[str]] = {
    "python": [
        "https://docs.python.org/3/tutorial/index.html",
        "https://docs.python.org/3/library/functions.html",
        "https://docs.python.org/3/library/stdtypes.html",
        "https://docs.python.org/3/reference/expressions.html",
        "https://docs.python.org/3/library/exceptions.html",
        "https://docs.python.org/3/library/asyncio.html",
        "https://docs.python.org/3/library/dataclasses.html",
        "https://docs.python.org/3/library/pathlib.html",
        "https://docs.python.org/3/library/os.html",
        "https://docs.python.org/3/library/json.html",
    ],
    "javascript": [
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Introduction",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/async_function",
        "https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Object",
    ],
    "react": [
        "https://react.dev/learn",
        "https://react.dev/reference/react",
        "https://react.dev/reference/react/hooks",
        "https://react.dev/reference/react/useState",
        "https://react.dev/reference/react/useEffect",
        "https://react.dev/reference/react/useCallback",
        "https://react.dev/reference/react/useMemo",
        "https://react.dev/reference/react/useContext",
        "https://react.dev/learn/managing-state",
        "https://react.dev/learn/sharing-state-between-components",
    ],
    "fastapi": [
        "https://fastapi.tiangolo.com/tutorial/",
        "https://fastapi.tiangolo.com/tutorial/path-params/",
        "https://fastapi.tiangolo.com/tutorial/query-params/",
        "https://fastapi.tiangolo.com/tutorial/body/",
        "https://fastapi.tiangolo.com/tutorial/response-model/",
        "https://fastapi.tiangolo.com/tutorial/middleware/",
        "https://fastapi.tiangolo.com/tutorial/bigger-applications/",
        "https://fastapi.tiangolo.com/advanced/",
        "https://fastapi.tiangolo.com/tutorial/security/",
    ],
    "flask": [
        "https://flask.palletsprojects.com/en/stable/quickstart/",
        "https://flask.palletsprojects.com/en/stable/api/",
        "https://flask.palletsprojects.com/en/stable/blueprints/",
        "https://flask.palletsprojects.com/en/stable/views/",
        "https://flask.palletsprojects.com/en/stable/errorhandling/",
    ],
    "stripe": [
        "https://docs.stripe.com/api",
        "https://docs.stripe.com/payments/quickstart",
        "https://docs.stripe.com/webhooks",
        "https://docs.stripe.com/api/payment_intents",
    ],
    "postgresql": [
        "https://www.postgresql.org/docs/current/sql-commands.html",
        "https://www.postgresql.org/docs/current/datatype.html",
        "https://www.postgresql.org/docs/current/functions.html",
        "https://www.postgresql.org/docs/current/indexes.html",
    ],
    "github": [
        "https://docs.github.com/en/actions/quickstart",
        "https://docs.github.com/en/rest/overview/about-the-rest-api",
        "https://docs.github.com/en/get-started/using-git/about-git",
    ],
    "cloudflare": [
        "https://developers.cloudflare.com/workers/get-started/guide/",
        "https://developers.cloudflare.com/pages/",
        "https://developers.cloudflare.com/tunnel/",
    ],
    "ollama": [
        "https://github.com/ollama/ollama/blob/main/README.md",
        "https://ollama.com/blog/openai-compatibility",
    ],
    "railway": [
        "https://docs.railway.com/getting-started",
        "https://docs.railway.com/deploy/dockerfiles",
    ],
    "tailwind": [
        "https://tailwindcss.com/docs/installation",
        "https://tailwindcss.com/docs/utility-first",
        "https://tailwindcss.com/docs/responsive-design",
        "https://tailwindcss.com/docs/hover-focus-and-other-states",
    ],
    "typescript": [
        "https://www.typescriptlang.org/docs/handbook/2/types-from-types.html",
        "https://www.typescriptlang.org/docs/handbook/2/generics.html",
        "https://www.typescriptlang.org/docs/handbook/declaration-files/introduction.html",
    ],
    "docker": [
        "https://docs.docker.com/get-started/",
        "https://docs.docker.com/compose/",
        "https://docs.docker.com/reference/dockerfile/",
    ],
}

# ── HTML cleaner ───────────────────────────────────────────────────────────────

def _clean_html(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["nav", "header", "footer", "aside", "script", "style", "noscript", "form"]):
            tag.decompose()
        for tag in soup.find_all(class_=re.compile(r"nav|sidebar|footer|menu|cookie|banner|toc", re.I)):
            tag.decompose()
        main = (soup.find("main") or soup.find("article") or
                soup.find(id=re.compile(r"content|main|docs|article", re.I)) or
                soup.body)
        text = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)
    except ImportError:
        text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _extract_title(html: str, url: str) -> str:
    try:
        m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        if m:
            t = m.group(1).strip()
            # Strip common suffixes like " | React" or " - MDN Web Docs"
            t = re.sub(r"\s*[|\-–—]\s*.{0,40}$", "", t)
            return t.strip()
    except Exception:
        pass
    return url.split("/")[-1].replace("-", " ").replace("_", " ").title()


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 80) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if end < len(text):
            last_break = max(chunk.rfind(". "), chunk.rfind("\n"))
            if last_break > chunk_size // 2:
                chunk = chunk[:last_break + 1]
        chunk = chunk.strip()
        if len(chunk) > 80:
            chunks.append(chunk)
        start += len(chunk) - overlap
        if start <= 0:
            break
    return chunks


# ── Page fetcher (async, concurrent) ──────────────────────────────────────────

async def _fetch_async(session, url: str) -> tuple[str, Optional[str]]:
    """Fetch a single URL asynchronously. Returns (url, html_or_None)."""
    import httpx
    headers = {"User-Agent": "MiniAssistant/1.0 (documentation indexer)"}
    try:
        resp = await session.get(url, headers=headers, timeout=15.0, follow_redirects=True)
        if resp.status_code == 200:
            logger.info("  ✓ fetched %s", url)
            return url, resp.text
        else:
            logger.warning("  HTTP %s for %s", resp.status_code, url)
    except Exception as exc:
        logger.warning("  Fetch failed %s: %s", url, exc)
    return url, None


async def _fetch_all_async(urls: list[str]) -> dict[str, str]:
    """Fetch all URLs concurrently. Returns {url: html}."""
    import httpx
    import asyncio
    results = {}
    async with httpx.AsyncClient() as session:
        tasks = [_fetch_async(session, url) for url in urls]
        for url, html in await asyncio.gather(*tasks):
            if html:
                results[url] = html
    return results


def _fetch_all(urls: list[str]) -> dict[str, str]:
    """Sync wrapper for concurrent fetch."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                fut = pool.submit(asyncio.run, _fetch_all_async(urls))
                return fut.result()
        return loop.run_until_complete(_fetch_all_async(urls))
    except RuntimeError:
        return asyncio.run(_fetch_all_async(urls))


# ── Indexer ────────────────────────────────────────────────────────────────────

def index_library(library_key: str, urls: list[str]) -> int:
    """
    Fetch and index all pages for a library concurrently. Returns count of chunks saved.
    """
    library_name = library_key.title()
    entries: list[dict] = []

    logger.info("  Fetching %d pages concurrently...", len(urls))
    fetched = _fetch_all(urls)
    logger.info("  Got %d/%d pages", len(fetched), len(urls))

    for url in urls:
        html = fetched.get(url)
        if not html:
            continue
        title = _extract_title(html, url)
        text = _clean_html(html)
        if len(text) < 100:
            logger.warning("  Skipping %s — too little content (%d chars)", url, len(text))
            continue
        chunks = _chunk_text(text)
        source = re.sub(r"https?://", "", url).split("/")[0]
        for chunk in chunks:
            entries.append({
                "library": library_name,
                "title":   title,
                "url":     url,
                "source":  source,
                "text":    chunk,
            })
        logger.info("  ✓ %s → %d chunks", title, len(chunks))

    if entries:
        out_file = INDEX_DIR / f"{library_key}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        logger.info("Saved %d chunks for %s → %s", len(entries), library_name, out_file)
    else:
        logger.warning("No content indexed for %s", library_name)

    return len(entries)


def build_index(libs: Optional[list[str]] = None):
    """Build/update the local docs index for the specified libraries (or all)."""
    targets = libs or list(SEED_URLS.keys())
    total = 0
    for key in targets:
        if key not in SEED_URLS:
            logger.warning("Unknown library: %s (available: %s)", key, ", ".join(SEED_URLS))
            continue
        logger.info("=== Indexing %s ===", key.upper())
        n = index_library(key, SEED_URLS[key])
        total += n
    logger.info("=== Done. Total chunks indexed: %d ===", total)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Mini Assistant local docs index")
    parser.add_argument("--libs", nargs="+", metavar="LIB",
                        help="Libraries to index (e.g. python react fastapi)")
    parser.add_argument("--all", action="store_true", help="Index all configured libraries")
    parser.add_argument("--list", action="store_true", help="List available libraries")
    args = parser.parse_args()

    if args.list:
        print("Available libraries:", ", ".join(sorted(SEED_URLS.keys())))
    elif args.all:
        build_index()
    elif args.libs:
        build_index(args.libs)
    else:
        parser.print_help()
