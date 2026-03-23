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

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Globe, BarChart2, Wand2, Star, Gamepad2, Sparkles,
  ArrowRight, ChevronLeft, X,
} from 'lucide-react';
import { useApp } from '../context/AppContext';

// ---------------------------------------------------------------------------
// AppBuilder-focused category data.
// builder:true → uses firePendingBuildPrompt; otherwise firePendingTemplate.
// ALL Tailwind classes written as full literal strings so JIT includes them.
// ---------------------------------------------------------------------------
const CATEGORIES = [
  {
    id: 'landing',   label: 'Landing Page', icon: Globe,    builder: true,
    bg: 'bg-cyan-500/10', border: 'border-cyan-500/30', text: 'text-cyan-400',
    ring: 'ring-cyan-500/40',
    cardActive:  'active:bg-cyan-500/20 hover:bg-cyan-500/20',
    promptActive:'hover:bg-cyan-500/10 hover:border-cyan-500/40 active:bg-cyan-500/10',
    arrowText: 'text-cyan-400',
    prompts: [
      'SaaS landing page with hero, feature grid, pricing table, and email signup',
      'Startup landing page with animated headline, product screenshots, and CTA buttons',
      'Agency landing page with client logos, case studies, and contact form',
    ],
  },
  {
    id: 'dashboard', label: 'Dashboard',    icon: BarChart2, builder: true,
    bg: 'bg-violet-500/10', border: 'border-violet-500/30', text: 'text-violet-400',
    ring: 'ring-violet-500/40',
    cardActive:  'active:bg-violet-500/20 hover:bg-violet-500/20',
    promptActive:'hover:bg-violet-500/10 hover:border-violet-500/40 active:bg-violet-500/10',
    arrowText: 'text-violet-400',
    prompts: [
      'Analytics dashboard with line and bar charts, KPI cards, and date range filter',
      'Admin panel with user management table, search, and role badges',
      'Sales dashboard with revenue chart, conversion funnel, and top products list',
    ],
  },
  {
    id: 'tool',      label: 'Tool / App',   icon: Wand2,    builder: true,
    bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', text: 'text-emerald-400',
    ring: 'ring-emerald-500/40',
    cardActive:  'active:bg-emerald-500/20 hover:bg-emerald-500/20',
    promptActive:'hover:bg-emerald-500/10 hover:border-emerald-500/40 active:bg-emerald-500/10',
    arrowText: 'text-emerald-400',
    prompts: [
      'Budget tracker with income and expense categories, monthly charts, and balance',
      'Pomodoro timer with 25/5 sessions, history, and streak counter',
      'Password generator with length slider, strength meter, and copy button',
    ],
  },
  {
    id: 'portfolio', label: 'Portfolio',    icon: Star,     builder: true,
    bg: 'bg-amber-500/10', border: 'border-amber-500/30', text: 'text-amber-400',
    ring: 'ring-amber-500/40',
    cardActive:  'active:bg-amber-500/20 hover:bg-amber-500/20',
    promptActive:'hover:bg-amber-500/10 hover:border-amber-500/40 active:bg-amber-500/10',
    arrowText: 'text-amber-400',
    prompts: [
      'Developer portfolio with project cards, skills section, GitHub links, and contact form',
      'Designer portfolio with full-screen image gallery and case studies',
      'Creative portfolio with animated transitions and a dark minimal aesthetic',
    ],
  },
  {
    id: 'game',      label: 'Game',         icon: Gamepad2, builder: true,
    bg: 'bg-pink-500/10', border: 'border-pink-500/30', text: 'text-pink-400',
    ring: 'ring-pink-500/40',
    cardActive:  'active:bg-pink-500/20 hover:bg-pink-500/20',
    promptActive:'hover:bg-pink-500/10 hover:border-pink-500/40 active:bg-pink-500/10',
    arrowText: 'text-pink-400',
    prompts: [
      'Classic Snake game with score tracking, speed scaling, and high score saved',
      'Breakout brick breaker with multiple rows, ball physics, lives, and power-ups',
      'Space shooter with enemy waves, explosions, shield, and boss every 5 levels',
    ],
  },
  {
    id: 'custom',    label: 'Custom idea',  icon: Sparkles, builder: true,
    bg: 'bg-slate-500/10', border: 'border-slate-500/30', text: 'text-slate-400',
    ring: 'ring-slate-500/40',
    cardActive:  'active:bg-slate-500/20 hover:bg-slate-500/20',
    promptActive:'hover:bg-slate-500/10 hover:border-slate-500/40 active:bg-slate-500/10',
    arrowText: 'text-slate-400',
    prompts: [],
  },
];

