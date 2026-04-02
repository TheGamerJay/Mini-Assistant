"""
execution/tier_output_filter.py — Apply tier depth constraints to module output.

Tier filtering controls OUTPUT DEPTH, not experience quality or intelligence.
Free users get the same smart output — just less of it in depth-limited modules.

Rules:
- NEVER degrade intelligence — only depth
- free users see complete summaries + limited file/code visibility
- paid users see full structured outputs with all files and code
- filtering is applied AFTER module execution and validation
- filter never removes the result entirely — always returns usable output

Depth constraints applied (from tier_controller.DEPTH_CONSTRAINTS):
  web_intelligence:
    - max_results: 3
    - sources_shown: False (URLs hidden)
    - max_content_length: 500

  builder:
    - max_files: 2
    - max_lines_per_file: 80
    - backend_scaffold: False (backend files truncated to summary)

  image:
    - watermark: True  (metadata flag, rendering handles actual watermark)
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("ceo_router.tier_output_filter")


def apply_tier_filter(
    module:          str,
    result:          dict[str, Any],
    tier_visibility: str,
) -> dict[str, Any]:
    """
    Apply depth constraints to result based on tier_visibility.

    Returns the filtered result dict. Internal keys (_events, _validation, etc.)
    are never touched.
    """
    if tier_visibility in ("paid", "free"):
        # No filtering — full depth or no restrictions
        return result

    if tier_visibility == "free_limited":
        return _apply_limited(module, result)

    # blocked is handled upstream (CEO reroutes to core_chat)
    return result


# ---------------------------------------------------------------------------
# Per-module free_limited filters
# ---------------------------------------------------------------------------

def _apply_limited(module: str, result: dict[str, Any]) -> dict[str, Any]:
    filters = {
        "web_intelligence": _filter_web,
        "builder":          _filter_builder,
        "image":            _filter_image,
    }
    fn = filters.get(module)
    if fn is None:
        return result
    try:
        filtered = fn(result)
        filtered["_tier_filtered"] = True
        log.debug("tier_filter: applied free_limited filter for module=%s", module)
        return filtered
    except Exception as exc:
        log.warning("tier_filter: filter failed for module=%s — %s", module, exc)
        return result


def _filter_web(result: dict[str, Any]) -> dict[str, Any]:
    """
    web_intelligence free_limited:
    - max 3 results
    - URLs hidden (sources_shown = False)
    - content truncated to 500 chars per result
    """
    results = result.get("results", [])
    limited: list[dict] = []
    for r in results[:3]:
        limited.append({
            "title":   r.get("title", ""),
            "snippet": r.get("snippet", "")[:500],
            # url intentionally omitted — sources_shown = False
        })
    return {**result, "results": limited, "_tier_note": "Results limited to 3. Upgrade for full access."}


def _filter_builder(result: dict[str, Any]) -> dict[str, Any]:
    """
    builder free_limited:
    - max 2 files shown
    - each file code truncated to 80 lines
    - backend scaffold files reduced to description-only
    """
    files = result.get("files", [])
    limited_files: list[dict] = []

    for f in files[:2]:
        ftype = f.get("type", "backend")
        code  = f.get("code", "")

        if ftype == "backend":
            # Backend files: show first 80 lines with truncation note
            lines = code.split("\n")
            if len(lines) > 80:
                code = "\n".join(lines[:80]) + "\n# ... (upgrade to see full backend code)"
        else:
            # Frontend/config: show first 80 lines
            lines = code.split("\n")
            if len(lines) > 80:
                code = "\n".join(lines[:80]) + "\n# ... (truncated)"

        limited_files.append({**f, "code": code})

    hidden_count = max(0, len(files) - 2)
    notes = list(result.get("notes", []))
    if hidden_count > 0:
        notes.append(f"{hidden_count} file(s) hidden. Upgrade to see full output.")

    return {
        **result,
        "files":      limited_files,
        "notes":      notes,
        "_tier_note": "Output depth limited. Upgrade for full file and code visibility.",
    }


def _filter_image(result: dict[str, Any]) -> dict[str, Any]:
    """
    image free_limited:
    - watermark metadata flag set (UI handles actual rendering)
    - resolution note added
    """
    return {
        **result,
        "_watermark":  True,
        "_tier_note":  "Free tier: watermark applied. Upgrade for clean image output.",
    }
