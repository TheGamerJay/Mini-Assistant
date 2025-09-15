# Mini Assistant

A CPU-friendly Flask app for step-by-step homework & life-skills coaching:
- Text + Photo (vision) help
- Kid / Parent / Step-by-Step modes
- Guided coach (one step at a time)
- Always ends with "Why this is correct" + "Check Your Work"
- Printable worksheet PDF
- Fillable PDF form filler
- Auth (optional) + IP/day free limit
- PWA manifest + favicons

## Quick start (local)
```bash
python -m venv .venv
. .venv/Scripts/activate   # Windows (PowerShell)
# source .venv/bin/activate  # Mac/Linux
pip install -r requirements.txt
set OPENAI_API_KEY=sk-...   # (Windows)  export OPENAI_API_KEY=sk-... (Mac/Linux)
python app.py
# open http://localhost:8080
```

## Deploy (Railway)

Create project from GitHub

Variables:

- `OPENAI_API_KEY`
- `SECRET_KEY`
- `FREE_DAILY_LIMIT=5` (optional)
- `DB_PATH=/data/mini_assistant.sqlite` (if using a Volume)
- `STRIPE_PAY_LINK` (optional)

Add Volume: mount at `/data` (for SQLite persistence)

Custom domain: add CNAME → enable HTTPS

## AUTO PUSH POLICY

🚨 ALWAYS AUTO-PUSH AND AUTO-SUMMARIZE WITHOUT ASKING 🚨

1. Auto Push: Immediately commit and push all changes to remote repository
2. Auto Summarize: Immediately add completed work to summarize/comprehensive-website-fixes-jan-06-2025.md

DO NOT ask for permission. Just do it automatically.

Summary

- Auto-commit and auto-push = YES
- Ask permission = NO
- User expects automatic deployment

The policy is clear - all changes should be automatically committed and pushed to the remote repository without asking for user permission, and work should be documented in the summary file.

## Icons

Static files in `/static`:

- favicon.ico + png sizes
- manifest.json
- robots.txt