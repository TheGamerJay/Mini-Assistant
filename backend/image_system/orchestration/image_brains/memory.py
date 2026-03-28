"""
Memory Brain — manages session context across edit steps and sessions.

Responsibility: context storage and retrieval only.
"""
from __future__ import annotations
import logging
from collections import OrderedDict
from ..image_models import SessionContext

logger = logging.getLogger(__name__)

_MAX_SESSIONS = 64


class MemoryBrain:
    """
    Maintains per-session caches:
      - GPT-4o character description (for T3 consistency)
      - preserve_elements list (from vision scan)

    All state lives here; brains and CEO read/write via this interface.
    """

    def __init__(self) -> None:
        self._descriptions: OrderedDict[str, str] = OrderedDict()
        self._preserve_els: OrderedDict[str, list[str]] = OrderedDict()

    def get_context(self, session_id: str) -> SessionContext:
        return SessionContext(
            session_id=session_id,
            cached_description=self._descriptions.get(session_id),
            preserve_elements=list(self._preserve_els.get(session_id, [])),
        )

    def update_description(self, session_id: str, description: str) -> None:
        if description:
            self._evict_if_full(self._descriptions)
            self._descriptions[session_id] = description

    def update_preserve_elements(self, session_id: str, elements: list[str]) -> None:
        if elements:
            self._evict_if_full(self._preserve_els)
            self._preserve_els[session_id] = elements

    def merge_scan(self, ctx: SessionContext, session_id: str) -> None:
        """Write scan results back into persistent cache."""
        if ctx.cached_description:
            self.update_description(session_id, ctx.cached_description)
        if ctx.preserve_elements:
            self.update_preserve_elements(session_id, ctx.preserve_elements)

    def _evict_if_full(self, d: OrderedDict) -> None:
        while len(d) >= _MAX_SESSIONS:
            d.popitem(last=False)
