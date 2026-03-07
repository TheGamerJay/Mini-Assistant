"""
main.py – MiniAssistant Orchestrator
──────────────────────────────────────
Full autonomous pipeline:

  User Request
    → Router       (route to brain + task type)
    → Planner      (decompose into steps)
    → Executor     (run tools + brains per step)
    → RepairLoop   (test code → fix → retry, up to MAX_RETRIES)
    → Reviewer     (quality gate)
    → Reflection   (log lesson learned)
    → SolutionMem  (store successful patterns)
    → Final Response

All components are lazily initialised.
The assistant can be used in three modes:
  - Simple chat   → assistant.chat(message)
  - Full pipeline → assistant.chat(message, use_planner=True)
  - Direct brain  → assistant.ask_brain("coding", "Write X")

Memory layers:
  - Conversation: short-term turn buffer
  - Vector store: document / RAG memory
  - Long-term:    structured facts (preferences, project settings)
  - Solutions:    successful patterns for reuse

Example:
    assistant = MiniAssistant()
    response  = assistant.chat("Write a binary search and test it.")
    print(response.text)
    print(f"Tests passed: {response.tests_passed}")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .router   import route, RouteResult
from .planner  import plan as make_plan, Plan
from .executor import Executor, ExecutionResult

from .brains.coder    import CoderBrain
from .brains.vision   import VisionBrain
from .brains.research import ResearchBrain
from .brains.fast     import FastBrain

from .tools.search    import web_search
from .tools.image_gen import generate_image
from .tools.code_exec import execute_python
from .tools.computer  import take_screenshot

from .memory.vector_store        import VectorStore
from .memory.conversation_memory import ConversationMemory
from .memory.long_term_memory    import LongTermMemory
from .memory.solution_memory     import SolutionMemory

from .self_improvement.repair_loop import RepairLoop, RepairResult
from .self_improvement.reviewer    import Reviewer
from .self_improvement.reflection  import Reflection
from .self_improvement.tester      import Tester

logger = logging.getLogger(__name__)


# ─── Response model ───────────────────────────────────────────────────────────

@dataclass
class AssistantResponse:
    """Structured response returned from every chat() call."""
    text: str                                    # Main response text
    brain: str       = ""                        # Brain that handled the request
    task: str        = ""                        # Fine-grained task label
    model: str       = ""                        # Ollama model used
    routing_method: str = ""                     # "keyword" | "llm" | "fallback"

    # Self-improvement
    tests_passed: Optional[bool] = None          # None = no tests run
    tests_run: int               = 0
    review_passed: Optional[bool] = None
    review_score: float          = 0.0
    repair_attempts: int         = 1

    # Tool outputs
    tool_outputs: dict = field(default_factory=dict)
    image_b64: Optional[str]    = None
    code_result: Optional[dict] = None
    sources: list[dict]         = field(default_factory=list)

    # Planner / executor
    plan: Optional[object]   = None
    execution: Optional[object] = None


# ─── Main assistant ───────────────────────────────────────────────────────────

class MiniAssistant:
    """
    Multi-brain AI assistant with planning, execution, and self-improvement.

    All components are lazily instantiated on first use.
    """

    def __init__(self, store_path: Optional[str] = None):
        # ── Memory layers ─────────────────────────────────────────────────────
        self._vector_store   = VectorStore(store_path)
        self._conversation   = ConversationMemory(max_turns=30)
        self._long_term      = LongTermMemory()
        self._solutions      = SolutionMemory()

        # ── Self-improvement ──────────────────────────────────────────────────
        self._reflection     = Reflection()
        self._reviewer       = Reviewer()
        self._tester         = Tester()

        # ── Lazy registries ───────────────────────────────────────────────────
        self._brains: dict[str, Any] = {}
        self._executor: Optional[Executor] = None
        self._repair: Optional[RepairLoop]  = None

    # ── Lazy factories ────────────────────────────────────────────────────────

    def _get_brain(self, name: str):
        if name not in self._brains:
            brain_map = {
                "coding":    CoderBrain,
                "coder":     CoderBrain,
                "vision":    VisionBrain,
                "research":  ResearchBrain,
                "fast":      FastBrain,
                "search":    FastBrain,
                "image_gen": FastBrain,
                "computer":  FastBrain,
                "memory":    ResearchBrain,
            }
            cls = brain_map.get(name, FastBrain)
            self._brains[name] = cls()
            logger.debug("Instantiated %s brain.", cls.__name__)
        return self._brains[name]

    def _get_executor(self) -> Executor:
        if self._executor is None:
            self._executor = Executor(self)
        return self._executor

    def _get_repair_loop(self) -> RepairLoop:
        if self._repair is None:
            self._repair = RepairLoop(self)
        return self._repair

    # ── Tool pre-execution ────────────────────────────────────────────────────

    def _run_tools(self, route_result: RouteResult, message: str) -> dict:
        """Execute tools whose results are needed before the brain responds."""
        outputs: dict = {}

        if route_result.brain == "search":
            outputs["search"] = web_search(message)

        elif route_result.brain == "memory":
            rag_context = self._vector_store.format_context(message)
            outputs["memory"] = rag_context

        elif route_result.brain == "computer" and "screenshot" in message.lower():
            outputs["screenshot"] = take_screenshot()

        return outputs

    # ── Code extraction & auto-exec ───────────────────────────────────────────

    def _maybe_execute_code(self, response_text: str) -> Optional[dict]:
        """Extract and run the first Python block from a response."""
        match = re.search(r"```python\n(.*?)```", response_text, re.DOTALL)
        if not match:
            return None
        code = match.group(1)
        result = execute_python(code)
        logger.info("Auto-executed code: success=%s rc=%d", result["success"], result["returncode"])
        return result

    # ── Lesson injection ──────────────────────────────────────────────────────

    def _build_tool_results(self, tool_outputs: dict, message: str) -> list[dict]:
        """Convert tool outputs into brain-injectable tool_results list."""
        tool_results: list[dict] = []

        if "search" in tool_outputs:
            formatted = "\n\n".join(
                f"[{r.get('title','')}]({r.get('url','')})\n{r.get('body','')}"
                for r in tool_outputs["search"][:5]
            )
            tool_results.append({"tool": "web_search", "result": formatted})

        if "memory" in tool_outputs and tool_outputs["memory"]:
            tool_results.append({"tool": "memory", "result": tool_outputs["memory"]})

        # Inject relevant past solutions
        sol_context = self._solutions.format_for_prompt(message, top_k=2)
        if sol_context:
            tool_results.append({"tool": "solutions", "result": sol_context})

        # Inject relevant lessons
        lesson_context = self._reflection.format_relevant_lessons(message, max_lessons=2)
        if lesson_context:
            tool_results.append({"tool": "lessons", "result": lesson_context})

        # Inject long-term facts
        facts = self._long_term.format_for_prompt()
        if facts:
            tool_results.append({"tool": "user_facts", "result": facts})

        return tool_results

    # ── Simple brain dispatch ─────────────────────────────────────────────────

    def _simple_chat(
        self,
        message: str,
        route_result: RouteResult,
        images: Optional[list[str]] = None,
        auto_execute_code: bool = False,
    ) -> AssistantResponse:
        """Direct single-step routing without planner."""
        tool_outputs = self._run_tools(route_result, message)
        tool_results = self._build_tool_results(tool_outputs, message)
        brain        = self._get_brain(route_result.brain)
        sources: list[dict] = []
        image_b64: Optional[str] = None

        if "search" in tool_outputs:
            sources = tool_outputs["search"]
        if "screenshot" in tool_outputs and tool_outputs["screenshot"].get("success"):
            image_b64 = tool_outputs["screenshot"]["image_b64"]

        # Image generation is a pure tool path
        if route_result.brain == "image_gen":
            gen = generate_image(message)
            return AssistantResponse(
                text=f"Image generated: {message}" if gen["success"] else f"Image generation failed: {gen.get('error')}",
                brain="image_gen", task=route_result.task,
                model=route_result.model, routing_method=route_result.routing_method,
                tool_outputs=gen, image_b64=gen.get("image_b64"),
            )

        # Conversation context injection
        history = self._conversation.to_ollama_messages()

        response_text = brain.respond(
            message,
            tool_results=tool_results if tool_results else None,
            images=images,
            history=history if history else None,
        )

        # Auto-execute code if requested
        code_result: Optional[dict] = None
        if route_result.brain in ("coding", "coder") and auto_execute_code:
            code_result = self._maybe_execute_code(response_text)
            if code_result:
                out = code_result.get("stdout", "") or code_result.get("stderr", "")
                response_text += f"\n\n**Execution output:**\n```\n{out}\n```"

        return AssistantResponse(
            text=response_text,
            brain=route_result.brain, task=route_result.task,
            model=route_result.model, routing_method=route_result.routing_method,
            tool_outputs=tool_outputs, image_b64=image_b64,
            code_result=code_result, sources=sources,
        )

    # ── Coding pipeline with repair ───────────────────────────────────────────

    def _coding_pipeline(
        self,
        message: str,
        route_result: RouteResult,
        images: Optional[list[str]] = None,
        run_tests: bool = True,
    ) -> AssistantResponse:
        """
        Full coding pipeline:
          brain generates code → tests run → repair loop → reflection.
        """
        tool_results = self._build_tool_results(
            self._run_tools(route_result, message), message
        )
        brain = self._get_brain("coding")

        # Initial generation
        initial_response = brain.respond(
            message,
            tool_results=tool_results if tool_results else None,
            images=images,
        )

        # Repair loop (test → fix → retry)
        repair_loop = self._get_repair_loop()
        repair_result: RepairResult = repair_loop.run(
            request=message,
            response=initial_response,
            run_tests=run_tests,
            run_review=True,
        )

        # Log reflection
        self._reflection.log_from_repair(message, "coding", repair_result)

        # Store solution if successful
        if repair_result.success:
            from .self_improvement.tester import extract_python_code
            code = extract_python_code(repair_result.final_response)
            tests = ""
            if repair_result.attempts:
                last = repair_result.attempts[-1]
                if last.test_result:
                    tests = last.test_result.generated_tests or ""
            if code:
                self._solutions.store_solution(
                    title=message[:80],
                    description=message,
                    code=code,
                    tests=tests,
                    fixes=repair_result.fixes_applied,
                    tags=["python", route_result.task],
                )

        # Determine test stats
        last_attempt = repair_result.attempts[-1] if repair_result.attempts else None
        tr = last_attempt.test_result   if last_attempt else None
        rr = last_attempt.review_result if last_attempt else None

        return AssistantResponse(
            text=repair_result.final_response,
            brain=route_result.brain, task=route_result.task,
            model=route_result.model, routing_method=route_result.routing_method,
            tests_passed  = repair_result.tests_passed,
            tests_run     = tr.tests_run if tr else 0,
            review_passed = repair_result.review_passed,
            review_score  = rr.score if rr else 0.0,
            repair_attempts = repair_result.attempt_count,
        )

    # ── Planner pipeline ──────────────────────────────────────────────────────

    def _planned_chat(
        self,
        message: str,
        route_result: RouteResult,
    ) -> AssistantResponse:
        """Full planner → executor pipeline for complex multi-step requests."""
        plan = make_plan(message, brain_hint=route_result.brain)
        logger.info("Plan: %s", plan)

        executor = self._get_executor()
        exec_result: ExecutionResult = executor.execute(plan)

        self._reflection.log(
            task=message,
            result="success" if exec_result.success else "partial",
            brain=route_result.brain,
            errors_seen=[e for e in exec_result.errors if e],
        )

        return AssistantResponse(
            text=exec_result.final_output,
            brain=route_result.brain, task=route_result.task,
            model=route_result.model, routing_method=route_result.routing_method,
            plan=plan,
            execution=exec_result,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def chat(
        self,
        message: str,
        images: Optional[list[str]] = None,
        history: Optional[list[dict]] = None,
        metadata: Optional[dict] = None,
        use_planner: bool = False,
        auto_execute_code: bool = False,
        run_tests: bool = True,
    ) -> AssistantResponse:
        """
        Process a user message through the multi-brain pipeline.

        Args:
            message:           User's text message.
            images:            Image file paths or base64 strings.
            history:           Explicit conversation history (overrides internal buffer).
            metadata:          Arbitrary request-level metadata.
            use_planner:       If True, decompose into steps via planner.
            auto_execute_code: If True, auto-run generated Python (simple mode only).
            run_tests:         If True (default), run test-repair loop for coding tasks.

        Returns:
            AssistantResponse with text, metadata, and self-improvement info.
        """
        # Update internal conversation memory
        self._conversation.add_user(message)

        # Route the request
        route_result = route(message, images)
        logger.info(
            "chat: brain=%s task=%s method=%s",
            route_result.brain, route_result.task, route_result.routing_method,
        )

        # Store any user preferences from metadata
        if metadata:
            for key, val in metadata.items():
                self._long_term.store_fact(key, val)

        # Choose pipeline
        if use_planner and len(message) >= 30:
            response = self._planned_chat(message, route_result)

        elif route_result.brain in ("coding", "coder") and run_tests:
            response = self._coding_pipeline(
                message, route_result, images=images, run_tests=run_tests
            )

        else:
            response = self._simple_chat(
                message, route_result, images=images,
                auto_execute_code=auto_execute_code,
            )

        # Record assistant turn in conversation memory
        self._conversation.add_assistant(response.text)

        return response

    def ask_brain(self, brain_name: str, prompt: str, **kwargs) -> str:
        """Direct call to a specific brain, bypassing the router."""
        brain = self._get_brain(brain_name)
        return brain.respond(prompt, **kwargs)

    # ── Memory management (public) ────────────────────────────────────────────

    def learn_file(self, file_path: str) -> dict:
        """Ingest a file into the vector store."""
        chunks = self._vector_store.ingest_file(file_path)
        return {"success": True, "chunks": chunks, "file": file_path}

    def learn_text(self, text: str, source: str = "manual") -> dict:
        """Ingest raw text into the vector store."""
        chunks = self._vector_store.ingest_text(text, source=source)
        return {"success": True, "chunks": chunks, "source": source}

    def memory_search(self, query: str, top_k: int = 5) -> list[dict]:
        """Semantic search over the vector store."""
        return self._vector_store.search(query, top_k=top_k)

    def store_fact(self, key: str, value: Any) -> None:
        """Store a long-term fact (user preference, project setting)."""
        self._long_term.store_fact(key, value)

    def get_fact(self, key: str, default: Any = None) -> Any:
        """Retrieve a long-term fact."""
        return self._long_term.get(key, default)

    def find_solutions(self, query: str, top_k: int = 5) -> list[dict]:
        """Search the solution memory for relevant past patterns."""
        return self._solutions.find_solutions(query, top_k=top_k)

    def recent_reflections(self, n: int = 10) -> list[dict]:
        """Return the n most recent reflection log entries."""
        return self._reflection.recent(n)

    def clear_conversation(self) -> None:
        """Reset the short-term conversation buffer."""
        self._conversation.clear()

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def memory_doc_count(self) -> int:
        return self._vector_store.doc_count

    @property
    def fact_count(self) -> int:
        return len(self._long_term)

    @property
    def solution_count(self) -> int:
        return len(self._solutions)

    @property
    def reflection_count(self) -> int:
        return len(self._reflection)

    @property
    def conversation_length(self) -> int:
        return self._conversation.length

    def status(self) -> dict:
        """Return a summary of all memory layers and system state."""
        return {
            "vector_docs":       self.memory_doc_count,
            "long_term_facts":   self.fact_count,
            "solutions_stored":  self.solution_count,
            "reflections_logged":self.reflection_count,
            "conversation_turns":self.conversation_length,
            "brains_loaded":     list(self._brains.keys()),
        }
