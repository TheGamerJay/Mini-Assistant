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
│   │   │   └── Dashboard.js    # Main layout with tabs
│   │   ├── components/
│   │   │   ├── Chat/           # AI Chat interface
│   │   │   ├── Voice/          # Voice control
│   │   │   ├── Files/          # File explorer
│   │   │   ├── Terminal/       # Command terminal
│   │   │   ├── Search/         # Web & Code search
│   │   │   ├── Profiles/       # Project profiles
│   │   │   ├── AppBuilder/     # App builder
│   │   │   ├── CodeReview/     # Code review
│   │   │   ├── CodeRunner/     # Code runner
│   │   │   ├── APITester/      # API testing
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

## Implemented Features

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
5. **Database Designer** - Schema visualization
6. **Package Manager** - npm/pip package management
7. **Environment Manager** - Manage env variables
8. **Snippet Library** - Code snippets storage
9. **Git Integration** - Git commands, GitHub

### Utility Tools (P1) ✅
1. **Dev Tools**
   - Regex Tester
   - JSON Formatter
   - Markdown Preview
   - Color Picker

2. **Advanced Tools**
   - Security Scanner
   - Deploy (Vercel/Netlify/Railway - MOCKED)
   - Docker Management
   - Performance Monitor

### Project Management ✅
1. **Project Profiles** - Save/load project configs

## API Endpoints

### Chat
- `POST /api/chat` - Send message to Ollama
- `POST /api/chat/summarize` - Summarize conversation

### Search
- `POST /api/search/web` - Web search (DuckDuckGo)
- `POST /api/search/codebase` - Code search (grep)

### Files
- `POST /api/files/list` - List directory
- `POST /api/files/read` - Read file
- `POST /api/files/write` - Write file

### Voice
- `POST /api/voice/stt` - Speech to text
- `POST /api/voice/tts` - Text to speech

### Commands
- `POST /api/commands/execute` - Run shell command

### Git
- `POST /api/git-command` - Execute git commands

### Advanced Tools
- `POST /api/security/scan` - Scan code for vulnerabilities
- `POST /api/deploy/start` - Start deployment (MOCKED)
- `GET /api/docker/containers` - List Docker containers
- `POST /api/docker/start/{id}` - Start container
- `POST /api/docker/stop/{id}` - Stop container
- `GET /api/monitor/performance` - Get system metrics

### Health
- `GET /api/health` - Health check

## User Requirements (From Chat)
1. ✅ Local and free models (Ollama)
2. ✅ Cyan and Violet theme
3. ✅ Name: Mini Assistant
4. ✅ GitHub integration
5. ✅ VS Code extension scaffold
6. ✅ Conversation summarization

## Known Limitations
1. Deploy endpoint is MOCKED - needs API tokens for real deployment
2. Ollama must be running locally for chat features
3. Docker commands require Docker to be installed
4. Voice features require audio device access

## Testing Status
- Backend: 100% pass rate
- Frontend: 100% pass rate
- Test file: `/app/backend/tests/test_mini_assistant.py`
- Test report: `/app/test_reports/iteration_1.json`

## Backlog / Future Tasks (P2)
1. AI Pair Programming - Real-time code suggestions
2. One-Click Deploy - Full Vercel/Netlify integration with API tokens
3. Database GUI - Visual DB management
4. UI from Screenshot - Convert images to code
5. Live Code Sharing - Collaborative coding
6. Full FAISS integration for semantic code search
7. FixLoop automation

---
Last Updated: December 2025
