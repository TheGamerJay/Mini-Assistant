# UX + Control — Fail-Safe Rules (Phase 50)

## Core principle

The system must be honest, responsive, and controllable at all times.
Users must never see fake states, be surprised by unexpected execution,
or have their input silently ignored.

---

## Phase 41 — Real-time event streaming rules

System FAILS if:
- UI displays states that were not emitted as real events
- Fake "thinking" or typing indicators are shown
- Progress is simulated rather than reflecting actual execution steps
- Events are reordered or invented

Correct behavior:
- Every visible UI state maps 1:1 to a real emitted event
- `step_started` / `step_finished` bracket every execution step
- `output_ready` is the ONLY trigger for showing final output
- `partial_output` is the ONLY trigger for showing intermediate content

---

## Phase 42 — Checkpoint system rules

System FAILS if:
- Checkpoints do not match actual execution steps
- Execution continues past a checkpoint with `requires_user_input: True`
- Checkpoints are invented (not created by real execution events)
- Paused state is not preserved across UI interactions
- Revision data is not applied before resumption

Correct behavior:
- Checkpoints are created at: post_plan, post_module, pre_validation, post_validation
- `post_plan` with `complexity = full_system` always `requires_user_input = True`
- `post_validation` with `ok = False` always `requires_user_input = True`
- Completed checkpoints cannot be re-opened
- `get_pending_checkpoint()` is authoritative — executor must respect it

---

## Phase 43 — Clarification rules

System FAILS if:
- Clarification is triggered for non-critical optional info
- Clarification question is vague ("please provide more details")
- Execution proceeds without resolving required clarification
- Options are not meaningful choices
- Clarification is asked for information the user already provided

Correct behavior:
- Clarification triggers only when input is genuinely required
- Every clarification has a specific `question`, `options[]`, and `reason`
- `options` must be 2-3 concrete labeled choices (A/B/C) or empty []
- Execution halts completely until clarification is resolved

---

## Phase 44 — Partial output rules

System FAILS if:
- Partial output is invented or speculative
- Partial output contradicts the final output
- Partial state is displayed without indicating incomplete status
- `partial_output` events are emitted without real intermediate data

Correct behavior:
- `partial_output` is emitted only when real intermediate data exists
- Each partial output includes a `stage` label (e.g., "plan_built", "component_1")
- Partial output is a subset of final output — never contradicts it

---

## Phase 45 — Error handling rules

System FAILS if:
- Errors are hidden or swallowed silently
- Error messages are vague ("something went wrong")
- No recovery options are presented after failure
- The system retries indefinitely without surfacing the failure

Correct behavior:
- Every error surfaces with `type`, `error_type`, `issue`, `recovery_options`, `next_step`
- Recovery options are actionable (retry, simplify, provide data, switch approach)
- Module failure → `module_failure` error with specific error message
- Validation failure → `validation_failure` error with specific issues list
- Web failure → `web_failure` error with mode and error message

---

## Phase 46 — User control rules

System FAILS if:
- User input (pause, reject, modify) is ignored and execution continues
- Plan changes bypass CEO re-evaluation
- Execution continues after a rejected step
- Control state (paused, pending mods) leaks between sessions

Correct behavior:
- All control actions emit `user_control` events
- Paused sessions stay paused until `resume_execution()` is called
- Plan modifications queue via `_PENDING_MODS` and are read before next step
- CEO must re-route after `modify_plan` — no blind continuation
- `clear_session_controls()` is called on mode change

---

## Phase 47 — Tier experience rules

System FAILS if:
- Free users are blocked from core functionality (not just depth)
- Intelligence or output quality is degraded based on tier
- Paid features leak to free users
- Tier filtering removes the output entirely (user gets nothing)

Correct behavior:
- Free users receive full intelligence — only depth is limited
- `free_limited` modules return complete summaries with truncated detail
- `blocked` modules redirect to `core_chat` — no error, no blank
- Watermark is a metadata flag (`_watermark: True`) — never a hard error
- Tier note (`_tier_note`) is included so UI can show upgrade prompt

---

## Phase 48 — Session memory rules

System FAILS if:
- Session state leaks between modes (chat → builder → image contamination)
- Expired session state is used as if current
- Session memory is persisted to disk (it must be in-memory only)
- Session state accumulates without TTL-based expiry

Correct behavior:
- `on_mode_change()` is called whenever mode changes — clears old mode state
- Default TTL is 30 minutes — expired state is reset on access
- Each (session_id, mode) pair has its own isolated `SessionState`
- `clear_session()` is called on session end

---

## Phase 49 — X-Ray mode rules

System FAILS if:
- X-Ray detail is shown to regular users by default
- X-Ray endpoint is accessible without admin auth
- X-Ray data is stale (not updated after each execution)
- User-facing events endpoint includes detail payloads

Correct behavior:
- `GET /api/ceo/xray/{session_id}` requires `X-Admin-Key` header
- `GET /api/ceo/events/{session_id}` returns summary-only (no detail)
- X-Ray data is stored via `store_xray_data()` after every chat execution
- X-Ray shows: decision, plan, all events (with detail), checkpoints, validation, session state
