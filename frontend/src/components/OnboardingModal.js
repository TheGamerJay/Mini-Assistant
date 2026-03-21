/**
 * OnboardingModal.js
 * First-session welcome flow — shown once per account, never again.
 *
 * Layout:
 *   Mobile  → bottom sheet (slides up, rounded-t-3xl)
 *   Desktop → centered modal (rounded-3xl, max-w-md)
 *
 * Touch-safe: min 52px targets, active: tap feedback, safe-area insets.
 * All Tailwind classes written as full static strings so JIT includes them.
 */

import React, { useState, useEffect } from 'react';
import { Sparkles, Code2, Image, MessageSquare, ArrowRight, ChevronLeft, X } from 'lucide-react';
import { useApp } from '../context/AppContext';

// ---------------------------------------------------------------------------
// Category data — ALL Tailwind classes written as full literal strings
// so the JIT scanner includes them without dynamic concatenation
// ---------------------------------------------------------------------------
const CATEGORIES = [
  {
    id: 'app',
    label: 'AI App',
    icon: Sparkles,
    bg:          'bg-violet-500/10',
    border:      'border-violet-500/30',
    text:        'text-violet-400',
    ring:        'ring-violet-500/40',
    cardActive:  'active:bg-violet-500/20 hover:bg-violet-500/20',
    promptActive:'hover:bg-violet-500/10 hover:border-violet-500/40 active:bg-violet-500/10',
    arrowText:   'text-violet-400',
    prompts: [
      'Build me a todo app with dark mode and local storage',
      'Create a portfolio website with smooth animations',
      'Make a weather dashboard that fetches real data',
      'Build a Pomodoro timer with sound alerts',
    ],
  },
  {
    id: 'code',
    label: 'Code',
    icon: Code2,
    bg:          'bg-cyan-500/10',
    border:      'border-cyan-500/30',
    text:        'text-cyan-400',
    ring:        'ring-cyan-500/40',
    cardActive:  'active:bg-cyan-500/20 hover:bg-cyan-500/20',
    promptActive:'hover:bg-cyan-500/10 hover:border-cyan-500/40 active:bg-cyan-500/10',
    arrowText:   'text-cyan-400',
    prompts: [
      'Write a Python web scraper with BeautifulSoup',
      'Create a REST API in FastAPI with JWT auth',
      'Write a binary search tree in JavaScript',
      'Build a CLI tool that monitors file changes',
    ],
  },
  {
    id: 'image',
    label: 'Image',
    icon: Image,
    bg:          'bg-pink-500/10',
    border:      'border-pink-500/30',
    text:        'text-pink-400',
    ring:        'ring-pink-500/40',
    cardActive:  'active:bg-pink-500/20 hover:bg-pink-500/20',
    promptActive:'hover:bg-pink-500/10 hover:border-pink-500/40 active:bg-pink-500/10',
    arrowText:   'text-pink-400',
    prompts: [
      'Generate a futuristic city skyline at night with neon lights',
      'Create a fantasy landscape with mountains and a waterfall',
      'Design a minimalist logo for a tech startup',
      'Paint an anime character in a glowing forest setting',
    ],
  },
  {
    id: 'chat',
    label: 'Chat',
    icon: MessageSquare,
    bg:          'bg-emerald-500/10',
    border:      'border-emerald-500/30',
    text:        'text-emerald-400',
    ring:        'ring-emerald-500/40',
    cardActive:  'active:bg-emerald-500/20 hover:bg-emerald-500/20',
    promptActive:'hover:bg-emerald-500/10 hover:border-emerald-500/40 active:bg-emerald-500/10',
    arrowText:   'text-emerald-400',
    prompts: [
      'Explain quantum computing in simple terms',
      'Help me write a compelling cover letter',
      'Give me 10 unique business ideas for 2025',
      'Summarize the key principles of stoicism',
    ],
  },
];

