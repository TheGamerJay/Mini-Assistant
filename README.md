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

## Icons

Static files in `/static`:

- favicon.ico + png sizes
- manifest.json
- robots.txt