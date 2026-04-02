"""
web/web_crawler.py — Limited link-following crawler.

Only used when web_decider returns web_mode="crawler".
Strictly bounded: max 5 pages, same domain only, 10s timeout per page.

Rules:
- same domain only — never follow external links
- max 5 pages per crawl call
- 10 second timeout per page
- no JavaScript rendering
- do not call unless CEO explicitly routed here
- this is the most restricted web tool — prefer search or scraper first
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse
from typing import Any

log = logging.getLogger("ceo_router.web_crawler")

_MAX_PAGES  = 5
_TIMEOUT_S  = 10
_MAX_CHARS  = 4000  # per page


async def crawl(seed_url: str) -> dict[str, Any]:
    """
    Crawl up to _MAX_PAGES pages starting from seed_url, same domain only.

    Returns:
        {
            "ok": bool,
            "pages": [ {"url": str, "text": str}, ... ],
            "error": str | None,
        }
    """
    try:
        import httpx
    except ImportError:
        return {"ok": False, "pages": [], "error": "httpx not installed"}

    domain = urlparse(seed_url).netloc
    visited: set[str] = set()
    queue   = [seed_url]
    pages   = []

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True) as client:
            while queue and len(pages) < _MAX_PAGES:
                url = queue.pop(0)
                if url in visited:
                    continue
                visited.add(url)

                try:
                    resp = await client.get(
                        url,
                        headers={"User-Agent": "Mini-Assistant-Crawler/1.0"},
                    )
                    resp.raise_for_status()
                    html = resp.text
                except Exception as exc:
                    log.warning("crawler: skip %s — %s", url[:60], exc)
                    continue

                text = _extract_text(html)[:_MAX_CHARS]
                pages.append({"url": url, "text": text})

                # Find same-domain links
                for link in _find_links(html, url, domain):
                    if link not in visited and link not in queue:
                        queue.append(link)

        log.info("web_crawler: seed=%s pages_crawled=%d", seed_url[:60], len(pages))
        return {"ok": True, "pages": pages, "error": None}

    except Exception as exc:
        log.error("web_crawler failed: %s", exc)
        return {"ok": False, "pages": [], "error": str(exc)}


def _extract_text(html: str) -> str:
    html = re.sub(r"<(script|style|nav|footer)[^>]*>.*?</\1>", " ", html,
                  flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def _find_links(html: str, base_url: str, domain: str) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE)
    links = []
    for href in hrefs:
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.netloc == domain and parsed.scheme in ("http", "https"):
            links.append(full.split("#")[0])  # strip anchors
    return links
