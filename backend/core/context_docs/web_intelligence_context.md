# Web Intelligence — System Context

## Purpose

The Web Intelligence system provides real-world information retrieval for the CEO pipeline.
It fetches, extracts, validates, and summarizes external data before passing it to generation modules.

Web tools are ONLY used when:
- The user explicitly requests real-time or external information
- The data is not available in TR memory
- External data validation is required

## Available Tools

| Tool        | Mode      | Use case                                          | Limit          |
|-------------|-----------|---------------------------------------------------|----------------|
| Web Search  | `search`  | Fast query-based lookup — returns links + summaries | 5 results max  |
| Web Scraper | `scraper` | Extract structured content from a single URL      | 1 URL, 8k chars|
| Web Crawler | `crawler` | Follow related links from a seed URL              | 5 pages max    |

## CEO-Controlled Flow

```
User message
    │
    ▼
web_decider.decide_web(message, intent, memory_available)
    │
    ├── requires_web = False → skip (use memory or generate directly)
    │
    └── requires_web = True
            │
            ├── mode = "search"  → web_search.run_search(query)
            ├── mode = "scraper" → web_scraper.scrape_url(url)
            └── mode = "crawler" → web_crawler.crawl(seed_url)
                    │
                    ▼
            web_validator.validate_web_results(query, results, mode)
                    │
                    ▼
            Validated results injected into module context
```

## When to use web vs NOT use web

### USE web when:
- User asks for real-time data (prices, news, scores, weather)
- User asks to extract content from a specific URL
- User asks to research a topic not in memory
- User explicitly says "search the web", "look it up", "check online"

### DO NOT use web for:
- Basic content generation (essays, emails, resumes, campaigns)
- Questions answerable from TR memory
- Tasks where internet access adds no value
- Any task where the user provided all needed context in their message

## CPU-Friendly Constraints

- No heavy crawling (max 5 pages)
- No large-scale indexing
- No background scraping jobs
- Process only what is needed for the current request
- Token size from scraped content is capped (8k chars)
- Web results are summarized before being passed to generation

## Validation Requirement

All web data MUST be validated before use. Raw web content is NOT trusted.
See `web_intelligence_guardrails.md` for validation rules.
