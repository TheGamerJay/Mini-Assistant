# CEO Router — Data Flow

## Request → Response lifecycle

```
POST /api/ceo/chat
       │
       ▼
ChatRouteRequest (Pydantic)
       │  normalize
       ▼
RouterRequest (dataclass)
       │
       ▼
ceo_router.route_request()
  ├── detect_intent()         → primary, secondary, confidence
  ├── detect_complexity()     → complexity, is_underspecified
  ├── select_module()         → module name
  ├── decide_tier_visibility()→ "free" | "paid" | "free_limited" | "blocked"
  ├── decide_memory()         → requires_memory, memory_scope
  ├── decide_web()            → requires_web, web_mode
  ├── check_clarification()   → needs_user_input, question
  └── build_execution_plan()  → [ExecutionStep, ...]
       │
       ▼
RouterDecision (dataclass)
       │
       │  if needs_user_input → return clarify immediately (no execution)
       │
       ▼
module_executor.execute_plan()
  ├── step: memory_load  → tr_loader.load_scope()
  ├── step: web_call     → web_search / web_scraper / web_crawler
  ├── step: module_call  → core.modules.<module>.execute(decision, memory, web)
  └── step: validation   → output_validator.validate(module, output, validation_type)
       │
       ▼
Result dict:
  {
    <module output keys>,
    "_validation": { ok, issues, validation_type },
    "_events":     [ event, ... ],
    "_elapsed_ms": float,
  }
       │
       ▼
API response:
  {
    "action":     "respond" | "clarify",
    "decision":   RouterDecision.to_dict(),
    "result":     { module output },
    "validation": { ok, issues, validation_type },
    "events":     [ routing events + execution events ],
    "elapsed_ms": float,
  }
```

## Event flow

Events are the ONLY source of truth for UI state. Two event pools are merged:

1. **Routing events** — emitted inside `ceo_router.route_request()`, stored in local list, 
   accessible via `ctx.events_emitted`. Currently not yet plumbed to the API response 
   (pending future pass — executor events are returned).

2. **Execution events** — emitted inside `module_executor.execute_plan()`, 
   returned in `result["_events"]`, merged into response `events` list.

## Key invariants

- `module_executor` receives `decision.to_dict()` — a plain dict, not the dataclass.
  Modules never import RouterDecision directly.
- Modules receive exactly `(decision_dict, memory_dict, web_results_dict)`.
- Memory is loaded BEFORE module_call. Module cannot trigger its own load.
- Web is fetched BEFORE module_call. Module cannot trigger its own fetch.
- Validation runs AFTER module_call. Validation result is advisory — 
  it is returned to the caller, not used to block the response automatically.

## Tier depth flow

```
decide_tier_visibility() → "free_limited"
       │
       ▼
get_depth_constraints(module, "free_limited")
       → { max_results: 3, sources_shown: False, ... }
       │
       ▼
module.execute() reads constraints from decision_dict["tier_depth"]
  (CEO adds constraints to decision if tier = free_limited)
```

Note: depth constraints are currently advisory. Modules must read and apply them.
CEO plumbing of `tier_depth` into `decision_dict` is a future pass.
