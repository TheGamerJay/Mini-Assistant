"""
long_term_memory.py – Long-Term Structured Facts
──────────────────────────────────────────────────
Stores persistent user preferences, project settings, and structured facts
as JSON on disk.

Stored facts look like:
    {"preferred_language": "Python", "deployment_platform": "Railway"}

Usage:
    ltm = LongTermMemory()
    ltm.store_fact("preferred_language", "Python")
    lang = ltm.retrieve_fact("preferred_language")   # → "Python"
    ltm.store_fact("project_name", "Mini Assistant")
    all_facts = ltm.all_facts()
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_PATH = os.getenv("LONG_TERM_MEMORY_PATH", "./memory_store/long_term.json")


class LongTermMemory:
    """
    JSON-backed key-value store for structured long-term facts.

    Each entry stores:
        key, value, updated_at, access_count
    """

    def __init__(self, store_path: Optional[str] = None):
        self._path = Path(store_path or _DEFAULT_PATH)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, dict] = {}
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if self._path.exists():
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
                logger.debug("Loaded %d long-term facts from %s", len(self._data), self._path)
        except Exception as exc:
            logger.warning("Could not load long-term memory: %s", exc)
            self._data = {}

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Could not save long-term memory: %s", exc)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def store_fact(self, key: str, value: Any) -> None:
        """Store or update a fact. Value can be any JSON-serialisable object."""
        self._data[key] = {
            "value":        value,
            "updated_at":   datetime.now(timezone.utc).isoformat(),
            "access_count": self._data.get(key, {}).get("access_count", 0),
        }
        self._save()
        logger.debug("Stored fact: %s = %s", key, value)

    def retrieve_fact(self, key: str) -> Optional[Any]:
        """Retrieve a fact by exact key. Returns None if not found."""
        entry = self._data.get(key)
        if entry is None:
            return None
        # Increment access count
        entry["access_count"] = entry.get("access_count", 0) + 1
        self._save()
        return entry["value"]

    def delete_fact(self, key: str) -> bool:
        """Delete a fact. Returns True if it existed."""
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def update_fact(self, key: str, value: Any) -> None:
        """Alias for store_fact for clarity."""
        self.store_fact(key, value)

    # ── Search / listing ──────────────────────────────────────────────────────

    def all_facts(self) -> dict[str, Any]:
        """Return all facts as a plain {key: value} dict."""
        return {k: v["value"] for k, v in self._data.items()}

    def search_facts(self, query: str) -> dict[str, Any]:
        """
        Simple substring search across keys and string values.
        Returns matching {key: value} pairs.
        """
        q = query.lower()
        results: dict[str, Any] = {}
        for key, entry in self._data.items():
            val = entry["value"]
            if q in key.lower() or (isinstance(val, str) and q in val.lower()):
                results[key] = val
        return results

    def format_for_prompt(self) -> str:
        """Return all facts as a human-readable block for LLM injection."""
        if not self._data:
            return ""
        lines = ["User preferences and known facts:"]
        for key, entry in self._data.items():
            lines.append(f"  {key}: {entry['value']}")
        return "\n".join(lines)

    # ── Convenience helpers ───────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style get with optional default."""
        val = self.retrieve_fact(key)
        return val if val is not None else default

    def set(self, key: str, value: Any) -> None:
        """Dict-style set."""
        self.store_fact(key, value)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"LongTermMemory(facts={len(self._data)}, path={self._path})"
