# Mini Assistant - All-in-One Local AI Assistant

A sleek, modern AI assistant system powered by local and free models with cyan and violet theme. Features include chat, voice control, file management, command execution, web search, codebase search, and project profiles.

## Features

✅ **Local Ollama Chat Assistant** - Chat with local LLMs (Llama 3.2, Mistral, Phi-3, etc.)
✅ **Voice Mode** - Speech-to-Text (Whisper) + Text-to-Speech (gTTS)
✅ **File Manager** - Browse, view, and edit workspace files
✅ **Command Terminal** - Execute allowlisted commands safely
✅ **Web Search** - DuckDuckGo powered web search
✅ **Codebase Search** - Fast grep-based code search across your projects
✅ **Project Profiles** - Save and manage project-specific commands
✅ **FixLoop Ready** - Error analysis using AI (future enhancement)
✅ **Futuristic UI** - Modern dark theme with cyan and violet gradient accents

## Tech Stack

### Backend
- **FastAPI** - High-performance Python web framework
- **Ollama** - Local LLM inference (llama3.2, mistral, phi3, etc.)
- **Faster-Whisper** - Local speech-to-text (4x faster than OpenAI Whisper)
- **gTTS** - Google Text-to-Speech for voice output
- **FAISS** - Vector database for semantic search (future enhancement)
- **DuckDuckGo Search** - Free web search API
- **MongoDB** - Database for storing project profiles

### Frontend
- **React 19** - Modern UI framework
- **Tailwind CSS** - Utility-first styling
- **Shadcn/UI** - Component library
- **Lucide React** - Icon library
- **Sonner** - Toast notifications
- **Axios** - HTTP client

## Prerequisites

### 1. Install Ollama (Required for Chat)

**macOS/Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
Download from https://ollama.com/download

**Verify Installation:**
```bash
ollama --version
```

### 2. Pull Models

Pull at least one model to get started:

```bash
# Recommended: Llama 3.2 (default)
ollama pull llama3.2

# Or try other models:
ollama pull llama3.2:1b  # Faster, smaller model
ollama pull llama3.2:3b  # Balanced
ollama pull mistral      # Good for reasoning
ollama pull phi3         # Efficient
```

**List installed models:**
```bash
ollama list
```

### 3. Start Ollama Service

**Linux/macOS:**
```bash
ollama serve
```

**Windows:** Ollama runs as a service automatically after installation.

**Verify:** Visit http://localhost:11434 - you should see "Ollama is running"

## Quick Start

The application is already running! Just ensure:

1. ✅ Ollama is installed and running (`ollama serve`)
2. ✅ At least one model is downloaded (`ollama pull llama3.2`)
3. ✅ Visit the app at: `https://jarvis-hub-12.preview.emergentagent.com`

## Usage Guide

### 1. AI Chat
- Select your preferred model from the dropdown (LLAMA 3.2, MISTRAL, PHI-3, etc.)
- Type your message and press Enter or click SEND
- Chat history is maintained during your session
- Use "Clear" to reset the conversation

### 2. Voice Mode
- Click "START RECORDING" to begin voice input
- Speak your question
- Click "STOP RECORDING" when done
- The system will:
  - Transcribe your speech (Whisper)
  - Send to Ollama for processing
  - Read the response aloud (TTS)

### 3. File Manager
- Browse through `/app` directory
- Click on folders to navigate
- Click on files to view content
- Click "EDIT" to modify files
- Click "SAVE" to save changes

### 4. Command Terminal
- Execute safe commands (ls, pwd, cat, echo, grep, find, etc.)
- View stdout, stderr, and return codes
- Commands are restricted to an allowlist for security
- Use "CLEAR" to reset terminal output

### 5. Web Search
- Enter your search query
- Press Enter or click "SEARCH"
- Browse results with titles, URLs, and snippets
- Click any result to open in a new tab

### 6. Codebase Search
- Search for code patterns or text
- Specify the search path (default: /app)
- View matching files with line numbers
- Results show file paths and matched content

### 7. Project Profiles
- Create profiles for different projects
- Save project-specific commands
- Store project paths and descriptions
- Quick access to frequently used commands

## Architecture

