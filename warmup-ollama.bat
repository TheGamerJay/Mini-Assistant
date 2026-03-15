@echo off
echo Warming up Ollama models...
echo This window will close automatically when done.

REM Wait for Ollama to finish starting (5 seconds)
timeout /t 5 /nobreak >nul

REM Load both models with 2-hour keep_alive in background
start /b "" curl -s -m 300 http://localhost:11434/api/generate -d "{\"model\":\"gemma3:4b\",\"prompt\":\"hi\",\"keep_alive\":\"2h\",\"stream\":false}" -o nul
start /b "" curl -s -m 300 http://localhost:11434/api/generate -d "{\"model\":\"moondream:latest\",\"prompt\":\"hi\",\"keep_alive\":\"2h\",\"stream\":false}" -o nul

echo Models loading in background (takes ~2 min first time).
echo You can close this window.
