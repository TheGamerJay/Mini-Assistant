# Mini Casino World

A modern casino gaming platform with JWT authentication and React frontend:
- JWT-based user authentication
- Three casino games (Blackjack, Roulette, Slots)
- Wallet system with chip deposits
- Single-file Flask API backend
- React frontend with Tailwind CSS
- PostgreSQL database with SQLAlchemy
- CORS-enabled API for cross-origin requests

## Quick start (local)
```bash
# 1) Create venv and install deps
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # Mac/Linux
pip install -r requirements.txt

# 2) Set up environment
cp .env.example .env
# Edit .env with your PostgreSQL DATABASE_URL and SECRET_KEY

# 3) Initialize database
# Set environment variables:
# Windows PowerShell:
$env:DATABASE_URL="postgresql://USERNAME:PASSWORD@HOST:PORT/dbname"
$env:SECRET_KEY="your-secret-key-here"
# Mac/Linux:
# export DATABASE_URL="postgresql://USERNAME:PASSWORD@HOST:PORT/dbname"
# export SECRET_KEY="your-secret-key-here"

# Create tables (run app.py once to auto-create)
python app.py
# Press Ctrl+C to stop after "Running on http://0.0.0.0:8080"

# 4) Run the app
python app.py
# Frontend: Open http://localhost:8080 and use the React UI
# API: Backend runs on same port with /api/* endpoints
```

## Deploy (Railway)

Create project from GitHub

Required Variables:

- `SECRET_KEY` (required for JWT tokens)
- `DATABASE_URL` (PostgreSQL connection string)
- `PORT=8080` (optional, defaults to 8080)

Optional Variables:

- `LOAD_SEED=1` (creates demo games on startup)

Custom domain: add CNAME → enable HTTPS

## API Endpoints

### Authentication
- `POST /api/auth/register` - Create account
- `POST /api/auth/login` - Login and get JWT token

### Wallet
- `GET /api/users/me/balance` - Get current balance
- `POST /api/wallet/deposit` - Add chips to account

### Games
- `POST /api/blackjack/play` - Play blackjack hand
- `POST /api/roulette/bet` - Place roulette bet
- `POST /api/slots/spin` - Spin slot machine

### Health
- `GET /healthz` - Health check

All authenticated endpoints require `Authorization: Bearer <jwt_token>` header.

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