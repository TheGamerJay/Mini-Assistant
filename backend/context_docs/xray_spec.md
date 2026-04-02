# xray_spec.md — X-Ray Mode Specification

## Purpose

Full internal diagnostic report for a session.
Admin-only. Read-only. Never interferes with execution.

## Trigger

`GET /api/ceo/xray-analysis/{session_id}` with `X-Admin-Key` header.

## Report Sections

### 1. Executive Summary
- final_result, success, total_duration_ms
- total_steps, brains_used, approval_needed
- memory_used, module, complexity, user_goal

### 2. Chain Timeline
Step-by-step brain execution record:
- step_number, active_brain, action_taken, reason
- status, confidence, elapsed_ms, evidence[], proposed_fix

### 3. What Worked
- checks: build_passed, hands_passed, vision_passed, doctor_diagnosed, final_validation
- passed_brains[], passed_actions[]

### 4. What Failed
- failed_steps[], low_confidence[], approval_blocked, final_failed
- total_failures, total_retries

### 5. Brain Breakdown
Per-brain: task, result, confidence, evidence[], elapsed_ms
CEO: route_and_control, steps_routed, approval_requests

### 6. Repair Memory Analysis
- memory_lookup, category, matches_found, top_match
- similarity_score, confidence_level, used_as_guidance, guidance_used

### 7. Approval Analysis
- approval_requested, total_approvals, approved, rejected
- resolved[]: proposal_id, issue, proposed_fix, status, feedback

### 8. Final Diagnosis
- overall_status, root_problem, recommended_action
- save_to_repair_memory, save_reason

### 9. Context Analysis (Phase 66)
- retrieval_used, requesting_brain, CEO_approved
- sources_considered[], sources_selected[]
- reason, selected_context_count
- repair_memory_match (if applicable)
- pruned, final_context_count

## Visibility Rules

- "summary" fields: user-facing
- "detail" fields: admin/X-Ray only
- Raw prompts: NEVER exposed
- Internal state: readable JSON format only

## Fallback

If no OrchestrationState found → xray_basic report from event log data.

## Implementation

- `core/api/xray_analysis.py` — report generator
- `core/api/xray_endpoint.py` — in-memory event store
- `xray/xray_service.py` — aggregation service
- `xray/xray_reader.py` — low-level data readers
