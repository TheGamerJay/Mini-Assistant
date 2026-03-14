"""
backend/mini_assistant/phase9/cross_session_memory.py

CrossSessionMemory — persistent long-term memory that survives session resets.

Unlike Phase 6 SessionMemory (per-session, ephemeral), CrossSessionMemory
stores facts that are globally true about the user / project and should be
recalled in every new conversation.

Storage: JSON file at memory_store/cross_session_memory.json
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_STORE_PATH = Path(__file__).parent.parent.parent / "memory_store" / "cross_session_memory.json"

# Maximum facts to keep (evict oldest low-confidence facts first)
_MAX_FACTS = 200


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class LongTermFact:
    id: str
    key: str
    value: str
    category: str           # user_pref | project | tech_stack | lesson | explicit
    confidence: float = 0.80
    recall_count: int = 0
    reinforced_count: int = 0
    source_session: str = "global"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_recalled: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def score(self) -> float:
        """Rank score for retrieval (confidence + recall bonus)."""
        return self.confidence + min(self.recall_count * 0.02, 0.2)


# ---------------------------------------------------------------------------
# CrossSessionMemory
# ---------------------------------------------------------------------------

class CrossSessionMemory:
    def __init__(self, store_path: Path = _STORE_PATH):
        self._store_path = store_path
        self._facts: Dict[str, LongTermFact] = {}
        self._load()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store(
        self,
        key: str,
        value: str,
        category: str = "explicit",
        confidence: float = 0.85,
        source_session: str = "global",
    ) -> LongTermFact:
        """Store or reinforce a long-term fact."""
        key_norm = key.strip().lower()

        # Reinforce if same key already exists
        for fact in self._facts.values():
            if fact.key.lower() == key_norm:
                fact.value = value
                fact.confidence = min(max(fact.confidence, confidence), 0.99)
                fact.reinforced_count += 1
                self._save()
                return fact

        fact = LongTermFact(
            id=str(uuid.uuid4())[:8],
            key=key.strip(),
            value=value.strip(),
            category=category,
            confidence=confidence,
            source_session=source_session,
        )
        self._facts[fact.id] = fact
        self._evict_if_needed()
        self._save()
        logger.info("CrossSessionMemory: stored [%s] %s=%s", fact.category, key, value[:60])
        return fact

    def delete(self, fact_id: str) -> bool:
        if fact_id in self._facts:
            del self._facts[fact_id]
            self._save()
            return True
        return False

    def clear(self) -> int:
        count = len(self._facts)
        self._facts.clear()
        self._save()
        return count

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_all(self, category: Optional[str] = None) -> List[LongTermFact]:
        facts = list(self._facts.values())
        if category:
            facts = [f for f in facts if f.category == category]
        return sorted(facts, key=lambda f: f.score, reverse=True)

    def search(self, query: str, top_k: int = 10) -> List[LongTermFact]:
        """Simple keyword search across key + value."""
        q = query.lower()
        hits = [
            f for f in self._facts.values()
            if q in f.key.lower() or q in f.value.lower()
        ]
        for h in hits:
            h.recall_count += 1
            h.last_recalled = datetime.now(timezone.utc).isoformat()
        self._save()
        return sorted(hits, key=lambda f: f.score, reverse=True)[:top_k]

    def as_context_string(self, top_k: int = 8) -> str:
        """Format top facts as a context prefix for injection into prompts."""
        facts = self.get_all()[:top_k]
        if not facts:
            return ""
        lines = ["[LONG-TERM MEMORY — user/project facts recalled across sessions]"]
        for f in facts:
            lines.append(f"• {f.key}: {f.value}")
        return "\n".join(lines)

    def stats(self) -> dict:
        by_cat: Dict[str, int] = {}
        for f in self._facts.values():
            by_cat[f.category] = by_cat.get(f.category, 0) + 1
        return {
            "total": len(self._facts),
            "by_category": by_cat,
            "top_facts": [f.to_dict() for f in self.get_all()[:5]],
        }

    # ------------------------------------------------------------------
    # Eviction + Persistence
    # ------------------------------------------------------------------

    def _evict_if_needed(self):
        if len(self._facts) <= _MAX_FACTS:
            return
        # Drop lowest-scoring facts until under limit
        sorted_facts = sorted(self._facts.values(), key=lambda f: f.score)
        to_remove = len(self._facts) - _MAX_FACTS
        for f in sorted_facts[:to_remove]:
            del self._facts[f.id]

    def _save(self):
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "facts":    {k: asdict(v) for k, v in self._facts.items()},
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            self._store_path.write_text(json.dumps(data, indent=2))
        except Exception as exc:
            logger.warning("CrossSessionMemory: save failed: %s", exc)

    def _load(self):
        try:
            if not self._store_path.exists():
                return
            data = json.loads(self._store_path.read_text())
            for fid, fd in data.get("facts", {}).items():
                self._facts[fid] = LongTermFact(**fd)
            logger.info("CrossSessionMemory: loaded %d facts", len(self._facts))
        except Exception as exc:
            logger.warning("CrossSessionMemory: load failed (fresh start): %s", exc)


# Singleton
_instance: Optional[CrossSessionMemory] = None

def get_cross_memory() -> CrossSessionMemory:
    global _instance
    if _instance is None:
        _instance = CrossSessionMemory()
    return _instance