// ---------------------------------------------------------------------------
// OnboardingModal
// ---------------------------------------------------------------------------
export default function OnboardingModal({ onDone }) {
  const { firePendingTemplate, setPage } = useApp();
  const [step, setStep]         = useState(1);
  const [category, setCategory] = useState(null);

  // Lock background scroll while modal is open; restore on close
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);

  const handleCategory = (cat) => { setCategory(cat); setStep(2); };

  const handlePrompt = (prompt) => {
    // Navigate first so ChatInput is mounted, then fire auto-submit
    setPage(category.id === 'image' ? 'images' : 'chat');
    firePendingTemplate(prompt, true);   // true = auto-submit
    onDone();
  };

  const handleSkip = () => onDone();

  return (
    /* Full-screen flex column — backdrop click to dismiss */
    <div
      className="fixed inset-0 z-50 flex flex-col justify-end sm:justify-center sm:items-center sm:p-4"
      onClick={handleSkip}
    >
      {/* Spring keyframe — mobile slide-up with subtle bounce at end */}
      <style>{`
        @keyframes sheet-up {
          0%   { transform: translateY(100%); }
          70%  { transform: translateY(-6px); }
          85%  { transform: translateY(3px); }
          100% { transform: translateY(0); }
        }
        @keyframes modal-in {
          0%   { opacity: 0; transform: scale(0.96) translateY(8px); }
          100% { opacity: 1; transform: scale(1)    translateY(0); }
        }
        .onboarding-sheet  { animation: sheet-up  280ms cubic-bezier(0.34,1.56,0.64,1) both; }
        .onboarding-modal  { animation: modal-in  220ms cubic-bezier(0.34,1.56,0.64,1) both; }
        @media (min-width: 640px) {
          .onboarding-sheet { animation-name: modal-in; }
        }
      `}</style>

      {/* Dimmed backdrop */}
      <div className="absolute inset-0 bg-black/75" />

      {/* Modal — bottom sheet on mobile, floating card on sm+ */}
      <div
        className="onboarding-sheet relative bg-[#0f0f18] border-t border-l border-r sm:border border-white/10
                   rounded-t-3xl sm:rounded-3xl w-full sm:max-w-md
                   shadow-2xl overflow-hidden flex flex-col"
        style={{ maxHeight: '88svh' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Drag handle — mobile only */}
        <div className="flex justify-center pt-3 pb-1 sm:hidden">
          <div className="w-10 h-1 rounded-full bg-white/15" />
        </div>

        {/* Header */}
        <div className="px-5 pt-3 sm:pt-5 pb-3 flex items-start justify-between gap-3 flex-shrink-0">
          <div className="min-w-0">
            {step === 2 && (
              <button
                onClick={() => setStep(1)}
                className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 active:text-slate-300 mb-1.5 transition-colors"
              >
                <ChevronLeft size={13} /> Back
              </button>
            )}
            <h2 className="text-base sm:text-lg font-bold text-white leading-tight">
              {step === 1 ? 'What do you want to build?' : 'Pick a starter prompt'}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
              {step === 1
                ? 'Choose a category to get started in seconds.'
                : `${category?.label} — tap one to auto-fill your chat.`}
            </p>
          </div>
          {/* Close / skip button — 44×44 tap target */}
          <button
            onClick={handleSkip}
            className="flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-full text-slate-600 hover:text-slate-400 active:text-slate-300 hover:bg-white/5 active:bg-white/5 transition-colors"
            aria-label="Skip onboarding"
          >
            <X size={15} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="overflow-y-auto flex-1 overscroll-contain">

          {/* Step 1 — Category grid */}
          {step === 1 && (
            <div className="px-5 pb-4 grid grid-cols-2 gap-3">
              {CATEGORIES.map((cat) => {
                const Icon = cat.icon;
                return (
                  <button
                    key={cat.id}
                    onClick={() => handleCategory(cat)}
                    className={`flex flex-col items-start gap-2.5 p-4 rounded-2xl border
                      ${cat.bg} ${cat.border}
                      ${cat.cardActive}
                      ring-0 hover:ring-2 active:ring-2 ${cat.ring}
                      transition-all duration-150 text-left`}
                  >
                    <div className={`w-10 h-10 rounded-xl ${cat.bg} border ${cat.border}
                                    flex items-center justify-center flex-shrink-0`}>
                      <Icon size={18} className={cat.text} />
                    </div>
                    <span className="text-sm font-semibold text-white">{cat.label}</span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Step 2 — Prompt list */}
          {step === 2 && category && (
            <div className="px-5 pb-4 space-y-2">
              {category.prompts.map((prompt, i) => (
                <button
                  key={i}
                  onClick={() => handlePrompt(prompt)}
                  className={`w-full min-h-[52px] flex items-center justify-between gap-3
                    px-4 py-3.5 rounded-xl
                    border border-white/[0.07] bg-white/[0.03]
                    ${category.promptActive}
                    transition-all duration-150 text-left group`}
                >
                  <span className="text-sm text-slate-300 group-hover:text-white group-active:text-white transition-colors leading-snug">
                    {prompt}
                  </span>
                  <ArrowRight
                    size={14}
                    className={`flex-shrink-0 ${category.arrowText} opacity-0 group-hover:opacity-100 group-active:opacity-100 transition-opacity`}
                  />
                </button>
              ))}
            </div>
          )}

        </div>

        {/* Footer — progress + skip */}
        <div
          className="border-t border-white/[0.06] px-5 py-3 flex justify-between items-center flex-shrink-0"
          style={{ paddingBottom: 'max(12px, env(safe-area-inset-bottom))' }}
        >
          <div className="flex gap-1.5 items-center">
            {[1, 2].map(s => (
              <div
                key={s}
                className={`h-1.5 rounded-full transition-all duration-300 ${
                  s === step ? 'w-5 bg-violet-500' : 'w-1.5 bg-white/15'
                }`}
              />
            ))}
          </div>
          <button
            onClick={handleSkip}
            className="text-xs text-slate-600 hover:text-slate-400 active:text-slate-300 transition-colors py-2 px-1"
          >
            Skip for now
          </button>
        </div>

      </div>
    </div>
  );
}
