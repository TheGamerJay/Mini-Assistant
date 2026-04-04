/**
 * PricingPage.js
 * Single-plan BYOK pricing page — monthly / yearly toggle.
 */

import React, { useState, useCallback } from 'react';
import {
  Check, KeyRound, Zap, Code2, Download, Github,
  Sparkles, ArrowRight, Shield, RefreshCw,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { startCheckout, getPriceId, openBillingPortal } from '../api/checkout';

const FEATURES = [
  { icon: Code2,    text: 'Full source code — HTML, CSS, JS' },
  { icon: Download, text: 'Download as HTML & ZIP' },
  { icon: Github,   text: 'Push directly to GitHub' },
  { icon: Zap,      text: 'AI chat, app building & code generation' },
  { icon: Sparkles, text: 'Image generation (uses your API key)' },
  { icon: Shield,   text: 'Your key, encrypted with AES-256-GCM' },
  { icon: KeyRound, text: 'Works with Anthropic & OpenAI keys' },
];

const MONTHLY_PRICE  = 20;
const YEARLY_MONTHLY = 17;
const YEARLY_TOTAL   = 200;

export default function PricingPage() {
  const { isSubscribed, setPage } = useApp();
  const [billing, setBilling]     = useState('monthly');
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState(null);
  const [portalLoading, setPortalLoading] = useState(false);

  const handleSubscribe = useCallback(async () => {
    const priceId = await getPriceId(billing);
    if (!priceId) {
      setError('Stripe is not configured. Please contact support.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await startCheckout(priceId);
    } catch (err) {
      setError(err.message || 'Checkout failed. Please try again.');
      setLoading(false);
    }
  }, [billing]);

  const handleManage = useCallback(async () => {
    setPortalLoading(true);
    try {
      await openBillingPortal();
    } catch (err) {
      setError(err.message || 'Could not open billing portal.');
    } finally {
      setPortalLoading(false);
    }
  }, []);

  return (
    <div className="h-full overflow-y-auto bg-[#0b0b12] px-4 py-10">
      <div className="max-w-2xl mx-auto">

        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl sm:text-4xl font-black text-white mb-3 tracking-tight">
            One Plan. Full Access.
          </h1>
          <p className="text-slate-400 text-base max-w-md mx-auto">
            Bring your own Anthropic or OpenAI key. No credit meter, no per-request limits — just raw AI power on your budget.
          </p>
        </div>

        {/* Billing toggle */}
        <div className="flex items-center justify-center mb-6">
          <div className="flex items-center gap-1 p-1 rounded-xl bg-white/5 border border-white/[0.06]">
            {['monthly', 'yearly'].map((b) => (
              <button
                key={b}
                onClick={() => setBilling(b)}
                className={`px-5 py-2 rounded-lg text-sm font-semibold transition-all ${
                  billing === b
                    ? 'bg-violet-600 text-white shadow'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {b === 'monthly' ? 'Monthly' : 'Yearly'}
                {b === 'yearly' && (
                  <span className="ml-2 text-[10px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded-full">
                    Save 15%
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Plan card */}
        <div className="rounded-2xl border border-violet-500/30 bg-gradient-to-br from-violet-500/5 to-cyan-500/5 overflow-hidden mb-6">
          {/* Price */}
          <div className="px-8 pt-8 pb-6 text-center border-b border-white/5">
            <div className="flex items-end justify-center gap-1 mb-1">
              <span className="text-5xl font-black text-white">
                ${billing === 'yearly' ? YEARLY_MONTHLY : MONTHLY_PRICE}
              </span>
              <span className="text-slate-500 mb-2">/mo</span>
            </div>
            {billing === 'yearly' && (
              <p className="text-sm text-slate-500">Billed ${YEARLY_TOTAL}/year</p>
            )}
          </div>

          {/* Features */}
          <div className="px-8 py-6">
            <ul className="space-y-3">
              {FEATURES.map(({ icon: FIcon, text }) => (
                <li key={text} className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-lg bg-violet-500/10 border border-violet-500/20 flex items-center justify-center flex-shrink-0">
                    <FIcon className="w-3.5 h-3.5 text-violet-400" />
                  </div>
                  <span className="text-sm text-slate-300">{text}</span>
                  <Check className="w-4 h-4 ml-auto text-emerald-400 flex-shrink-0" />
                </li>
              ))}
            </ul>
          </div>

          {/* CTA */}
          <div className="px-8 pb-8">
            {error && (
              <p className="text-xs text-red-400 mb-3 text-center">{error}</p>
            )}
            {isSubscribed ? (
              <div className="space-y-3">
                <div className="w-full py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm font-semibold text-center flex items-center justify-center gap-2">
                  <Check size={16} /> Subscribed — active plan
                </div>
                <button
                  onClick={handleManage}
                  disabled={portalLoading}
                  className="w-full py-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 text-sm font-medium transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {portalLoading ? <RefreshCw size={14} className="animate-spin" /> : null}
                  Manage Subscription
                </button>
              </div>
            ) : (
              <button
                onClick={handleSubscribe}
                disabled={loading}
                className="w-full py-3 rounded-xl bg-gradient-to-r from-violet-600 to-cyan-600 text-white text-sm font-bold hover:opacity-90 transition-all disabled:opacity-50 flex items-center justify-center gap-2 shadow-lg"
              >
                {loading ? 'Redirecting…' : `Subscribe ${billing === 'yearly' ? 'Yearly' : 'Monthly'}`}
                {!loading && <ArrowRight size={14} />}
              </button>
            )}
            <p className="text-[10px] text-slate-600 text-center mt-3">
              Cancel anytime · No credits · Powered by Stripe
            </p>
          </div>
        </div>

        {/* BYOK explanation */}
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-6">
          <h3 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
            <KeyRound size={14} className="text-violet-400" /> How BYOK works
          </h3>
          <ol className="space-y-2 text-sm text-slate-400">
            {[
              'Subscribe below — you get full access to all features.',
              'Go to Settings → add your Anthropic or OpenAI API key.',
              'Mini Assistant encrypts and stores it securely (AES-256-GCM).',
              'All AI calls use your key — you control your own costs.',
            ].map((step, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-[10px] font-bold text-violet-400 mt-0.5 w-4 flex-shrink-0">{i + 1}.</span>
                {step}
              </li>
            ))}
          </ol>
        </div>

        <div className="text-center mt-6">
          <button
            onClick={() => setPage('chat')}
            className="text-xs text-slate-600 hover:text-slate-400 transition-colors"
          >
            ← Back to chat
          </button>
        </div>
      </div>
    </div>
  );
}
