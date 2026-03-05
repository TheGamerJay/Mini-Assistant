# Mini Assistant - Local Setup Guide

Complete guide to run Mini Assistant on your local machine.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Detailed Setup](#detailed-setup)
- [Configuration](#configuration)
- [Optional Services](#optional-services)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

| Software | Version | Download |
|----------|---------|----------|
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| Python | 3.10+ | [python.org](https://python.org) |
| MongoDB | 6.0+ | [mongodb.com](https://www.mongodb.com/try/download/community) |
| Ollama | Latest | [ollama.com](https://ollama.com) |
| Git | Latest | [git-scm.com](https://git-scm.com) |

### System Requirements
- **OS**: Windows 10+, macOS 10.15+, or Linux (Ubuntu 20.04+)
- **RAM**: 8GB minimum (16GB recommended for AI features)
- **Storage**: 10GB free space
- **GPU**: Optional but recommended for faster AI inference

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/mini-assistant.git
cd mini-assistant

# 2. Run the setup script (creates .env files and installs dependencies)
chmod +x setup.sh
./setup.sh

# 3. Start MongoDB (in a separate terminal)
mongod

# 4. Start Ollama (in a separate terminal)
ollama serve

# 5. Pull an AI model
ollama pull llama3.2

# 6. Start the backend (in a separate terminal)
cd backend
source venv/bin/activate
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# 7. Start the frontend (in a separate terminal)
cd frontend
yarn start

# 8. Open http://localhost:3000 in your browser
```

---

## Detailed Setup

### Step 1: Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/mini-assistant.git
cd mini-assistant
```

### Step 2: Install MongoDB

#### macOS (Homebrew)
```bash
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community
```

#### Ubuntu/Debian
```bash
wget -qO - https://www.mongodb.org/static/pgp/server-6.0.asc | sudo apt-key add -
echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list
sudo apt update
sudo apt install -y mongodb-org
sudo systemctl start mongod
sudo systemctl enable mongod
```

#### Windows
1. Download from [mongodb.com](https://www.mongodb.com/try/download/community)
2. Run the installer (choose "Complete" installation)
3. MongoDB will run as a Windows service automatically

#### Alternative: MongoDB Atlas (Cloud - Free Tier)
1. Go to [mongodb.com/atlas](https://www.mongodb.com/atlas)
2. Create a free cluster
3. Get your connection string
4. Use it in your `.env` file

### Step 3: Install Ollama

#### macOS
```bash
brew install ollama
```

#### Linux
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

#### Windows
Download and run the installer from [ollama.com](https://ollama.com)

#### Pull AI Models
```bash
# Start Ollama service
ollama serve

# In another terminal, pull models
ollama pull llama3.2        # Default model (3.2GB)
ollama pull llama3.2:1b     # Smaller/faster (1.3GB)
ollama pull mistral         # Alternative model (4.1GB)
ollama pull phi3            # Microsoft's model (2.3GB)
```

### Step 4: Setup Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright for FixLoop screenshots
python -m playwright install chromium
python -m playwright install-deps  # Linux only

# Create environment file
cat > .env << EOF
MONGO_URL=mongodb://localhost:27017
DB_NAME=mini_assistant
EOF
```

### Step 5: Setup Frontend

```bash
cd frontend

# Install Node.js dependencies (use yarn, not npm)
yarn install

# Create environment file
cat > .env << EOF
REACT_APP_BACKEND_URL=http://localhost:8001
EOF
```

### Step 6: Start the Application

You'll need **4 terminal windows**:

#### Terminal 1: MongoDB
```bash
# If not running as a service
mongod --dbpath /path/to/data/db
```

#### Terminal 2: Ollama
```bash
ollama serve
```

#### Terminal 3: Backend
```bash
cd backend
source venv/bin/activate  # or venv\Scripts\activate on Windows
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

#### Terminal 4: Frontend
```bash
cd frontend
yarn start
```

### Step 7: Access the App

Open your browser and go to: **http://localhost:3000**

---

## Configuration

### Backend Environment Variables (`backend/.env`)

```env
# Required
MONGO_URL=mongodb://localhost:27017
DB_NAME=mini_assistant

# Optional - for Railway integration
RAILWAY_API_TOKEN=your_railway_token

# Optional - for PostgreSQL features
POSTGRES_URL=postgresql://user:pass@localhost:5432/dbname

# Optional - for Redis features
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
```

### Frontend Environment Variables (`frontend/.env`)

```env
REACT_APP_BACKEND_URL=http://localhost:8001
```

---

## Optional Services

### PostgreSQL (for PostgreSQL Manager tab)

#### macOS
```bash
brew install postgresql
brew services start postgresql
createdb mini_assistant
```

#### Ubuntu/Debian
```bash
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo -u postgres createdb mini_assistant
```

#### Connection String Format
```
postgresql://username:password@localhost:5432/database_name
```

### Redis (for Redis Manager tab)

#### macOS
```bash
brew install redis
brew services start redis
```

#### Ubuntu/Debian
```bash
sudo apt install redis-server
sudo systemctl start redis
```

#### Windows
Download from [github.com/microsoftarchive/redis/releases](https://github.com/microsoftarchive/redis/releases)

### Railway (for Railway deployment tab)

1. Create account at [railway.app](https://railway.app)
2. Go to [railway.app/account/tokens](https://railway.app/account/tokens)
3. Generate a new token
4. Enter the token in the Railway tab in Mini Assistant

---

## Features Overview

| Tab | Description | Requirements |
|-----|-------------|--------------|
| Chat | AI conversation with Ollama | Ollama running |
| App Builder | Generate apps with AI | Ollama running |
| Code Review | AI-powered code review | Ollama running |
| Code Runner | Execute code snippets | Python/Node.js |
| API Tester | Test HTTP endpoints | None |
| Tester Agent | Automated testing | None |
| FixLoop | Screenshot errors & AI fixes | Playwright installed |
| PostgreSQL | Database management | PostgreSQL server |
| Redis | Cache management | Redis server |
| Railway | Deploy to Railway | Railway API token |
| DB Designer | Schema visualization | None |
| Git & GitHub | Version control | Git installed |
| Packages | npm/pip management | Node.js/Python |
| Env Vars | Environment management | None |
| Snippets | Code snippet library | None |
| Dev Tools | Regex, JSON, Color tools | None |
| Advanced | Security, Docker, Monitor | Docker (optional) |
| Files | File explorer | None |
| Terminal | Command execution | None |
| Web Search | DuckDuckGo search | Internet connection |
| Code Search | Codebase grep search | None |
| Voice | Speech-to-text, text-to-speech | Microphone |
| Profiles | Project configurations | None |

---

## Troubleshooting

### Backend won't start

**Error**: `ModuleNotFoundError: No module named 'xxx'`
```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

**Error**: `Connection refused` to MongoDB
```bash
# Check if MongoDB is running
mongosh --eval "db.adminCommand('ping')"

# Start MongoDB
brew services start mongodb-community  # macOS
sudo systemctl start mongod            # Linux
```

### Frontend won't start

**Error**: `ENOENT: no such file or directory`
```bash
cd frontend
rm -rf node_modules
yarn install
```

**Error**: Port 3000 already in use
```bash
# Find and kill the process
lsof -i :3000
kill -9 <PID>
```

### Ollama issues

**Error**: `Ollama not available`
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve
```

**Error**: Model not found
```bash
# Pull the model
ollama pull llama3.2
```

### FixLoop screenshots not working

**Error**: Playwright not installed
```bash
cd backend
source venv/bin/activate
pip install playwright
python -m playwright install chromium
python -m playwright install-deps  # Linux only
```

### Voice features not working

- Ensure your browser has microphone permissions
- Use HTTPS or localhost (required for Web Speech API)
- Check browser console for errors

---

## Running in Production

### Using PM2 (Node.js Process Manager)

```bash
# Install PM2
npm install -g pm2

# Start backend
cd backend
pm2 start "uvicorn server:app --host 0.0.0.0 --port 8001" --name mini-backend

# Build and serve frontend
cd frontend
yarn build
pm2 serve build 3000 --name mini-frontend

# Save PM2 configuration
pm2 save
pm2 startup
```

### Using Docker (Coming Soon)

A `docker-compose.yml` file will be added for containerized deployment.

---

## Updating

```bash
# Pull latest changes
git pull origin main

# Update backend dependencies
cd backend
source venv/bin/activate
pip install -r requirements.txt

# Update frontend dependencies
cd ../frontend
yarn install

# Restart services
```

---

## Support

- **Issues**: Open a GitHub issue
- **Documentation**: See `/app/memory/PRD.md` for full feature list
- **API Reference**: Backend runs on `http://localhost:8001/docs` (Swagger UI)

---

## License

MIT License - See LICENSE file for details.
