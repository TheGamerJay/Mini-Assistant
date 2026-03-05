# Mini Assistant - Product Requirements Document

## Original Problem Statement
Build an "all-in-one Jarvis" AI assistant application with the following features:
- Local Ollama chat assistant
- Web search tool
- Workspace file edit tools
- Allowlisted command runner
- FAISS for fast codebase search
- Watcher for auto-indexing ("learn as you build")
- Project Profiles (save/list/run commands per repo)
- FixLoop (run → read error → patch → rerun)
- Voice mode (STT + TTS)
- Theme: Cyan and Violet
- App name: Mini Assistant

## Tech Stack
- **Frontend**: React (Create React App) with Tailwind CSS
- **Backend**: FastAPI (Python)
- **Database**: MongoDB (Motor async driver)
- **Local AI**: Ollama for LLM, FAISS for vector search
- **Voice**: Faster-Whisper (STT), gTTS (TTS)

## Architecture
```
/app
├── backend/
│   ├── server.py          # Main FastAPI application (all endpoints)
│   ├── requirements.txt   # Python dependencies
│   └── .env              # Environment variables
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   └── Dashboard.js    # Main layout with 23 tabs
│   │   ├── components/
│   │   │   ├── Chat/           # AI Chat + Summarization
│   │   │   ├── Voice/          # Voice control
│   │   │   ├── Files/          # File explorer
│   │   │   ├── Terminal/       # Command terminal
│   │   │   ├── Search/         # Web & Code search
│   │   │   ├── Profiles/       # Project profiles
│   │   │   ├── AppBuilder/     # App builder
│   │   │   ├── CodeReview/     # Code review
│   │   │   ├── CodeRunner/     # Code runner
│   │   │   ├── APITester/      # API testing
│   │   │   ├── TesterAgent/    # Automated testing (NEW)
│   │   │   ├── FixLoop/        # Auto error fix (NEW)
│   │   │   ├── PostgreSQL/     # PostgreSQL manager (NEW)
│   │   │   ├── Redis/          # Redis manager (NEW)
│   │   │   ├── Railway/        # Railway deployment (NEW)
│   │   │   ├── DatabaseDesigner/
│   │   │   ├── PackageManager/
│   │   │   ├── EnvManager/
│   │   │   ├── SnippetLibrary/
│   │   │   ├── Git/            # Git integration
│   │   │   ├── DevTools/       # Regex, JSON, Markdown, Color
│   │   │   └── AdvancedTools/  # Security, Deploy, Docker, Monitor
│   │   └── App.js
│   └── package.json
└── vscode-extension/           # VS Code extension scaffold
```

## Implemented Features (23 Total Tabs)

### Core Features (P0) ✅
1. **AI Chat** - Local Ollama chat with model selection
2. **Conversation Summarization** - Summarize long conversations
3. **Web Search** - DuckDuckGo integration
4. **Codebase Search** - Grep-based code search
5. **File Explorer** - Browse, read, edit files
6. **Terminal** - Execute allowlisted commands
7. **Voice Control** - STT (Whisper) and TTS (gTTS)

### Developer Tools (P1) ✅
1. **App Builder** - Generate apps with AI
2. **Code Review** - AI-powered code review
3. **Code Runner** - Execute code snippets
4. **API Tester** - HTTP request testing
5. **Tester Agent** - Automated testing with AI suggestions (NEW)
6. **FixLoop** - Auto error detection & AI-powered fixes (NEW)
7. **Database Designer** - Schema visualization
8. **Package Manager** - npm/pip package management
9. **Environment Manager** - Manage env variables
10. **Snippet Library** - Code snippets storage
11. **Git Integration** - Git commands, GitHub

### Database & Infrastructure (NEW P1) ✅
1. **PostgreSQL** - Connect, query, browse tables/schemas
2. **Redis** - Key-value browser, cache management
3. **Railway** - Deploy to Railway, manage projects/services

### Utility Tools (P1) ✅
1. **Dev Tools** - Regex Tester, JSON Formatter, Markdown Preview, Color Picker
2. **Advanced Tools** - Security Scanner, Deploy, Docker, Performance Monitor

### Project Management ✅
1. **Project Profiles** - Save/load project configs

## New API Endpoints (December 2025)

### PostgreSQL
- `POST /api/postgres/connect` - Test connection
- `POST /api/postgres/query` - Execute SQL query
- `POST /api/postgres/tables` - List tables
- `POST /api/postgres/schema` - Get table schema

### Redis
- `POST /api/redis/connect` - Connect to Redis
- `POST /api/redis/keys` - List all keys
- `POST /api/redis/get` - Get key value
- `POST /api/redis/set` - Set key value
- `POST /api/redis/delete` - Delete key

### Railway
- `POST /api/railway/projects` - List projects
- `POST /api/railway/services` - List services
- `POST /api/railway/deploy` - Trigger deployment

### FixLoop
- `POST /api/fixloop/start` - Analyze URL for errors with real screenshot capture
- `GET /api/fixloop/sessions` - Get session history
- `GET /api/fixloop/screenshot/{session_id}` - Get captured screenshot image

### Tester Agent
- `POST /api/tester/run` - Run automated tests
- `POST /api/tester/generate` - AI generate test cases
- `GET /api/tester/history` - Get test run history

## Testing Status
- Backend: 100% pass rate (34/34 tests)
- Frontend: 100% pass rate (23 tabs working)
- Test reports: `/app/test_reports/iteration_1.json`, `/app/test_reports/iteration_2.json`

## Backlog / Future Tasks (P2)
1. AI Pair Programming - Real-time code suggestions
2. One-Click Deploy - Full Vercel/Netlify integration with API tokens
3. Database GUI - Visual DB management
4. UI from Screenshot - Convert images to code
5. Live Code Sharing - Collaborative coding
6. Full FAISS integration for semantic code search

---
Last Updated: December 2025
