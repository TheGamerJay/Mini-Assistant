# project_context.md — Project Context

## What Is Mini Assistant?

A full-stack AI assistant for software development.
Runs locally. No cloud dependency for execution (only LLM API calls).

## Tech Stack

| Layer      | Tech                                    |
|------------|-----------------------------------------|
| Frontend   | React (Craco), Tailwind CSS, Lucide     |
| Backend    | Python FastAPI + Flask (image server)   |
| LLM        | Anthropic Claude (claude-sonnet-4-6)    |
| Deployment | Railway — Docker multi-stage build      |
| Storage    | MongoDB (user data), JSON files (state) |

## Key Components

- `backend/server.py` — main FastAPI server
- `backend/image_system/api/server.py` — image + chat server (mounted at /image-api)
- `frontend/src/` — React app
- `backend/core/` — CEO Router + all brain modules
- `backend/context/` — session context storage
- `backend/internal_library/repair_memory/` — repair knowledge base
- `backend/logs/` — NDJSON execution logs
- `backend/xray/` — X-Ray diagnostic service

## Modes

- **Chat mode** — general conversation and code tasks
- **Builder mode** — multi-brain orchestration for complex builds
- **Image Edit mode** — vision-guided image manipulation
- **Campaign Lab** — ad copy and image prompt generation
- **Task Assist** — structured professional writing tasks

## User Tiers

- `free_limited` — usage caps, watermarks on images
- `standard` — full chat, limited builder
- `pro` — all features, higher limits
- `admin` — no limits, X-Ray access, admin dashboard

## External APIs Used

- Anthropic Messages API (claude-sonnet-4-6) — all LLM calls
- Replicate API — image generation/editing
- Resend — transactional email
- Stripe — billing and subscriptions
