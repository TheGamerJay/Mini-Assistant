"""
research_agent.py – Research Agent
────────────────────────────────────
Performs web research, documentation review, and deep analysis.

Uses the Research brain (deepseek-v3:671b) backed by live web search
when the task requires current information, and pure reasoning otherwise.
"""

from __future__ import annotations

from .base_agent  import BaseAgent
from .task_models import SwarmTask, TaskResult
from ..tools.search import web_search


_RESEARCH_SYSTEM = """\
You are a rigorous research analyst. Your role is to gather information,
synthesize it clearly, and deliver well-structured, accurate summaries.

When you receive web search results, analyse them critically.
When asked to compare options, use a clear pros/cons format.
When asked for a deep dive, provide comprehensive coverage with sections.
Always cite sources when you have URLs available.
Be factual, concise, and thorough.
"""


class ResearchAgent(BaseAgent):
    """
    Research agent: web search + deep reasoning synthesis.

    Automatically performs a web search if the task looks like it needs
    current data (keywords: latest, current, today, best, compare, etc.).
    """

    agent_name = "research_agent"
    agent_type = "research"

    _SEARCH_KEYWORDS = {
        "latest", "current", "best", "today", "compare", "vs",
        "which", "top", "review", "benchmark", "price", "news",
        "how to", "what is", "who is", "when did",
    }

    def _needs_search(self, text: str) -> bool:
        tl = text.lower()
        return any(kw in tl for kw in self._SEARCH_KEYWORDS)

    def run(self, task: SwarmTask, context: dict[str, TaskResult]) -> TaskResult:
        self._logger.info("Researching: %s", task.description[:80])

        # Build the full prompt including dependency context
        prompt = self._inject_context(task, context)

        # Optionally enrich with live search results
        search_results: list[dict] = []
        query = task.args.get("query") or task.description
        if self._needs_search(query):
            self._logger.info("Running web search: %s", query[:60])
            search_results = web_search(query, max_results=6)

        if search_results:
            snippets = "\n\n".join(
                f"[{r.get('title','')}]({r.get('url','')})\n{r.get('body','')}"
                for r in search_results[:5]
            )
            prompt = f"{prompt}\n\n--- Web Search Results ---\n{snippets}"

        response = self._call_llm(
            user_prompt   = prompt,
            system_prompt = _RESEARCH_SYSTEM,
            temperature   = 0.1,
        )

        self._logger.info("Research complete (%d chars).", len(response))
        return self._make_result(
            task   = task,
            output = response,
            data   = {"search_results": [r.get("url", "") for r in search_results]},
        )
