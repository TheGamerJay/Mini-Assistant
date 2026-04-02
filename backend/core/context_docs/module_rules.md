# Module System — Rules and Fail-Safes

## Module inventory

| Module           | Intent          | Output type        | LLM | Structured |
|------------------|-----------------|--------------------|-----|-----------|
| core_chat        | general_chat    | plain response     | Yes | No        |
| task_assist      | task_assist     | professional text  | Yes | No        |
| campaign_lab     | campaign_lab    | marketing content  | Yes | No        |
| web_intelligence | web_lookup      | search results     | Yes | No        |
| builder          | builder         | build_output       | Yes | **Yes**   |
| doctor           | debug           | repair_output      | Yes | **Yes**   |
| vision           | image_analyze   | vision_output      | Yes | **Yes**   |
| hands            | execute         | hands_output       | No  | **Yes**   |
| image            | image_generate  | image url/base64   | Yes | No        |
| image_edit       | image_edit      | edited image       | Yes | No        |

## Phase 38 — Module interaction rules

1. **Modules NEVER call each other directly.**
   - Builder does not call Doctor. Doctor does not call Hands. Vision does not call Builder.
   - All inter-module coordination flows through CEO → execution_plan.
   - If multiple modules are needed, CEO builds a multi-step plan.

2. **Modules operate only on their assigned task.**
   - A module receives `(decision_dict, memory_dict, web_results_dict)`.
   - It may NOT read from other modules' memory.
   - It may NOT modify the decision or execution plan.

3. **No shared hidden state.**
   - Modules are stateless within a single execution pass.
   - State persistence (repair_memory, task_state) is done via TR memory, written by CEO.

4. **No cross-module contamination.**
   - Builder memory is builder-only. Doctor repair_memory is doctor-only.
   - task_assist memory never bleeds into campaign_lab.

## Phase 39 — Module validation integration

All module outputs go through `output_validator.validate(module, output, validation_type)`.

| Module           | Validation type      | Key checks                                      |
|------------------|----------------------|-------------------------------------------------|
| builder          | structured_code      | type=build_output, files present, code present  |
| doctor           | repair_output        | type=repair_output, root_cause not vague, fix present |
| vision           | vision_output        | type=vision_output, analysis grounded, lists present |
| hands            | hands_output         | type=hands_output, actions list, summary present|
| task_assist      | professional_content | non-empty, sufficient length, no fabrication    |
| campaign_lab     | marketing_content    | non-empty, CTA present, no false claims         |
| web_intelligence | web_content          | results list, at least one result               |
| image            | image_output         | image_url or base64 present                     |
| image_edit       | image_output         | image_url or base64 present                     |
| core_chat        | general_chat         | non-empty response                              |

**No output bypasses validation.** Validation runs as the final step in every execution plan.

## Phase 40 — Fail-safe rules (modules)

System is considered FAILING if ANY of the following occur:

### Builder failures
- Returns plain text instead of structured `build_output` dict
- `type` field is missing or not `"build_output"`
- `files` list is empty for a non-trivial build
- Components are listed in the plan but missing from files
- Code contains obvious placeholders (`# TODO`, `pass`, `...`) without explanation
- File paths are unrealistic or broken
- Missing imports or broken dependency references

### Doctor failures
- Returns without a `root_cause` field
- `root_cause` contains "unknown", "unclear", "might be" without confidence = "low"
- Returns guesses without traceback, logs, or code evidence
- Confidence is "high" when only a user description was provided

### Vision failures
- Returns analysis of an image when no attachment was provided
- `analysis` contains elements not visible in the image (hallucination)
- `type` field is not `"vision_output"`

### Hands failures
- Executes destructive actions autonomously (without CEO routing)
- Returns without an `actions` list
- Reports actions as completed when in limited mode

### General module failures
- Any module calls another module directly
- Any module loads its own memory (bypasses CEO/module_executor)
- Any module modifies the execution plan
- Any module output bypasses validation
- Any structured module returns plain text instead of the required dict format
