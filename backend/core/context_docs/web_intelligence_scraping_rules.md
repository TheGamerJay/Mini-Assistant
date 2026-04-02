# Web Intelligence — Scraping Rules

## What to extract

Extract only the content relevant to the user's task:
- Main article or page body text
- Title and key headings
- Distinct factual sentences or bullet points

## What to strip

The following are ALWAYS removed before output:
- `<script>` blocks (JavaScript)
- `<style>` blocks (CSS)
- `<nav>` blocks (navigation menus)
- `<footer>` and `<header>` blocks (site chrome)
- `<aside>` blocks (sidebars)
- `<form>` blocks (login forms, search boxes)
- `<noscript>` fallbacks
- HTML entities → decoded to readable characters

## Structured output format

Every scraper result MUST have this shape:

```json
{
    "ok":         true,
    "url":        "https://example.com/article",
    "title":      "Article Title",
    "summary":    "First meaningful paragraph or opening sentences (max 500 chars).",
    "key_points": [
        "Key sentence 1 (40–300 chars).",
        "Key sentence 2.",
        "Key sentence 3."
    ],
    "text":       "Full cleaned text (max 8,000 chars).",
    "error":      null
}
```

## Content size rules

| Field       | Limit       | Notes                                    |
|-------------|-------------|------------------------------------------|
| text        | 8,000 chars | Hard cap — truncate before returning     |
| summary     | 500 chars   | First meaningful paragraph               |
| key_points  | 5 items max | 40–300 chars each; skip short fragments  |

## Loop and duplicate prevention

- Crawler tracks `visited` URLs — never fetches the same URL twice
- Links are filtered to same-domain only (no external link following)
- Anchor fragments are stripped from links (#section → ignored)
- Stop crawling as soon as `max_pages` (5) is reached

## Quality checks (via web_validator)

After scraping, results are passed through `web_validator.validate_web_results()`:

| Check          | Rule                                                          |
|----------------|---------------------------------------------------------------|
| Sanity         | Error page signals → discard                                  |
| Length         | Fewer than 20 meaningful words → discard                      |
| Average length | Average word length < 3 chars → likely gibberish → discard    |
| Relevance      | < 10% keyword overlap with query → discard                    |
| Duplication    | > 80% word overlap with another result → discard as duplicate |
| Source trust   | Social media / low-trust domains → flag or discard            |

## Fail conditions — scraper FAILS if

- Raw HTML is returned without stripping
- Output exceeds token cap without truncation
- Error pages are passed forward as valid content
- The same URL is fetched more than once per crawl session
- External domains are followed during a crawl
