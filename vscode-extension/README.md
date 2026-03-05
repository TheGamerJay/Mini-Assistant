# Mini Assistant VS Code Extension

Integrate the powerful Mini Assistant directly into Visual Studio Code! Access AI chat, code review, API testing, and 17+ developer tools without leaving your editor.

## 🚀 Features

### **Right-Click Context Menu:**
- **Review Current File** - AI-powered code analysis
- **Fix Code Issues** - Automatic bug fixing
- **Run in Code Runner** - Execute Python/JavaScript instantly
- **Ask AI About This** - Get explanations for selected code
- **Save as Snippet** - Save code to snippet library

### **Command Palette (Ctrl+Shift+P):**
- `Mini Assistant: Open` - Open main panel
- `Mini Assistant: Review Current File`
- `Mini Assistant: Fix Code Issues`
- `Mini Assistant: Test API`
- `Mini Assistant: Quick Git Commit`
- `Mini Assistant: Format JSON`
- `Mini Assistant: Save as Snippet`

### **Keyboard Shortcuts:**
- `Ctrl+Shift+M` (Cmd+Shift+M on Mac) - Open Mini Assistant
- `Ctrl+Shift+R` (Cmd+Shift+R on Mac) - Review current file
- `Ctrl+Shift+A` (Cmd+Shift+A on Mac) - Ask AI about selection

### **Status Bar:**
- Quick access button in status bar
- Click to open Mini Assistant instantly

## 📦 Installation

### Method 1: Install from VSIX (Recommended)

1. **Package the extension:**
   ```bash
   cd /app/vscode-extension
   npm install -g vsce
   vsce package
   ```

2. **Install in VS Code:**
   - Open VS Code
   - Press `Ctrl+Shift+P` (Cmd+Shift+P on Mac)
   - Type "Install from VSIX"
   - Select `mini-assistant-1.0.0.vsix`

### Method 2: Development Mode

1. **Copy extension to VS Code extensions folder:**
   ```bash
   # Linux/Mac
   cp -r /app/vscode-extension ~/.vscode/extensions/mini-assistant
   
   # Windows
   xcopy /E /I /app/vscode-extension %USERPROFILE%\\.vscode\\extensions\\mini-assistant
   ```

2. **Reload VS Code:**
   - Press `Ctrl+Shift+P` (Cmd+Shift+P on Mac)
   - Type "Reload Window"
   - Press Enter

### Method 3: VS Code Marketplace (Future)

Once published, install directly from VS Code marketplace.

## ⚙️ Configuration

Open VS Code settings (`Ctrl+,`) and search for "Mini Assistant":

```json
{
  \"miniAssistant.serverUrl\": \"https://jarvis-hub-12.preview.emergentagent.com\",
  \"miniAssistant.autoOpen\": false,
  \"miniAssistant.showInStatusBar\": true
}
```

**Settings:**
- `miniAssistant.serverUrl` - Your Mini Assistant server URL
- `miniAssistant.autoOpen` - Open Mini Assistant when VS Code starts
- `miniAssistant.showInStatusBar` - Show status bar button

## 🎯 Usage Examples

### 1. Review Code
1. Open any code file
2. Right-click in editor
3. Select "Mini Assistant: Review Current File"
4. See AI analysis in Mini Assistant panel

### 2. Fix Bugs
1. Select problematic code
2. Right-click → "Mini Assistant: Fix Code Issues"
3. Get fixed code instantly

### 3. Run Code
1. Write Python or JavaScript
2. Right-click → "Mini Assistant: Run in Code Runner"
3. See output in real-time

### 4. Ask AI
1. Select code snippet
2. Press `Ctrl+Shift+A`
3. Type your question
4. Get AI explanation

### 5. Test API
1. Press `Ctrl+Shift+P`
2. Type "Mini Assistant: Test API"
3. Enter API URL
4. View response in API Tester

### 6. Save Snippets
1. Select useful code
2. Right-click → "Mini Assistant: Save as Snippet"
3. Enter title
4. Reuse later from Snippet Library

## 🔌 Integration Features

### Seamless Workflow
- **Panel Integration** - Mini Assistant opens beside your editor
- **Context Awareness** - Automatically passes current file info
- **Two-Way Communication** - Actions in Mini Assistant can affect VS Code
- **Persistent State** - Panel stays open when switching files

### All Mini Assistant Features Available:
1. **AI Chat** - Ollama-powered conversations
2. **App Builder** - Generate full apps
3. **Code Review** - AI-powered analysis
4. **Code Runner** - Execute code live
5. **API Tester** - Test REST APIs
6. **Database Designer** - Visual schemas
7. **Git & GitHub** - Version control
8. **Package Manager** - Install npm/pip
9. **Env Manager** - Edit .env files
10. **Snippet Library** - Code snippets
11. **Dev Tools** - Regex, JSON, Markdown, Colors
12. **File Manager** - Browse files
13. **Terminal** - Run commands
14. **Web Search** - Internet search
15. **Code Search** - Codebase search
16. **Voice Mode** - STT + TTS
17. **Profiles** - Project configs

## 🛠️ Development

### Build Extension
```bash
cd /app/vscode-extension
npm install
vsce package
```

### Debug Extension
1. Open `/app/vscode-extension` in VS Code
2. Press F5 to launch Extension Development Host
3. Test features in new window

### Publish to Marketplace
```bash
vsce login <publisher>
vsce publish
```

## 📝 Requirements

- VS Code 1.80.0 or higher
- Mini Assistant server running
- Node.js (for development)

## 🔧 Troubleshooting

### Extension not appearing
1. Check VS Code version (should be 1.80.0+)
2. Reload window: `Ctrl+Shift+P` → "Reload Window"
3. Check extension is enabled: `Ctrl+Shift+P` → "Extensions"

### Mini Assistant not loading
1. Verify server URL in settings
2. Check Mini Assistant is running
3. Try opening in browser first to test

### Commands not working
1. Reload window
2. Check keyboard shortcuts: `Ctrl+K Ctrl+S`
3. Look for conflicts with other extensions

## 🎨 Customization

### Change Server URL
If running Mini Assistant locally or on custom domain:

1. Open settings
2. Find "Mini Assistant: Server Url"
3. Update to your URL
4. Reload window

### Customize Keyboard Shortcuts
1. Press `Ctrl+K Ctrl+S`
2. Search "Mini Assistant"
3. Click pencil icon to change binding

## 📚 Resources

- **Mini Assistant Docs:** `/app/README.md`
- **Setup Guide:** `/app/SETUP_GUIDE.md`
- **Git Guide:** `/app/GIT_INTEGRATION_GUIDE.md`

## 🤝 Support

Issues or questions? 
- Check troubleshooting section
- Review Mini Assistant documentation
- Ensure Ollama is running for AI features

## 📄 License

MIT

## 🎉 What's Next?

Try these workflows:
1. Open your project in VS Code
2. Right-click any file → "Review Current File"
3. Press `Ctrl+Shift+M` to open full Mini Assistant
4. Use all 17 features without leaving VS Code!

**Mini Assistant + VS Code = Perfect Development Environment! 🚀**
