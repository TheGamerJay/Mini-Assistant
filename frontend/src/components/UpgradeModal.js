/**
 * UpgradeModal.js
 * High-converting plan upgrade modal — triggered globally from AppContext.
 * Shows a plan comparison with monthly/annual toggle, context-aware headline,
 * and direct Stripe checkout CTA buttons.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  X, Lock, Zap, Code2, Download, Github, Rocket, Users,
  Check, Crown, Star, ArrowRight, Sparkles, Shield,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { startCheckout, getPriceId } from '../api/checkout';

// ---------------------------------------------------------------------------
// Plan data
// ---------------------------------------------------------------------------
const PLANS = [
  {
    id: 'standard',
    name: 'Standard',
    icon: Zap,
    color: 'cyan',
    monthlyPrice: 20,
    annualPrice: 17,
    credits: 1000,
    badge: null,
    description: '1,000 credits per month for AI app building, chat, and code generation. Includes full access to core features with standard performance.',
    features: [
      { text: '1,000 Mini Credits / month', highlight: true },
      { text: 'Full source code access (HTML, CSS, JS)' },
      { text: 'Download as HTML & ZIP' },
      { text: 'Push to GitHub' },
      { text: 'Live preview for all builds' },
      { text: 'Standard AI model priority' },
      { text: 'Email support' },
    ],
    cta: 'Get Standard',
  },
  {
    id: 'pro',
    name: 'Pro',
    icon: Crown,
    color: 'violet',
    monthlyPrice: 50,
    annualPrice: 42,
    credits: 4000,
    badge: 'Most Popular',
    description: '4,000 credits per month with priority performance, advanced AI capabilities, and full access to app building, code generation, and export features.',
    features: [
      { text: '4,000 Mini Credits / month', highlight: true },
      { text: 'Everything in Standard' },
      { text: 'One-click deploy to Vercel', highlight: true },
      { text: 'Full-stack project export' },
      { text: 'Priority AI model access', highlight: true },
      { text: 'Faster generation queue' },
      { text: 'Priority support' },
    ],
    cta: 'Get Pro',
  },
  {
    id: 'max',
    name: 'Max',
    icon: Users,
    color: 'amber',
    monthlyPrice: 100,
    annualPrice: 83,
    credits: 10000,
    badge: null,
    description: '10,000 credits per month with maximum performance, fastest processing, and complete access to all features including advanced AI, exports, and deployment tools.',
    features: [
      { text: '10,000 Mini Credits / month', highlight: true },
      { text: 'Everything in Pro' },
      { text: 'Up to 10 team seats' },
      { text: 'Shared credit pool' },
      { text: 'Admin dashboard & usage analytics' },
      { text: 'Dedicated support channel' },
      { text: 'Custom onboarding' },
    ],
    cta: 'Get Max',
  },
];

// Reason → headline + subtext
const REASON_COPY = {
  code: {
    headline: 'Unlock Your Full Source Code',
    sub: "You've built something great. Now own it. Upgrade to view, edit, copy, and export your complete HTML, CSS, and JS.",
    icon: Code2,
  },
  credits: {
    headline: "You've Run Out of Credits",
    sub: "Upgrade to a paid plan and get up to 10,000 credits/month — enough to build, iterate, and ship without limits.",
    icon: Zap,
  },
  export: {
    headline: 'Export Your Project',
    sub: "Download your app as a ZIP with structured files, ready for deployment. This feature is available on paid plans.",
    icon: Download,
  },
  deploy: {
    headline: 'Deploy to Vercel in One Click',
    sub: "Paid plans unlock one-click Vercel deployment. Ship your app live in seconds.",
    icon: Rocket,
  },
  github: {
    headline: 'Push to GitHub',
    sub: "Paid plans let you push directly to a GitHub repo — perfect for version control and collaboration.",
    icon: Github,
  },
  generic: {
    headline: 'Upgrade Mini Assistant',
    sub: "Unlock the full power of Mini Assistant AI — source code, exports, deployments, and more credits.",
    icon: Sparkles,
  },
};

// ---------------------------------------------------------------------------
// PlanCard
// ---------------------------------------------------------------------------
function PlanCard({ plan, annual, currentPlan, onSelect, checkoutLoading }) {
  const Icon = plan.icon;
  const price = annual ? plan.annualPrice : plan.monthlyPrice;
  const isCurrentPlan = currentPlan === plan.id;
  const isLoading = checkoutLoading === plan.id;

  const colorMap = {
    cyan:   { ring: 'ring-cyan-500/60',   bg: 'bg-cyan-500/10',   border: 'border-cyan-500/30',   btn: 'from-cyan-500 to-cyan-600',   text: 'text-cyan-400',   badge: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30' },
    violet: { ring: 'ring-violet-500/60', bg: 'bg-violet-500/10', border: 'border-violet-500/30', btn: 'from-violet-500 to-violet-600', text: 'text-violet-400', badge: 'bg-violet-500/20 text-violet-300 border-violet-500/30' },
    amber:  { ring: 'ring-amber-500/60',  bg: 'bg-amber-500/10',  border: 'border-amber-500/30',  btn: 'from-amber-500 to-amber-600',  text: 'text-amber-400',  badge: 'bg-amber-500/20 text-amber-300 border-amber-500/30' },
  };
  const c = colorMap[plan.color];

  return (
    <div
      className={`relative flex flex-col rounded-2xl border bg-[#111118] p-5 transition-all duration-200
        ${plan.badge === 'Most Popular'
          ? `border-violet-500/40 ring-1 ${c.ring} shadow-lg shadow-violet-900/20`
          : 'border-white/10 hover:border-white/20'
        }`}
    >
      {/* Badge */}
      {plan.badge && (
        <div className={`absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${c.badge}`}>
          {plan.badge}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center gap-2.5 mb-3">
        <div className={`w-8 h-8 rounded-xl ${c.bg} border ${c.border} flex items-center justify-center flex-shrink-0`}>
          <Icon className={`w-4 h-4 ${c.text}`} />
        </div>
        <div>
          <p className="text-sm font-bold text-white">{plan.name}</p>
          <p className="text-[10px] text-slate-500 leading-none mt-0.5">{plan.description}</p>
        </div>
      </div>

      {/* Price */}
      <div className="mb-4">
        <div className="flex items-end gap-1">
          <span className="text-3xl font-black text-white">${price}</span>
          <span className="text-xs text-slate-500 mb-1">/mo</span>
        </div>
        {annual && (
          <p className="text-[10px] text-emerald-400 mt-0.5">
            Billed annually · Save ${(plan.monthlyPrice - plan.annualPrice) * 12}/yr
          </p>
        )}
        <p className={`text-[11px] font-semibold mt-1 ${c.text}`}>
          {plan.credits.toLocaleString()} credits / month
        </p>
      </div>

      {/* Features */}
      <ul className="space-y-2 flex-1 mb-5">
        {plan.features.map((f, i) => (
          <li key={i} className="flex items-start gap-2">
            <Check className={`w-3.5 h-3.5 flex-shrink-0 mt-0.5 ${f.highlight ? c.text : 'text-slate-500'}`} />
            <span className={`text-[11px] leading-relaxed ${f.highlight ? 'text-slate-200 font-medium' : 'text-slate-500'}`}>
              {f.text}
            </span>
          </li>
        ))}
      </ul>

      {/* CTA */}
      {isCurrentPlan ? (
        <div className="w-full py-2.5 rounded-xl text-center text-xs font-semibold text-slate-500 bg-white/5 border border-white/10 cursor-default">
          Current Plan
        </div>
      ) : (
        <button
          onClick={() => onSelect(plan)}
          disabled={!!checkoutLoading}
          className={`w-full py-2.5 rounded-xl text-white text-xs font-bold bg-gradient-to-r ${c.btn} hover:opacity-90 transition-all shadow-lg flex items-center justify-center gap-1.5 disabled:opacity-60 disabled:cursor-wait`}
        >
          {isLoading
            ? <><span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Redirecting…</>
            : <>{plan.cta} <ArrowRight className="w-3 h-3" /></>
          }
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// UpgradeModal
// ---------------------------------------------------------------------------
export default function UpgradeModal() {
  const { upgradeModalOpen, setUpgradeModalOpen, upgradeReason, plan: currentPlan, setPage } = useApp();
  const [annual, setAnnual] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState(null);

  const copy = REASON_COPY[upgradeReason] || REASON_COPY.generic;
  const HeadlineIcon = copy.icon;

  const close = useCallback(() => {
    setUpgradeModalOpen(false);
    setCheckoutLoading(null);
  }, [setUpgradeModalOpen]);

  // Close on Escape
  useEffect(() => {
    if (!upgradeModalOpen) return;
    const handler = (e) => { if (e.key === 'Escape') close(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [upgradeModalOpen, close]);

  // Clear loading state when user presses Back from Stripe (bfcache restore)
  useEffect(() => {
    const handler = (e) => { if (e.persisted) setCheckoutLoading(null); };
    window.addEventListener('pageshow', handler);
    return () => window.removeEventListener('pageshow', handler);
  }, []);

  if (!upgradeModalOpen) return null;

  const handleSelect = async (plan) => {
    const period = annual ? 'yearly' : 'monthly';
    const priceId = await getPriceId(plan.id, period);

    if (!priceId) {
      // Price not configured — fall back to pricing page
      close();
      setPage('pricing');
      return;
    }

    setCheckoutLoading(plan.id);
    try {
      await startCheckout(priceId);
      // Tab navigates away on success — no need to clear loading
    } catch (err) {
      console.error('Stripe checkout error:', err);
      setCheckoutLoading(null);
      close();
      setPage('pricing');
    }
  };

  const handleViewAllPlans = () => {
    close();
    setPage('pricing');
  };

  return (
    <div
      className="fixed inset-0 bg-black/80 backdrop-blur-md z-[100] flex items-center justify-center p-4 overflow-y-auto"
      onClick={close}
    >
      <div
        className="relative bg-[#0c0c14] border border-white/10 rounded-2xl w-full max-w-3xl shadow-2xl my-4"
        onClick={e => e.stopPropagation()}
      >
        {/* Close */}
        <button
          onClick={close}
          className="absolute top-4 right-4 p-1.5 rounded-lg text-slate-600 hover:text-slate-300 hover:bg-white/5 transition-colors z-10"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Header */}
        <div className="px-6 pt-6 pb-5 border-b border-white/[0.06]">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500/20 to-violet-500/20 border border-white/10 flex items-center justify-center flex-shrink-0">
              <HeadlineIcon className="w-4 h-4 text-violet-400" />
            </div>
            <h2 className="text-lg font-bold text-white">{copy.headline}</h2>
          </div>
          <p className="text-sm text-slate-400 leading-relaxed max-w-lg">{copy.sub}</p>
        </div>

        {/* Billing toggle */}
        <div className="flex items-center justify-center gap-3 px-6 py-4">
          <span className={`text-xs font-medium ${!annual ? 'text-slate-200' : 'text-slate-500'}`}>Monthly</span>
          <button
            onClick={() => setAnnual(v => !v)}
            className={`relative w-11 h-6 rounded-full transition-colors ${annual ? 'bg-violet-600' : 'bg-white/10'}`}
            aria-label="Toggle billing period"
          >
            <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${annual ? 'translate-x-5' : 'translate-x-0'}`} />
          </button>
          <span className={`text-xs font-medium ${annual ? 'text-slate-200' : 'text-slate-500'}`}>
            Annual
          </span>
          {annual && (
            <span className="text-[10px] font-bold text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 px-2 py-0.5 rounded-full">
              Save up to 17%
            </span>
          )}
        </div>

        {/* Plan cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 px-6 pb-5">
          {PLANS.map(plan => (
            <PlanCard
              key={plan.id}
              plan={plan}
              annual={annual}
              currentPlan={currentPlan}
              onSelect={handleSelect}
              checkoutLoading={checkoutLoading}
            />
          ))}
        </div>

        {/* Trust signals + free note */}
        <div className="px-6 pb-6 space-y-4">
          <div className="flex items-center justify-center gap-6 py-3 border-t border-white/[0.06]">
            <div className="flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-slate-500" />
              <span className="text-[10px] text-slate-500">Stripe-secured payments</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Star className="w-3.5 h-3.5 text-slate-500" />
              <span className="text-[10px] text-slate-500">Cancel anytime</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-slate-500" />
              <span className="text-[10px] text-slate-500">Instant access</span>
            </div>
          </div>

          <div className="text-center">
            <span className="text-xs text-slate-600">
              Keep building on free — or{' '}
              <button
                onClick={handleViewAllPlans}
                className="text-cyan-500 hover:text-cyan-400 underline underline-offset-2"
              >
                view full plan details
              </button>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
