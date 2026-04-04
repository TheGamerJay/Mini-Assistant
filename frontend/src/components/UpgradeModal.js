/**
 * UpgradeModal.js
 * Single-plan subscription modal (BYOK model).
 * Shown when user lacks subscription or API key.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { X, Check, KeyRound, Sparkles, ArrowRight } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { startCheckout, PRICE_IDS } from '../api/checkout';

const FEATURES = [
  'Unlimited AI chat, code generation & app building',
  'Full source code access (HTML, CSS, JS)',
  'Download as HTML & ZIP',
  'Push to GitHub',
  'Live preview for all builds',
  'Image generation via your API key',
  'Priority support',
];

export default function UpgradeModal() {
  const { upgradeModalOpen, setUpgradeModalOpen, upgradeReason, isSubscribed, setPage } = useApp();
  const [billing, setBilling]     = useState('monthly');
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState(null);

  // Reset on open
  useEffect(() => {
    if (upgradeModalOpen) {
      setError(null);
      setLoading(false);
    }
  }, [upgradeModalOpen]);

  const close = useCallback(() => setUpgradeModalOpen(false), [setUpgradeModalOpen]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape') close();
  }, [close]);

  useEffect(() => {
    if (upgradeModalOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [upgradeModalOpen, handleKeyDown]);

  const handleSubscribe = async () => {
    const priceId = billing === 'yearly' ? PRICE_IDS.yearly : PRICE_IDS.monthly;
    if (!priceId) {
      setError('Stripe is not configured yet. Please try again later.');
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
  };

  const handleAddKey = () => {
    close();
    setPage('settings');
  };

  if (!upgradeModalOpen) return null;

  // If already subscribed but no key — show the key-add flow
  const needsKey = isSubscribed && upgradeReason === 'no_api_key';

  const monthlyPrice  = 20;
  const yearlyMonthly = 17; // $200/yr

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={(e) => e.target === e.currentTarget && close()}
    >
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />

      <div className="relative w-full max-w-md rounded-2xl bg-[#13131f] border border-white/10 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="relative px-6 pt-6 pb-4 bg-gradient-to-br from-violet-500/10 to-cyan-500/10 border-b border-white/5">
          <button
            onClick={close}
            className="absolute top-4 right-4 p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/10 transition-colors"
          >
            <X size={16} />
          </button>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-cyan-500 flex items-center justify-center">
              {needsKey ? <KeyRound size={18} className="text-white" /> : <Sparkles size={18} className="text-white" />}
            </div>
            <div>
              <h2 className="text-base font-bold text-white">
                {needsKey ? 'Add your API key' : 'Unlock Mini Assistant'}
              </h2>
              <p className="text-[11px] text-slate-400">
                {needsKey
                  ? 'Your subscription is active — just add an Anthropic or OpenAI key to start.'
                  : 'One plan. Bring your own key. Full access.'}
              </p>
            </div>
          </div>
        </div>

        {needsKey ? (
          /* Key-add flow */
          <div className="px-6 py-5">
            <p className="text-sm text-slate-300 mb-4">
              Mini Assistant uses <strong className="text-white">your own API key</strong> for all AI execution — no credits, no limits we control.
            </p>
            <ul className="space-y-2 mb-5">
              {['Works with Anthropic (Claude) and OpenAI (GPT)', 'Key encrypted with AES-256-GCM — never logged', 'Remove or replace anytime from Settings'].map(f => (
                <li key={f} className="flex items-start gap-2 text-sm text-slate-400">
                  <Check size={14} className="text-emerald-400 mt-0.5 flex-shrink-0" />
                  {f}
                </li>
              ))}
            </ul>
            <button
              onClick={handleAddKey}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-violet-600 to-cyan-600 text-white text-sm font-bold hover:opacity-90 transition-all flex items-center justify-center gap-2"
            >
              Go to Settings <ArrowRight size={14} />
            </button>
          </div>
        ) : (
          /* Subscribe flow */
          <div className="px-6 py-5">
            {/* Billing toggle */}
            <div className="flex items-center justify-center gap-1 p-1 rounded-xl bg-white/5 mb-5">
              {['monthly', 'yearly'].map((b) => (
                <button
                  key={b}
                  onClick={() => setBilling(b)}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    billing === b
                      ? 'bg-violet-600 text-white shadow'
                      : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {b === 'monthly' ? 'Monthly' : 'Yearly'}
                  {b === 'yearly' && (
                    <span className="ml-1.5 text-[9px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded-full">
                      Save 15%
                    </span>
                  )}
                </button>
              ))}
            </div>

            {/* Price */}
            <div className="text-center mb-5">
              <span className="text-4xl font-black text-white">
                ${billing === 'yearly' ? yearlyMonthly : monthlyPrice}
              </span>
              <span className="text-slate-500 text-sm ml-1">/mo</span>
              {billing === 'yearly' && (
                <p className="text-[11px] text-slate-500 mt-0.5">Billed $200/year</p>
              )}
            </div>

            {/* Features */}
            <ul className="space-y-2 mb-5">
              {FEATURES.map(f => (
                <li key={f} className="flex items-start gap-2 text-sm text-slate-400">
                  <Check size={13} className="text-emerald-400 mt-0.5 flex-shrink-0" />
                  {f}
                </li>
              ))}
            </ul>

            {error && (
              <p className="text-xs text-red-400 mb-3 text-center">{error}</p>
            )}

            <button
              onClick={handleSubscribe}
              disabled={loading}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-violet-600 to-cyan-600 text-white text-sm font-bold hover:opacity-90 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? 'Redirecting…' : `Subscribe ${billing === 'yearly' ? 'Yearly' : 'Monthly'}`}
              {!loading && <ArrowRight size={14} />}
            </button>

            <p className="text-[10px] text-slate-600 text-center mt-3">
              Cancel anytime · Powered by Stripe · Bring your own API key after checkout
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
