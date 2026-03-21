/**
 * PurchaseCreditsModal.js
 * Subscriber-only credit top-up — wired to real Stripe checkout.
 * Free users see an upgrade prompt instead.
 */

import React, { useState, useCallback } from 'react';
import { X, Zap, Star, ArrowRight, Lock } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { startCheckout, PRICE_IDS } from '../api/checkout';

// ---------------------------------------------------------------------------
// Top-up bundles — mirror backend TOPUP_PRICES
// ---------------------------------------------------------------------------
const BUNDLES = [
  {
    id: 'topup_10',
    credits: 100,
    price: 10,
    label: null,
    highlight: false,
    priceId: PRICE_IDS.topup.t10,
    perCredit: (10 / 100).toFixed(3),
  },
  {
    id: 'topup_25',
    credits: 300,
    price: 25,
    label: 'Most Popular',
    highlight: false,
    priceId: PRICE_IDS.topup.t25,
    perCredit: (25 / 300).toFixed(3),
    savings: 'Save 17% vs basic',
  },
  {
    id: 'topup_50',
    credits: 800,
    price: 50,
    label: 'Best Value',
    highlight: true,
    priceId: PRICE_IDS.topup.t50,
    perCredit: (50 / 800).toFixed(3),
    savings: 'Save 47% vs basic',
  },
];

// ---------------------------------------------------------------------------
// BundleCard
// ---------------------------------------------------------------------------
function BundleCard({ bundle, onSelect, loading }) {
  const { credits, price, label, highlight, savings, perCredit } = bundle;
  const isLoading = loading === bundle.id;

  return (
    <div
      className={`relative rounded-2xl border p-5 flex flex-col gap-3 transition-all cursor-pointer group
        ${highlight
          ? 'border-amber-500/40 bg-amber-500/5 hover:border-amber-500/60 hover:bg-amber-500/10'
          : 'border-white/10 bg-white/[0.02] hover:border-cyan-500/30 hover:bg-white/[0.04]'
        }
        ${loading && loading !== bundle.id ? 'opacity-50 pointer-events-none' : ''}
      `}
      onClick={() => !loading && onSelect(bundle)}
    >
      {/* Badge */}
      {label && (
        <div className="absolute -top-2.5 left-1/2 -translate-x-1/2">
          <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full whitespace-nowrap
            ${label === 'Best Value' ? 'bg-amber-500 text-black' : 'bg-cyan-500 text-black'}`}>
            {label}
          </span>
        </div>
      )}

      {/* Credits */}
      <div className="text-center mt-1">
        <p className={`text-2xl font-bold ${highlight ? 'text-amber-400' : 'text-white'}`}>
          {credits.toLocaleString()}
          <span className="text-sm font-medium text-slate-500 ml-1">credits</span>
        </p>
        <p className={`text-sm font-semibold mt-0.5 ${highlight ? 'text-amber-500' : 'text-cyan-400'}`}>
          ${price} one-time
        </p>
        {savings && (
          <p className="text-[10px] text-emerald-400 mt-0.5">{savings}</p>
        )}
      </div>

      {/* Per-credit cost */}
      <p className="text-center text-[10px] text-slate-600 font-mono">
        ${perCredit} / credit
      </p>

      {/* CTA */}
      <button
        disabled={!!loading}
        className={`w-full py-2 rounded-xl text-sm font-semibold transition-all mt-auto flex items-center justify-center gap-1.5
          ${highlight
            ? 'bg-amber-500 hover:bg-amber-400 text-black'
            : 'bg-white/10 hover:bg-white/15 text-white group-hover:bg-cyan-500/20 group-hover:text-cyan-400'
          }
          disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        {isLoading
          ? <><span className="w-3 h-3 border-2 border-current/40 border-t-current rounded-full animate-spin" /> Redirecting…</>
          : <>Buy Now <ArrowRight size={13} /></>
        }
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subscriber-only gate — shown to free users
// ---------------------------------------------------------------------------
function SubscriberGate({ onClose, onViewPlans }) {
  return (
    <div className="px-6 py-10 flex flex-col items-center text-center gap-4">
      <div className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
        <Lock size={22} className="text-amber-400" />
      </div>
      <div>
        <h3 className="text-base font-bold text-white mb-1">Subscribers Only</h3>
        <p className="text-sm text-slate-400 max-w-xs leading-relaxed">
          Credit top-ups are available exclusively for paid plan members.
          Subscribe to get monthly credits and unlock the ability to purchase additional top-ups.
        </p>
      </div>
      <div className="flex flex-col sm:flex-row gap-2 w-full max-w-xs">
        <button
          onClick={onViewPlans}
          className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-violet-600 text-white text-sm font-bold hover:opacity-90 transition-all"
        >
          View Plans <ArrowRight size={14} />
        </button>
        <button
          onClick={onClose}
          className="flex-1 px-4 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-400 text-sm font-medium transition-all"
        >
          Maybe Later
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main modal
// ---------------------------------------------------------------------------
export default function PurchaseCreditsModal({ onClose }) {
  const { credits, plan, isSubscribed, setPage } = useApp();
  const [loading, setLoading] = useState(null); // bundle id while loading

  const handleViewPlans = useCallback(() => {
    onClose();
    setPage('pricing');
  }, [onClose, setPage]);

  const handleSelectBundle = useCallback(async (bundle) => {
    if (!bundle.priceId) {
      // Price not configured — fall back to pricing page
      onClose();
      setPage('pricing');
      return;
    }
    setLoading(bundle.id);
    try {
      await startCheckout(bundle.priceId);
      // If we get here checkout didn't redirect — leave spinner as "loading"
    } catch (err) {
      console.error('Top-up checkout error:', err);
      setLoading(null);
    }
  }, [onClose, setPage]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg bg-[#111118] border border-white/10 rounded-2xl sm:rounded-3xl shadow-2xl overflow-y-auto max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-white/5">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Zap size={16} className="text-amber-400" /> Top-Up Credits
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              One-time purchases · Never expire · 1 chat = 1 credit · 1 image = 3 credits
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-all"
          >
            <X size={16} />
          </button>
        </div>

        {/* Subscriber gate or bundles */}
        {!isSubscribed ? (
          <SubscriberGate onClose={onClose} onViewPlans={handleViewPlans} />
        ) : (
          <>
            {/* Current balance */}
            <div className="mx-6 mt-4 px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/5 flex items-center justify-between">
              <span className="text-xs text-slate-500">Current balance</span>
              <span className="text-sm font-mono font-semibold text-cyan-400 flex items-center gap-1">
                <Zap size={12} /> {credits ?? '—'} credits
              </span>
            </div>

            {/* Bundle grid */}
            <div className="px-4 sm:px-6 pt-4 pb-2 grid grid-cols-1 sm:grid-cols-3 gap-3">
              {BUNDLES.map(bundle => (
                <BundleCard
                  key={bundle.id}
                  bundle={bundle}
                  onSelect={handleSelectBundle}
                  loading={loading}
                />
              ))}
            </div>

            {/* Info footer */}
            <div className="px-6 py-4 border-t border-white/5 mt-2">
              <p className="text-[11px] text-slate-600 text-center">
                Top-up credits stack on top of your {plan} plan's monthly credits and never expire.
                Powered by Stripe — secure, instant delivery.
              </p>
            </div>
          </>
        )}

      </div>
    </div>
  );
}
