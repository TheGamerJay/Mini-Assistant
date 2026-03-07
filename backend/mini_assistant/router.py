"""
router.py – Modular Brain Router
──────────────────────────────────
Plug-in routing architecture:

  1. Matchers — small, single-responsibility classes registered via @register_matcher.
     Each matcher receives the message + context and returns a RouteResult or None.
     Matchers are checked in priority order (lower number = checked first).

  2. LLM Classifier — fallback if no matcher fires.

Adding a new routing rule requires only:
    @register_matcher(priority=25)
    class MyMatcher(BaseMatcher):
        def match(self, ctx: RoutingContext) -> RouteResult | None: ...

No changes to any other file needed.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import ollama

from .config import MODELS, TASK_TYPES, OLLAMA_HOST

logger = logging.getLogger(__name__)


# ─── Data types ───────────────────────────────────────────────────────────────

@dataclass
class RoutingContext:
    """Everything a matcher can inspect to make a routing decision."""
    message: str
    message_lower: str
    images: list = field(default_factory=list)
    history: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class RouteResult:
    brain: str
    task: str
    model: str
    context: dict = field(default_factory=dict)
    routing_method: str = "keyword"


# ─── Base matcher interface ───────────────────────────────────────────────────

class BaseMatcher(ABC):
    """
    Subclass this and decorate with @register_matcher(priority=N) to add a rule.
    Lower priority numbers are tried first.
    """
    priority: int = 50

    @abstractmethod
    def match(self, ctx: RoutingContext) -> Optional[RouteResult]:
        """Return a RouteResult if this matcher fires, else None."""
        ...


# ─── Matcher registry ─────────────────────────────────────────────────────────

_MATCHERS: list = []


def register_matcher(priority: int = 50):
    """
    Class decorator that registers a matcher at the given priority.

    Usage:
        @register_matcher(priority=10)
        class MyMatcher(BaseMatcher):
            def match(self, ctx): ...
    """
    def decorator(cls):
        instance = cls()
        instance.priority = priority
        _MATCHERS.append(instance)
        _MATCHERS.sort(key=lambda m: m.priority)
        return cls
    return decorator


def get_registered_matchers() -> list:
    """Return the current list of registered matchers (sorted by priority)."""
    return list(_MATCHERS)


# ─── Built-in matchers ────────────────────────────────────────────────────────

@register_matcher(priority=1)
class ImageAttachmentMatcher(BaseMatcher):
    """Any request with an image goes straight to the vision brain."""
    def match(self, ctx: RoutingContext) -> Optional[RouteResult]:
        if ctx.images:
            return RouteResult(
                brain="vision", task="describe_image",
                model=MODELS["vision"], context={"images": ctx.images},
                routing_method="keyword",
            )
        return None


@register_matcher(priority=10)
class ImageGenerationMatcher(BaseMatcher):
    _re = re.compile(
        r"\b(generate|create|draw|make|paint|render|produce)\b.{0,30}"
        r"\b(image|picture|photo|art|illustration|logo|icon|wallpaper)\b",
        re.IGNORECASE,
    )
    def match(self, ctx: RoutingContext) -> Optional[RouteResult]:
        if self._re.search(ctx.message):
            return RouteResult("image_gen", "generate_image", MODELS["fast"], routing_method="keyword")
        return None


@register_matcher(priority=15)
class ComputerControlMatcher(BaseMatcher):
    _re = re.compile(
        r"\b(click|press|type into|open app|launch|close window|move mouse"
        r"|drag|scroll|take screenshot|capture screen|automate|hotkey)\b",
        re.IGNORECASE,
    )
    def match(self, ctx: RoutingContext) -> Optional[RouteResult]:
        if self._re.search(ctx.message):
            return RouteResult("computer", "automate", MODELS["fast"], routing_method="keyword")
        return None


@register_matcher(priority=20)
class CodingMatcher(BaseMatcher):
    _debug   = re.compile(r"\b(debug|fix|error|bug|traceback|exception|not working|broken|fails|crash)\b", re.IGNORECASE)
    _explain = re.compile(r"\b(explain|what does|how does|understand|walk me through)\b.{0,40}\b(code|function|class|snippet|method)\b", re.IGNORECASE)
    _write   = re.compile(r"\b(write|create|build|implement|code|program|function|class|script|algorithm|refactor|optimise|optimize)\b", re.IGNORECASE)

    def match(self, ctx: RoutingContext) -> Optional[RouteResult]:
        m = ctx.message
        if self._debug.search(m):
            return RouteResult("coding", "debug_code",   MODELS["coder"], routing_method="keyword")
        if self._explain.search(m):
            return RouteResult("coding", "explain_code", MODELS["coder"], routing_method="keyword")
        if self._write.search(m):
            return RouteResult("coding", "write_code",   MODELS["coder"], routing_method="keyword")
        return None


@register_matcher(priority=25)
class WebSearchMatcher(BaseMatcher):
    _re = re.compile(
        r"\b(search|look up|find|google|latest news|current|today|recent"
        r"|what is the|who is|when did|how many|stock price|weather)\b",
        re.IGNORECASE,
    )
    def match(self, ctx: RoutingContext) -> Optional[RouteResult]:
        if self._re.search(ctx.message):
            return RouteResult("search", "web_search", MODELS["fast"], routing_method="keyword")
        return None


@register_matcher(priority=30)
class MemoryMatcher(BaseMatcher):
    _learn = re.compile(r"\b(learn|read|ingest|upload|remember|store|index)\b.{0,30}\b(file|document|pdf|txt|doc|note)\b", re.IGNORECASE)
    _query = re.compile(r"\b(what did i|recall|remember|from the document|from the file|in my notes|based on|according to)\b", re.IGNORECASE)

    def match(self, ctx: RoutingContext) -> Optional[RouteResult]:
        if self._learn.search(ctx.message):
            return RouteResult("memory", "learn_doc",    MODELS["research"], routing_method="keyword")
        if self._query.search(ctx.message):
            return RouteResult("memory", "query_memory", MODELS["research"], routing_method="keyword")
        return None


@register_matcher(priority=35)
class ResearchMatcher(BaseMatcher):
    _re = re.compile(
        r"\b(analyze|analyse|research|deep dive|compare|evaluate|investigate"
        r"|pros and cons|comprehensive|detailed report|explain in depth)\b",
        re.IGNORECASE,
    )
    def match(self, ctx: RoutingContext) -> Optional[RouteResult]:
        if self._re.search(ctx.message):
            return RouteResult("research", "deep_analysis", MODELS["research"], routing_method="keyword")
        return None


@register_matcher(priority=90)
class FastCatchallMatcher(BaseMatcher):
    """Low-priority catch-all for short conversational messages (< 60 chars)."""
    def match(self, ctx: RoutingContext) -> Optional[RouteResult]:
        if len(ctx.message) < 60:
            return RouteResult("fast", "quick_answer", MODELS["fast"], routing_method="keyword")
        return None


# ─── LLM Classifier fallback ──────────────────────────────────────────────────

_ROUTER_SYSTEM = (
    "You are a task router for a multi-brain AI assistant.\n"
    "Classify the user's request into exactly ONE of these categories:\n"
    f"{', '.join(TASK_TYPES)}\n\n"
    "Respond with ONLY valid JSON:\n"
    '{"brain": "<brain>", "task": "<short_task_label>", "reason": "<one sentence>"}\n\n'
    "Brain options: coding, vision, research, search, image_gen, computer, memory, fast"
)


def _llm_classify(ctx: RoutingContext) -> RouteResult:
    router_model = MODELS["router"]
    try:
        client = ollama.Client(host=OLLAMA_HOST)
        resp = client.chat(
            model=router_model,
            messages=[
                {"role": "system", "content": _ROUTER_SYSTEM},
                {"role": "user",   "content": ctx.message},
            ],
            options={"temperature": 0.0},
        )
        raw  = resp["message"]["content"].strip()
        raw  = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        data = json.loads(raw)
        brain = data.get("brain", "fast")
        task  = data.get("task",  "general")
        return RouteResult(brain=brain, task=task, model=MODELS.get(brain, MODELS["fallback"]), routing_method="llm")
    except Exception as exc:
        logger.warning("Router LLM failed: %s — using fast fallback.", exc)
        return RouteResult("fast", "general", MODELS["fallback"], routing_method="fallback")


# ─── Public API ───────────────────────────────────────────────────────────────

def route(
    message: str,
    images: Optional[list] = None,
    history: Optional[list] = None,
    metadata: Optional[dict] = None,
) -> RouteResult:
    """
    Classify a user request and return the best RouteResult.

    Matchers are checked in priority order. First match wins.
    If no matcher fires, the LLM router classifies the request.

    Extend routing by creating a new BaseMatcher subclass and decorating
    it with @register_matcher(priority=N) — no other changes required.
    """
    ctx = RoutingContext(
        message=message,
        message_lower=message.lower(),
        images=images or [],
        history=history or [],
        metadata=metadata or {},
    )

    for matcher in _MATCHERS:
        try:
            result = matcher.match(ctx)
            if result is not None:
                logger.info(
                    "Routed by %s → brain=%s task=%s model=%s",
                    type(matcher).__name__, result.brain, result.task, result.model,
                )
                return result
        except Exception as exc:
            logger.warning("Matcher %s raised: %s", type(matcher).__name__, exc)

    result = _llm_classify(ctx)
    logger.info("Routed by LLM → brain=%s task=%s", result.brain, result.task)
    return result
