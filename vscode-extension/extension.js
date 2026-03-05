const vscode = require('vscode');
const path = require('path');

let assistantPanel = undefined;
let statusBarItem = undefined;

function activate(context) {
    console.log('Mini Assistant extension is now active!');

    // Create status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.text = '$(zap) Mini Assistant';
    statusBarItem.tooltip = 'Click to open Mini Assistant';
    statusBarItem.command = 'mini-assistant.open';
    
    const config = vscode.workspace.getConfiguration('miniAssistant');
    if (config.get('showInStatusBar')) {
        statusBarItem.show();
    }
    context.subscriptions.push(statusBarItem);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('mini-assistant.open', () => {
            openMiniAssistant(context);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mini-assistant.reviewFile', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showErrorMessage('No active editor');
                return;
            }
            
            const code = editor.document.getText(editor.selection.isEmpty ? undefined : editor.selection);
            const language = editor.document.languageId;
            
            openMiniAssistant(context, 'codereview', { code, language });
            vscode.window.showInformationMessage('Opening Code Review in Mini Assistant...');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mini-assistant.fixCode', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;
            
            const code = editor.document.getText(editor.selection.isEmpty ? undefined : editor.selection);
            const language = editor.document.languageId;
            
            openMiniAssistant(context, 'codereview', { code, language, autoFix: true });
            vscode.window.showInformationMessage('Analyzing and fixing code...');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mini-assistant.runCode', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;
            
            const code = editor.document.getText(editor.selection.isEmpty ? undefined : editor.selection);
            const language = editor.document.languageId;
            
            if (!['python', 'javascript'].includes(language)) {
                vscode.window.showErrorMessage('Only Python and JavaScript are supported');
                return;
            }
            
            openMiniAssistant(context, 'coderunner', { code, language });
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mini-assistant.testAPI', async () => {
            const url = await vscode.window.showInputBox({
                prompt: 'Enter API URL to test',
                placeHolder: 'https://api.example.com/endpoint'
            });
            
            if (url) {
                openMiniAssistant(context, 'apitester', { url });
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mini-assistant.askAI', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor || editor.selection.isEmpty) {
                vscode.window.showErrorMessage('Please select some text');
                return;
            }
            
            const selection = editor.document.getText(editor.selection);
            const question = await vscode.window.showInputBox({
                prompt: 'What do you want to know about this code?',
                placeHolder: 'e.g., Explain this function, Find bugs, Optimize this'
            });
            
            if (question) {
                openMiniAssistant(context, 'chat', { context: selection, question });
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mini-assistant.gitCommit', async () => {
            const message = await vscode.window.showInputBox({
                prompt: 'Enter commit message',
                placeHolder: 'feat: Add new feature'
            });
            
            if (message) {
                openMiniAssistant(context, 'git', { action: 'commit', message });
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mini-assistant.formatJSON', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;
            
            const text = editor.document.getText(editor.selection.isEmpty ? undefined : editor.selection);
            openMiniAssistant(context, 'devtools', { tool: 'json', data: text });
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mini-assistant.saveSnippet', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor || editor.selection.isEmpty) return;
            
            const code = editor.document.getText(editor.selection);
            const title = await vscode.window.showInputBox({
                prompt: 'Enter snippet title',
                placeHolder: 'My useful snippet'
            });
            
            if (title) {
                openMiniAssistant(context, 'snippets', { 
                    action: 'save', 
                    title, 
                    code, 
                    language: editor.document.languageId 
                });
                vscode.window.showInformationMessage('Snippet saved to Mini Assistant!');
            }
        })
    );

    // Auto-open if configured
    if (config.get('autoOpen')) {
        openMiniAssistant(context);
    }
}

function openMiniAssistant(context, tab = null, data = null) {
    const config = vscode.workspace.getConfiguration('miniAssistant');
    const serverUrl = config.get('serverUrl');

    if (assistantPanel) {
        assistantPanel.reveal(vscode.ViewColumn.Beside);
        if (tab) {
            assistantPanel.webview.postMessage({ command: 'navigate', tab, data });
        }
    } else {
        assistantPanel = vscode.window.createWebviewPanel(
            'miniAssistant',
            'Mini Assistant',
            vscode.ViewColumn.Beside,
            {
                enableScripts: true,
                retainContextWhenHidden: true
            }
        );

        let url = serverUrl;
        if (tab) {
            url += `?tab=${tab}`;
            if (data) {
                url += `&data=${encodeURIComponent(JSON.stringify(data))}`;
            }
        }

        assistantPanel.webview.html = getWebviewContent(url);

        assistantPanel.onDidDispose(
            () => {
                assistantPanel = undefined;
            },
            null,
            context.subscriptions
        );

        // Handle messages from webview
        assistantPanel.webview.onDidReceiveMessage(
            message => {
                switch (message.command) {
                    case 'showInfo':
                        vscode.window.showInformationMessage(message.text);
                        break;
                    case 'showError':
                        vscode.window.showErrorMessage(message.text);
                        break;
                    case 'openFile':
                        vscode.workspace.openTextDocument(message.path).then(doc => {
                            vscode.window.showTextDocument(doc);
                        });
                        break;
                }
            },
            undefined,
            context.subscriptions
        );
    }
}

function getWebviewContent(url) {
    return `<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Mini Assistant</title>
        <style>
            body, html {
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
                overflow: hidden;
            }
            iframe {
                width: 100%;
                height: 100%;
                border: none;
            }
            .loading {
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                font-family: monospace;
                color: #00f3ff;
                background: #050505;
            }
        </style>
    </head>
    <body>
        <div class="loading">Loading Mini Assistant...</div>
        <iframe src="${url}" sandbox="allow-scripts allow-same-origin allow-forms allow-popups"></iframe>
        <script>
            const vscode = acquireVsCodeApi();
            
            window.addEventListener('message', event => {
                const message = event.data;
                if (message.command === 'navigate') {
                    // Handle navigation from extension
                    console.log('Navigate to:', message.tab, message.data);
                }
            });
        </script>
    </body>
    </html>`;
}

function deactivate() {
    if (assistantPanel) {
        assistantPanel.dispose();
    }
}

module.exports = {
    activate,
    deactivate
};