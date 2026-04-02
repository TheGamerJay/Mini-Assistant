"""
retrieval/retrieval_engine.py — CEO-controlled context retrieval engine.

The CEO is the ONLY entity that may trigger retrieval.
Brains NEVER call this directly.

CEO calls retrieve() with:
  - session_id: current session
  - mode: "chat" | "image_edit"
  - task_description: what the brain is about to do
  - sources_allowed: which source types are permitted for this brain

Returns a RetrievalResult dict that CEO passes to the brain.

SOURCES:
  context_docs  — system behavior documentation
  repair_memory — similar past problem+solution pairs
  project_files — user's project context (from session memory)
  logs          — recent execution events (doctor only)
  task_state    — current session context (recent messages, facts)
  prior_outputs — previous module outputs in this session

RULES:
  - CEO must explicitly allow each source type
  - retrieve() enforces budget caps per source
  - context is ranked + pruned before returning (context_ranker)
  - output format: {retrieval_used, sources, selected_context, reason}
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger("ceo_router.retrieval")

# Per-brain source allowances — CEO enforces this
_BRAIN_ALLOWANCES: dict[str, set[str]] = {
    "ceo":          {"context_docs", "task_state"},
    "builder":      {"project_files", "context_docs", "task_state"},
    "doctor":       {"repair_memory", "project_files", "logs", "context_docs"},
    "hands":        {"task_state", "test_results"},
    "vision":       {"task_state", "project_files"},
    "general_chat": {"context_docs", "task_state"},
    "task_assist":  {"task_state", "context_docs"},
    "campaign_lab": {"task_state", "context_docs"},
    "web_search":   {"task_state"},
}

# Token budget caps per source type (approximate character counts)
_BUDGET_CAPS: dict[str, int] = {
    "context_docs":   3000,
    "repair_memory":  1500,
    "project_files":  4000,
    "logs":           2000,
    "task_state":     3000,
    "prior_outputs":  2000,
    "test_results":   1500,
}


def retrieve(
    session_id:       str,
    mode:             str,
    brain:            str,
    task_description: str,
    sources_allowed:  Optional[list[str]] = None,
    extra_sources:    Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    CEO-controlled retrieval.

    Args:
        session_id:       current session identifier
        mode:             "chat" | "image_edit"
        brain:            which brain this context is for
        task_description: what the brain is about to do (used for ranking)
        sources_allowed:  override default brain allowances (CEO may restrict further)
        extra_sources:    pre-loaded data to include (bypasses file reads)

    Returns:
        {
            retrieval_used:     bool,
            sources:            list[str],  # sources consulted
            selected_context:   list[dict], # ranked, pruned context items
            reason:             str,
            candidates_found:   int,
            selected_count:     int,
            pruned_count:       int,
        }
    """
    from .context_ranker import rank_and_prune

    # Determine allowed sources for this brain
    allowed = _resolve_allowed_sources(brain, sources_allowed)
    log.debug("retrieval: brain=%s allowed_sources=%s", brain, sorted(allowed))

    if not allowed:
        return _empty_result("No sources allowed for this brain")

    # Gather candidates from each allowed source
    candidates: list[dict[str, Any]] = []

    if "task_state" in allowed:
        candidates.extend(_load_task_state(session_id, mode))

    if "repair_memory" in allowed:
        candidates.extend(_load_repair_memory(task_description))

    if "context_docs" in allowed:
        candidates.extend(_load_context_docs(task_description))

    if "logs" in allowed:
        candidates.extend(_load_recent_logs(session_id))

    if "project_files" in allowed:
        candidates.extend(_load_project_files(session_id))

    if "prior_outputs" in allowed:
        candidates.extend(_load_prior_outputs(session_id))

    # Merge any extra pre-loaded sources (CEO may inject data directly)
    if extra_sources:
        for source_type, data in extra_sources.items():
            if source_type in allowed and data:
                candidates.append({
                    "source":   source_type,
                    "content":  str(data)[:_BUDGET_CAPS.get(source_type, 2000)],
                    "relevance": 1.0,  # CEO-injected data is pre-qualified
                })

    candidates_found = len(candidates)
    log.debug("retrieval: candidates_found=%d for brain=%s", candidates_found, brain)

    if not candidates:
        return _empty_result(f"No context found in allowed sources: {sorted(allowed)}")

    # Rank and prune to final context
    ranked = rank_and_prune(candidates, task_description, brain, allowed)
    selected_count = len(ranked)
    pruned_count   = candidates_found - selected_count

    log.info(
        "retrieval: brain=%s sources=%d candidates=%d selected=%d pruned=%d",
        brain, len(allowed), candidates_found, selected_count, pruned_count,
    )

    return {
        "retrieval_used":   True,
        "sources":          list(allowed),
        "selected_context": ranked,
        "reason":           f"CEO retrieved context for {brain}: {task_description[:80]}",
        "candidates_found": candidates_found,
        "selected_count":   selected_count,
        "pruned_count":     pruned_count,
    }


# ---------------------------------------------------------------------------
# Source loaders
# ---------------------------------------------------------------------------

def _load_task_state(session_id: str, mode: str) -> list[dict]:
    """Load session context (recent messages, facts learned, etc.)."""
    try:
        from context.context_store import load
        ctx = load(session_id, mode)
        items = []

        # Recent messages (last 5 for context, not full 20)
        msgs = ctx.get("recent_messages", [])[-5:]
        if msgs:
            items.append({
                "source":   "task_state",
                "subtype":  "recent_messages",
                "content":  _format_messages(msgs),
                "relevance": 0.8,
            })

        # Facts learned
        facts = ctx.get("facts_learned", {})
        if facts:
            items.append({
                "source":   "task_state",
                "subtype":  "facts_learned",
                "content":  "\n".join(f"{k}: {v}" for k, v in facts.items())[:1000],
                "relevance": 0.7,
            })

        # Tools used
        tools = ctx.get("tools_used", [])
        if tools:
            items.append({
                "source":   "task_state",
                "subtype":  "tools_used",
                "content":  f"Tools used this session: {', '.join(tools)}",
                "relevance": 0.4,
            })

        return items
    except Exception as exc:
        log.debug("retrieval: task_state load failed — %s", exc)
        return []


