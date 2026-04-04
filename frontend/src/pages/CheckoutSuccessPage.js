/**
 * CheckoutSuccessPage.js
 * Post-checkout success page — shown after Stripe redirects back.
 * Subscription confirmed → redirects to settings to add API key.
 */

import React, { useState, useEffect, useRef } from 'react';
import { Check, KeyRound, ArrowRight, Code2, Download, Github, Sparkles } from 'lucide-react';
import { useApp } from '../context/AppContext';

const FEATURES = [
  { icon: Code2,     text: 'Full source code — view, copy, edit' },
  { icon: Download,  text: 'Download as HTML & ZIP' },
  { icon: Github,    text: 'Push directly to GitHub' },
  { icon: Sparkles,  text: 'AI chat, image generation & more' },
];

const CONFETTI_COLORS = ['#7c3aed', '#06b6d4', '#f59e0b', '#10b981', '#f43f5e'];
const CONFETTI_COUNT  = 48;

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
            position: 'absolute', left: `${p.left}%`, top: 0,
            width: p.shape === 'circle' ? p.size : p.size * 0.6,
            height: p.shape === 'circle' ? p.size : p.size * 1.4,
            backgroundColor: p.color,
            borderRadius: p.shape === 'circle' ? '50%' : '2px',
            animation: `confetti-fall ${p.duration}s ${p.delay}s ease-in forwards`,
            transform: `rotate(${p.rotation}deg)`, opacity: 0,
          }}
        />
      ))}
    </div>
  );
}

const AUTO_REDIRECT_SECS = 10;

export default function CheckoutSuccessPage() {
  const { setPage, refreshSubscription } = useApp();
  const [countdown, setCountdown] = useState(AUTO_REDIRECT_SECS);
  const timerRef = useRef(null);

  useEffect(() => {
    // Refresh subscription state so TopBar and gate reflect new status
    refreshSubscription();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    timerRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          setPage('settings');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const goSettings = () => { clearInterval(timerRef.current); setPage('settings'); };
  const goChat     = () => { clearInterval(timerRef.current); setPage('chat');     };

  return (
    <div className="relative h-full overflow-y-auto bg-[#0b0b12] flex items-center justify-center px-4 py-12">
      <Confetti />

      <div className="relative z-10 w-full max-w-lg text-center">
        {/* Icon */}
        <div className="flex justify-center mb-6">
          <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-violet-500 to-cyan-500 flex items-center justify-center shadow-2xl animate-[bounceIn_0.6s_ease-out]">
            <Check className="w-10 h-10 text-white" strokeWidth={2.5} />
          </div>
        </div>

        <div className="mb-2">
          <span className="text-xs font-bold uppercase tracking-widest text-violet-400">
            Payment confirmed
          </span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-black text-white mb-2 tracking-tight">
          You're subscribed!
        </h1>
        <p className="text-slate-400 text-base mb-6">
          One last step — add your API key to start building.
        </p>

        {/* What's unlocked */}
        <div className="rounded-2xl border border-violet-500/30 bg-violet-500/10 p-5 mb-6 text-left">
          <p className="text-[11px] font-bold text-slate-500 uppercase tracking-widest mb-3">
            What's unlocked
          </p>
          <ul className="space-y-2.5">
            {FEATURES.map(({ icon: FIcon, text }, i) => (
              <li key={i} className="flex items-center gap-3">
                <div className="w-7 h-7 rounded-lg bg-violet-500/10 border border-violet-500/30 flex items-center justify-center flex-shrink-0">
                  <FIcon className="w-3.5 h-3.5 text-violet-400" />
                </div>
                <span className="text-sm text-slate-200">{text}</span>
                <Check className="w-4 h-4 ml-auto flex-shrink-0 text-violet-400" />
              </li>
            ))}
          </ul>
        </div>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center mb-6">
          <button
            onClick={goSettings}
            className="flex items-center justify-center gap-2 px-6 py-3 rounded-2xl bg-gradient-to-r from-violet-600 to-cyan-600 text-white font-bold text-sm hover:opacity-90 transition-all shadow-lg"
          >
            <KeyRound className="w-4 h-4" /> Add API Key
          </button>
          <button
            onClick={goChat}
            className="flex items-center justify-center gap-2 px-6 py-3 rounded-2xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 font-medium text-sm transition-all"
          >
            Go to Chat <ArrowRight className="w-4 h-4" />
          </button>
        </div>

        <p className="text-xs text-slate-600">
          Redirecting to settings in{' '}
          <span className="font-mono text-slate-400 font-bold">{countdown}s</span>
          {' '}—{' '}
          <button onClick={goSettings} className="text-cyan-600 hover:text-cyan-400 underline underline-offset-2 transition-colors">
            go now
          </button>
        </p>
      </div>

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
