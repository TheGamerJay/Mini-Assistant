# Mini Assistant + VS Code - Complete Integration Guide

## 🎉 Your Mini Assistant is now available in VS Code!

### **What You Get:**
- Mini Assistant panel **inside** VS Code
- Right-click context menu for quick actions
- Keyboard shortcuts for common tasks
- Status bar integration
- All 17 features accessible without leaving your editor

---

## 📦 Installation (Choose One Method)

### **Method 1: Quick Install Script (Easiest)**

**Linux/Mac:**
```bash
cd /app/vscode-extension
./install.sh
```

**Windows:**
```cmd
cd \\app\\vscode-extension
install.bat
```

Then:
1. Reload VS Code: `Ctrl+Shift+P` → "Reload Window"
2. Done! ✅

---

### **Method 2: Manual Install**

**Step 1: Copy Extension**

Linux/Mac:
```bash
cp -r /app/vscode-extension ~/.vscode/extensions/mini-assistant-1.0.0
```

Windows (PowerShell):
```powershell
Copy-Item -Recurse -Force "\\app\\vscode-extension" "$env:USERPROFILE\\.vscode\\extensions\\mini-assistant-1.0.0"
```

**Step 2: Reload VS Code**
- Press `Ctrl+Shift+P` (Cmd+Shift+P on Mac)
- Type "Reload Window"
- Press Enter

---

### **Method 3: Package & Install VSIX (For Distribution)**

**Step 1: Install vsce (once)**
```bash
npm install -g vsce
```

**Step 2: Package Extension**
```bash
cd /app/vscode-extension
vsce package
```

**Step 3: Install VSIX**
- Open VS Code
- Press `Ctrl+Shift+P` (Cmd+Shift+P)
- Type "Install from VSIX"
- Select `mini-assistant-1.0.0.vsix`

---

## ⚙️ Configuration

After installation, configure Mini Assistant:

1. Open VS Code Settings: `Ctrl+,` (Cmd+, on Mac)
2. Search for "Mini Assistant"
3. Configure:

```json
{
  "miniAssistant.serverUrl": "http://localhost:8000",
  "miniAssistant.autoOpen": false,
  "miniAssistant.showInStatusBar": true
}
```

**Settings Explained:**
- `serverUrl` - Your Mini Assistant URL (change if running locally)
- `autoOpen` - Open panel automatically when VS Code starts
- `showInStatusBar` - Show quick access button in status bar

---

## 🎯 How to Use

### **Opening Mini Assistant**

**Option 1: Status Bar**
- Click "⚡ Mini Assistant" button in bottom-right

**Option 2: Command Palette**
- Press `Ctrl+Shift+P` (Cmd+Shift+P)
- Type "Mini Assistant: Open"
- Press Enter

**Option 3: Keyboard Shortcut**
- Press `Ctrl+Shift+M` (Cmd+Shift+M on Mac)

---

### **Quick Actions via Right-Click**

1. **Review Code:**
   - Right-click in editor
   - Select "Mini Assistant: Review Current File"
   - AI analysis appears in Mini Assistant panel

2. **Fix Bugs:**
   - Select problematic code
   - Right-click → "Mini Assistant: Fix Code Issues"
   - Get automatic fixes

3. **Run Code:**
   - Right-click in Python/JavaScript file
   - Select "Mini Assistant: Run in Code Runner"
   - See output instantly

4. **Ask AI:**
   - Select code snippet
   - Right-click → "Mini Assistant: Ask AI About This"
   - Enter your question
   - Get explanation

5. **Save Snippet:**
   - Select useful code
   - Right-click → "Mini Assistant: Save as Snippet"
   - Reuse later

---

### **Keyboard Shortcuts**

| Action | Windows/Linux | Mac |
|--------|---------------|-----|
| Open Mini Assistant | `Ctrl+Shift+M` | `Cmd+Shift+M` |
| Review Current File | `Ctrl+Shift+R` | `Cmd+Shift+R` |
| Ask AI About Selection | `Ctrl+Shift+A` | `Cmd+Shift+A` |

**Change Shortcuts:**
1. Press `Ctrl+K Ctrl+S` (Cmd+K Cmd+S)
2. Search "Mini Assistant"
3. Click pencil icon to customize

---

### **Command Palette Commands**

Press `Ctrl+Shift+P` (Cmd+Shift+P) and type:

- `Mini Assistant: Open` - Open main panel
- `Mini Assistant: Review Current File` - Code review
- `Mini Assistant: Fix Code Issues` - Auto-fix bugs
- `Mini Assistant: Run in Code Runner` - Execute code
- `Mini Assistant: Test API` - API testing
- `Mini Assistant: Ask AI About This` - Get AI help
- `Mini Assistant: Quick Git Commit` - Fast commit
- `Mini Assistant: Format JSON` - Format JSON
- `Mini Assistant: Save as Snippet` - Save code

