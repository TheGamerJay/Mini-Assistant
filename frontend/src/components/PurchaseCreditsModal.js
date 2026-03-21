/**
 * PurchaseCreditsModal.js
 * Credit purchase UI — bundles pre-wired for Stripe (buttons placeholder until keys added).
 */

import React, { useState } from 'react';
import { X, Zap, Star, Check } from 'lucide-react';
import { useApp } from '../context/AppContext';

// ---------------------------------------------------------------------------
// Credit bundles — swap priceId with real Stripe Price IDs when ready
// ---------------------------------------------------------------------------
const BUNDLES = [
  {
    id: 'starter',
    base: 50,
    credits: 50,
    price: 5,
    bonus: null,
    label: null,
    highlight: false,
    priceId: null, // e.g. 'price_xxx'
  },
  {
    id: 'popular',
    base: 100,
    credits: 120,
    price: 10,
    bonus: '20% More',
    label: 'Most Popular',
    highlight: false,
    priceId: null,
  },
  {
    id: 'value',
    base: 250,
    credits: 375,
    price: 20,
    bonus: '50% More',
    label: null,
    highlight: false,
    priceId: null,
  },
  {
    id: 'pro',
    base: 600,
    credits: 1000,
    price: 50,
    bonus: '67% More',
    label: 'Best Value',
    highlight: true,
    priceId: null,
  },
];

function BundleCard({ bundle, onSelect, loading }) {
  const { credits, base, price, bonus, label, highlight } = bundle;

  return (
    <div
      className={`relative rounded-2xl border p-5 flex flex-col gap-3 transition-all cursor-pointer group
        ${highlight
          ? 'border-amber-500/40 bg-amber-500/5 hover:border-amber-500/60 hover:bg-amber-500/10'
          : 'border-white/10 bg-white/[0.02] hover:border-cyan-500/30 hover:bg-white/[0.04]'
        }`}
      onClick={() => onSelect(bundle)}
    >
      {/* Badge */}
      {(bonus || label) && (
        <div className="absolute -top-2.5 left-1/2 -translate-x-1/2">
          <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full whitespace-nowrap
            ${label === 'Best Value' ? 'bg-amber-500 text-black' :
              label === 'Most Popular' ? 'bg-cyan-500 text-black' :
              'bg-emerald-500 text-black'}`}>
            {label || bonus}
          </span>
        </div>
      )}

      {/* Credits */}
      <div className="text-center mt-1">
        {bonus && (
          <p className="text-[11px] text-slate-600 line-through mb-0.5">{base.toLocaleString()} credits</p>
        )}
        <p className={`text-2xl font-bold ${highlight ? 'text-amber-400' : 'text-white'}`}>
          {credits.toLocaleString()}
          <span className="text-sm font-medium text-slate-500 ml-1">credits</span>
        </p>
        <p className={`text-sm font-semibold mt-0.5 ${highlight ? 'text-amber-500' : 'text-cyan-400'}`}>
          ${price}
        </p>
      </div>

      {/* Per-credit cost */}
      <p className="text-center text-[10px] text-slate-600 font-mono">
        ${(price / credits).toFixed(3)} / credit
      </p>

      {/* CTA */}
      <button
        disabled={loading}
        className={`w-full py-2 rounded-xl text-sm font-semibold transition-all mt-auto
          ${highlight
            ? 'bg-amber-500 hover:bg-amber-400 text-black'
            : 'bg-white/10 hover:bg-white/15 text-white group-hover:bg-cyan-500/20 group-hover:text-cyan-400'
          }
          disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        {loading ? 'Processing…' : 'Buy Now'}
      </button>
    </div>
  );
}

export default function PurchaseCreditsModal({ onClose }) {
  const { credits, plan, setPage } = useApp();
  const [loading, setLoading] = useState(false);
  const [customAmount, setCustomAmount] = useState('');

  const computedCustomCredits = customAmount
    ? Math.floor(parseFloat(customAmount) * 10) // $1 = 10 credits placeholder rate
    : 0;

  function handleSelectBundle(bundle) {
    // TODO: wire to Stripe checkout once keys are added
    // For now: show coming soon toast
    alert(`Stripe coming soon! Bundle: ${bundle.credits} credits for $${bundle.price}`);
  }

  function handleCustomBuy() {
    const amount = parseFloat(customAmount);
    if (!amount || amount < 1) return;
    // TODO: wire to Stripe checkout
    alert(`Stripe coming soon! Custom: ~${computedCustomCredits} credits for $${amount}`);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-2xl bg-[#111118] border border-white/10 rounded-2xl sm:rounded-3xl shadow-2xl overflow-y-auto max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-white/5">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Zap size={16} className="text-amber-400" /> Purchase Mini Credits
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Choose a bundle or enter a custom amount.{' '}
              <span className="text-slate-600">1 chat = 1 credit · 1 image = 3 credits</span>
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-all"
          >
            <X size={16} />
          </button>
        </div>

        {/* Current balance */}
        {credits !== null && plan === 'free' && (
          <div className="mx-6 mt-4 px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/5 flex items-center justify-between">
            <span className="text-xs text-slate-500">Current balance</span>
            <span className="text-sm font-mono font-semibold text-cyan-400 flex items-center gap-1">
              <Zap size={12} /> {credits} credits
            </span>
          </div>
        )}

        {/* Bundles grid */}
        <div className="px-4 sm:px-6 pt-4 pb-2 grid grid-cols-2 gap-3 sm:gap-4">
          {BUNDLES.map(bundle => (
            <BundleCard
              key={bundle.id}
              bundle={bundle}
              onSelect={handleSelectBundle}
              loading={loading}
            />
          ))}
        </div>

        {/* Custom amount */}
        <div className="px-6 py-5 border-t border-white/5 mt-2">
          <p className="text-xs font-medium text-slate-400 mb-3">Custom amount</p>
          <div className="flex items-center gap-3">
            <div className="flex-1 flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/5 border border-white/10 focus-within:border-cyan-500/40 transition-all">
              <span className="text-slate-600 text-sm">$</span>
              <input
                type="number"
                min="1"
                placeholder="Enter amount"
                value={customAmount}
                onChange={e => setCustomAmount(e.target.value)}
                className="flex-1 bg-transparent text-slate-200 text-sm outline-none placeholder-slate-700"
              />
            </div>
            <button
              onClick={handleCustomBuy}
              disabled={!customAmount || parseFloat(customAmount) < 1 || loading}
              className="px-4 py-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-sm font-semibold hover:bg-amber-500/20 transition-all disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
            >
              {computedCustomCredits > 0 ? `Buy ${computedCustomCredits} Credits` : 'Buy Credits'}
            </button>
          </div>
        </div>

        {/* Footer: upgrade to subscription */}
        <div className="px-6 pb-5">
          <div className="rounded-2xl bg-gradient-to-r from-cyan-500/5 to-violet-500/5 border border-cyan-500/10 p-4 flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold text-white flex items-center gap-1.5">
                <Star size={11} className="text-cyan-400" /> Want unlimited access?
              </p>
              <p className="text-[11px] text-slate-500 mt-0.5">Subscribe and never worry about credits again.</p>
            </div>
            <button
              onClick={() => { setPage('settings'); onClose(); }}
              className="flex-shrink-0 px-4 py-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs font-semibold hover:bg-cyan-500/20 transition-all"
            >
              View Plans
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
