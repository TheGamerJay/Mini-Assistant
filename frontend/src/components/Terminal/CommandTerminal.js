import React, { useState } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Terminal as TerminalIcon, Play, X } from 'lucide-react';
import { usePersist } from '../../hooks/usePersist';

const CommandTerminal = () => {
  const [command, setCommand] = useState('');
  const [history, setHistory] = usePersist('ma_terminal_history', []);
  const [executing, setExecuting] = useState(false);

  const executeCommand = async () => {
    if (!command.trim() || executing) return;

    setExecuting(true);
    const cmd = command;
    setHistory(prev => [...prev, { type: 'input', content: cmd }]);
    setCommand('');

    try {
      const response = await axiosInstance.post('/commands/execute', {
        command: cmd,
        allowlist: ['ls', 'pwd', 'cat', 'echo', 'grep', 'find', 'wc', 'head', 'tail', 'tree', 'whoami']
      });

      setHistory(prev => [...prev, {
        type: 'output',
        stdout: response.data.stdout,
        stderr: response.data.stderr,
        returncode: response.data.returncode
      }]);

      if (response.data.returncode !== 0) {
        toast.error('Command execution failed');
      }
    } catch (error) {
      setHistory(prev => [...prev, {
        type: 'error',
        content: error.response?.data?.detail || 'Execution error'
      }]);
      toast.error(error.response?.data?.detail || 'Command failed');
    } finally {
      setExecuting(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      executeCommand();
    }
  };

  const clearTerminal = () => {
    setHistory([]);
    toast.success('Terminal cleared');
  };

  return (
    <div className="h-full flex flex-col bg-black/80" data-testid="command-terminal">
      {/* Terminal Header */}
      <div className="p-4 border-b border-cyan-500/20 bg-black/60 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <TerminalIcon className="w-6 h-6 text-cyan-400" />
          <h2 className="text-xl font-bold text-cyan-400 uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
            COMMAND TERMINAL
          </h2>
        </div>
        <button
          data-testid="clear-terminal-btn"
          onClick={clearTerminal}
          className="px-4 py-2 text-slate-400 hover:text-red-400 transition-colors uppercase text-sm font-mono flex items-center gap-2"
        >
          <X className="w-4 h-4" />
          CLEAR
        </button>
      </div>

      {/* Terminal Output */}
      <div className="flex-1 overflow-y-auto p-6 font-mono text-sm space-y-3" data-testid="terminal-output">
        {history.length === 0 && (
          <div className="text-cyan-400/50">
            $ Allowlisted commands: ls, pwd, cat, echo, grep, find, wc, head, tail, tree, whoami
          </div>
        )}

        {history.map((entry, idx) => (
          <div key={idx}>
            {entry.type === 'input' && (
              <div className="text-cyan-400">
                <span className="text-green-400">$</span> {entry.content}
              </div>
            )}
            {entry.type === 'output' && (
              <div>
                {entry.stdout && <div className="text-slate-300 whitespace-pre-wrap">{entry.stdout}</div>}
                {entry.stderr && <div className="text-red-400 whitespace-pre-wrap">{entry.stderr}</div>}
              </div>
            )}
            {entry.type === 'error' && (
              <div className="text-red-400">{entry.content}</div>
            )}
          </div>
        ))}

        {executing && (
          <div className="text-cyan-400 animate-pulse">Executing...</div>
        )}
      </div>

      {/* Command Input */}
      <div className="p-4 border-t border-cyan-500/20 bg-black/60">
        <div className="flex items-center gap-3">
          <span className="text-green-400 font-mono text-sm">$</span>
          <input
            data-testid="terminal-input"
            type="text"
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Enter command..."
            className="flex-1 bg-transparent border-none text-cyan-100 placeholder:text-cyan-900/50 font-mono text-sm outline-none"
            disabled={executing}
          />
          <button
            data-testid="execute-command-btn"
            onClick={executeCommand}
            disabled={executing || !command.trim()}
            className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-sm flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Play className="w-4 h-4" />
            RUN
          </button>
        </div>
      </div>
    </div>
  );
};

export default CommandTerminal;