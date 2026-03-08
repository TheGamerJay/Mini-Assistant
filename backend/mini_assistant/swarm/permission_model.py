"""
permission_model.py – Agent Permission Model
─────────────────────────────────────────────
Defines what each brain is allowed to do:
  - which workflow states it may run in
  - which tool categories it may invoke
  - which file scopes it may touch
  - whether it needs a SecurityBrain pre-check
  - whether it may write to memory
  - whether it may mutate project files
  - whether it may execute external actions (shell, deploy)
  - whether human approval is required before it runs

OrchestratorEngine enforces these rules at step dispatch time.
Violations are logged to the task's debug_log and raise PermissionError.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .orchestrator_task import WorkflowState


# ── Allowed tool categories ────────────────────────────────────────────────────

class ToolCategory:
    FILE_READ    = "file_read"
    FILE_WRITE   = "file_write"
    SHELL        = "shell"
    GIT          = "git"
    NPM          = "npm"
    PIP          = "pip"
    PYTHON       = "python"
    DOCKER       = "docker"
    MEMORY_READ  = "memory_read"
    MEMORY_WRITE = "memory_write"
    NONE         = "none"


# ── Permission dataclass ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class BrainPermissions:
    """
    Defines the permission envelope for one brain/agent.

    Fields
    ------
    allowed_states          Which WorkflowState values this brain may run in.
                            Empty tuple = no restriction (use with care).
    allowed_tools           Set of ToolCategory values the brain may invoke.
    allowed_file_scopes     Path prefixes/patterns the brain may read/write.
                            Empty tuple = no file access.
    requires_security_check Whether every tool action must pass SecurityBrain first.
    can_write_memory        Whether the brain may persist to MemoryBrain store.
    can_mutate_project_files Whether the brain may write/edit source files.
    can_execute_external    Whether the brain may run shell/git/npm/pip/docker.
    approval_required       Whether a human-approval step is needed before this
                            brain's actions take effect (used for high-risk ops).
    """
    allowed_states:           tuple[str, ...]      # WorkflowState.value strings
    allowed_tools:            frozenset[str]
    allowed_file_scopes:      tuple[str, ...]
    requires_security_check:  bool
    can_write_memory:         bool
    can_mutate_project_files: bool
    can_execute_external:     bool
    approval_required:        bool

    def may_run_in(self, state_value: str) -> bool:
        """Return True if this brain may run in the given state."""
        if not self.allowed_states:
            return True   # no restriction
        return state_value in self.allowed_states

    def may_use_tool(self, tool_category: str) -> bool:
        return tool_category in self.allowed_tools

    def may_write_file(self, path: str) -> bool:
        if not self.can_mutate_project_files:
            return False
        if not self.allowed_file_scopes:
            return True   # no scope restriction
        return any(path.startswith(scope) or path.endswith(scope)
                   for scope in self.allowed_file_scopes)

    def to_dict(self) -> dict:
        return {
            "allowed_states":           list(self.allowed_states),
            "allowed_tools":            sorted(self.allowed_tools),
            "allowed_file_scopes":      list(self.allowed_file_scopes),
            "requires_security_check":  self.requires_security_check,
            "can_write_memory":         self.can_write_memory,
            "can_mutate_project_files": self.can_mutate_project_files,
            "can_execute_external":     self.can_execute_external,
            "approval_required":        self.approval_required,
        }


# ── Permission registry ────────────────────────────────────────────────────────

BRAIN_PERMISSIONS: dict[str, BrainPermissions] = {

    "manager": BrainPermissions(
        allowed_states           = (),   # runs across all states (coordinator)
        allowed_tools            = frozenset({ToolCategory.MEMORY_READ}),
        allowed_file_scopes      = (),
        requires_security_check  = False,
        can_write_memory         = False,
        can_mutate_project_files = False,
        can_execute_external     = False,
        approval_required        = False,
    ),

    "planner_agent": BrainPermissions(
        allowed_states           = ("planning",),
        allowed_tools            = frozenset({ToolCategory.MEMORY_READ, ToolCategory.FILE_READ}),
        allowed_file_scopes      = (),
        requires_security_check  = False,
        can_write_memory         = False,
        can_mutate_project_files = False,
        can_execute_external     = False,
        approval_required        = False,
    ),

    "research_agent": BrainPermissions(
        allowed_states           = ("loading_context", "planning"),
        allowed_tools            = frozenset({ToolCategory.FILE_READ, ToolCategory.MEMORY_READ}),
        allowed_file_scopes      = ("src/", "backend/", "frontend/", "*.md", "*.json",
                                    "*.py", "*.js", "*.ts"),
        requires_security_check  = False,
        can_write_memory         = False,
        can_mutate_project_files = False,
        can_execute_external     = False,
        approval_required        = False,
    ),

    "coding_agent": BrainPermissions(
        allowed_states           = ("coding",),
        allowed_tools            = frozenset({ToolCategory.FILE_READ, ToolCategory.FILE_WRITE}),
        allowed_file_scopes      = ("src/", "backend/", "frontend/", "*.py", "*.js",
                                    "*.ts", "*.tsx", "*.jsx", "*.css"),
        requires_security_check  = True,
        can_write_memory         = False,
        can_mutate_project_files = True,
        can_execute_external     = False,
        approval_required        = False,
    ),

    "debug_agent": BrainPermissions(
        allowed_states           = ("fixing",),
        allowed_tools            = frozenset({ToolCategory.FILE_READ, ToolCategory.FILE_WRITE}),
        allowed_file_scopes      = ("src/", "backend/", "frontend/", "*.py", "*.js",
                                    "*.ts", "*.tsx", "*.jsx"),
        requires_security_check  = True,
        can_write_memory         = False,
        can_mutate_project_files = True,
        can_execute_external     = False,
        approval_required        = False,
    ),

    "tester_agent": BrainPermissions(
        allowed_states           = ("testing",),
        allowed_tools            = frozenset({ToolCategory.FILE_READ, ToolCategory.FILE_WRITE,
                                              ToolCategory.PYTHON, ToolCategory.NPM}),
        allowed_file_scopes      = ("tests/", "test/", "__tests__/", "*.test.*", "*.spec.*"),
        requires_security_check  = True,
        can_write_memory         = False,
        can_mutate_project_files = True,  # test files only
        can_execute_external     = False,
        approval_required        = False,
    ),

    "file_analyst_agent": BrainPermissions(
        allowed_states           = ("loading_context", "planning", "reviewing"),
        allowed_tools            = frozenset({ToolCategory.FILE_READ}),
        allowed_file_scopes      = ("src/", "backend/", "frontend/", "*.py", "*.js",
                                    "*.ts", "*.tsx"),
        requires_security_check  = False,
        can_write_memory         = False,
        can_mutate_project_files = False,
        can_execute_external     = False,
        approval_required        = False,
    ),

    "doc_agent": BrainPermissions(
        allowed_states           = ("documenting",),
        allowed_tools            = frozenset({ToolCategory.FILE_READ, ToolCategory.FILE_WRITE}),
        allowed_file_scopes      = ("docs/", "*.md", "README*", "CHANGELOG*"),
        requires_security_check  = False,
        can_write_memory         = False,
        can_mutate_project_files = True,   # doc files only
        can_execute_external     = False,
        approval_required        = False,
    ),

    "tool_agent": BrainPermissions(
        allowed_states           = ("deploying",),
        allowed_tools            = frozenset({
            ToolCategory.SHELL, ToolCategory.GIT, ToolCategory.NPM,
            ToolCategory.PIP, ToolCategory.PYTHON, ToolCategory.DOCKER,
        }),
        allowed_file_scopes      = (),    # tool agent reads/writes via shell
        requires_security_check  = True,  # MANDATORY
        can_write_memory         = False,
        can_mutate_project_files = False,
        can_execute_external     = True,
        approval_required        = True,  # high-risk: need explicit approval
    ),

    "security_agent": BrainPermissions(
        allowed_states           = ("coding", "deploying", "fixing"),
        allowed_tools            = frozenset(),   # reads only — no execution
        allowed_file_scopes      = (),
        requires_security_check  = False,   # it IS the security check
        can_write_memory         = False,
        can_mutate_project_files = False,
        can_execute_external     = False,
        approval_required        = False,
    ),

    "memory_agent": BrainPermissions(
        allowed_states           = ("loading_context", "planning", "completed", "failed"),
        allowed_tools            = frozenset({ToolCategory.MEMORY_READ, ToolCategory.MEMORY_WRITE}),
        allowed_file_scopes      = ("data/memory/",),
        requires_security_check  = False,
        can_write_memory         = True,
        can_mutate_project_files = False,
        can_execute_external     = False,
        approval_required        = False,
    ),

    "learning_agent": BrainPermissions(
        allowed_states           = ("completed", "failed"),
        allowed_tools            = frozenset({ToolCategory.MEMORY_READ, ToolCategory.MEMORY_WRITE}),
        allowed_file_scopes      = ("data/",),
        requires_security_check  = False,
        can_write_memory         = True,
        can_mutate_project_files = False,
        can_execute_external     = False,
        approval_required        = False,
    ),

    "vision_agent": BrainPermissions(
        allowed_states           = ("coding", "reviewing"),
        allowed_tools            = frozenset({ToolCategory.FILE_READ}),
        allowed_file_scopes      = ("src/", "frontend/", "screenshots/", "*.png", "*.jpg"),
        requires_security_check  = False,
        can_write_memory         = False,
        can_mutate_project_files = False,
        can_execute_external     = False,
        approval_required        = False,
    ),

    "ui_agent": BrainPermissions(
        allowed_states           = ("coding", "reviewing"),
        allowed_tools            = frozenset({ToolCategory.FILE_READ, ToolCategory.FILE_WRITE}),
        allowed_file_scopes      = ("frontend/", "src/components/", "*.css", "*.jsx", "*.tsx"),
        requires_security_check  = True,
        can_write_memory         = False,
        can_mutate_project_files = True,
        can_execute_external     = False,
        approval_required        = False,
    ),
}


# ── Permission check helper ────────────────────────────────────────────────────

@dataclass
class PermissionCheckResult:
    allowed:     bool
    brain_id:    str
    state:       str
    reason:      str = ""
    checked_at:  str = field(default_factory=lambda: __import__("datetime").datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "allowed":    self.allowed,
            "brain_id":   self.brain_id,
            "state":      self.state,
            "reason":     self.reason,
            "checked_at": self.checked_at,
        }


def check_permission(
    brain_id:   str,
    state:      str,
    tool:       Optional[str] = None,
    file_path:  Optional[str] = None,
) -> PermissionCheckResult:
    """
    Central permission check. Returns PermissionCheckResult.
    If the brain is not in the registry, allow with a warning (forward-compat).
    """
    perms = BRAIN_PERMISSIONS.get(brain_id)
    if perms is None:
        return PermissionCheckResult(
            allowed  = True,
            brain_id = brain_id,
            state    = state,
            reason   = f"Brain '{brain_id}' not in permission registry — allowed by default",
        )

    if not perms.may_run_in(state):
        return PermissionCheckResult(
            allowed  = False,
            brain_id = brain_id,
            state    = state,
            reason   = (
                f"Brain '{brain_id}' not permitted in state '{state}'. "
                f"Allowed states: {list(perms.allowed_states) or 'all'}"
            ),
        )

    if tool and not perms.may_use_tool(tool):
        return PermissionCheckResult(
            allowed  = False,
            brain_id = brain_id,
            state    = state,
            reason   = (
                f"Brain '{brain_id}' may not use tool category '{tool}'. "
                f"Allowed: {sorted(perms.allowed_tools)}"
            ),
        )

    if file_path and not perms.may_write_file(file_path):
        return PermissionCheckResult(
            allowed  = False,
            brain_id = brain_id,
            state    = state,
            reason   = (
                f"Brain '{brain_id}' may not write to '{file_path}'. "
                f"Allowed scopes: {list(perms.allowed_file_scopes)}"
            ),
        )

    return PermissionCheckResult(
        allowed  = True,
        brain_id = brain_id,
        state    = state,
        reason   = "permitted",
    )


def all_permissions_dict() -> dict[str, dict]:
    """Return all brain permissions serialised (for API/diagnostic export)."""
    return {k: v.to_dict() for k, v in BRAIN_PERMISSIONS.items()}
