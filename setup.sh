#!/bin/bash

# Mini Assistant - Setup Script
# This script sets up the development environment

set -e

echo "=========================================="
echo "   Mini Assistant - Setup Script"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for required commands
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}Error: $1 is not installed${NC}"
        echo "Please install $1 and try again"
        exit 1
    else
        echo -e "${GREEN}✓${NC} $1 found"
    fi
}

echo "Checking prerequisites..."
echo ""

check_command "node"
check_command "python3"
check_command "git"

# Check Node version
NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo -e "${RED}Error: Node.js 18+ is required (found v$NODE_VERSION)${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Node.js version OK"

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [ "$PYTHON_VERSION" -lt 10 ]; then
    echo -e "${YELLOW}Warning: Python 3.10+ is recommended${NC}"
fi
echo -e "${GREEN}✓${NC} Python version OK"

echo ""
echo "Setting up backend..."
echo ""

cd backend

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt -q

# Install Playwright for screenshots
echo "Installing Playwright browsers..."
python -m playwright install chromium 2>/dev/null || true

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating backend .env file..."
    cat > .env << EOF
MONGO_URL=mongodb://localhost:27017
DB_NAME=mini_assistant
EOF
    echo -e "${GREEN}✓${NC} Created backend/.env"
else
    echo -e "${YELLOW}!${NC} backend/.env already exists, skipping"
fi

cd ..

echo ""
echo "Setting up frontend..."
echo ""

cd frontend

# Install dependencies
echo "Installing Node.js dependencies..."
if command -v yarn &> /dev/null; then
    yarn install --silent
else
    npm install --silent
fi

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating frontend .env file..."
    cat > .env << EOF
REACT_APP_BACKEND_URL=http://localhost:8001
EOF
    echo -e "${GREEN}✓${NC} Created frontend/.env"
else
    echo -e "${YELLOW}!${NC} frontend/.env already exists, skipping"
fi

cd ..

echo ""
echo "=========================================="
echo -e "${GREEN}Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Start MongoDB:"
echo "   mongod"
echo ""
echo "2. Start Ollama and pull a model:"
echo "   ollama serve"
echo "   ollama pull llama3.2"
echo ""
echo "3. Start the backend:"
echo "   cd backend"
echo "   source venv/bin/activate"
echo "   uvicorn server:app --host 0.0.0.0 --port 8001 --reload"
echo ""
echo "4. Start the frontend (new terminal):"
echo "   cd frontend"
echo "   yarn start"
echo ""
echo "5. Open http://localhost:3000 in your browser"
echo ""
echo "For detailed instructions, see SETUP_GUIDE.md"
echo ""
