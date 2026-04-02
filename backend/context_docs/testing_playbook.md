# testing_playbook.md — System Testing Playbook

## CEO Router

Test: intent classification
  → Send "fix this bug" → expect intent=debug, module=doctor
  → Send "build a login page" → expect intent=builder, module=builder
  → Send "what time is it" → expect truth_type=live_current

Test: module selection
  → intent=debug → module=doctor
  → intent=image_analyze → module=vision
  → intent=execute → module=hands

Test: complexity detection
  → Single clear task → simple
  → "Build a full-stack app with auth and payments" → full_system

## Retrieval Engine

Test: CEO-only retrieval
  → Simulate brain attempting self-fetch → must be rejected
  → CEO retrieval with no matching context → returns empty selected_context

Test: context pruning
  → Load 10 context items, task relevance low → max 3 returned

Test: repair memory integration
  → Known problem text → must find match with score ≥ 0.50
  → Unrelated text → must return no matches above threshold

## Truth Classifier

Test: stable_knowledge
  → "What is Python?" → truth_type=stable_knowledge, no search needed

Test: live_current
  → "What time is it?" → truth_type=live_current, tool_required=true
  → "What's the weather?" → truth_type=live_current, tool_required=true

Test: search_dependent
  → "What happened in the news today?" → truth_type=search_dependent
  → "Latest version of React?" → truth_type=search_dependent

Test: fail-safe
  → live_current with no tool → must return cannot_verify response
  → Never hallucinate current data

## Search Pipeline

Test: query rewriting
  → "latest react version" → expanded query variants

Test: web validation
  → Low-trust domain (reddit.com) → trust_ok=False
  → Irrelevant content → relevance_ok=False

Test: grounded answer
  → Search result with clear answer → answer includes source citation
  → Search fails → returns "search unavailable" message

## Builder Mode

Test: build loop limits
  → Simulate 3 consecutive builder failures → escalate to Doctor

Test: QA loop limits
  → Simulate 2 QA failures → escalate to Doctor

Test: approval gate
  → Doctor proposes fix → status=needs_approval
  → User rejects → next_step=ask for alternative
  → User approves → Builder executes fix → full QA again

## Repair Memory

Test: save conditions
  → Attempt save without approval → must fail
  → Full conditions met → save succeeds

Test: duplicate detection
  → Save problem A, then attempt save of similar problem → blocked, returns match

Test: similarity scoring
  → Identical text → score ~1.0 (HIGH)
  → Completely different text → score < 0.25 (IGNORE)

## Validation

Test: build_output validation
  → Plain text output → validation fails
  → Missing files[] key → validation fails
  → Real code in files[] → passes

Test: repair_output validation
  → Missing root_cause → fails
  → Vague root_cause ("unknown") with confidence=high → fails

## X-Ray

Test: report generation
  → Active session → generates 8-section report
  → No orchestration state → generates xray_basic from logs

Test: admin key enforcement
  → Missing key → 403
  → Wrong key → 403
  → Correct key → 200
