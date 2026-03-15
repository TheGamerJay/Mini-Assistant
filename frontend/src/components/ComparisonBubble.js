/**
 * ComparisonBubble.js
 * Side-by-side response comparison shown every 10 assistant replies.
 * User picks which response they prefer; that one is committed to chat history.
 */

import React, { useState } from 'react';

function shortModelName(model) {
  // e.g. "qwen3:14b" → "Qwen3 14B"
  return model
    .replace(':', ' ')
    .replace(/-/g, ' ')
    .split(' ')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

export default function ComparisonBubble({ replyA, modelA, replyB, modelB, onPick, loading }) {
  const [picked, setPicked] = useState(null); // 'a' | 'b'

  function handlePick(side) {
    if (picked) return;
    setPicked(side);
    onPick(side === 'a' ? replyA : replyB, side === 'a' ? modelA : modelB);
  }

  return (
    <div className="w-full flex flex-col gap-3 msg-enter">
      {/* Header */}
      <div className="flex items-center gap-2 px-1">
        <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
        <span className="text-[11px] font-mono text-slate-500 tracking-wide uppercase">
          Model Showdown — pick your favourite
        </span>
      </div>

      {/* Two columns */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {[
          { side: 'a', reply: replyA, model: modelA },
          { side: 'b', reply: replyB, model: modelB },
        ].map(({ side, reply, model }) => {
          const isPicked   = picked === side;
          const isRejected = picked && picked !== side;

          return (
            <div
              key={side}
              className={`flex flex-col rounded-2xl border transition-all duration-300
                ${isPicked
                  ? 'border-cyan-500/60 bg-cyan-500/5 shadow-[0_0_20px_rgba(6,182,212,0.12)]'
                  : isRejected
                    ? 'border-white/5 bg-[#151520] opacity-40'
                    : 'border-white/8 bg-[#151520]'}`}
            >
              {/* Model label */}
              <div className="flex items-center justify-between px-4 pt-3 pb-2 border-b border-white/5">
                <span className={`text-[11px] font-mono font-semibold tracking-wide
                  ${isPicked ? 'text-cyan-400' : 'text-slate-500'}`}>
                  {shortModelName(model)}
                </span>
                {isPicked && (
                  <span className="text-[10px] font-mono text-cyan-500 bg-cyan-500/10 px-2 py-0.5 rounded-full border border-cyan-500/20">
                    Preferred ✓
                  </span>
                )}
              </div>

              {/* Response body */}
              <div className="flex-1 px-4 py-3 text-sm leading-relaxed text-slate-200 overflow-y-auto max-h-80">
                {loading && !reply ? (
                  <div className="flex items-center gap-1.5 text-slate-600">
                    <span className="w-1.5 h-1.5 bg-slate-600 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-1.5 h-1.5 bg-slate-600 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-1.5 h-1.5 bg-slate-600 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                ) : (
                  <p className="whitespace-pre-wrap">{reply || ''}</p>
                )}
              </div>

              {/* Pick button */}
              {!picked && !loading && (
                <div className="px-4 pb-3">
                  <button
                    onClick={() => handlePick(side)}
                    className="w-full py-1.5 rounded-xl text-[12px] font-medium border transition-all
                      border-white/10 text-slate-400 hover:border-cyan-500/40 hover:text-cyan-300
                      hover:bg-cyan-500/5 active:scale-95"
                  >
                    Prefer this
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
