"""
Multi-brain agent pipeline for Mini Assistant.

Brains and models:
  manager   → glm-5:cloud
  analysis  → glm-5:cloud  (planner + researcher merged)
  coder     → devstral-2:cloud
  debugger  → qwen3-coder-next:cloud
  tester    → devstral-small-2:cloud
  fast_chat → minimax-m2.1:cloud
"""

import json
import re
import asyncio
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Callable

# ── Model assignments ──────────────────────────────────────────────────────────
MODELS = {
    "manager":   "glm-5:cloud",
    "analysis":  "glm-5:cloud",
    "coder":     "devstral-2:cloud",
    "debugger":  "qwen3-coder-next:cloud",
    "tester":    "devstral-small-2:cloud",
    "fast_chat": "minimax-m2.1:cloud",
}

MAX_DEBUG_ATTEMPTS = 2


# ── Shared Task Context ────────────────────────────────────────────────────────
@dataclass
class TaskContext:
    task: str
    route: str = "pending"          # "fast_chat" | "full"
    plan: List[str] = field(default_factory=list)
    research: str = ""
    code_output: str = ""
    test_results: str = ""          # "pass" | "fail" | ""
    errors: str = ""
    debug_attempts: int = 0
    final_response: str = ""
    status: str = "routing"
    active_brain: str = "manager"
    logs: List[dict] = field(default_factory=list)

    def log(self, brain: str, message: str):
        self.logs.append({"brain": brain, "message": message[:600]})

    def to_dict(self):
        return asdict(self)


# ── Internal LLM call ─────────────────────────────────────────────────────────
def _call(client, model: str, messages: list) -> str:
    resp = client.chat(model=model, messages=messages)
    return resp["message"]["content"]


# ── Brain: Manager — routing ──────────────────────────────────────────────────
def brain_manager_route(ctx: TaskContext, client):
    ctx.active_brain = "manager"
    prompt = (
        "You are the Manager Brain of a multi-agent AI system.\n\n"
        f"User request: {ctx.task}\n\n"
        "Decide the execution route:\n"
        "- ROUTE:fast_chat → simple conversational question, greeting, or quick factual answer\n"
        "- ROUTE:full → requires coding, building, debugging, research, planning, or any multi-step work\n\n"
        "Reply with ROUTE:fast_chat or ROUTE:full on the very first line, then one sentence of reasoning."
    )
    result = _call(client, MODELS["manager"], [{"role": "user", "content": prompt}])
    ctx.log("manager", result)
    ctx.route = "fast_chat" if "ROUTE:fast_chat" in result else "full"


# ── Brain: Fast Chat ───────────────────────────────────────────────────────────
def brain_fast_chat(ctx: TaskContext, client):
    ctx.active_brain = "fast_chat"
    result = _call(client, MODELS["fast_chat"], [
        {"role": "system", "content": "You are Mini Assistant. Answer helpfully and concisely."},
        {"role": "user", "content": ctx.task},
    ])
    ctx.final_response = result
    ctx.log("fast_chat", "Direct response generated")


# ── Brain: Analysis (Planner + Researcher merged) ─────────────────────────────
def brain_analysis(ctx: TaskContext, client):
    ctx.active_brain = "analysis"
    prompt = (
        "You are the Analysis Brain — you handle both planning and research.\n\n"
        f"Task: {ctx.task}\n\n"
        "1. Break the task into concrete, numbered implementation steps.\n"
        "2. Note the key technologies, libraries, and architectural approach.\n\n"
        "Respond ONLY in this exact JSON format (no markdown wrapping):\n"
        '{"steps": ["step 1", "step 2", ...], "research": "technical notes and approach here"}'
    )
    result = _call(client, MODELS["analysis"], [{"role": "user", "content": prompt}])
    ctx.log("analysis", result)
    try:
        m = re.search(r'\{.*\}', result, re.DOTALL)
        if m:
            data = json.loads(m.group())
            ctx.plan = data.get("steps", [])
            ctx.research = data.get("research", "")
    except Exception:
        # Fallback: treat whole response as a single step
        ctx.plan = [result[:500]]
        ctx.research = ""


# ── Brain: Coder ──────────────────────────────────────────────────────────────
def brain_coder(ctx: TaskContext, client):
    ctx.active_brain = "coder"
    plan_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(ctx.plan))
    prompt = (
        "You are the Coding Brain. Implement the task below completely.\n\n"
        f"Task: {ctx.task}\n\n"
        f"Execution Plan:\n{plan_text}\n\n"
        f"Research / Technical Notes:\n{ctx.research}\n\n"
        "Write complete, working, production-ready code. "
        "Include all files, imports, configurations, and setup instructions. "
        "Do not omit any part of the implementation."
    )
    result = _call(client, MODELS["coder"], [{"role": "user", "content": prompt}])
    ctx.code_output = result
    ctx.log("coder", "Code generated")


