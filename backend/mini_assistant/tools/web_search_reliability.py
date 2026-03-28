"""
web_search_reliability.py — Live Search Reliability Layer
──────────────────────────────────────────────────────────
Deterministic control layer for all live/current/product search requests.

Pipeline:
  normalize_intent → generate_queries → run_searches → aggregate_and_score
  → auto_retry_if_weak → format_for_injection

Never gives up after one search. Never tells users to search manually.
Uses DuckDuckGo shopping results for product queries.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class NormalizedIntent:
    search_type: str           # "product", "news", "price_check", "availability", "general"
    raw_query: str
    product: Optional[str]     = None
    category: Optional[str]    = None
    platform: Optional[str]    = None  # "amazon", "ebay", etc.
    goal: Optional[str]        = None  # "cheapest", "best_deal", "in_stock", "latest"
    max_price: Optional[float] = None
    min_price: Optional[float] = None
    condition: Optional[str]   = None  # "new", "used", "refurbished"
    keywords: list             = field(default_factory=list)


@dataclass
class SearchResult:
    title: str
    url: str
    source: str
    source_type: str           # "listing", "article", "forum", "category", "shopping"
    snippet: str
    price: Optional[float]     = None
    price_str: Optional[str]   = None
    seller: Optional[str]      = None
    availability: Optional[str] = None
    image_url: Optional[str]   = None
    matched_product: Optional[str] = None
    confidence_score: float    = 0.0


@dataclass
class ReliabilityOutput:
    intent: NormalizedIntent
    results: list              # list[SearchResult]
    answer_mode: str           # "exact_match","closest_match","market_context","hard_failure"
    queries_used: list         # list[str]
    retry_used: bool
    web_available: bool
    top_confidence: float
    log: dict


# ─── Intent Normalization ──────────────────────────────────────────────────────

_RETAILER_MAP = {
    "amazon": "amazon", "amzn": "amazon",
    "ebay": "ebay",
    "walmart": "walmart",
    "best buy": "bestbuy", "bestbuy": "bestbuy",
    "newegg": "newegg",
    "etsy": "etsy",
    "aliexpress": "aliexpress",
    "target": "target",
}

_GOAL_MAP = {
    "cheapest": "cheapest", "cheap": "cheapest", "lowest price": "cheapest",
    "best deal": "best_deal", "good deal": "best_deal",
    "in stock": "in_stock", "available": "in_stock", "buy now": "in_stock",
    "latest": "latest", "newest": "latest", "new release": "latest",
    "under": "max_price", "below": "max_price", "less than": "max_price",
}

_CONDITION_MAP = {
    "used": "used", "refurbished": "refurbished", "refurb": "refurbished",
    "open box": "open_box", "new": "new",
}

_PRODUCT_CATEGORIES = {
    "gpu": "GPU", "graphics card": "GPU", "video card": "GPU",
    "cpu": "CPU", "processor": "CPU",
    "laptop": "laptop", "notebook": "laptop",
    "phone": "smartphone", "iphone": "smartphone", "android": "smartphone",
    "monitor": "monitor", "display": "monitor",
    "headphones": "audio", "earbuds": "audio", "speaker": "audio",
    "keyboard": "keyboard", "mouse": "mouse",
    "tv": "TV", "television": "TV",
    "console": "gaming console", "playstation": "gaming console", "xbox": "gaming console",
    "ssd": "storage", "hard drive": "storage",
    "ram": "memory", "memory": "memory",
}

_PRICE_RE = re.compile(r"(?:under|below|less than|max|at most)\s*\$?([\d,]+)", re.I)
_NUMBER_RE = re.compile(r"\$?([\d,]+)")


def normalize_intent(user_query: str) -> NormalizedIntent:
    """Parse a natural-language query into a structured NormalizedIntent."""
    q = user_query.lower()
    intent = NormalizedIntent(
        search_type="general",
        raw_query=user_query,
    )

    # Detect retailer/platform
    for key, val in _RETAILER_MAP.items():
        if key in q:
            intent.platform = val
            break

    # Detect goal
    for key, val in _GOAL_MAP.items():
        if key in q:
            if val != "max_price":
                intent.goal = val
            break

    # Detect max price
    pm = _PRICE_RE.search(q)
    if pm:
        try:
            intent.max_price = float(pm.group(1).replace(",", ""))
            if not intent.goal:
                intent.goal = "max_price"
        except ValueError:
            pass

    # Detect condition
    for key, val in _CONDITION_MAP.items():
        if key in q:
            intent.condition = val
            break

    # Detect category
    for key, val in _PRODUCT_CATEGORIES.items():
        if key in q:
            intent.category = val
            break

    # Classify search type
    product_signals = ["price", "buy", "order", "cheap", "deal", "stock",
                       "available", "cost", "msrp", "retail", "listing",
                       "amazon", "ebay", "walmart", "best buy", "newegg",
                       "rtx", "rx ", "i9", "i7", "ryzen", "iphone", "ps5", "xbox"]
    news_signals    = ["news", "latest news", "headline", "announced", "release",
                       "launched", "update", "breaking", "today"]
    price_signals   = ["price", "how much", "cost", "msrp", "retail price", "priced at"]

    if any(s in q for s in price_signals):
        intent.search_type = "price_check"
    if any(s in q for s in product_signals):
        intent.search_type = "product"
    if any(s in q for s in news_signals) and intent.search_type == "general":
        intent.search_type = "news"

    # Extract product name — strip filler words and keep noun phrases
    stop = {
        "can", "u", "you", "check", "if", "theres", "there", "is", "any",
        "on", "at", "for", "the", "a", "an", "find", "me", "show", "look",
        "up", "what", "whats", "are", "to", "i", "want", "need", "looking",
        "buy", "get", "available", "in", "stock", "price", "cheapest", "cheap",
        "best", "deal", "how", "much", "does", "cost", "under", "below",
        "least", "least", "than", "2k", "1k", "k",
    }
    # Also strip retailer names from product extraction
    retailer_words = set(_RETAILER_MAP.keys())
    words = re.sub(r"[^\w\s]", " ", user_query).split()
    product_words = [w for w in words if w.lower() not in stop and w.lower() not in retailer_words and len(w) > 1]

    # Common product model patterns: keep uppercase tokens and tech model strings
    model_re = re.compile(r"\b([Rr][Tt][Xx]\s*\d+[A-Za-z]*|[Rr][Xx]\s*\d+[A-Za-z]*|"
                           r"[Ii]\d[-\s]\d+[A-Za-z]*|[Rr]yzen\s*\d+\s*\d+[A-Za-z]*|"
                           r"[Gg][Tt][Xx]\s*\d+[A-Za-z]*|[Ii][Pp]hone\s*\d+[A-Za-z\s]*|"
                           r"[Pp][Ss]\s*\d+|[Xx]box\s*\w+)\b", re.I)
    model_m = model_re.search(user_query)
    if model_m:
        intent.product = model_m.group(0).strip()
    elif product_words:
        intent.product = " ".join(product_words[:4])

    intent.keywords = product_words
    return intent


# ─── Query Generation ──────────────────────────────────────────────────────────

def generate_queries(intent: NormalizedIntent) -> list[str]:
    """
    Generate multiple search queries from a normalized intent.
    Returns 3-5 query strings ordered from most to least specific.
    """
    queries = []
    base = intent.product or " ".join(intent.keywords[:5]) or intent.raw_query

    if intent.search_type in ("product", "price_check"):
        # 1. Exact product + platform
        if intent.platform and intent.platform != "general":
            queries.append(f"{base} {intent.platform}")

        # 2. Exact product + price constraint
        if intent.max_price:
            queries.append(f"{base} under ${int(intent.max_price)}")

        # 3. Plain product query (for shopping search)
        queries.append(base)

        # 4. Site-specific search
        _SITE_MAP = {
            "amazon": "site:amazon.com",
            "ebay": "site:ebay.com",
            "walmart": "site:walmart.com",
            "bestbuy": "site:bestbuy.com",
            "newegg": "site:newegg.com",
        }
        if intent.platform and intent.platform in _SITE_MAP:
            queries.append(f"{_SITE_MAP[intent.platform]} {base}")

        # 5. Broad market fallback
        queries.append(f"{base} price 2025")

    elif intent.search_type == "news":
        queries.append(f"{base} latest news")
        queries.append(f"{base} 2025")
        queries.append(base)

    else:
        # General
        queries.append(intent.raw_query)
        if intent.product:
            queries.append(intent.product)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for q in queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            unique.append(q)
    return unique[:5]


# ─── Scoring ──────────────────────────────────────────────────────────────────

_JUNK_DOMAINS = {"reddit.com", "quora.com", "youtube.com", "wikipedia.org",
                 "stackoverflow.com", "tomshardware.com", "anandtech.com"}
_GOOD_SHOP_DOMAINS = {"amazon.com", "ebay.com", "walmart.com", "bestbuy.com",
                      "newegg.com", "target.com", "bhphotovideo.com", "antonline.com",
                      "microcenter.com", "adorama.com", "costco.com"}

def _extract_domain(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1).lower() if m else ""


def score_result(raw: dict, intent: NormalizedIntent) -> float:
    """
    Score a raw search result dict on 0.0–1.0 scale.
    Higher = more relevant, more usable for the user.
    """
    score = 0.3  # baseline

    title   = (raw.get("title") or "").lower()
    url     = (raw.get("url") or "").lower()
    snippet = (raw.get("body") or raw.get("snippet") or "").lower()
    domain  = _extract_domain(url)
    price   = raw.get("price")

    # Product match
    if intent.product:
        prod_lower = intent.product.lower()
        if prod_lower in title:
            score += 0.25
        elif any(w in title for w in prod_lower.split() if len(w) > 2):
            score += 0.10

    # Platform match
    _PLATFORM_DOMAIN = {
        "amazon": "amazon.com", "ebay": "ebay.com", "walmart": "walmart.com",
        "bestbuy": "bestbuy.com", "newegg": "newegg.com", "target": "target.com",
    }
    if intent.platform and _PLATFORM_DOMAIN.get(intent.platform, "") in domain:
        score += 0.20

    # Shopping domain bonus
    if domain in _GOOD_SHOP_DOMAINS:
        score += 0.10

    # Price present
    if price is not None:
        score += 0.10
        # Price within constraint
        if intent.max_price and isinstance(price, (int, float)):
            if price <= intent.max_price:
                score += 0.15
            else:
                score -= 0.10  # over budget

    # Extract price from snippet if not present
    if price is None:
        pm = re.search(r"\$[\d,]+(?:\.\d{2})?", snippet + title)
        if pm:
            score += 0.05

    # Junk domain penalty
    if domain in _JUNK_DOMAINS:
        score -= 0.15

    # Article/review penalty
    article_signals = ["review", "best", "top 10", "comparison", "vs", "roundup", "guide"]
    if any(s in title for s in article_signals):
        score -= 0.10

    # Recency bonus
    if "2025" in title or "2025" in snippet:
        score += 0.05

    return max(0.0, min(1.0, score))


# ─── Result Aggregation ────────────────────────────────────────────────────────

def _parse_price(raw: dict) -> tuple[Optional[float], Optional[str]]:
    """Return (float_price, display_string) from a result dict."""
    if "price" in raw and raw["price"] is not None:
        try:
            p = float(str(raw["price"]).replace(",", "").replace("$", ""))
            currency = raw.get("currency", "USD")
            return p, f"${p:,.2f}" if currency == "USD" else f"{p:,.2f} {currency}"
        except (ValueError, TypeError):
            pass
    # Try to extract from text
    for field in ("title", "body", "snippet"):
        m = re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", raw.get(field, ""))
        if m:
            try:
                p = float(m.group(1).replace(",", ""))
                return p, f"${p:,.2f}"
            except ValueError:
                pass
    return None, None


def _classify_source_type(url: str, title: str) -> str:
    domain = _extract_domain(url)
    title_lower = title.lower()
    if domain in _GOOD_SHOP_DOMAINS:
        return "listing"
    if "shopping" in url.lower():
        return "shopping"
    if any(s in title_lower for s in ["review", "best ", "top ", "vs ", "comparison", "guide", "roundup"]):
        return "article"
    if any(s in domain for s in ["reddit", "forum", "quora", "discuss"]):
        return "forum"
    return "article"


def aggregate_results(raw_list: list[dict], intent: NormalizedIntent) -> list[SearchResult]:
    """Deduplicate, score, and sort raw search results."""
    seen_urls = set()
    results = []
    for raw in raw_list:
        url = raw.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        price_f, price_str = _parse_price(raw)
        title = raw.get("title", "")
        source = _extract_domain(url)
        source_type = raw.get("source_type") or _classify_source_type(url, title)

        r = SearchResult(
            title         = title,
            url           = url,
            source        = source or raw.get("source", ""),
            source_type   = source_type,
            snippet       = (raw.get("body") or raw.get("snippet") or "")[:300],
            price         = price_f,
            price_str     = price_str,
            seller        = raw.get("seller") or raw.get("source"),
            availability  = raw.get("availability"),
            image_url     = raw.get("image") or raw.get("image_url"),
            matched_product = intent.product,
            confidence_score = score_result(raw, intent),
        )
        results.append(r)

    results.sort(key=lambda x: x.confidence_score, reverse=True)
    return results


# ─── Search Execution ──────────────────────────────────────────────────────────

def _check_web_available() -> bool:
    """Quick connectivity check — tries a known reliable endpoint."""
    try:
        import urllib.request
        urllib.request.urlopen("https://duckduckgo.com", timeout=5)
        return True
    except Exception:
        return False


def _run_text_search(query: str, max_results: int = 6) -> list[dict]:
    from .search import web_search
    return web_search(query, max_results=max_results)


def _run_shopping_search(query: str, max_results: int = 8) -> list[dict]:
    """Use DuckDuckGo shopping search — returns price + image data."""
    try:
        from ddgs import DDGS
        results = []
        with DDGS(timeout=15) as ddgs:
            for r in ddgs.shopping(query, max_results=max_results):
                results.append({
                    "title":    r.get("title", ""),
                    "url":      r.get("url", ""),
                    "body":     r.get("description", ""),
                    "price":    r.get("price"),
                    "currency": r.get("currency", "USD"),
                    "source":   r.get("vendor") or r.get("source", ""),
                    "image":    r.get("image", ""),
                    "source_type": "shopping",
                })
        logger.info("Shopping search: query=%r results=%d", query, len(results))
        return results
    except Exception as exc:
        logger.warning("Shopping search failed (%s), falling back to text", exc)
        return _run_text_search(query, max_results)


# ─── Reliability Orchestrator ──────────────────────────────────────────────────

_MIN_RESULTS          = 2    # minimum acceptable result count
_MIN_TOP_CONFIDENCE   = 0.40  # minimum confidence for top result


async def reliable_search(user_query: str, max_results: int = 8) -> ReliabilityOutput:
    """
    Full reliability pipeline:
      normalize → generate queries → search → aggregate → auto-retry → return

    Never raises — always returns a ReliabilityOutput.
    answer_mode is set based on result quality.
    """
    import asyncio

    t0 = time.perf_counter()
    intent = normalize_intent(user_query)
    queries = generate_queries(intent)
    queries_used: list[str] = []
    all_raw: list[dict] = []
    retry_used = False
    web_available = True

    log: dict = {
        "user_query":       user_query,
        "normalized_intent": {
            "search_type": intent.search_type,
            "product":     intent.product,
            "platform":    intent.platform,
            "goal":        intent.goal,
            "max_price":   intent.max_price,
        },
        "generated_queries": queries,
        "result_count":      0,
        "filtered_count":    0,
        "top_confidence":    0.0,
        "retry_used":        False,
        "final_answer_mode": "hard_failure",
        "web_available":     True,
        "tool_used":         "text",
        "elapsed_ms":        0.0,
    }

    loop = asyncio.get_event_loop()

    # ── Pass 1: primary queries ──────────────────────────────────────────────
    try:
        for q in queries[:3]:
            queries_used.append(q)
            if intent.search_type in ("product", "price_check"):
                # Shopping search for first query; text for extras
                fn = _run_shopping_search if q == queries[0] else _run_text_search
                raw = await loop.run_in_executor(None, lambda qq=q, f=fn: f(qq, max_results))
            else:
                raw = await loop.run_in_executor(
                    None, lambda qq=q: _run_text_search(qq, max_results)
                )
            all_raw.extend(raw)
    except Exception as exc:
        logger.warning("Primary search pass failed: %s", exc)

    # ── Aggregate pass 1 ────────────────────────────────────────────────────
    results = aggregate_results(all_raw, intent)
    top_conf = results[0].confidence_score if results else 0.0

    # ── Auto-retry if weak ───────────────────────────────────────────────────
    good_results = [r for r in results if r.confidence_score >= _MIN_TOP_CONFIDENCE]
    if len(good_results) < _MIN_RESULTS and len(queries) > 3:
        retry_used = True
        log["retry_used"] = True
        logger.info("Weak results (count=%d top_conf=%.2f) — retrying", len(good_results), top_conf)
        try:
            for q in queries[3:]:
                queries_used.append(q)
                raw = await loop.run_in_executor(
                    None, lambda qq=q: _run_text_search(qq, max_results)
                )
                all_raw.extend(raw)
            results = aggregate_results(all_raw, intent)
            top_conf = results[0].confidence_score if results else 0.0
        except Exception as exc:
            logger.warning("Retry search pass failed: %s", exc)

    # ── Determine answer mode ────────────────────────────────────────────────
    filtered = [r for r in results if r.confidence_score >= _MIN_TOP_CONFIDENCE]
    exact    = [r for r in filtered if (
        intent.product and intent.product.lower() in r.title.lower()
        and (not intent.platform or intent.platform in r.source.lower())
    )]

    if exact:
        answer_mode = "exact_match"
    elif filtered:
        answer_mode = "closest_match"
    elif results:
        answer_mode = "market_context"
    else:
        answer_mode = "hard_failure"
        # Only check web availability on total failure
        web_available = _check_web_available()

    top_conf = results[0].confidence_score if results else 0.0

    elapsed = (time.perf_counter() - t0) * 1000
    log.update({
        "result_count":      len(all_raw),
        "filtered_count":    len(filtered),
        "top_confidence":    round(top_conf, 3),
        "final_answer_mode": answer_mode,
        "web_available":     web_available,
        "tool_used":         "shopping+text" if intent.search_type in ("product", "price_check") else "text",
        "queries_used":      queries_used,
        "elapsed_ms":        round(elapsed, 1),
    })

    logger.info(
        "reliable_search | mode=%s results=%d filtered=%d top_conf=%.2f retry=%s elapsed=%.0fms",
        answer_mode, len(results), len(filtered), top_conf, retry_used, elapsed,
    )

    return ReliabilityOutput(
        intent        = intent,
        results       = results[:max_results],
        answer_mode   = answer_mode,
        queries_used  = queries_used,
        retry_used    = retry_used,
        web_available = web_available,
        top_confidence = top_conf,
        log           = log,
    )


# ─── Response Formatter ────────────────────────────────────────────────────────

def format_for_injection(output: ReliabilityOutput) -> str:
    """
    Format ReliabilityOutput into a context string for LLM injection.
    Structured so Claude returns usable results with links and prices.
    """
    intent  = output.intent
    results = output.results
    mode    = output.answer_mode

    if mode == "hard_failure":
        if not output.web_available:
            return (
                "[WEB SEARCH — UNAVAILABLE]\n"
                "Web connectivity could not be confirmed. "
                "Tell the user live search is temporarily unavailable and ask them to try again."
            )
        return (
            "[WEB SEARCH — NO RESULTS]\n"
            f"Searched for: {', '.join(output.queries_used)}\n"
            "No usable results were returned. "
            "Tell the user the search returned nothing and suggest specific sites to check directly."
        )

    # Build header
    lines = []
    if mode == "exact_match":
        lines.append(f"[WEB SEARCH RESULTS — EXACT MATCH]")
    elif mode == "closest_match":
        lines.append(f"[WEB SEARCH RESULTS — CLOSEST MATCHES]")
        if intent.product:
            lines.append(
                f"Note: Could not find exact listings matching all constraints. "
                f"Returning closest available results for '{intent.product}'."
            )
    else:
        lines.append("[WEB SEARCH RESULTS — MARKET CONTEXT]")

    lines.append(f"Query: {intent.raw_query}")
    if intent.product:
        lines.append(f"Product: {intent.product}")
    if intent.platform:
        lines.append(f"Platform: {intent.platform}")
    if intent.max_price:
        lines.append(f"Budget: under ${intent.max_price:,.0f}")
    lines.append("")

    # Results
    shown = 0
    for i, r in enumerate(results[:6]):
        if r.confidence_score < 0.15:
            continue
        lines.append(f"Result {shown + 1}:")
        lines.append(f"  Title: {r.title}")
        if r.price_str:
            lines.append(f"  Price: {r.price_str}")
        if r.seller:
            lines.append(f"  Seller/Source: {r.seller}")
        if r.availability:
            lines.append(f"  Availability: {r.availability}")
        lines.append(f"  URL: {r.url}")
        if r.image_url:
            lines.append(f"  Image: {r.image_url}")
        if r.snippet:
            lines.append(f"  Snippet: {r.snippet[:200]}")
        lines.append(f"  Confidence: {r.confidence_score:.2f}")
        lines.append("")
        shown += 1
        if shown >= 6:
            break

    if shown == 0:
        lines.append("(No results met the quality threshold.)")
        lines.append("")

    # Instructions for the model
    lines.append("─" * 60)
    lines.append("RESPONSE INSTRUCTIONS:")
    lines.append("- Lead with a direct answer to the user's question")
    lines.append("- List each result with: title, price, clickable link formatted as [View listing](URL)")
    lines.append("- If an image URL is present, include it as a markdown image: ![title](image_url)")
    lines.append("- If max_price constraint was not met, say so clearly and show closest options")
    lines.append("- End with a short takeaway (1-2 sentences)")
    lines.append("- NEVER tell the user to search manually — you have already searched")
    lines.append("- NEVER say you cannot browse the internet — you just did")

    return "\n".join(lines)
