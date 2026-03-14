"""
engineering_assistant.py — Phase 6 Engineering Assistant Context Injector
───────────────────────────────────────────────────────────────────────────
When the Planner routes to code_runner or debugging intents, this layer
automatically enriches the LLM call with:

  1. Session memory facts (tech stack, language, framework, project name)
  2. Relevant past reflection lessons (last 3 coding/debug entries)
  3. Project structure summary (from Phase 0 context scanner)
  4. Active mission context (from Phase 4 — if a coding mission is active)

The output is a system_prefix string that gets prepended to the user's
message before the Ollama call. No extra LLM inference — purely context
assembly, runs in < 5 ms.

Phase 6 rules:
  - Only activates for code_runner, debugging, file_analysis intents
  - Gracefully degrades: each source is tried independently; failures are
    logged but never block the main request
  - Does NOT replace or modify the existing coding_brain.py
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_ENGINEERING_INTENTS = {"code_runner", "debugging", "file_analysis", "app_builder"}


# ── Output ────────────────────────────────────────────────────────────────────

@dataclass
class EngineeringContext:
    system_prefix:  str    # formatted context to prepend to the user message
    sources_used:   list[str]
    assembly_ms:    float

    def to_dict(self) -> dict:
        return {
            "system_prefix_len": len(self.system_prefix),
            "sources_used":      self.sources_used,
            "assembly_ms":       self.assembly_ms,
        }


# ── Assembler ─────────────────────────────────────────────────────────────────

class EngineeringAssistant:
    """
    Assembles rich engineering context for code/debug requests.

    Usage:
        asst = EngineeringAssistant()
        ctx  = asst.build(intent="debugging", message="...", session_id="...")
        if ctx.system_prefix:
            enriched_msg = ctx.system_prefix + "\\n\\n" + user_message
    """

    # ── Session memory ────────────────────────────────────────────────────────

    def _get_memory_context(self, session_id: str) -> tuple[str, bool]:
        try:
            from .session_memory import get_memory
            mem = get_memory()
            ctx = mem.format_for_prompt(session_id, max_facts=6)
            return ctx, bool(ctx)
        except Exception as exc:
            logger.debug("EngineeringAssistant: memory failed: %s", exc)
            return "", False

    # ── Reflection lessons ────────────────────────────────────────────────────

    def _get_lesson_context(self, intent: str, message: str) -> tuple[str, bool]:
        try:
            from ..self_improvement.reflection import Reflection
            ref = Reflection()
            # Search for lessons matching message keywords (max 3)
            entries = ref.search_lessons(message[:60])
            # Also include coding/debug lessons if none found by keyword
            if not entries:
                entries = [
                    e for e in ref.recent(20)
                    if e.get("brain") in ("coding", "debug") and e.get("lesson")
                ]
            lessons = [e["lesson"] for e in entries[:3] if e.get("lesson")]
            if not lessons:
                return "", False
            ctx = "[Past lessons]\n" + "\n".join(f"  • {l}" for l in lessons)
            return ctx, True
        except Exception as exc:
            logger.debug("EngineeringAssistant: lessons failed: %s", exc)
            return "", False

    # ── Project scanner ───────────────────────────────────────────────────────

    def _get_project_context(self) -> tuple[str, bool]:
        try:
            from ..scanner import get_context
            ctx = get_context()
            d = ctx.to_dict()
            stack   = d.get("stack", {})
            feat    = d.get("feature_map", [])[:6]
            warns   = d.get("warnings", [])[:2]
            lines = ["[Project structure]"]
            if stack.get("languages"):
                lines.append(f"  Languages: {', '.join(stack['languages'][:5])}")
            if stack.get("frameworks"):
                lines.append(f"  Frameworks: {', '.join(stack['frameworks'][:5])}")
            if feat:
                lines.append(f"  Key features: {', '.join(f['feature'] for f in feat)}")
            if warns:
                lines.append(f"  Warnings: {'; '.join(warns)}")
            return "\n".join(lines), True
        except Exception as exc:
            logger.debug("EngineeringAssistant: scanner failed: %s", exc)
            return "", False

    # ── Mission context ───────────────────────────────────────────────────────

    def _get_mission_context(self, session_id: str) -> tuple[str, bool]:
        try:
            from ..phase4.mission_manager import get_mission_manager
            ctx = get_mission_manager().get_mission_context(session_id)
            if not ctx:
                return "", False
            return "[" + ctx + "]", True
        except Exception as exc:
            logger.debug("EngineeringAssistant: mission failed: %s", exc)
            return "", False

    # ── Public API ────────────────────────────────────────────────────────────

    def build(
        self,
        intent:     str,
        message:    str,
        session_id: str,
    ) -> EngineeringContext:
        """
        Assemble the engineering context prefix for a code/debug request.

        Returns EngineeringContext with system_prefix="" if intent is not
        engineering-relevant or if all sources fail.
        """
        t0 = time.perf_counter()

        if intent not in _ENGINEERING_INTENTS:
            return EngineeringContext(system_prefix="", sources_used=[], assembly_ms=0.0)

        parts:       list[str]  = []
        sources_used: list[str] = []

        # 1. Session memory
        mem_ctx, mem_ok = self._get_memory_context(session_id)
        if mem_ok:
            parts.append(mem_ctx)
            sources_used.append("session_memory")

        # 2. Past reflection lessons
        lesson_ctx, lesson_ok = self._get_lesson_context(intent, message)
        if lesson_ok:
            parts.append(lesson_ctx)
            sources_used.append("reflection_lessons")

        # 3. Project structure (only for file_analysis and app_builder; too noisy for quick fixes)
        if intent in ("file_analysis", "app_builder", "code_runner"):
            proj_ctx, proj_ok = self._get_project_context()
            if proj_ok:
                parts.append(proj_ctx)
                sources_used.append("project_scanner")

        # 4. Active mission
        mission_ctx, mission_ok = self._get_mission_context(session_id)
        if mission_ok:
            parts.append(mission_ctx)
            sources_used.append("mission_context")

        elapsed = round((time.perf_counter() - t0) * 1000, 2)

        if not parts:
            return EngineeringContext(system_prefix="", sources_used=[], assembly_ms=elapsed)

        prefix = "\n\n".join(parts) + "\n\n---\n"
        logger.info(
            "EngineeringAssistant: assembled %d sources in %.1f ms (intent=%s)",
            len(sources_used), elapsed, intent,
        )
        return EngineeringContext(
            system_prefix=prefix,
            sources_used=sources_used,
            assembly_ms=elapsed,
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

_shared: Optional[EngineeringAssistant] = None

def get_engineering_assistant() -> EngineeringAssistant:
    global _shared
    if _shared is None:
        _shared = EngineeringAssistant()
    return _shared