def _load_repair_memory(task_description: str) -> list[dict]:
    """Search repair memory for similar past problems."""
    try:
        from core.repair_memory.repair_search import search_all_categories
        matches = search_all_categories(task_description, top_n=3)
        items = []
        for m in matches:
            score = m.get("similarity_score", 0)
            if score < 0.25:
                continue  # IGNORE threshold
            items.append({
                "source":    "repair_memory",
                "subtype":   "past_fix",
                "content":   (
                    f"Past problem: {m.get('problem_name', '')}\n"
                    f"Solution: {m.get('solution_name', '')}\n"
                    f"Steps: {'; '.join(m.get('solution_steps', [])[:3])}"
                ),
                "relevance": min(score, 1.0),
                "meta":      {
                    "category":         m.get("_category"),
                    "confidence_level": m.get("confidence_level"),
                    "similarity_score": score,
                    "success_count":    m.get("success_count", 0),
                },
            })
        return items
    except Exception as exc:
        log.debug("retrieval: repair_memory load failed — %s", exc)
        return []


def _load_context_docs(task_description: str) -> list[dict]:
    """
    Load relevant context docs by keyword matching.
    Returns at most 2 relevant doc excerpts.
    """
    try:
        from pathlib import Path as _Path
        docs_dir = _Path(__file__).resolve().parents[2] / "context_docs"
        if not docs_dir.exists():
            return []

        keywords = set(task_description.lower().split())
        results: list[tuple[float, str, str]] = []

        for doc_path in docs_dir.glob("*.md"):
            text = doc_path.read_text(encoding="utf-8", errors="ignore")
            text_lower = text.lower()
            # Score by keyword overlap
            overlap = sum(1 for kw in keywords if len(kw) > 3 and kw in text_lower)
            score = overlap / max(len(keywords), 1)
            if score > 0.05:
                results.append((score, doc_path.stem, text[:2000]))

        results.sort(key=lambda x: -x[0])
        return [
            {
                "source":   "context_docs",
                "subtype":  name,
                "content":  excerpt,
                "relevance": min(score * 2, 0.9),  # scale up but cap at 0.9
            }
            for score, name, excerpt in results[:2]
        ]
    except Exception as exc:
        log.debug("retrieval: context_docs load failed — %s", exc)
        return []


def _load_recent_logs(session_id: str) -> list[dict]:
    """Load recent execution events for this session (Doctor only)."""
    try:
        from logs.event_logger import read_events
        events = read_events(limit=20)
        session_events = [e for e in events if e.get("session_id") == session_id]
        if not session_events:
            return []
        summary = "\n".join(
            f"[{e.get('event_type')}] {e.get('module')} — {e.get('summary')}"
            for e in session_events[:10]
        )
        return [{
            "source":   "logs",
            "subtype":  "recent_execution",
            "content":  summary,
            "relevance": 0.75,
        }]
    except Exception as exc:
        log.debug("retrieval: logs load failed — %s", exc)
        return []


def _load_project_files(session_id: str) -> list[dict]:
    """Load project context from session memory (if engineering assistant populated it)."""
    try:
        from context.context_store import load
        ctx = load(session_id, "chat")
        facts = ctx.get("facts_learned", {})
        # Engineering assistant stores project context under specific keys
        project_keys = {"language", "framework", "database", "project_name", "project_type"}
        project_facts = {k: v for k, v in facts.items() if k in project_keys}
        if not project_facts:
            return []
        return [{
            "source":   "project_files",
            "subtype":  "project_context",
            "content":  "\n".join(f"{k}: {v}" for k, v in project_facts.items()),
            "relevance": 0.8,
        }]
    except Exception as exc:
        log.debug("retrieval: project_files load failed — %s", exc)
        return []


def _load_prior_outputs(session_id: str) -> list[dict]:
    """Load prior module outputs stored in session (if any)."""
    try:
        from core.api.xray_endpoint import get_xray_data
        data = get_xray_data(session_id) or {}
        decision = data.get("decision", {})
        if not decision:
            return []
        return [{
            "source":   "prior_outputs",
            "subtype":  "last_decision",
            "content":  f"Last module: {decision.get('selected_module', '')} — intent: {decision.get('intent', '')}",
            "relevance": 0.5,
        }]
    except Exception as exc:
        log.debug("retrieval: prior_outputs load failed — %s", exc)
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_allowed_sources(brain: str, override: Optional[list[str]]) -> set[str]:
    """Get allowed sources for a brain, with optional CEO override (can only restrict)."""
    brain_defaults = _BRAIN_ALLOWANCES.get(brain, {"task_state"})
    if override is None:
        return set(brain_defaults)
    # CEO may only restrict, never expand beyond brain defaults
    return set(override) & brain_defaults


def _format_messages(msgs: list[dict]) -> str:
    parts = []
    for m in msgs:
        role    = m.get("role", "?")
        content = m.get("content", "")[:300]
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _empty_result(reason: str) -> dict[str, Any]:
    return {
        "retrieval_used":   False,
        "sources":          [],
        "selected_context": [],
        "reason":           reason,
        "candidates_found": 0,
        "selected_count":   0,
        "pruned_count":     0,
    }
