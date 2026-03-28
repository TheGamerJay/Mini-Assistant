"""
Intent Lock — Clarification + Normalization Layer

Parses the user's request into a structured IntentLock before any execution.
Detects:
  - ambiguity
  - contradictions
  - under-specified decisions
  - scope boundary

An IntentLock once produced is stored per-session so subsequent steps
(decomposer, executor) can reference the normalized goal without re-parsing.

Lightweight: uses regex + keyword rules. LLM-assisted clarification is handled
by the orchestrator when decision_engine says ASK.
"""

from __future__ import annotations

import re
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class IntentLock:
    """Normalized, structured representation of the user's goal."""
    session_id:          str
    raw_request:         str
    normalized_goal:     str
    intent_type:         str           # "build" | "patch" | "query" | "image" | "analysis" | "chat"
    mode:                str           # "builder" | "chat" | "image"
    constraints:         List[str] = field(default_factory=list)
    assumptions_accepted: List[str] = field(default_factory=list)
    assumptions_blocked:  List[str] = field(default_factory=list)
    pending_decisions:   List[str] = field(default_factory=list)
    confirmed_scope:     str = ""      # explicit summary of what IS in scope
    ambiguity_score:     float = 0.0   # 0 = crystal clear, 1 = very ambiguous
    contradiction_found: bool = False
    lock_hash:           str = ""      # content hash — same request = same hash


# ---------------------------------------------------------------------------
# Regex signals
# ---------------------------------------------------------------------------

_BUILD_RE  = re.compile(r"\b(build|create|make|generate|develop|write|code|set\s*up|implement)\b", re.I)
_PATCH_RE  = re.compile(r"\b(fix|patch|update|change|adjust|tweak|add|remove|move|rename|"
                         r"slow|faster|bigger|smaller|darker|lighter)\b", re.I)
_QUERY_RE  = re.compile(r"^(what|how|why|when|where|who|is|are|can|does|did|will|should|could|would)\b", re.I)
_IMAGE_RE  = re.compile(r"\b(draw|paint|generate\s+an?\s+image|create\s+an?\s+image|render|"
                         r"illustrate|design\s+an?\s+(image|logo|banner)|photo|picture)\b", re.I)
_ANALYSIS_RE = re.compile(r"\b(analyze|analyse|review|audit|inspect|check|look\s+at|"
                           r"what.s wrong|debug|profile)\b", re.I)

_CONTRADICTION_PAIRS = [
    (re.compile(r"\bkeep\b", re.I),    re.compile(r"\bremove\b", re.I)),
    (re.compile(r"\badd\b", re.I),     re.compile(r"\bdelete\b", re.I)),
    (re.compile(r"\bsimple\b", re.I),  re.compile(r"\bcomplex\b", re.I)),
    (re.compile(r"\bslow\b", re.I),    re.compile(r"\bfast\b", re.I)),
    (re.compile(r"\bdark\b", re.I),    re.compile(r"\blight\b", re.I)),
]

_SCOPE_RE = re.compile(
    r"\b(everything|entire|whole|all|from scratch|rewrite|redesign|redo|overhaul)\b", re.I
)

_AMBIGUITY_WORDS = re.compile(
    r"\b(maybe|might|or|either|whatever|anything|something|some|not sure|"
    r"i guess|perhaps|ideally|kind of|sort of|could be)\b", re.I
)


# ---------------------------------------------------------------------------
# Storage (per-session, on disk)
# ---------------------------------------------------------------------------

_LOCK_DIR = Path(__file__).parent.parent.parent / "memory_store" / "intent_locks"


def _ensure_dir() -> None:
    _LOCK_DIR.mkdir(parents=True, exist_ok=True)