# ── Brain: Tester ─────────────────────────────────────────────────────────────
def brain_tester(ctx: TaskContext, client):
    ctx.active_brain = "tester"
    errors_note = f"\nPrevious issues flagged:\n{ctx.errors}" if ctx.errors else ""
    prompt = (
        "You are the Tester Brain. Review this code output rigorously.\n\n"
        f"Original Task: {ctx.task}\n\n"
        f"Code Output:\n{ctx.code_output}{errors_note}\n\n"
        "Check: (1) Does it fulfill all task requirements? "
        "(2) Are there bugs, missing pieces, or incorrect logic? "
        "(3) Would it run without errors?\n\n"
        "The VERY FIRST line of your response MUST be exactly RESULT:pass or RESULT:fail. "
        "Then explain your findings in detail."
    )
    result = _call(client, MODELS["tester"], [{"role": "user", "content": prompt}])
    ctx.log("tester", result)
    if "RESULT:pass" in result:
        ctx.test_results = "pass"
        ctx.errors = ""
    else:
        ctx.test_results = "fail"
        ctx.errors = result


# ── Brain: Debugger ───────────────────────────────────────────────────────────
def brain_debugger(ctx: TaskContext, client):
    ctx.active_brain = "debugger"
    prompt = (
        "You are the Debug Brain. Fix every issue found in this code.\n\n"
        f"Task: {ctx.task}\n\n"
        f"Current Code:\n{ctx.code_output}\n\n"
        f"Issues Found by Tester:\n{ctx.errors}\n\n"
        "Provide the COMPLETE corrected code with all fixes applied. "
        "Do not abbreviate or skip any section."
    )
    result = _call(client, MODELS["debugger"], [{"role": "user", "content": prompt}])
    ctx.code_output = result
    ctx.errors = ""
    ctx.log("debugger", "Fixes applied")


# ── Brain: Manager — finalize ─────────────────────────────────────────────────
def brain_manager_finalize(ctx: TaskContext, client):
    ctx.active_brain = "manager"
    plan_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(ctx.plan))
    debug_note = f" ({ctx.debug_attempts} debug cycle(s) required)" if ctx.debug_attempts else ""
    prompt = (
        "You are the Manager Brain. Compile the final response for the user.\n\n"
        f"Original Task: {ctx.task}\n\n"
        f"Execution Plan:\n{plan_text}\n\n"
        f"Final Code / Output:\n{ctx.code_output}\n\n"
        f"Test Result: {ctx.test_results}{debug_note}\n\n"
        "Produce a clean, well-formatted response that includes:\n"
        "1. A brief summary of what was built\n"
        "2. The complete code\n"
        "3. How to run / use it"
    )
    result = _call(client, MODELS["manager"], [{"role": "user", "content": prompt}])
    ctx.final_response = result
    ctx.log("manager", "Response finalized")


# ── Executor Pipeline ─────────────────────────────────────────────────────────
async def run_agent_pipeline(
    task: str,
    client,
    on_update: Optional[Callable] = None,
) -> TaskContext:
    ctx = TaskContext(task=task)
    loop = asyncio.get_event_loop()

    def notify(status: str):
        ctx.status = status
        if on_update:
            on_update(ctx)

    # Step 1: Manager routes
    notify("routing")
    await loop.run_in_executor(None, brain_manager_route, ctx, client)
    notify("routed")

    # Short-circuit: fast chat for simple questions
    if ctx.route == "fast_chat":
        notify("responding")
        await loop.run_in_executor(None, brain_fast_chat, ctx, client)
        notify("done")
        return ctx

    # Step 2: Analysis (plan + research)
    notify("planning")
    await loop.run_in_executor(None, brain_analysis, ctx, client)
    notify("planned")

    # Step 3: Coding
    notify("coding")
    await loop.run_in_executor(None, brain_coder, ctx, client)
    notify("coded")

    # Step 4: Test → Debug loop (max MAX_DEBUG_ATTEMPTS rounds)
    for attempt in range(MAX_DEBUG_ATTEMPTS + 1):
        notify("testing")
        await loop.run_in_executor(None, brain_tester, ctx, client)

        if ctx.test_results == "pass" or attempt >= MAX_DEBUG_ATTEMPTS:
            break

        ctx.debug_attempts += 1
        notify("debugging")
        await loop.run_in_executor(None, brain_debugger, ctx, client)

    # Step 5: Manager compiles final response
    notify("finalizing")
    await loop.run_in_executor(None, brain_manager_finalize, ctx, client)
    notify("done")

    return ctx
