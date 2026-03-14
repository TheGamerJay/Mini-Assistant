"""
backend/mini_assistant/phase9/learning_brain.py

LearningBrain — cross-session pattern extractor and lesson library.

Consumes:
  - ReflectionRecord objects from Phase 3
  - CriticResult objects from Phase 1
  - Explicit lesson strings from any pipeline stage

Produces:
  - Ranked lesson library (most useful first)
  - Per-intent pattern stats (success_rate, avg quality)
  - Global improvement suggestions
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_STORE_PATH = Path(__file__).parent.parent.parent / "memory_store" / "learning_patterns.json"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Lesson:
    id: str
    text: str
    intent: str
    source: str               # reflection | critic | explicit | tool_result
    confidence: float = 0.75
    times_applied: int = 0
    times_helped: int = 0
    times_hurt: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_used: Optional[str] = None

    @property
    def usefulness(self) -> float:
        """Score in [0, 1] — higher is more useful."""
        total = self.times_helped + self.times_hurt
        if total == 0:
            return self.confidence
        return self.times_helped / total

    def to_dict(self) -> dict:
        d = asdict(self)
        d["usefulness"] = round(self.usefulness, 3)
        return d


@dataclass
class IntentPattern:
    intent: str
    total_requests: int = 0
    successful: int = 0
    quality_sum: float = 0.0
    common_issues: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return (self.successful / self.total_requests) if self.total_requests else 0.0

    @property
    def avg_quality(self) -> float:
        return (self.quality_sum / self.total_requests) if self.total_requests else 0.0

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "total_requests": self.total_requests,
            "successful": self.successful,
            "success_rate": round(self.success_rate, 3),
            "avg_quality": round(self.avg_quality, 3),
            "common_issues": self.common_issues[-5:],
        }


# ---------------------------------------------------------------------------
# LearningBrain
# ---------------------------------------------------------------------------

class LearningBrain:
    def __init__(self, store_path: Path = _STORE_PATH):
        self._store_path = store_path
        self._lessons: Dict[str, Lesson] = {}
        self._patterns: Dict[str, IntentPattern] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_reflection(
        self,
        lesson: str,
        intent: str,
        quality_score: float = 0.7,
        success: bool = True,
        source: str = "reflection",
    ) -> Optional[Lesson]:
        """Ingest a lesson string from the reflection layer or critic."""
        if not lesson or len(lesson.strip()) < 10:
            return None

        lesson_text = lesson.strip()

        # Dedup: skip if very similar to an existing lesson for same intent
        for existing in self._lessons.values():
            if existing.intent == intent and self._similarity(existing.text, lesson_text) > 0.8:
                # Reinforce existing
                existing.times_helped += 1 if success else 0
                existing.times_applied += 1
                self._save()
                return existing

        import uuid
        new_lesson = Lesson(
            id=str(uuid.uuid4())[:8],
            text=lesson_text,
            intent=intent,
            source=source,
            confidence=min(quality_score, 0.95),
        )
        self._lessons[new_lesson.id] = new_lesson

        # Update pattern stats
        pat = self._patterns.setdefault(intent, IntentPattern(intent=intent))
        pat.total_requests += 1
        if success:
            pat.successful += 1
        pat.quality_sum += quality_score

        self._save()
        logger.info("LearningBrain: new lesson [%s/%s] %.0f%%", intent, new_lesson.id, quality_score * 100)
        return new_lesson

    def record_issue(self, intent: str, issue: str):
        """Record a common issue for an intent (used by critic)."""
        pat = self._patterns.setdefault(intent, IntentPattern(intent=intent))
        pat.total_requests += 1
        if issue and issue not in pat.common_issues:
            pat.common_issues.append(issue)
        self._save()

    def mark_lesson_helped(self, lesson_id: str):
        if lesson_id in self._lessons:
            self._lessons[lesson_id].times_helped += 1
            self._lessons[lesson_id].last_used = datetime.now(timezone.utc).isoformat()
            self._save()

    def mark_lesson_hurt(self, lesson_id: str):
        if lesson_id in self._lessons:
            self._lessons[lesson_id].times_hurt += 1
            self._save()

    def get_lessons(
        self,
        intent: Optional[str] = None,
        top_k: int = 5,
        min_usefulness: float = 0.4,
    ) -> List[Lesson]:
        """Return the most useful lessons for a given intent."""
        pool = list(self._lessons.values())
        if intent:
            # Prefer intent-specific, but fall back to general
            specific = [l for l in pool if l.intent == intent]
            general  = [l for l in pool if l.intent in ("chat", "general", "normal_chat") and l not in specific]
            pool = specific + general

        pool = [l for l in pool if l.usefulness >= min_usefulness]
        pool.sort(key=lambda l: l.usefulness, reverse=True)
        return pool[:top_k]

    def get_patterns(self) -> dict:
        return {
            "patterns": {k: v.to_dict() for k, v in self._patterns.items()},
            "lessons_total": len(self._lessons),
            "top_lessons": [l.to_dict() for l in self.get_lessons(top_k=10)],
        }

    def lessons_as_context(self, intent: Optional[str] = None, top_k: int = 3) -> str:
        """Format top lessons as a system context prefix string."""
        lessons = self.get_lessons(intent=intent, top_k=top_k)
        if not lessons:
            return ""
        lines = ["[LEARNED LESSONS — apply these based on past experience]"]
        for i, l in enumerate(lessons, 1):
            lines.append(f"{i}. ({l.intent}) {l.text}")
        return "\n".join(lines)

    def delete_lesson(self, lesson_id: str) -> bool:
        if lesson_id in self._lessons:
            del self._lessons[lesson_id]
            self._save()
            return True
        return False

    def clear_all(self):
        self._lessons.clear()
        self._patterns.clear()
        self._save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self):
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "lessons":  {k: asdict(v) for k, v in self._lessons.items()},
                "patterns": {k: asdict(v) for k, v in self._patterns.items()},
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            self._store_path.write_text(json.dumps(data, indent=2))
        except Exception as exc:
            logger.warning("LearningBrain: save failed: %s", exc)

    def _load(self):
        try:
            if not self._store_path.exists():
                return
            data = json.loads(self._store_path.read_text())
            for lid, ld in data.get("lessons", {}).items():
                self._lessons[lid] = Lesson(**{k: v for k, v in ld.items() if k != "usefulness"})
            for iid, pd in data.get("patterns", {}).items():
                pd_clean = {k: v for k, v in pd.items() if k not in ("success_rate", "avg_quality")}
                self._patterns[iid] = IntentPattern(**pd_clean)
            logger.info("LearningBrain: loaded %d lessons, %d patterns", len(self._lessons), len(self._patterns))
        except Exception as exc:
            logger.warning("LearningBrain: load failed (fresh start): %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        """Rough character n-gram overlap similarity."""
        def ngrams(s, n=3):
            s = s.lower()
            return set(s[i:i+n] for i in range(len(s) - n + 1))
        na, nb = ngrams(a), ngrams(b)
        if not na or not nb:
            return 0.0
        return len(na & nb) / len(na | nb)


# Singleton
_instance: Optional[LearningBrain] = None

def get_learning_brain() -> LearningBrain:
    global _instance
    if _instance is None:
        _instance = LearningBrain()
    return _instance
