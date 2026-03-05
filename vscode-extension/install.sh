#!/bin/bash

# Mini Assistant VS Code Extension - Quick Install Script

echo "🚀 Installing Mini Assistant VS Code Extension..."
echo ""

# Check if VS Code is installed
if ! command -v code &> /dev/null; then
    echo "❌ VS Code not found. Please install VS Code first."
    echo "   Download: https://code.visualstudio.com/"
    exit 1
fi

echo "✓ VS Code found"

# Get VS Code extensions directory
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    EXT_DIR="$HOME/.vscode/extensions"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    EXT_DIR="$HOME/.vscode/extensions"
else
    # Windows (Git Bash)
    EXT_DIR="$USERPROFILE/.vscode/extensions"
fi

echo "📁 Extensions directory: $EXT_DIR"

# Create extensions directory if it doesn't exist
mkdir -p "$EXT_DIR"

# Copy extension
echo "📦 Installing extension..."
cp -r /app/vscode-extension "$EXT_DIR/mini-assistant-1.0.0"

if [ $? -eq 0 ]; then
    echo "✓ Extension copied successfully"
else
    echo "❌ Failed to copy extension"
    exit 1
fi

echo ""
echo "✅ Mini Assistant extension installed successfully!"
echo ""
echo "📖 Next steps:"
echo "   1. Reload VS Code (Ctrl+Shift+P → 'Reload Window')"
echo "   2. Press Ctrl+Shift+M to open Mini Assistant"
echo "   3. Right-click in any file to see Mini Assistant options"
echo ""
echo "💡 Tip: Check status bar for Mini Assistant button"
echo ""
echo "🎉 Happy coding!"
