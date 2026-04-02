# Web Intelligence — Guardrails

## Hard rules

1. **Web tools must NEVER run without CEO approval.**
   `web_decider.decide_web()` is the ONLY gate. No module may call web tools directly.

2. **Do NOT scrape unnecessary pages.**
   Scraper and crawler run only when the module explicitly needs URL-level content.
   Web search covers 95% of use cases.

3. **Do NOT process full websites unless the task requires it.**
   Crawler depth is capped at 5 pages. Stop early when sufficient data is found.

4. **Do NOT trust raw web content blindly.**
   Every retrieval goes through `web_validator.validate_web_results()` before use.
   Relevance, trust, duplication, and sanity checks must all pass.

5. **Must validate relevance before use.**
   Content with < 10% keyword overlap with the query is discarded.

6. **Must limit token size.**
   Scraped content is capped at 8,000 characters per page.
   Search snippets are used as-is (already short).

7. **Must summarize before passing to generation.**
   Web scraper output includes `summary` and `key_points` — modules must prefer 
   these over raw `text` when context is tight.

8. **Must NOT override internal memory unless needed.**
   If TR memory is available and sufficient, web retrieval is skipped.
   Priority order: user input → TR memory → web.

## Failure conditions — system FAILS if any of these occur

- Web tools run without CEO routing them
- Raw HTML is forwarded directly to a generation module
- Web data is used without running through `web_validator`
- The crawler is allowed to loop infinitely
- More than 5 pages are crawled per request
- Scraped content exceeds the token cap and is passed untruncated
- Low-trust domains (Reddit, Pinterest, Facebook, etc.) are used as authoritative sources
- Web results replace TR memory when memory was available and relevant

## Soft rules (follow unless there is a clear reason not to)

- Prefer `search` over `scraper` over `crawler`
- If the user provides a URL, use scraper — don't search for content that is already linked
- If the user asks for "research" without a URL, use search
- If multiple pages from the same domain are needed, use crawler (max depth 2–3)
