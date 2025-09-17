# Mini Casino World Setup Guide

## Frontend Development

The React UI component is located at `src/MiniCasinoUI.jsx`. To integrate with a React project:

1. **Install dependencies:**
```bash
npm install react react-dom
# Tailwind CSS is used for styling - ensure it's configured
```

2. **Import and use the component:**
```jsx
import MiniCasinoUI from './src/MiniCasinoUI.jsx'

function App() {
  return <MiniCasinoUI />
}
```

3. **Environment variables for API base:**
```bash
# .env file for Vite
VITE_API_BASE=http://localhost:8080

# or use MCW_API_BASE
MCW_API_BASE=http://localhost:8080
```

## Backend API

The Flask backend (`app.py`) provides a complete casino gaming API with JWT authentication.

### Required Environment Variables

```bash
# Required
SECRET_KEY=your-jwt-secret-key
DATABASE_URL=postgresql://user:pass@host:port/dbname

# Optional
PORT=8080
LOAD_SEED=1  # Creates demo games on startup
```

### Database Schema

The app automatically creates tables on startup:

- **users**: User accounts with balance
- **games**: Available casino games
- **bets**: Game play records

## Development Workflow

1. **Backend**: Run `python app.py` (port 8080)
2. **Frontend**: Serve the React component or integrate into your app
3. **Database**: PostgreSQL required (Railway, local, etc.)

## Authentication Flow

1. User registers/logins via `/api/auth/register` or `/api/auth/login`
2. Backend returns JWT access token (7-day expiry)
3. Frontend stores token in localStorage as `mcw_token`
4. All game/wallet requests include `Authorization: Bearer <token>` header

## Game Logic

- **Blackjack**: Auto-play strategy (hit until 17+), 3:2 blackjack payout
- **Roulette**: Red/black bets only, European single-zero wheel
- **Slots**: 7-symbol reel with various payouts

All games use decimal precision for financial calculations and atomic database transactions.