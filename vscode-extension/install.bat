@echo off
REM Mini Assistant VS Code Extension - Windows Install Script

echo Installing Mini Assistant VS Code Extension...
echo.

REM Check if VS Code is installed
where code >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo VS Code not found. Please install VS Code first.
    echo Download: https://code.visualstudio.com/
    pause
    exit /b 1
)

echo VS Code found

REM Get extensions directory
set EXT_DIR=%USERPROFILE%\\.vscode\\extensions

echo Extensions directory: %EXT_DIR%

REM Create directory if doesn't exist
if not exist \"%EXT_DIR%\" mkdir \"%EXT_DIR%\"

REM Copy extension
echo Installing extension...
xcopy /E /I /Y \"\\app\\vscode-extension\" \"%EXT_DIR%\\mini-assistant-1.0.0\"

if %ERRORLEVEL% EQU 0 (
    echo Extension installed successfully!
) else (
    echo Failed to install extension
    pause
    exit /b 1
)

echo.
echo ========================================
echo Mini Assistant Extension Installed!
echo ========================================
echo.
echo Next steps:
echo   1. Reload VS Code (Ctrl+Shift+P - Reload Window)
echo   2. Press Ctrl+Shift+M to open Mini Assistant
echo   3. Right-click in any file for options
echo.
echo Happy coding!
echo.
pause
