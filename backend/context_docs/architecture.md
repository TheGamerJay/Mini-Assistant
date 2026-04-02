# architecture.md — CEO Router Architecture

## Data Flow

```
User Request
    │
    ▼
CEO Router (ceo_router.py)
    │
    ├── Intent Classification (intent_classifier.py)
    ├── Complexity Detection (complexity_detector.py)
    ├── Truth Classification (truth_classifier.py)       ← Phase 67
    ├── Module Selection (module_selector.py)
    ├── Tier Control (tier_controller.py)
    ├── Memory Decision (memory_decider.py)
    ├── Retrieval Engine (retrieval_engine.py)            ← Phase 64-65
    │
    ▼
Module Executor (module_executor.py)
    │
    ├── Memory Loading
    ├── Web Intelligence (if needed)
    ├── Module Execution
    ├── Validation (output_validator.py)
    ├── Checkpoint (checkpoint_manager.py)
    │
    ▼
Response → User
```

## Builder Mode Orchestration

```
CEO → Builder → CEO
CEO → Hands QA → CEO
CEO → Vision QA → CEO (frontend only)
CEO → Doctor (on failure) → CEO → Approval Gate → User
User approves → CEO → Builder (fix) → QA → CEO
```

## Brain Modules

| Brain   | Entry Point                    | Output Type     |
|---------|--------------------------------|-----------------|
| builder | core/modules/builder.py        | build_output    |
| doctor  | core/modules/doctor.py         | repair_output   |
| hands   | core/modules/hands.py          | hands_output    |
| vision  | core/modules/vision.py         | vision_output   |

## Context System (Phase 62+)

```
CEO
 │
 ├── ContextStore.load(session_id, mode)
 │     → chat context OR image_edit context
 │
 ├── RetrievalEngine.retrieve(...)
 │     → ranked, pruned context subset
 │
 └── Brain receives ONLY approved context
```

## Truth Routing (Phase 67+)

```
Request → TruthClassifier
    │
    ├── stable_knowledge → general_chat module
    ├── live_current → tool required (time/weather/etc)
    ├── search_dependent → SearchPipeline
    └── mixed → SearchPipeline + general_chat
```

## Retrieval Discipline

- CEO is the ONLY retrieval authority
- Brains NEVER self-fetch context
- Context is ranked by relevance before brain access
- Max 1-3 repair memory matches passed to any brain
- Context budget enforced per source type

## Event Pipeline

Every CEO pipeline event → event_emitter.emit() → logs/events.log (NDJSON)
Error events → logs/errors.log
Validation events → logs/validation.log
