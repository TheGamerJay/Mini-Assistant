import React, { useState } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Play, Loader2, Terminal, Code, Trash2 } from 'lucide-react';

const CodeRunner = () => {
  const [code, setCode] = useState('');
  const [language, setLanguage] = useState('python');
  const [output, setOutput] = useState('');
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState([]);

  const templates = {
    python: `# Python Code
print("Hello from Mini Assistant!")

# Calculate fibonacci
def fib(n):
    if n <= 1:
        return n
    return fib(n-1) + fib(n-2)

print(f"Fibonacci(10) = {fib(10)}")`,
    javascript: `// JavaScript Code
console.log("Hello from Mini Assistant!");

// Calculate factorial
function factorial(n) {
  return n <= 1 ? 1 : n * factorial(n - 1);
}

console.log(\`Factorial(5) = \${factorial(5)}\`);`,
    nodejs: `// Node.js Code
const fs = require('fs');

console.log("Node.js Version:", process.version);
console.log("Current Directory:", process.cwd());

// Simple HTTP server example (commented)
// const http = require('http');
// http.createServer((req, res) => {
//   res.end('Hello World!');
// }).listen(3000);`
  };

  const runCode = async () => {
    if (!code.trim() || loading) return;

    setLoading(true);
    setOutput('');
    try {
      const response = await axiosInstance.post('/code-runner/execute', {
        code: code,
        language: language,
        timeout: 10
      });

      const result = response.data;
      const outputText = `${result.stdout}${result.stderr ? '\n[ERROR]\n' + result.stderr : ''}`;
      setOutput(outputText);
      
      setHistory(prev => [{
        code: code.substring(0, 100) + '...',
        language,
        output: outputText.substring(0, 200),
        timestamp: new Date().toLocaleTimeString()
      }, ...prev.slice(0, 9)]);

      if (result.returncode === 0) {
        toast.success('Code executed successfully');
      } else {
        toast.error('Execution error');
      }
    } catch (error) {
      const errorMsg = error.response?.data?.detail || 'Execution failed';
      setOutput(`[ERROR] ${errorMsg}`);
      toast.error('Execution failed');
      console.error('Execution error:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadTemplate = () => {
    setCode(templates[language]);
    toast.success('Template loaded');
  };

  return (
    <div className="h-full flex" data-testid="code-runner">
      {/* Left Panel - Code Editor */}
      <div className="w-2/3 border-r border-cyan-500/20 flex flex-col bg-black/20">
        <div className="p-4 border-b border-cyan-500/20 bg-black/40">
          <div className="flex items-center gap-3 mb-4">
            <Play className="w-6 h-6 text-cyan-400" />
            <div>
              <h2 className="text-xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
                LIVE CODE RUNNER
              </h2>
              <p className="text-xs text-slate-400 font-mono mt-1">EXECUTE PYTHON & JAVASCRIPT</p>
            </div>
          </div>

          <div className="flex gap-3">
            <select
              data-testid="runner-language-select"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="bg-black/50 border border-cyan-500/50 text-cyan-100 px-4 py-2 rounded-sm font-mono text-sm focus:border-cyan-400 outline-none"
            >
              <option value="python">Python</option>
              <option value="javascript">JavaScript</option>
              <option value="nodejs">Node.js</option>
            </select>

            <button
              onClick={loadTemplate}
              className="px-4 py-2 bg-violet-500/20 text-violet-400 border border-violet-500/50 hover:bg-violet-500/30 rounded-sm text-sm font-semibold uppercase"
            >
              LOAD TEMPLATE
            </button>

            <button
              data-testid="run-code-btn"
              onClick={runCode}
              disabled={loading || !code.trim()}
              className="flex-1 px-6 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-sm flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  RUNNING...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  RUN CODE
                </>
              )}
            </button>
          </div>
        </div>

        <div className="flex-1 flex flex-col">
          <div className="flex-1 p-4">
            <textarea
              data-testid="code-runner-input"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Write your code here...\n\n// Example:\nconsole.log('Hello World!');"
              className="w-full h-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono text-sm p-4 outline-none resize-none"
              disabled={loading}
            />
          </div>

          {/* Output Panel */}
          <div className="h-64 border-t border-cyan-500/20 bg-black/40 p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 text-sm font-mono text-cyan-400 uppercase">
                <Terminal className="w-4 h-4" />
                OUTPUT
              </div>
              {output && (
                <button
                  onClick={() => setOutput('')}
                  className="text-slate-400 hover:text-red-400 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
            <pre className="h-48 overflow-auto text-slate-300 text-sm bg-black/30 p-3 rounded border border-cyan-900/20 font-mono" data-testid="code-output">
              {output || 'Output will appear here...'}
            </pre>
          </div>
        </div>
      </div>

      {/* Right Panel - History */}
      <div className="w-1/3 flex flex-col bg-[#0a0a0f]/50">
        <div className="p-4 border-b border-cyan-500/20 bg-black/40">
          <div className="flex items-center gap-2">
            <Code className="w-5 h-5 text-cyan-400" />
            <h3 className="text-lg font-semibold text-cyan-400">Execution History</h3>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {history.length === 0 ? (
            <div className="text-center py-12 text-slate-500">
              <Code className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Execution history will appear here</p>
            </div>
          ) : (
            history.map((item, idx) => (
              <div key={idx} className="p-3 bg-black/40 border border-cyan-900/30 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-violet-400 font-mono uppercase">{item.language}</span>
                  <span className="text-xs text-slate-500">{item.timestamp}</span>
                </div>
                <pre className="text-xs text-slate-400 mb-2 font-mono overflow-hidden">{item.code}</pre>
                <pre className="text-xs text-cyan-100 font-mono overflow-hidden">{item.output}</pre>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default CodeRunner;