# Mini Casino World

A CPU-friendly Flask app for entertainment casino gaming:
- User authentication with Flask-Login
- Casino games (Blackjack, Roulette, Slots)
- Entertainment chips with no monetary value
- Password reset with email tokens
- Multi-backend mailer (Resend/SMTP/echo)
- Responsive casino-themed UI
- Secure session management
- PWA manifest + favicons

## Quick start (local)
```bash
# 1) Create venv and install deps
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # Mac/Linux
pip install -r requirements.txt

# 2) Set up environment
cp .env.example .env
# Edit .env with your PostgreSQL DATABASE_URL

# 3) Initialize database schema
# Windows PowerShell:
$env:DATABASE_URL="postgresql://USERNAME:PASSWORD@HOST:PORT/railway"
$env:LOAD_SEED="1"  # Optional: load demo games
# Mac/Linux:
# export DATABASE_URL="postgresql://USERNAME:PASSWORD@HOST:PORT/railway"
# export LOAD_SEED="1"

python scripts/init_db.py

# 4) Run the app
python app.py
# open http://localhost:5000
```

## Deploy (Railway)

Create project from GitHub

Variables:

- `SECRET_KEY` (required)
- `DATABASE_URL=sqlite:///mcw.db` (or PostgreSQL URL)
- `APP_BASE_URL=https://your-domain.com` (for email links)
- `RESEND_API_KEY` and `RESEND_FROM` (for email)
- OR `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` (SMTP fallback)
- `DEV_MAIL_ECHO=true` (for development)

Add Volume: mount at `/data` (for SQLite persistence) - optional

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