def _lock_path(session_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", session_id)
    return _LOCK_DIR / f"{safe}.json"


def save_lock(lock: IntentLock) -> None:
    _ensure_dir()
    path = _lock_path(lock.session_id)
    data = {
        "session_id":          lock.session_id,
        "raw_request":         lock.raw_request,
        "normalized_goal":     lock.normalized_goal,
        "intent_type":         lock.intent_type,
        "mode":                lock.mode,
        "constraints":         lock.constraints,
        "assumptions_accepted": lock.assumptions_accepted,
        "assumptions_blocked": lock.assumptions_blocked,
        "pending_decisions":   lock.pending_decisions,
        "confirmed_scope":     lock.confirmed_scope,
        "ambiguity_score":     lock.ambiguity_score,
        "contradiction_found": lock.contradiction_found,
        "lock_hash":           lock.lock_hash,
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_lock(session_id: str) -> Optional[IntentLock]:
    path = _lock_path(session_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return IntentLock(**data)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(
    message: str,
    session_id: str,
    mode: str = "chat",
    history: Optional[List[Dict[str, Any]]] = None,
) -> IntentLock:
    """
    Parse a raw user message into a structured IntentLock.

    Does NOT call any LLM. Pure rule-based analysis.
    For LLM-assisted disambiguation, the orchestrator uses this output
    to construct a targeted question.
    """
    msg = message.strip()
    history = history or []

    # ── Intent type ─────────────────────────────────────────────────────────
    if _IMAGE_RE.search(msg):
        intent_type = "image"
    elif _QUERY_RE.match(msg) and not _BUILD_RE.search(msg):
        intent_type = "query"
    elif _ANALYSIS_RE.search(msg):
        intent_type = "analysis"
    elif _BUILD_RE.search(msg) and not _PATCH_RE.search(msg):
        intent_type = "build"
    elif _PATCH_RE.search(msg):
        intent_type = "patch"
    else:
        intent_type = "chat"

    # ── Ambiguity score ─────────────────────────────────────────────────────
    ambiguity_hits = len(_AMBIGUITY_WORDS.findall(msg))
    word_count = max(1, len(msg.split()))
    ambiguity_score = min(1.0, ambiguity_hits / max(1, word_count / 5))

    # ── Contradiction detection ─────────────────────────────────────────────
    contradiction_found = any(
        a.search(msg) and b.search(msg)
        for a, b in _CONTRADICTION_PAIRS
    )

    # ── Scope analysis ──────────────────────────────────────────────────────
    is_broad_scope = bool(_SCOPE_RE.search(msg))

    # ── Constraints extraction (simple keyword rules) ───────────────────────
    constraints: List[str] = []
    if re.search(r"\bno\s+(animation|transitions?)\b", msg, re.I):
        constraints.append("No animations")
    if re.search(r"\bno\s+(dark\s+mode|light\s+mode)\b", msg, re.I):
        constraints.append("Fixed color mode")
    if re.search(r"\bmobile[\s\-]?(?:first|only|friendly)\b", msg, re.I):
        constraints.append("Mobile-first layout")
    if re.search(r"\bresponsive\b", msg, re.I):
        constraints.append("Responsive design required")
    if re.search(r"\bno\s+backend\b", msg, re.I):
        constraints.append("Frontend-only (no backend)")
    if re.search(r"\bsingle\s+file\b", msg, re.I):
        constraints.append("Single-file output")

    # ── Assumptions accepted (safe defaults we'll apply) ───────────────────
    assumptions_accepted: List[str] = []
    if intent_type == "build":
        assumptions_accepted.append("Single self-contained HTML file output")
        assumptions_accepted.append("Dark theme by default unless specified")
    if intent_type == "patch":
        assumptions_accepted.append("Minimum-change patch — only what was requested")

    # ── Pending decisions (things we'll decide autonomously if low-risk) ────
    pending_decisions: List[str] = []
    if is_broad_scope:
        pending_decisions.append("Scope definition: which parts to change")
    if contradiction_found:
        pending_decisions.append("Resolve contradiction in request")
    if ambiguity_score > 0.4:
        pending_decisions.append("Clarify exact desired outcome")

    # ── Normalize goal (clean version of the request) ───────────────────────
    normalized_goal = _normalize(msg)

    # ── Confirmed scope summary ─────────────────────────────────────────────
    confirmed_scope = _build_scope(intent_type, msg, constraints)

    # ── Content hash (deduplication) ────────────────────────────────────────
    lock_hash = hashlib.md5(f"{normalized_goal}|{mode}".encode()).hexdigest()[:12]

    lock = IntentLock(
        session_id=session_id,
        raw_request=msg,
        normalized_goal=normalized_goal,
        intent_type=intent_type,
        mode=mode,
        constraints=constraints,
        assumptions_accepted=assumptions_accepted,
        assumptions_blocked=[],
        pending_decisions=pending_decisions,
        confirmed_scope=confirmed_scope,
        ambiguity_score=round(ambiguity_score, 2),
        contradiction_found=contradiction_found,
        lock_hash=lock_hash,
    )

    # Persist (non-blocking, non-fatal)
    try:
        save_lock(lock)
    except Exception:
        pass

    return lock


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _normalize(msg: str) -> str:
    """Strip filler words and produce a cleaner goal statement."""
    # Remove common filler starters
    msg = re.sub(r"^(hey|hi|hello|ok|okay|please|can you|could you|i need|i want|i'd like|"
                 r"make sure|make it so that|just)\s+", "", msg, flags=re.I)
    msg = re.sub(r"\s+", " ", msg).strip()
    if msg and not msg[0].isupper():
        msg = msg[0].upper() + msg[1:]
    return msg


def _build_scope(intent_type: str, msg: str, constraints: List[str]) -> str:
    parts = [f"Intent: {intent_type.title()}"]
    if constraints:
        parts.append("Constraints: " + ", ".join(constraints))
    # Extract key noun phrase (first non-stopword noun)
    nouns = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", msg)
    if nouns:
        parts.append(f"Subject: {nouns[0]}")
    return " | ".join(parts)