---

## 🔥 Real-World Workflows

### **Workflow 1: Fix Bugs**
```
1. Write code with a bug
2. Right-click → "Fix Code Issues"
3. Review AI-suggested fixes in panel
4. Apply fixes to your file
5. Done! ✅
```

### **Workflow 2: Learn & Understand**
```
1. Select confusing code
2. Press Ctrl+Shift+A
3. Ask: "Explain this code"
4. Read AI explanation
5. Understand better!
```

### **Workflow 3: Test APIs**
```
1. Press Ctrl+Shift+P
2. Type "Test API"
3. Enter API URL
4. View response in Mini Assistant
5. Debug API issues
```

### **Workflow 4: Full Development**
```
1. Open project in VS Code
2. Press Ctrl+Shift+M (open Mini Assistant)
3. Use App Builder to generate boilerplate
4. Design database schema
5. Write code in VS Code
6. Review with AI
7. Run in Code Runner
8. Test APIs
9. Commit via Mini Assistant
10. Push to GitHub
11. Ship it! 🚀
```

---

## 🎨 Features in VS Code

All 17 Mini Assistant features work in VS Code:

**Development:**
- ✅ AI Chat
- ✅ App Builder
- ✅ Code Review & Fix
- ✅ Code Runner
- ✅ API Tester
- ✅ Database Designer
- ✅ Git & GitHub

**Productivity:**
- ✅ Package Manager
- ✅ Env Manager
- ✅ Snippet Library
- ✅ Dev Utilities (Regex, JSON, Markdown, Colors)

**System:**
- ✅ File Manager
- ✅ Terminal
- ✅ Project Profiles
- ✅ Web Search
- ✅ Code Search
- ✅ Voice Mode

---

## 🛠️ Troubleshooting

### **Extension not showing**
1. Check VS Code version: Help → About (need 1.80.0+)
2. Reload window: `Ctrl+Shift+P` → "Reload Window"
3. Check extensions list: `Ctrl+Shift+X`

### **Panel not opening**
1. Check status bar for errors
2. Verify Mini Assistant is running
3. Test in browser first: http://localhost:8000
4. Check settings: `Ctrl+,` → search "Mini Assistant"

### **Commands not working**
1. Reload window
2. Check for keyboard shortcut conflicts
3. Try via Command Palette instead

### **Can't connect to Mini Assistant**
1. Check `miniAssistant.serverUrl` in settings
2. Ensure Mini Assistant server is running
3. Test URL in browser
4. Check for firewall/network issues

---

## 💡 Tips & Tricks

**Tip 1: Side-by-Side**
- Mini Assistant opens beside your editor
- Drag to resize panels
- Use both simultaneously

**Tip 2: Context Awareness**
- Extension automatically passes current file info
- No manual copy-paste needed

**Tip 3: Persistent Panel**
- Panel stays open when switching files
- Always accessible

**Tip 4: Quick Navigation**
- Use status bar for instant access
- Faster than Command Palette

**Tip 5: Save Frequently Used Code**
- Right-click → "Save as Snippet"
- Build personal snippet library
- Reuse across projects

---

## 🔄 Updating the Extension

When new version available:

**Method 1: Script**
```bash
cd /app/vscode-extension
./install.sh
```

**Method 2: Manual**
1. Delete old: `~/.vscode/extensions/mini-assistant-1.0.0`
2. Copy new version
3. Reload VS Code

---

## 🚀 What's Next?

**Try these:**
1. Open your current project
2. Right-click any file → "Review Current File"
3. Press `Ctrl+Shift+M` to explore all features
4. Save useful snippets
5. Use AI for code explanations
6. Test your APIs
7. Commit with Git integration

**You now have a COMPLETE AI development environment in VS Code! 🎉**

---

## 📚 Additional Resources

- **Mini Assistant Docs:** `/app/README.md`
- **Ollama Setup:** `/app/SETUP_GUIDE.md`
- **Git Guide:** `/app/GIT_INTEGRATION_GUIDE.md`
- **Extension README:** `/app/vscode-extension/README.md`

---

## ✨ Benefits

**Before:**
- Switch between VS Code and browser
- Copy-paste code manually
- Context switching overhead
- Multiple tools needed

**After:**
- Everything in one place
- Automatic context passing
- Seamless workflow
- Single environment

**Mini Assistant + VS Code = Perfect Productivity! 🏆**
