"""
solution_memory.py – Solution Pattern Store
─────────────────────────────────────────────
Stores successful task solutions for future reuse.

Saved patterns include:
  • bug + fix pairs
  • project scaffolds (file structures)
  • deployment patterns
  • common tool usage sequences
  • test templates

Usage:
    sm = SolutionMemory()
    sm.store_solution(
        title="FastAPI JWT auth",
        description="Add JWT authentication to a FastAPI app",
        code=generated_code,
        tests=test_code,
        tags=["python", "fastapi", "auth"],
    )
    matches = sm.find_solutions("fastapi authentication")
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_PATH = os.getenv("SOLUTION_MEMORY_PATH", "./memory_store/solutions.json")

MAX_SOLUTIONS = 500   # cap to avoid unbounded growth


class SolutionMemory:
    """
    JSON-backed store of successful solutions and patterns.

    Each solution entry:
    {
        "id":          str,
        "title":       str,
        "description": str,
        "code":        str,
        "tests":       str,
        "fixes":       [{"error": ..., "fix": ...}],
        "tags":        [str],
        "use_count":   int,
        "created_at":  ISO timestamp,
        "last_used":   ISO timestamp | null,
    }
    """

    def __init__(self, store_path: Optional[str] = None):
        self._path = Path(store_path or _DEFAULT_PATH)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._solutions: list[dict] = []
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if self._path.exists():
                self._solutions = json.loads(self._path.read_text(encoding="utf-8"))
                logger.debug("Loaded %d solutions from %s", len(self._solutions), self._path)
        except Exception as exc:
            logger.warning("Could not load solution memory: %s", exc)
            self._solutions = []

    def _save(self) -> None:
        # Trim to cap
        if len(self._solutions) > MAX_SOLUTIONS:
            # Keep most recently used first
            self._solutions.sort(
                key=lambda s: s.get("last_used") or s.get("created_at"), reverse=True
            )
            self._solutions = self._solutions[:MAX_SOLUTIONS]
        try:
            self._path.write_text(
                json.dumps(self._solutions, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Could not save solution memory: %s", exc)

    # ── Storage ───────────────────────────────────────────────────────────────

    def store_solution(
        self,
        title: str,
        description: str,
        code: str = "",
        tests: str = "",
        fixes: Optional[list[dict]] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Store a new solution. Returns the solution id.

        Args:
            title:       Short name for the pattern.
            description: What problem this solves.
            code:        The working code / scaffold.
            tests:       Associated tests (optional).
            fixes:       List of {"error": ..., "fix": ...} applied.
            tags:        Searchable labels.
            metadata:    Any additional fields.

        Returns:
            The new solution's id string.
        """
        now = datetime.now(timezone.utc).isoformat()
        solution = {
            "id":          str(uuid.uuid4()),
            "title":       title,
            "description": description,
            "code":        code,
            "tests":       tests,
            "fixes":       fixes or [],
            "tags":        [t.lower() for t in (tags or [])],
            "use_count":   0,
            "created_at":  now,
            "last_used":   None,
            **(metadata or {}),
        }
        self._solutions.append(solution)
        self._save()
        logger.info("Stored solution: %s (%s)", title, solution["id"][:8])
        return solution["id"]

    def store_bug_fix(self, error: str, fix: str, context: str = "") -> str:
        """Convenience wrapper for bug+fix pairs."""
        return self.store_solution(
            title=f"Fix: {error[:60]}",
            description=f"Bug fix for: {error}",
            code=fix,
            fixes=[{"error": error, "fix": fix, "context": context}],
            tags=["bug-fix"],
        )

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def find_solutions(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Text-search solutions by query against title, description, and tags.

        Results are sorted by relevance score then use_count.
        Returns a list of matching solution dicts (without full code).
        """
        q = query.lower().split()
        scored: list[tuple[int, dict]] = []

        for sol in self._solutions:
            score = 0
            haystack = (
                sol["title"].lower() + " " +
                sol["description"].lower() + " " +
                " ".join(sol["tags"])
            )
            for token in q:
                if token in haystack:
                    score += 1
                if token in sol["title"].lower():
                    score += 2   # title match is more relevant

            if score > 0:
                scored.append((score, sol))

        scored.sort(key=lambda x: (x[0], x[1]["use_count"]), reverse=True)
        results = [s for _, s in scored[:top_k]]

        # Increment use_count for returned results
        ids = {s["id"] for s in results}
        now = datetime.now(timezone.utc).isoformat()
        for sol in self._solutions:
            if sol["id"] in ids:
                sol["use_count"] = sol.get("use_count", 0) + 1
                sol["last_used"] = now
        if ids:
            self._save()

        return results

    def get_solution(self, solution_id: str) -> Optional[dict]:
        """Retrieve a full solution by id."""
        for sol in self._solutions:
            if sol["id"] == solution_id:
                sol["use_count"] = sol.get("use_count", 0) + 1
                sol["last_used"] = datetime.now(timezone.utc).isoformat()
                self._save()
                return sol
        return None

    def delete_solution(self, solution_id: str) -> bool:
        before = len(self._solutions)
        self._solutions = [s for s in self._solutions if s["id"] != solution_id]
        if len(self._solutions) < before:
            self._save()
            return True
        return False

    # ── Listing ───────────────────────────────────────────────────────────────

    def all_solutions(self, include_code: bool = False) -> list[dict]:
        """Return all solutions, optionally with code stripped to save bandwidth."""
        if include_code:
            return list(self._solutions)
        return [
            {k: v for k, v in s.items() if k not in ("code", "tests")}
            for s in self._solutions
        ]

    def format_for_prompt(self, query: str, top_k: int = 3) -> str:
        """
        Find relevant solutions and format them as an LLM context block.
        """
        results = self.find_solutions(query, top_k=top_k)
        if not results:
            return ""
        parts = ["Relevant past solutions:"]
        for s in results:
            parts.append(f"\n### {s['title']}\n{s['description']}")
            if s.get("code"):
                lang = "python"
                for tag in s.get("tags", []):
                    if tag in {"javascript", "typescript", "bash", "sql"}:
                        lang = tag
                        break
                parts.append(f"```{lang}\n{s['code'][:1000]}\n```")
        return "\n".join(parts)

    def __len__(self) -> int:
        return len(self._solutions)

    def __repr__(self) -> str:
        return f"SolutionMemory(solutions={len(self._solutions)}, path={self._path})"
