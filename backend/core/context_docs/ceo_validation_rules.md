# CEO Router — Validation Decision Rules

## When validation runs

Validation runs as the FINAL step in every execution plan, after `module_call`.
It cannot be skipped for any module (see `_SKIP_VALIDATION_MODULES = {}` in execution_planner.py).

## Validation type → module mapping

| Module           | Validation type        |
|------------------|------------------------|
| core_chat        | general_chat           |
| task_assist      | professional_content   |
| campaign_lab     | marketing_content      |
| web_intelligence | web_content            |
| builder          | structured_code        |
| image            | image_output           |
| image_edit       | image_output           |

## Per-type rules

### general_chat
- response field exists and is non-empty

### professional_content (task_assist)
- response exists, length >= 50 chars
- no fabricated-limitation phrases ("as an AI language model", etc.)

### marketing_content (campaign_lab)
- response exists
- at least one CTA indicator present (buy, get, try, sign up, subscribe, etc.)
- no unverified universal claims ("100% guaranteed", "proven X%", etc.)

### web_content (web_intelligence)
- results/web_results list exists
- at least one result in the list
- module did not return error status

### structured_code (builder)
- code or files field present
- if text: contains code markers (```, def, class, function, import, etc.)
- if files list: non-empty

### image_output (image / image_edit)
- module did not return error status
- image_url, url, image_base64, base64, or data field present

## Validation result shape

```json
{
  "ok":              true,
  "issues":          [],
  "validation_type": "professional_content"
}
```

On failure:
```json
{
  "ok":              false,
  "issues":          ["response is too short for professional content"],
  "validation_type": "professional_content"
}
```

## What validation does NOT do

- Does not block the response. Validation result is advisory — the API returns it
  alongside the module output. The caller decides what to do with a failed validation.
- Does not retry the module. Re-execution on validation failure is a future feature.
- Does not apply to streaming. Streaming output is validated post-generation via
  safe_return() in image_system/api/server.py — CEO validation applies to non-streaming.

## Fail-safe rules

1. Validation never raises. If the validator throws, `ok=True, reason="validation_unavailable"` 
   is returned so the response is not silently dropped.
2. The legacy validator (mini_assistant/system/validation.py) is tried first.
   If unavailable, built-in rules are applied.
3. Unknown validation_type defaults to general_chat rules.
