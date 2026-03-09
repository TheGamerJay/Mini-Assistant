/**
 * components/ChatInput.js
 * Textarea-based message input bar.
 * Props: { onSubmit, loading, variant: 'home'|'chat', placeholder }
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Paperclip, Mic, Send, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

function ChatInput({ onSubmit, loading = false, variant = 'chat', placeholder }) {
  const [value, setValue] = useState('');
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

  const handleSubmit = useCallback(() => {
    const text = value.trim();
    if (!text || loading) return;
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

  const isHome = variant === 'home';
  const isEmpty = !value.trim();

  const containerClass = isHome
    ? 'w-full max-w-2xl rounded-2xl bg-[#1a1a26] border border-white/10 flex items-end gap-2 px-4 py-3 focus-within:border-cyan-500/40 focus-within:shadow-[0_0_20px_rgba(0,229,255,0.08)] transition-all'
    : 'w-full rounded-xl bg-[#1a1a26] border border-white/10 flex items-end gap-2 px-4 py-3 focus-within:border-cyan-500/40 focus-within:shadow-[0_0_20px_rgba(0,229,255,0.08)] transition-all';

  return (
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

      {/* Textarea */}
      <textarea
        ref={textareaRef}
        className="flex-1 bg-transparent text-slate-200 text-sm font-sans placeholder-slate-600 resize-none outline-none border-none leading-6 max-h-[144px] py-0.5"
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
            : 'bg-gradient-to-br from-cyan-500 to-violet-600 text-white hover:from-cyan-400 hover:to-violet-500 shadow-lg hover:shadow-cyan-500/20'}`}
        title="Send message"
      >
        {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
      </button>
    </div>
  );
}

export default ChatInput;
