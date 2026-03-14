"""
session_memory.py — Phase 6 Persistent Session Memory
───────────────────────────────────────────────────────
Stores key facts from conversations that persist across server restarts
and multiple sessions for the same user/project.

Differs from Phase 2 Manager (in-memory, TTL-pruned, per-session deque):
  - Phase 2 Manager: ephemeral, lost on restart, last 5 intents only
  - Phase 6 Session Memory: JSON-persistent, unlimited retention,
    structured key-value facts with confidence scoring

Auto-extraction patterns (no LLM needed):
  "I'm using Python 3.11"          → fact(key="language", value="Python 3.11")
  "My project is called FoodApp"   → fact(key="project_name", value="FoodApp")
  "I prefer tabs over spaces"      → fact(key="indent_style", value="tabs")
  "Remember that we use MongoDB"   → fact(key="database", value="MongoDB")
  "The backend is FastAPI"         → fact(key="backend_framework", value="FastAPI")

Usage:
    mem = SessionMemory()
    mem.store("sess_abc", "language", "Python 3.11", confidence=0.9)
    facts = mem.get_facts("sess_abc")
    context = mem.format_for_prompt("sess_abc")
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_PATH  = os.getenv("SESSION_MEMORY_PATH", "./memory_store/session_memory.json")
MAX_FACTS_TOTAL = 2000   # across all sessions


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Fact model ────────────────────────────────────────────────────────────────

@dataclass
class MemoryFact:
    id:         str
    session_id: str
    key:        str         # e.g. "language", "backend_framework", "project_name"
    value:      str
    confidence: float       # 0.0–1.0; higher = more certain
    source:     str         # "explicit" | "extracted" | "inferred"
    intent:     str         # intent that produced this fact
    created_at: str         = field(default_factory=_now)
    updated_at: str         = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryFact":
        return cls(**d)


# ── Auto-extraction patterns ──────────────────────────────────────────────────

_EXTRACT_PATTERNS: list[tuple[str, re.Pattern, float]] = [
    # key,                  pattern,                                       confidence
    ("language",
     re.compile(r"\b(?:using|written in|coded in|built with)\s+(python|javascript|typescript|rust|go|java|kotlin|swift|ruby|php|c\+\+|c#)\b", re.I), 0.85),

    ("language",
     re.compile(r"\b(python|javascript|typescript|rust|go|java)\s+(?:\d+[\.\d]*)\b", re.I), 0.80),

    ("backend_framework",
     re.compile(r"\b(?:using|with|on)\s+(fastapi|flask|django|express|rails|spring|laravel|nestjs|gin|actix)\b", re.I), 0.85),

    ("frontend_framework",
     re.compile(r"\b(?:using|with)\s+(react|vue|angular|svelte|nextjs|nuxt|gatsby)\b", re.I), 0.85),

    ("database",
     re.compile(r"\b(?:using|with|on)\s+(mongodb|postgres|postgresql|mysql|sqlite|redis|supabase|firebase|dynamodb|cockroachdb)\b", re.I), 0.85),

    ("project_name",
     re.compile(r"\b(?:my (?:project|app|site|tool) is (?:called|named)|working on|building)\s+[\"']?([A-Z][A-Za-z0-9 ]{1,30})[\"']?", re.I), 0.75),

    ("indent_style",
     re.compile(r"\bprefer\s+(tabs|spaces)\b", re.I), 0.90),

    ("deploy_target",
     re.compile(r"\b(?:deploying|hosted|running)\s+(?:on|to|at)\s+(railway|vercel|heroku|aws|gcp|azure|netlify|fly\.io|render)\b", re.I), 0.85),

    ("os",
     re.compile(r"\b(?:on|using)\s+(windows|macos|linux|ubuntu|debian|fedora)\b", re.I), 0.80),

    ("package_manager",
     re.compile(r"\b(?:using|with)\s+(npm|yarn|pnpm|pip|poetry|cargo|go mod)\b", re.I), 0.80),
]

# "remember that X" → store as explicit high-confidence fact
_REMEMBER_PATTERN = re.compile(
    r"\bremember\s+(?:that\s+)?(.{5,100})", re.I
)


def _extract_facts(
    message: str,
    reply:   str,
    session_id: str,
    intent: str,
) -> list[MemoryFact]:
    """
    Auto-extract structured facts from a message+reply pair.
    Returns 0–N MemoryFact objects; never raises.
    """
    facts: list[MemoryFact] = []
    combined = message + " " + reply

    # "Remember that..." explicit instruction
    m = _REMEMBER_PATTERN.search(message)
    if m:
        value = m.group(1).strip().rstrip(".,;")
        facts.append(MemoryFact(
            id=str(uuid.uuid4()), session_id=session_id,
            key="user_note", value=value, confidence=0.95,
            source="explicit", intent=intent,
        ))

    # Pattern-based extraction
    for key, pattern, confidence in _EXTRACT_PATTERNS:
        match = pattern.search(combined)
        if match:
            value = match.group(1).strip()
            # Avoid duplicates
            if not any(f.key == key and f.value.lower() == value.lower() for f in facts):
                facts.append(MemoryFact(
                    id=str(uuid.uuid4()), session_id=session_id,
                    key=key, value=value, confidence=confidence,
                    source="extracted", intent=intent,
                ))

    return facts


# ── Memory store ──────────────────────────────────────────────────────────────

class SessionMemory:
    """Persistent JSON store for cross-session memory facts."""

    def __init__(self, store_path: Optional[str] = None):
        self._path = Path(store_path or _DEFAULT_PATH)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Dict[str, List[MemoryFact]]  — keyed by session_id
        self._store: dict[str, list[MemoryFact]] = {}
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if self._path.exists():
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                for sid, facts in raw.items():
                    self._store[sid] = [MemoryFact.from_dict(f) for f in facts]
                total = sum(len(v) for v in self._store.values())
                logger.debug("SessionMemory loaded: %d facts across %d sessions", total, len(self._store))
        except Exception as exc:
            logger.warning("Could not load session memory: %s", exc)
            self._store = {}

    def _save(self) -> None:
        # Prune if too large
        all_facts = [(sid, f) for sid, facts in self._store.items() for f in facts]
        if len(all_facts) > MAX_FACTS_TOTAL:
            # Keep newest facts sorted by updated_at
            all_facts.sort(key=lambda x: x[1].updated_at, reverse=True)
            all_facts = all_facts[:MAX_FACTS_TOTAL]
            self._store = {}
            for sid, f in all_facts:
                self._store.setdefault(sid, []).append(f)
        try:
            raw = {sid: [f.to_dict() for f in facts] for sid, facts in self._store.items()}
            self._path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.error("Could not save session memory: %s", exc)

    # ── Write ─────────────────────────────────────────────────────────────────

    def store(
        self,
        session_id:  str,
        key:         str,
        value:       str,
        confidence:  float = 0.80,
        source:      str   = "explicit",
        intent:      str   = "normal_chat",
    ) -> MemoryFact:
        """Store a single fact, updating if key already exists for this session."""
        facts = self._store.setdefault(session_id, [])

        # Update existing fact with same key if confidence is >= current
        for existing in facts:
            if existing.key == key:
                if confidence >= existing.confidence:
                    existing.value      = value
                    existing.confidence = confidence
                    existing.updated_at = _now()
                    self._save()
                    return existing
                return existing  # lower-confidence update ignored

        fact = MemoryFact(
            id=str(uuid.uuid4()), session_id=session_id,
            key=key, value=value, confidence=confidence,
            source=source, intent=intent,
        )
        facts.append(fact)
        self._save()
        logger.info("MemoryFact stored: [%s] %s=%s (conf=%.2f)", session_id[:8], key, value, confidence)
        return fact

    def extract_and_store(
        self,
        message:    str,
        reply:      str,
        session_id: str,
        intent:     str,
    ) -> list[MemoryFact]:
        """Auto-extract facts from a turn and persist them. Returns stored facts."""
        extracted = _extract_facts(message, reply, session_id, intent)
        stored: list[MemoryFact] = []
        for f in extracted:
            result = self.store(
                session_id=session_id, key=f.key, value=f.value,
                confidence=f.confidence, source=f.source, intent=f.intent,
            )
            stored.append(result)
        return stored

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_facts(self, session_id: str) -> list[MemoryFact]:
        """Return all facts for a session, sorted by confidence desc."""
        facts = self._store.get(session_id, [])
        return sorted(facts, key=lambda f: f.confidence, reverse=True)

    def get_fact(self, session_id: str, key: str) -> Optional[MemoryFact]:
        """Return the fact for a specific key, or None."""
        for f in self._store.get(session_id, []):
            if f.key == key:
                return f
        return None

    def search_facts(self, session_id: str, query: str) -> list[MemoryFact]:
        """Return facts whose key or value contains the query string."""
        q = query.lower()
        return [
            f for f in self._store.get(session_id, [])
            if q in f.key.lower() or q in f.value.lower()
        ]

    def format_for_prompt(self, session_id: str, max_facts: int = 8) -> str:
        """Return a compact context string for LLM injection."""
        facts = self.get_facts(session_id)[:max_facts]
        if not facts:
            return ""
        lines = ["[Session context from memory]"]
        for f in facts:
            lines.append(f"  {f.key}: {f.value}")
        return "\n".join(lines)

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete_fact(self, session_id: str, fact_id: str) -> bool:
        facts = self._store.get(session_id, [])
        before = len(facts)
        self._store[session_id] = [f for f in facts if f.id != fact_id]
        if len(self._store[session_id]) < before:
            self._save()
            return True
        return False

    def clear_session(self, session_id: str) -> int:
        count = len(self._store.pop(session_id, []))
        if count:
            self._save()
        return count

    def __len__(self) -> int:
        return sum(len(v) for v in self._store.values())


# ── Singleton ─────────────────────────────────────────────────────────────────

_shared: Optional[SessionMemory] = None

def get_memory() -> SessionMemory:
    global _shared
    if _shared is None:
        _shared = SessionMemory()
    return _shared
