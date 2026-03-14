/**
 * components/ChatInput.js
 * Textarea-based message input bar with slash command detection.
 * Props: { onSubmit, loading, variant: 'home'|'chat', placeholder }
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Paperclip, Mic, Send, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

// Known slash commands — matches backend command_parser.py
const SLASH_COMMANDS = [
  { cmd: '/chat',    desc: 'Normal conversation' },
  { cmd: '/search',  desc: 'Search the web' },
  { cmd: '/image',   desc: 'Generate an image' },
  { cmd: '/analyze', desc: 'Analyze attached image' },
  { cmd: '/code',    desc: 'Write or explain code' },
  { cmd: '/fix',     desc: 'Debug an error or issue' },
  { cmd: '/plan',    desc: 'Plan a multi-step task' },
  { cmd: '/build',   desc: 'Build a web app' },
  { cmd: '/files',   desc: 'Inspect project files' },
  { cmd: '/context', desc: 'Show project context scan' },
  { cmd: '/help',    desc: 'Show all commands' },
];

function ChatInput({ onSubmit, loading = false, variant = 'chat', placeholder }) {
  const [value, setValue] = useState('');
  const [slashHints, setSlashHints] = useState([]);
  const textareaRef = useRef(null);

  const defaultPlaceholder =
    variant === 'home'
      ? 'Ask anything, generate an image, or write code…'
      : 'Message Mini Assistant…';

  const resolvedPlaceholder = placeholder || defaultPlaceholder;

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    const maxH = 6 * 24; // ~6 rows at 24px line-height
    ta.style.height = Math.min(ta.scrollHeight, maxH) + 'px';
  }, [value]);

  // Slash command hint filtering
  useEffect(() => {
    const trimmed = value.trimStart();
    if (!trimmed.startsWith('/')) {
      setSlashHints([]);
      return;
    }
    // Only show hints while the user is still typing the command word (no space yet)
    const parts = trimmed.split(' ');
    if (parts.length > 1) {
      setSlashHints([]);
      return;
    }
    const typed = trimmed.toLowerCase();
    const matches = SLASH_COMMANDS.filter(c => c.cmd.startsWith(typed));
    setSlashHints(matches);
  }, [value]);

  const applySlashHint = useCallback((cmd) => {
    setValue(cmd + ' ');
    setSlashHints([]);
    textareaRef.current?.focus();
  }, []);

  const handleSubmit = useCallback(() => {
    const text = value.trim();
    if (text.length < 2 || loading) return;
    setSlashHints([]);
    onSubmit(text);
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [value, loading, onSubmit]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  const isHome   = variant === 'home';
  const isEmpty  = value.trim().length < 2;
  const isSlash  = value.trimStart().startsWith('/');

  const containerClass = isHome
    ? 'w-full max-w-2xl rounded-2xl bg-[#1a1a26] border border-white/10 flex items-end gap-2 px-5 py-3.5 focus-within:border-cyan-500/40 focus-within:shadow-[0_0_20px_rgba(0,229,255,0.08)] transition-all'
    : 'w-full rounded-xl bg-[#1a1a26] border border-white/10 flex items-end gap-2 px-5 py-3.5 focus-within:border-cyan-500/40 focus-within:shadow-[0_0_20px_rgba(0,229,255,0.08)] transition-all';

  return (
    <div className="relative w-full">
      {/* Slash command hints dropdown */}
      {slashHints.length > 0 && (
        <div className="absolute bottom-full mb-2 left-0 right-0 z-50 rounded-xl bg-[#13131f] border border-white/10 overflow-hidden shadow-xl">
          {slashHints.map(({ cmd, desc }) => (
            <button
              key={cmd}
              type="button"
              onMouseDown={(e) => { e.preventDefault(); applySlashHint(cmd); }}
              className="w-full text-left px-4 py-2.5 flex items-center gap-3 hover:bg-white/5 transition-colors"
            >
              <span className="text-cyan-400 font-mono text-sm font-medium w-20 flex-shrink-0">{cmd}</span>
              <span className="text-slate-400 text-sm">{desc}</span>
            </button>
          ))}
        </div>
      )}

    <div className={containerClass}>
      {/* Attach */}
      <button
        type="button"
        onClick={() => toast.info('Attach coming soon')}
        className="flex-shrink-0 p-1.5 rounded-lg text-slate-600 hover:text-slate-400 hover:bg-white/5 transition-colors mb-0.5"
        title="Attach file"
      >
        <Paperclip size={16} />
      </button>

      {/* Textarea — cyan text when slash command active */}
      <textarea
        ref={textareaRef}
        className={`flex-1 bg-transparent text-[15px] font-sans placeholder-slate-600 resize-none outline-none border-none leading-6 max-h-[144px] py-0.5
          ${isSlash ? 'text-cyan-300 font-mono' : 'text-slate-200'}`}
        placeholder={resolvedPlaceholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={1}
        disabled={loading}
        autoFocus={isHome}
      />

      {/* Mic */}
      <button
        type="button"
        onClick={() => toast.info('Voice coming soon')}
        className="flex-shrink-0 p-1.5 rounded-lg text-slate-600 hover:text-slate-400 hover:bg-white/5 transition-colors mb-0.5"
        title="Voice input"
      >
        <Mic size={16} />
      </button>

      {/* Send */}
      <button
        type="button"
        onClick={handleSubmit}
        disabled={isEmpty || loading}
        className={`flex-shrink-0 p-2.5 rounded-xl transition-all mb-0.5
          ${isEmpty || loading
            ? 'bg-slate-700/50 text-slate-600 cursor-not-allowed'
            : isSlash
              ? 'bg-gradient-to-br from-cyan-400 to-cyan-600 text-white hover:from-cyan-300 hover:to-cyan-500 shadow-lg hover:shadow-cyan-500/30'
              : 'bg-gradient-to-br from-cyan-500 to-violet-600 text-white hover:from-cyan-400 hover:to-violet-500 shadow-lg hover:shadow-cyan-500/20'}`}
        title="Send message"
      >
        {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
      </button>
    </div>
    </div>
  );
}

export default ChatInput;
