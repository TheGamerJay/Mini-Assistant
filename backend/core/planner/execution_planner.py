"""
planner/execution_planner.py — Build an ordered execution plan from CEO context.

The execution plan is a list of ExecutionSteps that the module_executor
will follow in order. CEO decides the plan — modules do not reorder it.

Step types (in order they can appear):
  clarify     — short-circuits the plan; no other steps follow
  memory_load — load TR memory before module has it
  web_call    — fetch live data before module needs it
  module_call — execute the selected module
  validation  — validate the module output before returning

Rules:
- all steps are explicit — no implicit jumps between them
- clarification always terminates the plan (return immediately)
- memory_load always precedes module_call
- web_call always precedes module_call
- validation always follows module_call for non-trivial output
- modules never appear more than once unless CEO explicitly plans multi-module
"""

from __future__ import annotations

from ..router_types import ExecutionStep
from ..router_context import RouterContext

# Modules whose output is always trivial enough to skip validation
_SKIP_VALIDATION_MODULES: set[str] = set()  # currently none — all modules validate

# Validation type per module
_VALIDATION_TYPE: dict[str, str] = {
    "task_assist":      "professional_content",
    "campaign_lab":     "marketing_content",
    "web_intelligence": "web_content",
    "builder":          "structured_code",
    "image":            "image_output",
    "image_edit":       "image_output",
    "core_chat":        "general_chat",
    "doctor":           "repair_output",
    "vision":           "vision_output",
    "hands":            "hands_output",
}


def build_execution_plan(ctx: RouterContext) -> list[ExecutionStep]:
    """
    Build ordered execution steps from the populated RouterContext.
    Returns a list of ExecutionStep in strict execution order.
    """
    steps: list[ExecutionStep] = []
    n = 0

    # ── Step 0: Clarification short-circuit ───────────────────────────────────
    # Nothing else runs when clarification is needed.
    if ctx.needs_user_input:
        n += 1
        steps.append(ExecutionStep(
            step=n,
            type="clarify",
            target="user",
            reason=ctx.clarification_question or "Clarification required before proceeding.",
        ))
        return steps

    # ── Step 1: Memory load ────────────────────────────────────────────────────
    # Must run before module_call so the module has the data it needs.
    if ctx.requires_memory and ctx.memory_scope:
        n += 1
        steps.append(ExecutionStep(
            step=n,
            type="memory_load",
            target=ctx.memory_scope,
            reason=f"Load TR memory scope '{ctx.memory_scope}' before {ctx.selected_module} executes.",
        ))

    # ── Step 2: Web call ───────────────────────────────────────────────────────
    # Must run before module_call so results can be injected as context.
    if ctx.requires_web and ctx.web_mode:
        n += 1
        steps.append(ExecutionStep(
            step=n,
            type="web_call",
            target=ctx.web_mode,
            reason=f"Fetch live data via '{ctx.web_mode}' before {ctx.selected_module} executes.",
        ))

    # ── Step 3: Module call ────────────────────────────────────────────────────
    n += 1
    steps.append(ExecutionStep(
        step=n,
        type="module_call",
        target=ctx.selected_module,
        reason=f"Execute {ctx.selected_module} for intent='{ctx.primary_intent}' complexity='{ctx.complexity}'.",
    ))

    # ── Step 4: Validation ────────────────────────────────────────────────────
    # Always follows module_call for non-trivial output.
    # validation_type tells the validator which rules to apply.
    if ctx.selected_module not in _SKIP_VALIDATION_MODULES:
        validation_type = _VALIDATION_TYPE.get(ctx.selected_module, "general_chat")
        n += 1
        steps.append(ExecutionStep(
            step=n,
            type="validation",
            target="output_validator",
            reason=f"Validate {ctx.selected_module} output using '{validation_type}' rules.",
        ))

    return steps
