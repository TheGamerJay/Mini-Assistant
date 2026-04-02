# CEO Router — Guardrails

## Hard rules

1. **CEO is the only authority.** No module self-routes. No UI hint overrides CEO.
2. **No execution in CEO.** `ceo_router.py` returns a decision, never a response.
3. **Modules do not call each other.** All inter-module coordination goes through CEO.
4. **Memory is CEO-scoped.** No module loads its own memory. CEO decides scope.
5. **Web is CEO-gated.** No module runs a web call. CEO decides web mode.
6. **full_system + underspecified = clarification required.** Never hallucinate a simple solution.
7. **Tier blocks are hard stops.** A blocked module routes to core_chat, not degrades silently.
8. **Validation always runs.** Every module output goes through output_validator.

## Soft rules (follow unless there is a clear reason not to)

- Prefer memory over web (web is last resort)
- Prefer search over scraper over crawler
- If intent confidence < 0.60, prefer clarification over guessing
- task_assist without a resume → ask before generating anything

## Fail-safe rules

These protect the pipeline from silent failure:

1. **Validation never raises.** If the validator throws, `ok=True, reason="validation_unavailable"` 
   is returned — the response is NOT silently dropped.
2. **Memory load failure is non-fatal.** If TR loader throws, memory dict is empty and execution continues.
3. **Web step failure is non-fatal.** If search/scraper/crawler throws, web_results dict is empty 
   and execution continues.
4. **Module failure IS surfaced.** If a module throws, result is `{status: "error", error: str(exc)}`.
   The caller sees the error — it is not swallowed.
5. **Unknown step types are skipped with a warning.** The executor logs but does not crash.
6. **Clarification always returns before execution.** No module is called when `needs_user_input=True`.

## What NOT to add here

- Model selection logic (handled by phase2/router.py)
- Credit deduction (handled by mini_credits.py)
- Auth checks (handled by auth_routes.py)
- Streaming logic (handled by image_system/api/server.py)