```
/app/
├── backend/
│   ├── server.py           # Main FastAPI application
│   ├── requirements.txt    # Python dependencies
│   └── .env               # Environment variables
├── frontend/
│   ├── src/
│   │   ├── App.js          # Main React app
│   │   ├── App.css         # Global styles
│   │   ├── index.css       # Tailwind + custom CSS
│   │   ├── pages/
│   │   │   └── Dashboard.js  # Main dashboard layout
│   │   └── components/
│   │       ├── Chat/       # Chat interface
│   │       ├── Voice/      # Voice control
│   │       ├── Files/      # File explorer
│   │       ├── Terminal/   # Command terminal
│   │       ├── Search/     # Web & code search
│   │       └── Profiles/   # Project profiles
│   └── package.json
└── README.md
```

## API Endpoints

### Chat
- `POST /api/chat` - Send messages to Ollama
- `GET /api/health` - Check service status

### Voice
- `POST /api/voice/stt` - Speech to text (upload audio file)
- `POST /api/voice/tts` - Text to speech (returns audio stream)

### Files
- `POST /api/files/list` - List directory contents
- `POST /api/files/read` - Read file content
- `POST /api/files/write` - Write file content

### Commands
- `POST /api/commands/execute` - Execute allowlisted commands

### Search
- `POST /api/search/web` - Web search via DuckDuckGo
- `POST /api/search/codebase` - Grep-based code search

### Profiles
- `GET /api/profiles` - List all project profiles
- `POST /api/profiles` - Create new profile
- `DELETE /api/profiles/{id}` - Delete profile

### FixLoop
- `POST /api/fixloop/analyze` - Analyze errors with AI

## Troubleshooting

### "Ollama service not available"
**Solution:** Make sure Ollama is running:
```bash
ollama serve
```
Check http://localhost:11434 to verify.

### "Model not found"
**Solution:** Pull the model first:
```bash
ollama pull llama3.2
```

### Voice recording not working
**Solution:** 
- Grant microphone permissions in your browser
- Use HTTPS (required for microphone access)

### Slow performance
**Solution:**
- Use smaller models like `llama3.2:1b` for faster responses
- Adjust `compute_type` in Whisper (int8 is faster)
- Consider GPU acceleration if available

## Model Recommendations

### Fast & Efficient (1-3GB RAM)
- `llama3.2:1b` - Fastest, good for simple queries
- `phi3` - Efficient, good quality

### Balanced (4-8GB RAM)
- `llama3.2` or `llama3.2:3b` - **Recommended** - Best balance
- `mistral` - Excellent reasoning

### High Quality (16GB+ RAM)
- `llama3.2:70b` - Best quality (requires powerful hardware)
- `mixtral` - High quality mix of experts model

## Future Enhancements

🔮 **FAISS Semantic Search** - Vector-based semantic code search
🔮 **Auto-Indexing Watcher** - Real-time codebase indexing
🔮 **FixLoop Auto-Patch** - Automatic error fixing
🔮 **Local Image Generation** - Stable Diffusion integration
🔮 **Advanced Voice Features** - Wake word detection, continuous conversation
🔮 **Multi-Project Support** - Switch between projects seamlessly
🔮 **Custom Agents** - Create specialized AI agents for different tasks

## Design System

The UI follows a modern, futuristic design:
- **Colors:** Deep black backgrounds with electric cyan (#00f3ff) and violet (#9333ea) gradient accents
- **Typography:** Orbitron/Rajdhani for headers, JetBrains Mono for code, Inter for body
- **Effects:** Glass-morphism, gradient glows, smooth animations
- **Layout:** Bento grid, sidebar navigation, dark theme by default

## License

This project uses:
- Ollama (MIT)
- Faster-Whisper (MIT)
- FastAPI (MIT)
- React (MIT)
- Other open source libraries

## Credits

Built with ❤️ using local and free AI models.

**Key Technologies:**
- [Ollama](https://ollama.com) - Local LLM runtime
- [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) - Speech recognition
- [FastAPI](https://fastapi.tiangolo.com) - Web framework
- [React](https://react.dev) - UI framework
- [Tailwind CSS](https://tailwindcss.com) - Styling

---

**Status:** ✅ ONLINE | **Version:** 1.0.0 | **Powered by:** Local AI Models
=======
# Mini Assistant

This repository contains the Mini Assistant project.
>>>>>>> 1a48297 (Add README)
