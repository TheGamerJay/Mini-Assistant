/**
 * OnboardingModal.js
 * First-session welcome flow — shown once per account, never again.
 * Step 1: pick a category  →  Step 2: pick a starter prompt → auto-fills chat
 */

import React, { useState } from 'react';
import { Sparkles, Code2, Image, MessageSquare, ArrowRight, ChevronLeft, X } from 'lucide-react';
import { useApp } from '../context/AppContext';

// ---------------------------------------------------------------------------
// Starter prompts per category
// ---------------------------------------------------------------------------
const CATEGORIES = [
  {
    id: 'app',
    label: 'AI App',
    icon: Sparkles,
    color: 'violet',
    bg: 'bg-violet-500/10',
    border: 'border-violet-500/30',
    text: 'text-violet-400',
    ring: 'ring-violet-500/40',
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
    color: 'cyan',
    bg: 'bg-cyan-500/10',
    border: 'border-cyan-500/30',
    text: 'text-cyan-400',
    ring: 'ring-cyan-500/40',
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
    color: 'pink',
    bg: 'bg-pink-500/10',
    border: 'border-pink-500/30',
    text: 'text-pink-400',
    ring: 'ring-pink-500/40',
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
    color: 'emerald',
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/30',
    text: 'text-emerald-400',
    ring: 'ring-emerald-500/40',
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
  const [step, setStep] = useState(1);
  const [category, setCategory] = useState(null);

  const handleCategory = (cat) => {
    setCategory(cat);
    setStep(2);
  };

  const handlePrompt = (prompt) => {
    firePendingTemplate(prompt);
    setPage(category.id === 'image' ? 'images' : 'chat');
    onDone();
  };

  const handleSkip = () => onDone();

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#0f0f18] border border-white/10 rounded-3xl w-full max-w-md shadow-2xl overflow-hidden">

        {/* Header */}
        <div className="px-6 pt-6 pb-4 flex items-start justify-between">
          <div>
            {step === 2 && (
              <button
                onClick={() => setStep(1)}
                className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 mb-2 transition-colors"
              >
                <ChevronLeft size={13} /> Back
              </button>
            )}
            <h2 className="text-lg font-bold text-white leading-tight">
              {step === 1 ? 'What do you want to build?' : `Pick a starter prompt`}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {step === 1
                ? 'Choose a category to get started in seconds.'
                : `${category?.label} — select one to auto-fill your chat.`}
            </p>
          </div>
          <button
            onClick={handleSkip}
            className="text-slate-600 hover:text-slate-400 transition-colors p-1 flex-shrink-0"
            aria-label="Skip"
          >
            <X size={16} />
          </button>
        </div>

        {/* Step 1 — Category grid */}
        {step === 1 && (
          <div className="px-6 pb-6 grid grid-cols-2 gap-3">
            {CATEGORIES.map((cat) => {
              const Icon = cat.icon;
              return (
                <button
                  key={cat.id}
                  onClick={() => handleCategory(cat)}
                  className={`flex flex-col items-start gap-2 p-4 rounded-2xl border ${cat.bg} ${cat.border} hover:ring-2 ${cat.ring} transition-all text-left group`}
                >
                  <div className={`w-9 h-9 rounded-xl ${cat.bg} border ${cat.border} flex items-center justify-center`}>
                    <Icon size={17} className={cat.text} />
                  </div>
                  <span className="text-sm font-semibold text-white">{cat.label}</span>
                </button>
              );
            })}
          </div>
        )}

        {/* Step 2 — Prompt list */}
        {step === 2 && category && (
          <div className="px-6 pb-6 space-y-2">
            {category.prompts.map((prompt, i) => (
              <button
                key={i}
                onClick={() => handlePrompt(prompt)}
                className={`w-full flex items-center justify-between gap-3 px-4 py-3 rounded-xl border border-white/8 bg-white/[0.03] hover:${category.bg} hover:${category.border} hover:border transition-all text-left group`}
              >
                <span className="text-sm text-slate-300 group-hover:text-white transition-colors leading-snug">
                  {prompt}
                </span>
                <ArrowRight size={14} className={`flex-shrink-0 ${category.text} opacity-0 group-hover:opacity-100 transition-opacity`} />
              </button>
            ))}
          </div>
        )}

        {/* Footer */}
        <div className="border-t border-white/[0.06] px-6 py-3 flex justify-between items-center">
          <div className="flex gap-1.5">
            {[1, 2].map(s => (
              <div key={s} className={`h-1.5 rounded-full transition-all ${s === step ? 'w-5 bg-violet-500' : 'w-1.5 bg-white/15'}`} />
            ))}
          </div>
          <button
            onClick={handleSkip}
            className="text-xs text-slate-600 hover:text-slate-400 transition-colors"
          >
            Skip for now
          </button>
        </div>
      </div>
    </div>
  );
}
