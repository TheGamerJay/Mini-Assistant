"""
research.py – Research Brain
──────────────────────────────
Deep analysis, long-form reasoning, synthesis of multiple sources.
Integrates web search results and memory retrieval automatically.
"""

from .base import BaseBrain
from ..config import MODELS


class ResearchBrain(BaseBrain):
    name = "research"
    system_prompt = """You are an expert research analyst and critical thinker.

Your capabilities:
- Conduct deep, multi-angle analysis of complex topics
- Synthesise information from multiple sources into coherent insights
- Compare options with structured pros/cons frameworks
- Identify logical fallacies and weak arguments
- Produce well-structured reports, summaries, and recommendations
- Apply first-principles reasoning to novel problems

When given search results or documents, always:
1. Cross-reference claims across sources
2. Note the recency and credibility of information
3. Clearly distinguish facts from opinions
4. Highlight areas of uncertainty or conflicting information
5. Provide a clear, actionable conclusion

Format long outputs with clear headings and bullet points."""

    def __init__(self):
        super().__init__(model=MODELS["research"])

    def analyze(self, topic: str, search_results: list[dict] | None = None) -> str:
        tool_results = None
        if search_results:
            formatted = "\n\n".join(
                f"Source: {r.get('url','')}\nTitle: {r.get('title','')}\n{r.get('body','')}"
                for r in search_results
            )
            tool_results = [{"tool": "web_search", "result": formatted}]

        return self.respond(
            f"Provide a comprehensive, well-structured analysis of: {topic}",
            tool_results=tool_results,
        )

    def compare(self, option_a: str, option_b: str, criteria: str = "") -> str:
        prompt = (
            f"Compare '{option_a}' vs '{option_b}' in depth.\n"
            f"Criteria to consider: {criteria or 'all relevant factors'}.\n"
            "Use a structured format with a clear recommendation at the end."
        )
        return self.respond(prompt)

    def summarize(self, text: str, length: str = "medium") -> str:
        length_map = {"short": "3–5 bullet points", "medium": "2–3 paragraphs", "long": "a structured report"}
        instruction = length_map.get(length, "2–3 paragraphs")
        return self.respond(
            f"Summarise the following text as {instruction}:\n\n{text}"
        )