// ---------------------------------------------------------------------------
// OnboardingModal
// ---------------------------------------------------------------------------
export default function OnboardingModal({ onDone }) {
  const { firePendingTemplate, firePendingBuildPrompt, setPendingChatMode, setPage } = useApp();
  const [step, setStep]           = useState(1);
  const [category, setCategory]   = useState(null);
  const [customText, setCustomText] = useState('');
  const modalRef  = useRef(null);
  const firedRef  = useRef(false);   // single-fire guard

  // Phase 3 — iOS Safari scroll lock (position:fixed method prevents rubber-band scroll)
  useEffect(() => {
    const scrollY       = window.scrollY;
    const prevOverflow  = document.body.style.overflow;
    const prevPosition  = document.body.style.position;
    const prevWidth     = document.body.style.width;
    const prevTop       = document.body.style.top;

    document.body.style.overflow  = 'hidden';
    document.body.style.position  = 'fixed';
    document.body.style.width     = '100%';
    document.body.style.top       = `-${scrollY}px`;

    return () => {
      document.body.style.overflow  = prevOverflow;
      document.body.style.position  = prevPosition;
      document.body.style.width     = prevWidth;
      document.body.style.top       = prevTop;
      window.scrollTo(0, scrollY);  // restore position without jump
    };
  }, []);

  // Phase 2 — ESC to close
  const handleSkip = useCallback(() => onDone(), [onDone]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') handleSkip(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [handleSkip]);

  // Phase 2 — Focus trap: Tab cycles only within modal
  useEffect(() => {
    const modal = modalRef.current;
    if (!modal) return;
    modal.focus();

    const FOCUSABLE = 'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

    const onTab = (e) => {
      if (e.key !== 'Tab') return;
      const nodes   = Array.from(modal.querySelectorAll(FOCUSABLE));
      const first   = nodes[0];
      const last    = nodes[nodes.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last?.focus(); }
      } else {
        if (document.activeElement === last)  { e.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', onTab);
    return () => document.removeEventListener('keydown', onTab);
  }, []);

  const handleCategory = (cat) => { setCategory(cat); setStep(2); };

  // Guard against double-fire from rapid taps
  const handlePrompt = (prompt) => {
    if (firedRef.current) return;
    firedRef.current = true;
    if (category?.builder) {
      setPendingChatMode('build'); // activate Build Mode in ChatInput before submitting
      firePendingBuildPrompt(prompt);
    } else {
      firePendingTemplate(prompt, true);
    }
    setPage('chat');
    onDone();
  };

  const handleCustomSubmit = () => {
    if (!customText.trim()) return;
    handlePrompt(customText.trim());
  };

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
        @media (prefers-reduced-motion: reduce) {
          .onboarding-sheet, .onboarding-modal { animation: none; }
        }
      `}</style>

      {/* Dimmed backdrop */}
      <div className="absolute inset-0 bg-black/75" />

      {/* Modal — bottom sheet on mobile, floating card on sm+ */}
      <div
        ref={modalRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="Get started"
        className="onboarding-sheet relative bg-[#0f0f18] border-t border-l border-r sm:border border-white/10
                   rounded-t-3xl sm:rounded-3xl w-full sm:max-w-md
                   shadow-2xl overflow-hidden flex flex-col outline-none"
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

          {/* Step 2 — Prompt list or custom textarea */}
          {step === 2 && category && (
            <div className="px-5 pb-4 space-y-2">
              {/* Example prompts (non-custom categories) */}
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
              {/* Custom textarea — shown for 'custom' category, or as extra option */}
              {(category.id === 'custom' || category.prompts.length === 0) && (
                <div className="pt-1 space-y-2">
                  <textarea
                    value={customText}
                    onChange={e => setCustomText(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleCustomSubmit(); }}
                    placeholder="Describe your idea — e.g. A recipe manager with categories, search, and a shopping list…"
                    rows={3}
                    autoFocus
                    className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder:text-slate-700 outline-none focus:border-cyan-500/50 resize-none"
                  />
                  <button
                    onClick={handleCustomSubmit}
                    disabled={!customText.trim()}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gradient-to-r from-cyan-500 to-violet-600 text-white text-sm font-bold rounded-xl hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Build it <ArrowRight size={14} />
                  </button>
                </div>
              )}
              {/* "Or describe your own" for non-custom categories */}
              {category.id !== 'custom' && category.prompts.length > 0 && (
                <details className="group pt-1">
                  <summary className="text-[11px] text-slate-600 hover:text-slate-400 cursor-pointer select-none list-none">
                    + Describe your own idea
                  </summary>
                  <div className="pt-2 space-y-2">
                    <textarea
                      value={customText}
                      onChange={e => setCustomText(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleCustomSubmit(); }}
                      placeholder="Describe your idea…"
                      rows={2}
                      className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder:text-slate-700 outline-none focus:border-cyan-500/50 resize-none"
                    />
                    <button
                      onClick={handleCustomSubmit}
                      disabled={!customText.trim()}
                      className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gradient-to-r from-cyan-500 to-violet-600 text-white text-sm font-bold rounded-xl hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      Build it <ArrowRight size={14} />
                    </button>
                  </div>
                </details>
              )}
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
