/**
 * CheckoutSuccessPage.js
 * Post-checkout celebration page — shown after Stripe redirects back.
 * Refreshes user plan/credits, shows what's unlocked, then auto-navigates to chat.
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  Check, Zap, ArrowRight, Code2, Download, Github,
  Rocket, Crown, Users, Star, Sparkles,
} from 'lucide-react';
import { useApp } from '../context/AppContext';

// ---------------------------------------------------------------------------
// Per-plan unlock config
// ---------------------------------------------------------------------------
const PLAN_UNLOCKS = {
  standard: {
    name: 'Standard',
    color: 'from-cyan-400 to-cyan-600',
    textColor: 'text-cyan-400',
    borderColor: 'border-cyan-500/30',
    bgColor: 'bg-cyan-500/10',
    icon: Zap,
    tagline: 'Ready to build something real.',
    features: [
      { icon: Code2,    text: 'Full source code — view, copy, edit' },
      { icon: Download, text: 'Download as HTML & ZIP' },
      { icon: Github,   text: 'Push directly to GitHub' },
      { icon: Zap,      text: '1,000 credits every month' },
    ],
  },
  pro: {
    name: 'Pro',
    color: 'from-violet-400 to-violet-600',
    textColor: 'text-violet-400',
    borderColor: 'border-violet-500/30',
    bgColor: 'bg-violet-500/10',
    icon: Crown,
    tagline: 'Ship faster than ever before.',
    features: [
      { icon: Rocket,   text: 'One-click deploy to Vercel' },
      { icon: Code2,    text: 'Full-stack project export' },
      { icon: Crown,    text: 'Priority AI model access' },
      { icon: Zap,      text: '4,000 credits every month' },
    ],
  },
  max: {
    name: 'Max',
    color: 'from-amber-400 to-amber-600',
    textColor: 'text-amber-400',
    borderColor: 'border-amber-500/30',
    bgColor: 'bg-amber-500/10',
    icon: Users,
    tagline: 'The full power of Mini Assistant.',
    features: [
      { icon: Users,    text: 'Unlimited builds & exports' },
      { icon: Zap,      text: '10,000 credits every month' },
      { icon: Crown,    text: 'Dedicated support channel' },
      { icon: Sparkles, text: 'Admin dashboard & usage analytics' },
    ],
  },
  topup: {
    name: 'Credits',
    color: 'from-amber-400 to-amber-500',
    textColor: 'text-amber-400',
    borderColor: 'border-amber-500/30',
    bgColor: 'bg-amber-500/10',
    icon: Zap,
    tagline: 'Topped up and ready to go.',
    features: [
      { icon: Zap,      text: 'Credits added instantly to your account' },
      { icon: Star,     text: 'Never expire — use them any time' },
      { icon: Code2,    text: 'Build, chat, generate images & more' },
    ],
  },
};

const AUTO_REDIRECT_SECS = 8;

// ---------------------------------------------------------------------------
// Confetti — pure CSS, no library
// ---------------------------------------------------------------------------
const CONFETTI_COLORS = [
  '#7c3aed', '#06b6d4', '#f59e0b', '#10b981', '#f43f5e', '#8b5cf6',
];
const CONFETTI_COUNT = 48;

function Confetti() {
  const pieces = useRef(
    Array.from({ length: CONFETTI_COUNT }, (_, i) => ({
      id: i,
      left: Math.random() * 100,
      delay: Math.random() * 1.5,
      duration: 2.2 + Math.random() * 1.8,
      size: 6 + Math.random() * 8,
      color: CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)],
      rotation: Math.random() * 360,
      shape: Math.random() > 0.5 ? 'circle' : 'rect',
    }))
  );

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden z-0">
      <style>{`
        @keyframes confetti-fall {
          0%   { transform: translateY(-20px) rotate(0deg); opacity: 1; }
          80%  { opacity: 1; }
          100% { transform: translateY(110vh) rotate(720deg); opacity: 0; }
        }
      `}</style>
      {pieces.current.map(p => (
        <div
          key={p.id}
          style={{
            position: 'absolute',
            left: `${p.left}%`,
            top: 0,
            width: p.shape === 'circle' ? p.size : p.size * 0.6,
            height: p.shape === 'circle' ? p.size : p.size * 1.4,
            backgroundColor: p.color,
            borderRadius: p.shape === 'circle' ? '50%' : '2px',
            animation: `confetti-fall ${p.duration}s ${p.delay}s ease-in forwards`,
            transform: `rotate(${p.rotation}deg)`,
            opacity: 0,
          }}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function CheckoutSuccessPage() {
  const { plan, credits, setPage, refreshCredits } = useApp();
  const [countdown, setCountdown] = useState(AUTO_REDIRECT_SECS);
  const [loaded, setLoaded] = useState(false);
  const timerRef = useRef(null);

  // Refresh credits/plan on mount so numbers are live
  useEffect(() => {
    refreshCredits();
    // Brief delay so the refresh resolves before we render
    const t = setTimeout(() => setLoaded(true), 600);
    return () => clearTimeout(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Countdown → auto-navigate
  useEffect(() => {
    timerRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          setPage('chat');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Detect plan key — if plan changed to a known upgrade, show that; else if topup, show topup
  const isTopup = !['standard', 'pro', 'max'].includes(plan);
  const planKey  = isTopup ? 'topup' : (plan || 'standard');
  const cfg      = PLAN_UNLOCKS[planKey] || PLAN_UNLOCKS.standard;
  const Icon     = cfg.icon;

  const handleStart = () => {
    clearInterval(timerRef.current);
    setPage('chat');
  };

  const handleDashboard = () => {
    clearInterval(timerRef.current);
    setPage('dashboard');
  };

  return (
    <div className="relative h-full overflow-y-auto bg-[#0b0b12] flex items-center justify-center px-4 py-12">
      <Confetti />

      <div className="relative z-10 w-full max-w-lg text-center">

        {/* Icon burst */}
        <div className="flex justify-center mb-6">
          <div className={`w-20 h-20 rounded-3xl bg-gradient-to-br ${cfg.color} flex items-center justify-center shadow-2xl animate-[bounceIn_0.6s_ease-out]`}>
            <Icon className="w-10 h-10 text-white" strokeWidth={1.5} />
          </div>
        </div>

        {/* Headline */}
        <div className="mb-2">
          <span className={`text-xs font-bold uppercase tracking-widest ${cfg.textColor}`}>
            Payment confirmed
          </span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-black text-white mb-2 tracking-tight">
          {isTopup ? 'Credits Added!' : `You're on ${cfg.name}!`}
        </h1>
        <p className="text-slate-400 text-base mb-1">{cfg.tagline}</p>
        {loaded && credits !== null && (
          <p className={`text-sm font-semibold ${cfg.textColor} mb-6`}>
            <Zap className="inline w-3.5 h-3.5 mr-1" />
            {credits.toLocaleString()} credits available now
          </p>
        )}

        {/* What's unlocked */}
        <div className={`rounded-2xl border ${cfg.borderColor} ${cfg.bgColor} p-5 mb-6 text-left`}>
          <p className="text-[11px] font-bold text-slate-500 uppercase tracking-widest mb-3">
            {isTopup ? 'What you got' : "What's unlocked"}
          </p>
          <ul className="space-y-2.5">
            {cfg.features.map(({ icon: FIcon, text }, i) => (
              <li key={i} className="flex items-center gap-3">
                <div className={`w-7 h-7 rounded-lg ${cfg.bgColor} border ${cfg.borderColor} flex items-center justify-center flex-shrink-0`}>
                  <FIcon className={`w-3.5 h-3.5 ${cfg.textColor}`} />
                </div>
                <span className="text-sm text-slate-200">{text}</span>
                <Check className={`w-4 h-4 ml-auto flex-shrink-0 ${cfg.textColor}`} />
              </li>
            ))}
          </ul>
        </div>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center mb-6">
          <button
            onClick={handleStart}
            className={`flex items-center justify-center gap-2 px-6 py-3 rounded-2xl bg-gradient-to-r ${cfg.color} text-white font-bold text-sm hover:opacity-90 transition-all shadow-lg`}
          >
            Start Building <ArrowRight className="w-4 h-4" />
          </button>
          <button
            onClick={handleDashboard}
            className="flex items-center justify-center gap-2 px-6 py-3 rounded-2xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 font-medium text-sm transition-all"
          >
            View Dashboard
          </button>
        </div>

        {/* Auto-redirect countdown */}
        <p className="text-xs text-slate-600">
          Redirecting to chat in{' '}
          <span className="font-mono text-slate-400 font-bold">{countdown}s</span>
          {' '}—{' '}
          <button
            onClick={handleStart}
            className="text-cyan-600 hover:text-cyan-400 underline underline-offset-2 transition-colors"
          >
            go now
          </button>
        </p>

      </div>

      {/* Inline bounce animation */}
      <style>{`
        @keyframes bounceIn {
          0%   { transform: scale(0.3); opacity: 0; }
          50%  { transform: scale(1.1); opacity: 1; }
          70%  { transform: scale(0.95); }
          100% { transform: scale(1); }
        }
      `}</style>
    </div>
  );
}
