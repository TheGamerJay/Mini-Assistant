"""
coder.py – Coding Brain
────────────────────────
Specialised for: writing, debugging, explaining, and refactoring code.
Automatically executes generated Python code if requested and feeds
the output back into the conversation.
"""

from .base import BaseBrain
from ..config import MODELS


class CoderBrain(BaseBrain):
    name = "coder"
    system_prompt = """You are an expert software engineer and coding assistant.

Your capabilities:
- Write clean, well-commented, production-ready code in any language
- Debug errors by reading tracebacks and suggesting precise fixes
- Explain code clearly to any experience level
- Refactor and optimise existing code
- Design software architecture and data structures

Rules:
- Always wrap code in fenced code blocks with the language tag (e.g. ```python)
- When writing Python, include brief inline comments
- If you run code and get output, interpret the output for the user
- Prefer simple, readable solutions over clever one-liners unless asked
- Point out potential security issues in code you review"""

    def __init__(self):
        super().__init__(model=MODELS["coder"])

    def write_code(self, description: str, language: str = "python") -> str:
        prompt = f"Write {language} code for the following:\n\n{description}"
        return self.respond(prompt)

    def debug_code(self, code: str, error: str, language: str = "python") -> str:
        prompt = (
            f"Debug this {language} code.\n\n"
            f"Code:\n```{language}\n{code}\n```\n\n"
            f"Error:\n```\n{error}\n```\n\n"
            "Identify the root cause and provide the corrected code."
        )
        return self.respond(prompt)

    def explain_code(self, code: str, language: str = "python") -> str:
        prompt = (
            f"Explain this {language} code step by step. "
            f"Be clear and assume the reader is a junior developer.\n\n"
            f"```{language}\n{code}\n```"
        )
        return self.respond(prompt)

    def review_code(self, code: str, language: str = "python") -> str:
        prompt = (
            f"Review this {language} code for:\n"
            "1. Bugs and logic errors\n"
            "2. Security vulnerabilities\n"
            "3. Performance improvements\n"
            "4. Code style and best practices\n\n"
            f"```{language}\n{code}\n```\n\n"
            "Provide the improved version at the end."
        )
        return self.respond(prompt)
