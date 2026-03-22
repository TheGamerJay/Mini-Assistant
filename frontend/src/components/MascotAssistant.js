/**
 * MascotAssistant.js
 * Floating animated mascot — bottom-right corner.
 *
 * Animations: float, breathe, glow-pulse, random blink — pure CSS.
 * GPU-safe: only transform + opacity used.
 * State (open/closed) persisted to localStorage.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { X, ChevronDown, Sparkles } from 'lucide-react';
import { useApp } from '../context/AppContext';

// ---------------------------------------------------------------------------
// Personality messages — cycle on open + every ~12s while open
// ---------------------------------------------------------------------------
const MESSAGES = [
  "Welcome! What are we creating today?",
  "Ready to help — just say the word.",
  "Got a new idea? Let's build it together.",
  "Need help with code, design, or content?",
  "Drop a prompt and let's get started.",
  "Here whenever you need me ⚡",
  "Let's ship something great today.",
  "What would you like to work on?",
  "Start with an idea — I'll handle the rest.",
  "New project? Let's break it down together.",
];

function randomMsg(exclude) {
  const pool = MESSAGES.filter((m) => m !== exclude);
  return pool[Math.floor(Math.random() * pool.length)];
}

// ---------------------------------------------------------------------------
// Quick-action chips shown in expanded panel
// ---------------------------------------------------------------------------
const CHIPS = [
  { label: 'Build an app', prompt: 'Build me a modern web app with a clean UI' },
  { label: 'Generate image', prompt: 'Generate a futuristic cityscape at night with neon lights' },
  { label: 'Explain code', prompt: 'Explain this code to me step by step' },
  { label: 'Write a script', prompt: 'Write a Python script that' },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function MascotAssistant() {
  const { firePendingTemplate, setPage } = useApp();

  const [open, setOpen]       = useState(() => {
    try { return localStorage.getItem('ma_mascot_open') === '1'; } catch { return false; }
  });
  const [visible, setVisible] = useState(false); // slide-in guard
  const [msg, setMsg]         = useState(MESSAGES[0]);
  const [blink, setBlink]     = useState(false);
  const msgTimer  = useRef(null);
  const blinkTimer = useRef(null);

  // Slide in after mount
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 400);
    return () => clearTimeout(t);
  }, []);

  // Persist open state
  useEffect(() => {
    try { localStorage.setItem('ma_mascot_open', open ? '1' : '0'); } catch {}
  }, [open]);

  // Rotate message while panel is open
  useEffect(() => {
    if (!open) return;
    setMsg(randomMsg(null));
    msgTimer.current = setInterval(() => {
      setMsg((prev) => randomMsg(prev));
    }, 12000);
    return () => clearInterval(msgTimer.current);
  }, [open]);

  // Random blink loop — always running
  const scheduleBlink = useCallback(() => {
    const delay = 3000 + Math.random() * 3000; // 3–6s
    blinkTimer.current = setTimeout(() => {
      setBlink(true);
      setTimeout(() => {
        setBlink(false);
        scheduleBlink();
      }, 180);
    }, delay);
  }, []);

  useEffect(() => {
    scheduleBlink();
    return () => clearTimeout(blinkTimer.current);
  }, [scheduleBlink]);

  const handleChip = (chip) => {
    setPage('chat');
    firePendingTemplate(chip.prompt, false);
    setOpen(false);
  };

  return (
    <>
      {/* ------------------------------------------------------------------ */}
      {/* Pure CSS keyframe animations                                        */}
      {/* ------------------------------------------------------------------ */}
      <style>{`
        @keyframes mascot-float {
          0%, 100% { transform: translateY(0px); }
          50%       { transform: translateY(-6px); }
        }
        @keyframes mascot-breathe {
          0%, 100% { transform: scale(1); }
          50%       { transform: scale(1.022); }
        }
        @keyframes mascot-glow {
          0%, 100% { filter: drop-shadow(0 0 8px rgba(96,165,250,0.55))
                             drop-shadow(0 0 20px rgba(139,92,246,0.30)); }
          50%       { filter: drop-shadow(0 0 16px rgba(96,165,250,0.90))
                             drop-shadow(0 0 36px rgba(139,92,246,0.55)); }
        }
        @keyframes mascot-eye-glow {
          0%, 100% { opacity: 0.7; }
          50%       { opacity: 1; }
        }
        @keyframes mascot-slide-in {
          0%   { opacity: 0; transform: translateY(24px) scale(0.92); }
          100% { opacity: 1; transform: translateY(0)    scale(1); }
        }
        @keyframes mascot-panel-in {
          0%   { opacity: 0; transform: translateY(12px) scale(0.96); }
          100% { opacity: 1; transform: translateY(0)    scale(1); }
        }
        @keyframes mascot-particle {
          0%   { opacity: 0; transform: translateY(0)    scale(0.5); }
          30%  { opacity: 0.7; }
          100% { opacity: 0; transform: translateY(-40px) scale(1.2); }
        }
        .mascot-float    { animation: mascot-float   2.8s ease-in-out infinite; }
        .mascot-breathe  { animation: mascot-breathe 2.8s ease-in-out infinite; }
        .mascot-glow     { animation: mascot-glow    2.8s ease-in-out infinite; }
        .mascot-slide-in { animation: mascot-slide-in 380ms cubic-bezier(0.34,1.4,0.64,1) both; }
        .mascot-panel-in { animation: mascot-panel-in 260ms cubic-bezier(0.34,1.4,0.64,1) both; }
        .mascot-particle { animation: mascot-particle 2.4s ease-out infinite; }
        @media (prefers-reduced-motion: reduce) {
          .mascot-float, .mascot-breathe, .mascot-glow,
          .mascot-slide-in, .mascot-panel-in, .mascot-particle {
            animation: none;
          }
        }
      `}</style>

      {/* ------------------------------------------------------------------ */}
      {/* Wrapper — slides in on mount                                        */}
      {/* ------------------------------------------------------------------ */}
      <div
        className="fixed bottom-5 right-4 z-40 flex flex-col items-end gap-2 pointer-events-none"
        style={{
          opacity: visible ? 1 : 0,
          transform: visible ? 'none' : 'translateY(20px)',
          transition: 'opacity 380ms ease, transform 380ms cubic-bezier(0.34,1.4,0.64,1)',
        }}
      >

        {/* ---------------------------------------------------------------- */}
        {/* Expanded panel                                                    */}
        {/* ---------------------------------------------------------------- */}
        {open && (
          <div
            className="mascot-panel-in pointer-events-auto
                       w-72 sm:w-80 rounded-2xl border border-white/10
                       bg-[#0f0f1a]/95 backdrop-blur-xl
                       shadow-[0_8px_40px_rgba(0,0,0,0.6),0_0_0_1px_rgba(139,92,246,0.12)]
                       overflow-hidden flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)] animate-pulse" />
                <span className="text-xs font-semibold text-white">Mini Assistant</span>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="w-6 h-6 flex items-center justify-center rounded-full text-slate-500
                           hover:text-slate-300 hover:bg-white/5 transition-colors"
              >
                <X size={13} />
              </button>
            </div>

            {/* Message bubble */}
            <div className="px-4 py-3">
              <p className="text-sm text-slate-200 leading-relaxed min-h-[40px] transition-all duration-500">
                {msg}
              </p>
            </div>

            {/* Quick-action chips */}
            <div className="px-4 pb-4 flex flex-wrap gap-2">
              {CHIPS.map((chip) => (
                <button
                  key={chip.label}
                  onClick={() => handleChip(chip)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl
                             bg-white/[0.05] border border-white/[0.08] text-xs text-slate-300
                             hover:bg-violet-500/15 hover:border-violet-500/30 hover:text-white
                             active:bg-violet-500/20
                             transition-all duration-150"
                >
                  <Sparkles size={11} className="text-violet-400 flex-shrink-0" />
                  {chip.label}
                </button>
              ))}
            </div>

            {/* Collapse handle */}
            <button
              onClick={() => setOpen(false)}
              className="flex items-center justify-center gap-1 py-2 text-xs text-slate-600
                         hover:text-slate-400 border-t border-white/[0.05] transition-colors"
            >
              <ChevronDown size={12} /> Minimise
            </button>
          </div>
        )}

        {/* ---------------------------------------------------------------- */}
        {/* Mascot button — always visible                                   */}
        {/* ---------------------------------------------------------------- */}
        <button
          onClick={() => setOpen((v) => !v)}
          className="pointer-events-auto relative w-20 h-20 sm:w-24 sm:h-24
                     focus:outline-none select-none"
          style={{ filter: 'drop-shadow(0 0 12px rgba(139,92,246,0.5))' }}
          aria-label={open ? 'Minimise assistant' : 'Open assistant'}
        >
          {/* Particle drifters */}
          <Particle delay="0s"    x="10%" />
          <Particle delay="0.8s"  x="75%" />
          <Particle delay="1.6s"  x="45%" />

          {/* Breathing + floating wrapper */}
          <span className="mascot-float mascot-breathe mascot-glow block w-full h-full">
            <img
              src="/Logo.png"
              alt=""
              draggable={false}
              className="w-full h-full object-contain"
            />

            {/* Blink overlay — covers just the top-half of the face area */}
            {blink && (
              <span
                className="absolute inset-0 rounded-full pointer-events-none"
                style={{
                  background: 'radial-gradient(ellipse 60% 30% at 50% 32%, rgba(15,15,24,0.92) 0%, transparent 100%)',
                  transition: 'opacity 80ms',
                }}
              />
            )}
          </span>

          {/* Online indicator */}
          <span
            className="absolute bottom-0.5 right-0.5 w-3.5 h-3.5 rounded-full
                       bg-emerald-400 border-2 border-[#0d0d12]
                       shadow-[0_0_8px_rgba(52,211,153,0.9)] animate-pulse"
          />
        </button>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Particle — tiny floating orb for aura effect
// ---------------------------------------------------------------------------
function Particle({ delay, x }) {
  return (
    <span
      className="mascot-particle absolute bottom-0 pointer-events-none"
      style={{
        left: x,
        width: '5px',
        height: '5px',
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(139,92,246,0.9) 0%, rgba(96,165,250,0.5) 100%)',
        animationDelay: delay,
        animationDuration: `${2.2 + Math.random()}s`,
      }}
    />
  );
}
