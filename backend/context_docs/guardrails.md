# guardrails.md — CEO Router Guardrails + Fail-Safe Rules

## Hard Rules (System-Level)

### Routing

1. CEO is the ONLY routing authority — no module self-routes
2. No brain-to-brain communication — all results return to CEO first
3. No module may call another module directly
4. Modules NEVER start unless CEO explicitly routes to them
5. CEO controls retry limits — no module self-retries

### Retrieval

6. No brain may self-fetch context, memory, or web results
7. CEO must approve all retrieval before it happens
8. Brains receive ONLY the context CEO passes — nothing more
9. Context budget must be enforced before passing to brain
10. Retrieval outputs must be ranked and pruned (Phase 65)

### Truth + Accuracy

11. Current/live facts CANNOT be answered without a tool
12. If no tool → CEO must say "cannot verify without search"
13. Fake search results are a hard failure
14. Raw HTML must never be passed to a brain
15. Verified facts and inferences must be clearly separated

### Validation

16. Every module output must be validated before returning to user
17. Validation failure → error path, not silent pass-through
18. plain text output from builder/doctor is a validation failure

### Repair Memory

19. Repair memory NEVER auto-saves
20. Save only if: confirmed + approved + applied + verified + CEO confirmed
21. No duplicates — check_duplicate() before every save
22. One file = one problem — no log mixing

### Builder Mode

23. Doctor diagnoses ONLY — never applies fixes
24. Builder applies ONLY after explicit user approval
25. Max retries: Builder 3, QA 2, Doctor 1
26. Vision QA only for frontend/full_system builds

### Security

27. Admin key required for X-Ray + repair-memory save endpoints
28. Tier filter applied AFTER module output, before user sees it
29. No raw prompts exposed in any API response
30. Session state is never shared across users

## Soft Rules (Best Practice)

- Prefer smallest context subset — avoid token bloat
- Log every CEO event (event_emitter → NDJSON logs)
- Emit checkpoints at meaningful steps
- Never crash execution due to logging failure
- Clarify before executing when request is underspecified

## Fail-Safe Matrix

| Condition                          | Action                                  |
|------------------------------------|-----------------------------------------|
| Brain returns plain text           | Validation fails → error path           |
| LLM call returns None              | Return error output, log warning        |
| Repair memory save conditions fail | Reject save, return reason              |
| Duplicate detected                 | Return existing match, block save       |
| Context budget exceeded            | Prune to budget, log warning            |
| Live fact with no tool             | Respond with "cannot verify" message    |
| Search fails                       | Respond with "search unavailable"       |
| CEO retrieval blocked by brain     | Hard reject — brain never executes      |
| Admin endpoint, wrong key          | 403 Forbidden                           |
| JSON parse fails on module output  | Return degraded structured output       |
