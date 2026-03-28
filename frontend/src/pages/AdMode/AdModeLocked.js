/**
 * AdModeLocked — shown when user does not have Ad Mode access.
 * Clean premium locked screen with pricing and checkout CTAs.
 */

import React, { useState, useEffect } from 'react';
import { Zap, Image, Sparkles, Target, Download, TrendingUp, Lock, Check } from 'lucide-react';
import { api } from '../../api/client';
import { toast } from 'sonner';

const FEATURES = [
  { icon: Sparkles, text: 'AI-generated ad copy — hooks, headlines, CTAs' },
  { icon: Image, text: 'DALL·E 3 ad images matched to your brand' },
  { icon: Target, text: 'Multiple ad angles: emotional, benefit, curiosity, urgency' },
  { icon: TrendingUp, text: 'Brand profile generation from your business info' },
  { icon: Download, text: 'Download creatives ready for ads manager' },
];

const PLANS = [
  {
    id: 'monthly',
    label: 'Monthly',
    price: '$29',
    period: '/month',
    note: 'Cancel anytime',
    highlight: false,
  },
  {
    id: 'yearly',
    label: 'Yearly',
    price: '$19',
    period: '/month',
    note: 'Billed $228/year · Save 34%',
    highlight: true,
    badge: 'Best Value',
  },
];

export default function AdModeLocked() {
  const [loading, setLoading] = useState(null);

  // Clear loading when user presses Back from Stripe (bfcache restore)
  useEffect(() => {
    const handler = (e) => { if (e.persisted) setLoading(null); };
    window.addEventListener('pageshow', handler);
    return () => window.removeEventListener('pageshow', handler);
  }, []);

  const handleCheckout = async (billingPeriod) => {
    setLoading(billingPeriod);
    try {
      const { checkout_url } = await api.adModeCheckout(billingPeriod);
      if (checkout_url) {
        window.location.href = checkout_url;
      } else {
        setLoading(null);
        toast.error('Could not start checkout. Try again.');
      }
    } catch (err) {
      toast.error(err?.message || 'Could not start checkout. Try again.');
      setLoading(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-2xl mx-auto px-6 py-12">

        {/* Hero */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 bg-violet-500/10 border border-violet-500/20 rounded-full px-4 py-1.5 text-xs text-violet-400 font-medium mb-6">
            <Lock size={11} /> Add-On Required
          </div>
          <h1 className="text-3xl font-bold text-slate-100 mb-3 leading-tight">
            Your ads never sleep.
          </h1>
          <p className="text-slate-400 text-base leading-relaxed max-w-lg mx-auto">
            Ad Mode uses Claude AI and DALL·E 3 to create complete ad campaigns —
            copy, images, and creative angles — in minutes.
          </p>
        </div>

        {/* Feature list */}
        <div className="bg-white/3 border border-white/8 rounded-2xl p-6 mb-8">
          <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-4">
            What's included
          </p>
          <div className="space-y-3">
            {FEATURES.map(({ icon: Icon, text }) => (
              <div key={text} className="flex items-center gap-3">
                <div className="h-7 w-7 rounded-lg bg-violet-500/10 flex items-center justify-center flex-shrink-0">
                  <Icon size={13} className="text-violet-400" />
                </div>
                <span className="text-sm text-slate-300">{text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Pricing cards */}
        <div className="grid grid-cols-2 gap-3 mb-6">
          {PLANS.map((plan) => (
            <div
              key={plan.id}
              className={`relative rounded-2xl border p-5 transition-all
                ${plan.highlight
                  ? 'border-violet-500/50 bg-violet-500/8'
                  : 'border-white/8 bg-white/3'}`}
            >
              {plan.badge && (
                <div className="absolute -top-2.5 left-1/2 -translate-x-1/2">
                  <span className="bg-violet-500 text-white text-[10px] font-bold px-3 py-0.5 rounded-full">
                    {plan.badge}
                  </span>
                </div>
              )}
              <p className="text-xs text-slate-500 mb-1">{plan.label}</p>
              <div className="flex items-baseline gap-1 mb-0.5">
                <span className="text-2xl font-bold text-slate-100">{plan.price}</span>
                <span className="text-xs text-slate-500">{plan.period}</span>
              </div>
              <p className="text-[10px] text-slate-600 mb-4">{plan.note}</p>
              <button
                onClick={() => handleCheckout(plan.id)}
                disabled={!!loading}
                className={`w-full py-2.5 rounded-xl text-sm font-medium transition-all
                  ${plan.highlight
                    ? 'bg-violet-500 hover:bg-violet-400 text-white'
                    : 'bg-white/8 hover:bg-white/12 text-slate-200 border border-white/10'}
                  disabled:opacity-50 disabled:cursor-not-allowed`}
              >
                {loading === plan.id ? 'Opening checkout…' : 'Unlock Ad Mode'}
              </button>
            </div>
          ))}
        </div>

        {/* Trust line */}
        <div className="flex items-center justify-center gap-1.5 text-[11px] text-slate-600">
          <Check size={11} className="text-emerald-500" />
          Cancel anytime from your billing portal · Powered by Stripe
        </div>

      </div>
    </div>
  );
}
