"""
backend/mini_assistant/phase8/tool_registry.py

Registry of all tools the assistant can invoke.
Each tool has a name, category, description, and default risk level.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ToolDef:
    name: str
    category: str          # shell | git | file_read | file_write | deploy
    description: str
    default_risk: str      # safe | caution | danger | blocked
    requires_approval: bool = False
    examples: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool catalogue
# ---------------------------------------------------------------------------

TOOLS: List[ToolDef] = [
    # --- Git ---
    ToolDef("git_status",  "git", "Show working tree status",              "safe",    False, ["git status"]),
    ToolDef("git_diff",    "git", "Show staged and unstaged changes",      "safe",    False, ["git diff", "git diff --staged"]),
    ToolDef("git_log",     "git", "Show recent commit history",            "safe",    False, ["git log --oneline -10"]),
    ToolDef("git_add",     "git", "Stage files for commit",                "caution", False, ["git add <file>"]),
    ToolDef("git_commit",  "git", "Commit staged changes",                 "caution", False, ["git commit -m '...'"]),
    ToolDef("git_push",    "git", "Push commits to remote",                "danger",  True,  ["git push origin main"]),
    ToolDef("git_pull",    "git", "Pull latest changes from remote",       "caution", False, ["git pull"]),
    ToolDef("git_branch",  "git", "List or create branches",               "safe",    False, ["git branch", "git checkout -b feature"]),
    ToolDef("git_reset",   "git", "Reset working tree (destructive)",      "danger",  True,  ["git reset --hard HEAD"]),

    # --- File read ---
    ToolDef("file_read",   "file_read",  "Read a file",                    "safe",    False, ["cat src/main.py"]),
    ToolDef("file_list",   "file_read",  "List directory contents",        "safe",    False, ["ls src/", "find . -name '*.py'"]),
    ToolDef("file_search", "file_read",  "Search file contents (grep)",    "safe",    False, ["grep -r 'TODO' src/"]),

    # --- File write ---
    ToolDef("file_write",  "file_write", "Write or overwrite a file",      "caution", False, ["echo '...' > file.txt"]),
    ToolDef("file_delete", "file_write", "Delete a file",                  "danger",  True,  ["rm file.txt"]),
    ToolDef("file_mkdir",  "file_write", "Create a directory",             "safe",    False, ["mkdir -p src/utils"]),

    # --- Shell ---
    ToolDef("shell_safe",  "shell", "Run a safe read-only shell command",  "caution", False, ["pwd", "echo $PATH"]),
    ToolDef("shell_exec",  "shell", "Execute an arbitrary shell command",  "danger",  True,  ["python script.py"]),

    # --- Deploy ---
    ToolDef("deploy_railway", "deploy", "Trigger Railway deployment",      "danger",  True,  ["railway up"]),
    ToolDef("deploy_docker",  "deploy", "Build and run Docker container",  "danger",  True,  ["docker build . && docker run"]),
]

_TOOL_MAP = {t.name: t for t in TOOLS}


def get_tool(name: str) -> Optional[ToolDef]:
    return _TOOL_MAP.get(name)


def list_tools(category: Optional[str] = None) -> List[ToolDef]:
    if category:
        return [t for t in TOOLS if t.category == category]
    return list(TOOLS)


def tools_as_dict() -> list:
    return [
        {
            "name": t.name,
            "category": t.category,
            "description": t.description,
            "default_risk": t.default_risk,
            "requires_approval": t.requires_approval,
            "examples": t.examples,
        }
        for t in TOOLS
    ]
