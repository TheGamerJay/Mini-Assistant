"""
backend/mini_assistant/phase9/context_injector.py

ContextInjector — assembles Phase 9 self-improvement context prefix.

Called once per chat request, before the prompt is sent to any brain.
Combines:
  1. Learned lessons from LearningBrain (intent-specific, ranked by usefulness)
  2. Long-term facts from CrossSessionMemory (global user/project knowledge)
  3. Auto-promotion: promotes high-confidence Phase 6 session facts to long-term memory

Returns an InjectionResult with the full prefix string + metadata.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class InjectionResult:
    prefix: str               # Full string to prepend to the user message / system prompt
    lessons_used: int = 0
    memory_facts_used: int = 0
    assembly_ms: float = 0.0
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lessons_used":      self.lessons_used,
            "memory_facts_used": self.memory_facts_used,
            "assembly_ms":       round(self.assembly_ms, 2),
            "sources":           self.sources,
        }


class ContextInjector:
    """
    Lightweight assembler — stateless, import-safe, never raises.
    """

    def build(
        self,
        intent: str,
        session_id: str,
        top_lessons: int = 3,
        top_memory: int = 6,
        promote_threshold: float = 0.90,
    ) -> InjectionResult:
        """
        Assemble the Phase 9 context prefix.

        promote_threshold: phase-6 session facts with confidence >= this value
          are auto-promoted to long-term memory.
        """
        t0 = time.perf_counter()
        parts: List[str] = []
        lessons_used = 0
        memory_used = 0
        sources: List[str] = []

        # ── 1. Learned lessons ────────────────────────────────────────────
        try:
            from .learning_brain import get_learning_brain
            lb = get_learning_brain()
            lessons_str = lb.lessons_as_context(intent=intent, top_k=top_lessons)
            if lessons_str:
                parts.append(lessons_str)
                lessons_used = lessons_str.count("\n")  # rough count
                sources.append("learning_brain")
        except Exception as exc:
            logger.debug("ContextInjector: LearningBrain unavailable: %s", exc)

        # ── 2. Long-term memory facts ─────────────────────────────────────
        try:
            from .cross_session_memory import get_cross_memory
            cm = get_cross_memory()
            mem_str = cm.as_context_string(top_k=top_memory)
            if mem_str:
                parts.append(mem_str)
                memory_used = mem_str.count("•")
                sources.append("cross_session_memory")
        except Exception as exc:
            logger.debug("ContextInjector: CrossSessionMemory unavailable: %s", exc)

        # ── 3. Auto-promote high-confidence Phase 6 facts to long-term ────
        try:
            self._promote_session_facts(session_id, threshold=promote_threshold)
        except Exception as exc:
            logger.debug("ContextInjector: promotion failed (non-fatal): %s", exc)

        prefix = "\n\n".join(parts) + "\n\n" if parts else ""

        return InjectionResult(
            prefix=prefix,
            lessons_used=lessons_used,
            memory_facts_used=memory_used,
            assembly_ms=(time.perf_counter() - t0) * 1000,
            sources=sources,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _promote_session_facts(session_id: str, threshold: float = 0.90):
        """
        Scan Phase 6 session memory for high-confidence facts and copy them
        into CrossSessionMemory so they persist beyond the session.
        """
        from mini_assistant.phase6.session_memory import get_memory
        from .cross_session_memory import get_cross_memory

        facts = get_memory().get_facts(session_id)
        cm = get_cross_memory()
        promoted = 0
        for f in facts:
            if f.confidence >= threshold:
                # category heuristic based on key name
                cat = "tech_stack" if f.key in (
                    "language", "framework", "database", "orm", "platform", "runtime"
                ) else "user_pref"
                cm.store(
                    key=f.key,
                    value=f.value,
                    category=cat,
                    confidence=f.confidence,
                    source_session=session_id,
                )
                promoted += 1
        if promoted:
            logger.info(
                "ContextInjector: promoted %d session facts to long-term memory (session %s)",
                promoted, session_id[:8],
            )


# Singleton
_instance: Optional[ContextInjector] = None

def get_injector() -> ContextInjector:
    global _instance
    if _instance is None:
        _instance = ContextInjector()
    return _instance
