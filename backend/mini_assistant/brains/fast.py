"""
fast.py – Fast Brain
─────────────────────
Lightweight, low-latency responses for quick factual questions,
conversational replies, and simple tasks. Uses the smallest model.
"""

from .base import BaseBrain
from ..config import MODELS


class FastBrain(BaseBrain):
    name = "fast"
    system_prompt = """You are Mini Assistant's quick-response brain.

Be concise, friendly, and direct. For simple questions, give short answers.
For factual queries, answer in 1–3 sentences. Avoid unnecessary padding.
If you don't know something, say so briefly and suggest how the user can find out."""

    def __init__(self):
        super().__init__(model=MODELS["fast"])

    def quick_answer(self, question: str) -> str:
        return self.respond(question)

    def chat(self, message: str) -> str:
        return self.respond(message)
