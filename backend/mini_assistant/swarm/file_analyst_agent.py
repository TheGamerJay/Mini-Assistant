"""
file_analyst_agent.py – File Analyst Agent
────────────────────────────────────────────
Reads project files, extracts architecture, summarises codebase structure,
and retrieves relevant file context for other agents.

Input (task.args):
  path   – file or directory path to analyse (required)
  query  – specific question about the codebase (optional)
  depth  – max folder traversal depth (default 3)
"""

from __future__ import annotations

from .base_agent          import BaseAgent
from .task_models         import SwarmTask, TaskResult
from ..tools.file_reader  import read_path, list_files, search_in_files


_ANALYST_SYSTEM = """\
You are an expert software architect and code analyst.

When given file contents or a directory listing, provide:
1. A clear overview of the architecture and components.
2. The purpose and responsibility of each significant module/file.
3. Key dependencies and data flows.
4. Any architectural patterns you identify (MVC, microservices, etc.).
5. Potential areas of concern or improvement (briefly).

Be structured, use headings, be concise but complete.
If asked a specific question about the codebase, answer it directly first.
"""


class FileAnalystAgent(BaseAgent):
    """
    File analyst agent: reads files and produces architecture summaries.
    """

    agent_name = "file_analyst_agent"
    agent_type = "file_analyst"

    def run(self, task: SwarmTask, context: dict[str, TaskResult]) -> TaskResult:
        self._logger.info("Analysing files: %s", task.description[:80])

        path  = task.args.get("path", ".")
        query = task.args.get("query", "") or task.description
        depth = int(task.args.get("depth", 3))

        # Read the file/directory content
        try:
            content = read_path(path, include_content=True)
        except Exception as exc:
            return self._make_result(
                task    = task,
                output  = f"Could not read path '{path}': {exc}",
                success = False,
                error   = str(exc),
            )

        # Limit content size to avoid overwhelming the model
        MAX_CONTENT = 12_000
        if len(content) > MAX_CONTENT:
            content = content[:MAX_CONTENT] + "\n\n[Content truncated – file too large]"

        # Also get a flat file list for orientation
        try:
            files = list_files(path, max_depth=depth)
            file_list = "\n".join(
                f"  {'[DIR]' if f['is_dir'] else '[FILE]'} {f['name']} "
                f"({f['size_bytes']:,} bytes)" if not f['is_dir'] else f"  [DIR] {f['name']}"
                for f in files[:50]
            )
        except Exception:
            file_list = ""

        # If a specific query is given, also do a text search
        search_context = ""
        if query and query != task.description:
            hits = search_in_files(path, query, max_results=10)
            if hits:
                search_context = "\n\nSearch results for query:\n" + "\n".join(
                    f"  {h['file']}:{h['line_number']}: {h['line']}"
                    for h in hits
                )

        prompt = (
            f"Analyse this codebase and answer: {query}\n\n"
            f"File structure:\n{file_list}\n\n"
            f"File contents:\n{content}"
            + search_context
        )

        # Add dependency context
        dep_context = self._inject_context(task, context)
        if dep_context != task.description:
            prompt += f"\n\nAdditional context:\n{dep_context[:1000]}"

        response = self._call_llm(
            user_prompt   = prompt,
            system_prompt = _ANALYST_SYSTEM,
            temperature   = 0.1,
        )

        self._logger.info("File analysis complete (%d chars).", len(response))
        return self._make_result(
            task   = task,
            output = response,
            data   = {"path": path, "files_scanned": len(files) if file_list else 0},
        )
