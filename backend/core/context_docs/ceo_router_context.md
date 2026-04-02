# CEO Router — System Context

## What this is

The CEO Router is the single decision authority for all user requests in Mini Assistant.

Every message — regardless of source — flows through `core/ceo_router.py → route_request()`.

CEO produces a `RouterDecision`. That decision is executed by `module_executor.py`.

## What CEO does NOT do

- Does not execute any module
- Does not call the AI model
- Does not load memory
- Does not run web searches
- Does not generate responses

CEO only decides. Everything else follows the decision.

## Decision pipeline (in order)

1. `intent_classifier.py` — detect what the user wants (7 CEO intents)
2. `complexity_detector.py` — simple / multi_step / full_system
3. `module_selector.py` — map intent → module name
4. `memory_decider.py` — should TR memory be loaded? what scope?
5. `web_decider.py` — is web needed? what mode?
6. `clarification_engine.py` — must we ask before acting?
7. `tier_controller.py` — what does this tier get to see?
8. `execution_planner.py` — ordered list of steps

## Module names

| Intent         | Module           |
|----------------|------------------|
| general_chat   | core_chat        |
| task_assist    | task_assist      |
| campaign_lab   | campaign_lab     |
| web_lookup     | web_intelligence |
| builder        | builder          |
| image_generate | image            |
| image_edit     | image_edit       |

## Integration with existing system

The existing `image_system/api/server.py` remains the execution backend.
CEO sits in front of it. The decision from CEO is passed to module_executor,
which routes to the correct existing pipeline.

No existing code was deleted. CEO is additive.
