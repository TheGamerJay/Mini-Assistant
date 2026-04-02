# Memory System — Global Rules

## Architecture

The Mini Assistant uses **Targeted Retrieval (TR)** memory.
- Flat JSON files per user per module per key
- No embeddings. No vector databases. No RAG pipelines.
- CEO is the ONLY controller of what gets loaded.
- All memory is module-isolated — no cross-contamination.

## Memory file structure

```
memory_store/tr/
  {user_id}/
    task_assist/
      user_profile.json
      resume.json
      skills.json
      applications.json
      last_followup.json
      message_history.json
      tone_preferences.json
    campaign_lab/
      campaign_profile.json
      past_campaigns.json
      concept.json
      hooks.json
      cta_patterns.json
      ... (see memory_scopes.py for full list)
    builder/
      project_context.json
      task_state.json
      prior_code.json
    core_chat/
      recent_turns.json
    image/
      style_preferences.json
    image_edit/
      source_metadata.json
```

## CEO retrieval control

1. `memory_decider.decide_memory(module, intent, message)` — decides IF memory is needed and WHICH scope
2. For `task_assist`: delegates to `task_assist_retrieval.get_scope(message)` — task-type-specific
3. For `campaign_lab`: delegates to `campaign_lab_retrieval.get_scope(message)` — task-type-specific
4. For all others: uses a fixed default scope from `_FIXED_SCOPES`
5. `tr_loader.load_scope(user_id, module, scope_str)` — executes the load

## Memory isolation rules

- `task_assist` memory NEVER bleeds into `campaign_lab` and vice versa
- `builder` memory is project-specific — never shared across users
- `web_intelligence` has NO persistent memory (web only, live data)
- CEO may NOT mix scopes across modules unless explicitly routed
- No module may call `tr_loader` directly — only `module_executor` does

## Retrieval prioritization

1. Most recent entries (newest first within each key)
2. Matching role/company/platform
3. Exact match preferred over partial
4. Fallback to user_profile / campaign_profile if specific data missing
5. If required memory is MISSING → ask the user. NEVER fabricate.

## What memory must NEVER do

- Load full history dumps
- Inject irrelevant memory into module context
- Use embeddings or similarity search
- Bypass CEO routing
- Fabricate missing data
- Cross-contaminate module memory

## Fail-safe rules (Phase 30 — Memory + Web combined)

System is considered FAILING if ANY of the following occur:

### Memory failures
- Full history is loaded (not scoped)
- Irrelevant memory is injected into a module
- Memory retrieval bypasses CEO (module self-loads)
- Embeddings or vector DB are used anywhere in the retrieval path
- Missing memory is fabricated instead of surfaced to the user

### Web failures
- Web tools run without CEO routing
- Raw HTML is passed forward to a generation module
- Web data is used without running `web_validator`
- Excessive pages are crawled (> 5 per request)
- A crawl enters a loop

### General retrieval failures
- A brain fetches context it is not allowed to retrieve (see `rag_discipline.py`)
- The context budget is exceeded (more than top-N items loaded)
- CEO control is bypassed at any retrieval point
