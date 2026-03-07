"""
main.py – MiniAssistant Orchestrator
──────────────────────────────────────
The single public entry point for the multi-brain system.

Flow:
  1. Route request  → router.route()
  2. Pre-fetch tools (search, memory) if needed
  3. Dispatch to the correct brain
  4. Optionally execute generated code
  5. Return a structured AssistantResponse

Example:
    assistant = MiniAssistant()
    response  = assistant.chat("Write a quicksort in Python and run it.")
    print(response.text)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .router import route, RouteResult
from .brains.coder    import CoderBrain
from .brains.vision   import VisionBrain
from .brains.research import ResearchBrain
from .brains.fast     import FastBrain
from .tools.search    import web_search
from .tools.image_gen import generate_image
from .tools.code_exec import execute_python
from .tools.computer  import take_screenshot
from .memory.vector_store import VectorStore

logger = logging.getLogger(__name__)


# ─── Response model ───────────────────────────────────────────────────────────

@dataclass
class AssistantResponse:
    text: str                          # Main LLM response
    brain: str = ""                    # Which brain handled this
    task: str  = ""                    # Fine-grained task label
    model: str = ""                    # Model used
    routing_method: str = ""          # "keyword" | "llm" | "fallback"
    tool_outputs: dict = field(default_factory=dict)   # Raw tool results
    image_b64: Optional[str] = None   # Generated/captured image (base64)
    code_result: Optional[dict] = None  # Code execution output
    sources: list[dict] = field(default_factory=list)  # Search / memory sources


# ─── Brain registry ───────────────────────────────────────────────────────────

class MiniAssistant:
    """
    Multi-brain AI assistant.

    All brains are lazily instantiated on first use.
    The vector store is shared across all sessions.
    """

    def __init__(self, store_path: Optional[str] = None):
        self._brains: dict[str, Any] = {}
        self._store  = VectorStore(store_path)

    # ── Lazy brain factory ────────────────────────────────────────────────────

    def _get_brain(self, name: str):
        if name not in self._brains:
            brain_map = {
                "coding":   CoderBrain,
                "coder":    CoderBrain,
                "vision":   VisionBrain,
                "research": ResearchBrain,
                "fast":     FastBrain,
                "search":   FastBrain,    # search pre-fetches, fast brain responds
                "image_gen":FastBrain,    # image gen is a tool; fast brain narrates
                "computer": FastBrain,    # computer actions + fast narration
                "memory":   ResearchBrain,# memory RAG → research brain summarises
            }
            cls = brain_map.get(name, FastBrain)
            self._brains[name] = cls()
            logger.debug("Instantiated %s brain (%s)", name, cls.__name__)
        return self._brains[name]

    # ── Tool pre-execution ────────────────────────────────────────────────────

    def _run_tools(self, route_result: RouteResult, message: str) -> dict:
        """Execute tools before calling the brain."""
        outputs: dict = {}

        if route_result.brain == "search":
            results = web_search(message)
            outputs["search"] = results

        elif route_result.brain == "memory":
            context = self._store.format_context(message)
            outputs["memory"] = context

        elif route_result.task == "write_code" and "run" in message.lower():
            # Will execute after the brain generates code
            outputs["_auto_execute"] = True

        elif route_result.brain == "computer" and "screenshot" in message.lower():
            shot = take_screenshot()
            outputs["screenshot"] = shot

        return outputs

    # ── Code auto-execution ───────────────────────────────────────────────────

    def _maybe_execute_code(
        self,
        response_text: str,
        auto_execute: bool,
    ) -> Optional[dict]:
        """Extract and run the first Python block from a response if requested."""
        if not auto_execute:
            return None

        import re
        match = re.search(r"```python\n(.*?)```", response_text, re.DOTALL)
        if not match:
            return None

        code    = match.group(1)
        result  = execute_python(code)
        logger.info(
            "Auto-executed code: success=%s returncode=%d",
            result["success"], result["returncode"],
        )
        return result

    # ── Main entry point ──────────────────────────────────────────────────────

    def chat(
        self,
        message: str,
        images: Optional[list[str]] = None,
        auto_execute_code: bool = False,
    ) -> AssistantResponse:
        """
        Process a user message through the multi-brain pipeline.

        Args:
            message:           User's text message.
            images:            Optional list of image file paths or base64 strings.
            auto_execute_code: If True, automatically run generated Python code.

        Returns:
            AssistantResponse with text, metadata, and tool outputs.
        """
        route_result = route(message, images)
        tool_outputs = self._run_tools(route_result, message)
        brain        = self._get_brain(route_result.brain)

        # Build tool result list for injection into the brain
        tool_results: list[dict] = []
        sources: list[dict]      = []
        image_b64: Optional[str] = None

        if "search" in tool_outputs:
            results = tool_outputs["search"]
            sources = results
            formatted = "\n\n".join(
                f"[{r['title']}]({r['url']})\n{r['body']}" for r in results
            )
            tool_results.append({"tool": "web_search", "result": formatted})

        if "memory" in tool_outputs and tool_outputs["memory"]:
            tool_results.append({"tool": "memory", "result": tool_outputs["memory"]})

        if "screenshot" in tool_outputs:
            shot = tool_outputs["screenshot"]
            if shot.get("success"):
                image_b64 = shot["image_b64"]

        # Handle image generation separately (it's a tool, not a brain)
        if route_result.brain == "image_gen":
            gen = generate_image(message)
            if gen["success"]:
                image_b64 = gen["image_b64"]
                text = f"Image generated successfully for prompt: {message}"
            else:
                text = f"Image generation failed: {gen.get('error', 'Unknown error')}"
            return AssistantResponse(
                text=text,
                brain="image_gen",
                task=route_result.task,
                model=route_result.model,
                routing_method=route_result.routing_method,
                tool_outputs=gen,
                image_b64=image_b64,
            )

        # Call the selected brain
        response_text = brain.respond(
            message,
            tool_results=tool_results if tool_results else None,
            images=images,
        )

        # Auto-execute generated Python if requested
        code_result: Optional[dict] = None
        auto_exec = tool_outputs.get("_auto_execute", False) or auto_execute_code
        if route_result.brain in ("coding", "coder") and auto_exec:
            code_result = self._maybe_execute_code(response_text, auto_exec)
            if code_result:
                # Append execution output to response
                out = code_result.get("stdout", "")
                err = code_result.get("stderr", "")
                response_text += f"\n\n**Execution output:**\n```\n{out or err}\n```"

        return AssistantResponse(
            text=response_text,
            brain=route_result.brain,
            task=route_result.task,
            model=route_result.model,
            routing_method=route_result.routing_method,
            tool_outputs=tool_outputs,
            image_b64=image_b64,
            code_result=code_result,
            sources=sources,
        )

    # ── Memory management ─────────────────────────────────────────────────────

    def learn_file(self, file_path: str) -> dict:
        """Ingest a file into the vector store."""
        chunks = self._store.ingest_file(file_path)
        return {"success": True, "chunks": chunks, "file": file_path}

    def learn_text(self, text: str, source: str = "manual") -> dict:
        """Ingest raw text into the vector store."""
        chunks = self._store.ingest_text(text, source=source)
        return {"success": True, "chunks": chunks, "source": source}

    def memory_search(self, query: str, top_k: int = 5) -> list[dict]:
        """Direct semantic search against the vector store."""
        return self._store.search(query, top_k=top_k)

    @property
    def memory_doc_count(self) -> int:
        return self._store.doc_count
