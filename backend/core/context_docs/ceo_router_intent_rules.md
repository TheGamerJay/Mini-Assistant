# CEO Router — Intent Rules

## The 7 CEO intents

These are coarser than phase1's 13 execution intents.
CEO cares about MODULE selection. Phase1 handles execution detail.

| CEO Intent     | Triggers                                                               |
|----------------|------------------------------------------------------------------------|
| general_chat   | anything not matched below — Q&A, explanation, conversation            |
| task_assist    | resume, cover letter, job application, follow-up, professional email   |
| campaign_lab   | ad copy, campaign, promo, hook, CTA, marketing, audience               |
| web_lookup     | latest, current, right now, search, news, live data, stock, weather    |
| builder        | build app, make app, create dashboard, add feature, add backend        |
| image_generate | generate/draw/create/render + image/picture/artwork/visual             |
| image_edit     | edit/modify/change + image AND an attachment is present                |

## Priority order (when multiple intents match)

1. image_edit — requires attachment, most specific
2. builder — "build" context is usually unambiguous
3. task_assist — professional context signals are specific
4. campaign_lab — marketing signals are specific
5. image_generate — generate + visual noun
6. web_lookup — recency signals
7. general_chat — fallback

## Secondary intent

CEO may detect a secondary intent (e.g. web_lookup + task_assist for
"find me the latest resume template and write me a cover letter").

The execution plan will handle both if complexity allows.
Primary module is selected first. Secondary is a follow-up step if needed.

## What intent detection does NOT do

- Does not consider mode_hint from UI
- Does not read prior conversation history (that is phase1's job)
- Does not consider user tier
