# repair_memory_spec.md — Repair Memory Library Specification

## Purpose

Stores confirmed problem+solution pairs that the CEO can reference
when similar problems appear in future sessions.

Not a log. Not a history. A knowledge base of proven fixes.

## Storage Location

```
backend/internal_library/repair_memory/
  {category}/
    {problem-slug}.json
```

## File Format

```json
{
  "problem_name":   "Short description of the problem",
  "category":       "build_pipeline",
  "solution_name":  "Short description of the fix applied",
  "solution_steps": [
    "Step 1: ...",
    "Step 2: ..."
  ],
  "success_count":  1,
  "last_used":      "2026-01-01T00:00:00+00:00",
  "created_at":     "2026-01-01T00:00:00+00:00"
}
```

## Allowed Categories

routing, frontend_state, backend_logic, validation, persistence,
billing, tooling, ui, image_pipeline, build_pipeline, testing, auth, unknown

## Save Conditions (ALL required)

1. Problem is confirmed (not hypothetical)
2. Root cause is identified with evidence
3. Solution was approved by the user via approval gate
4. Solution was applied by Builder
5. Hands QA (and Vision QA if applicable) passed verification
6. CEO confirmed final success status = "complete"

## Anti-Bloat Rules

- One file = one problem (never merge problems)
- check_duplicate() must run before every save (threshold 0.75)
- slug_exists() secondary check
- No logs, no chain history, no raw LLM outputs stored

## Similarity Scoring

score = 0.7 × query_coverage + 0.3 × Jaccard

Confidence levels:
- HIGH:   score ≥ 0.75
- MEDIUM: score ≥ 0.50
- LOW:    score ≥ 0.25
- IGNORE: score < 0.25

## Retrieval Rules

- Doctor: searches before diagnosing (reference only, not auto-applied)
- CEO Orchestrator: searches before calling Doctor (guidance only)
- Top match passed as "repair_memory_reference" context item
- NEVER auto-apply a past fix — user approval always required

## Implementation

- `core/repair_memory/repair_store.py` — save/load/list/increment
- `core/repair_memory/repair_search.py` — search/check_duplicate/score_pair
- Admin endpoint: `POST /api/ceo/repair-memory/save` (admin key required)
- Admin endpoint: `GET /api/ceo/repair-memory/search`
