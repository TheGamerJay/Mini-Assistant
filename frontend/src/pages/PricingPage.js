/**
 * PricingPage.js
 * Full-page plan comparison — clean, premium, Stripe-ready.
 * Accessible via setPage('pricing').
 */

import React, { useState, useCallback, useEffect } from 'react';
import { startCheckout, getPriceId } from '../api/checkout';
// getPriceId is async — call it inside handlers, not at module scope
import {
  Check, X as XIcon, Zap, Crown, Users, Star, Shield,
  Code2, Download, Github, Rocket, MessageSquare, Image,
  ArrowRight, HelpCircle, ChevronDown, Plus, ArrowLeft,
} from 'lucide-react';
import { useApp } from '../context/AppContext';

// ---------------------------------------------------------------------------
// Plan data
// ---------------------------------------------------------------------------
const PLANS = [
  {
    id: 'free',
    name: 'Free',
    icon: Star,
    color: 'slate',
    monthlyPrice: 0,
    annualTotal: 0,
    credits: 50,
    badge: null,
    description: 'Start with 5 free credits after email verification. Earn more through referrals. No card required.',
    cta: 'Current Plan',
    ctaDisabled: true,
  },
  {
    id: 'standard',
    name: 'Standard',
    icon: Zap,
    color: 'cyan',
    monthlyPrice: 20,
    annualTotal: 200,   // $200/yr = $16.67/mo
    credits: 1000,
    badge: null,
    description: '1,000 credits per month for AI app building, chat, and code generation. Includes full access to core features with standard performance.',
    cta: 'Upgrade to Standard',
  },
  {
    id: 'pro',
    name: 'Pro',
    icon: Crown,
    color: 'violet',
    monthlyPrice: 50,
    annualTotal: 500,   // $500/yr = $41.67/mo
    credits: 4000,
    badge: 'Most Popular',
    description: '4,000 credits per month with priority performance, advanced AI capabilities, and full access to app building, code generation, and export features.',
    cta: 'Upgrade to Pro',
  },
  {
    id: 'max',
    name: 'Max',
    icon: Users,
    color: 'amber',
    monthlyPrice: 100,
    annualTotal: 1000,  // $1000/yr = $83.33/mo
    credits: 10000,
    badge: null,
    description: '10,000 credits per month with maximum performance, fastest processing, and complete access to every feature — advanced AI, exports, and deployment tools.',
    cta: 'Upgrade to Max',
  },
];

// Feature comparison rows
// value: true = checkmark, false = X, string = custom text, null = dash
const FEATURE_ROWS = [
  { category: 'Credits & AI' },
  { label: 'Credits',                free: '5 to start', standard: '1,000/mo',   pro: '4,000/mo',    max: '10,000/mo' },
  { label: 'AI chat (Claude)',       free: true,      standard: true,         pro: true,          max: true },
  { label: 'Image generation',       free: '3/day',   standard: true,         pro: true,          max: true },
  { label: 'AI model priority',      free: 'Standard',standard: 'Standard',   pro: 'Priority',    max: 'Dedicated' },

  { category: 'App Builder' },
  { label: 'AI app generation',      free: true,      standard: true,         pro: true,          max: true },
  { label: 'Live preview',           free: true,      standard: true,         pro: true,          max: true },
  { label: 'Full source code',       free: false,     standard: true,         pro: true,          max: true },
  { label: 'Download HTML & ZIP',    free: false,     standard: true,         pro: true,          max: true },
  { label: 'Push to GitHub',         free: false,     standard: true,         pro: true,          max: true },
  { label: 'Deploy to Vercel',       free: false,     standard: false,        pro: true,          max: true },
  { label: 'Full-stack export',      free: false,     standard: false,        pro: true,          max: true },

  { category: 'Credit Top-Ups' },
  { label: 'Buy extra credits',      free: false,     standard: true,         pro: true,          max: true },
  { label: '$10 → 100 credits',      free: false,     standard: true,         pro: true,          max: true },
  { label: '$25 → 300 credits',      free: false,     standard: true,         pro: true,          max: true },
  { label: '$50 → 800 credits',      free: false,     standard: true,         pro: true,          max: true },

  { category: 'Support' },
  { label: 'Support type',           free: 'Community',standard: 'Email',     pro: 'Priority',    max: 'Dedicated' },
  { label: 'Response time',          free: '5+ days', standard: '2 days',     pro: '1 day',       max: '4 hours' },
];

// FAQ data
const FAQ = [
  {
    q: 'What are Mini Credits?',
    a: 'Mini Credits are the currency used on our platform. 1 credit = 1 chat message. Image generation uses 3 credits. App Builder generation uses credits based on complexity. Paid plan credits reset monthly on your billing date; free credits are granted once on signup.',
  },
  {
    q: 'Can I cancel anytime?',
    a: "Yes. You can cancel your subscription at any time from your account settings. You'll retain access until the end of your current billing period. No refunds are issued for unused time on annual plans.",
  },
  {
    q: 'What happens when I run out of credits?',
    a: "When you hit zero credits, AI features are paused. Paid subscribers get credits reset at the start of each billing cycle. Free users can earn additional credits through referrals or upgrade to a paid plan for a monthly allotment.",
  },
  {
    q: 'Can I upgrade or downgrade at any time?',
    a: "Yes. Upgrades take effect immediately (with prorated billing). Downgrades take effect at the end of your current billing period.",
  },
  {
    q: 'Do unused credits roll over?',
    a: "No. Paid plan credits reset at the start of each billing period and do not roll over. Free credits are granted once on signup and do not refresh.",
  },
  {
    q: 'Is there a free trial for paid plans?',
    a: "We don't offer time-limited trials, but the Free plan is available indefinitely so you can evaluate Mini Assistant before committing to a paid tier.",
  },
];

// ---------------------------------------------------------------------------
// Color helpers
// ---------------------------------------------------------------------------
const COLOR = {
  slate:  { text: 'text-slate-400',  border: 'border-slate-500/20', bg: 'bg-slate-500/10',  btn: 'bg-white/5 hover:bg-white/10 text-slate-300',     ring: '',                       badge: '' },
  cyan:   { text: 'text-cyan-400',   border: 'border-cyan-500/30',  bg: 'bg-cyan-500/10',   btn: 'bg-gradient-to-r from-cyan-500 to-cyan-600 text-white hover:opacity-90',     ring: '',                       badge: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30' },
  violet: { text: 'text-violet-400', border: 'border-violet-500/40', bg: 'bg-violet-500/10', btn: 'bg-gradient-to-r from-violet-500 to-violet-600 text-white hover:opacity-90', ring: 'ring-1 ring-violet-500/50 shadow-lg shadow-violet-900/20', badge: 'bg-violet-500/20 text-violet-300 border-violet-500/30' },
  amber:  { text: 'text-amber-400',  border: 'border-amber-500/30', bg: 'bg-amber-500/10',  btn: 'bg-gradient-to-r from-amber-500 to-amber-600 text-white hover:opacity-90',   ring: '',                       badge: 'bg-amber-500/20 text-amber-300 border-amber-500/30' },
};

// ---------------------------------------------------------------------------
// CellValue
// ---------------------------------------------------------------------------
function CellValue({ value, color }) {
  if (value === true)  return <Check className={`w-4 h-4 mx-auto ${color}`} />;
  if (value === false) return <XIcon className="w-4 h-4 mx-auto text-slate-700" />;
  if (value === null)  return <span className="text-slate-700 text-xs">—</span>;
  return <span className="text-xs text-slate-400">{value}</span>;
}

// ---------------------------------------------------------------------------
// FaqItem
// ---------------------------------------------------------------------------
function FaqItem({ q, a }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-white/[0.06] last:border-0">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between gap-4 py-4 text-left"
      >
        <span className="text-sm font-medium text-slate-200">{q}</span>
        <ChevronDown className={`w-4 h-4 flex-shrink-0 text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <p className="text-sm text-slate-400 leading-relaxed pb-4">{a}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PricingPage
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Top-up bundles
// ---------------------------------------------------------------------------
// priceKey resolved at click time via getPriceId() — avoids '' at module load
const TOPUP_BUNDLES = [
  { id: 't10', priceKey: 't10', credits: 100, price: 10, label: null },
  { id: 't25', priceKey: 't25', credits: 300, price: 25, label: 'Popular' },
  { id: 't50', priceKey: 't50', credits: 800, price: 50, label: 'Best Value' },
];

export default function PricingPage() {
  const { plan: currentPlan, isSubscribed, credits, openUpgradeModal, setPage, getPrevPage, setPurchaseModalOpen } = useApp();
  const [annual, setAnnual] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState(null); // plan id while loading
  const [topupLoading, setTopupLoading] = useState(null);

  // Clear loading states when user presses Back from Stripe (bfcache restore)
  useEffect(() => {
    const handler = (e) => { if (e.persisted) { setCheckoutLoading(null); setTopupLoading(null); } };
    window.addEventListener('pageshow', handler);
    return () => window.removeEventListener('pageshow', handler);
  }, []);

  const handleCta = useCallback(async (plan) => {
    if (plan.id === 'free' || plan.id === currentPlan) return;

    const priceId = await getPriceId(plan.id, annual ? 'yearly' : 'monthly');
    if (!priceId) {
      openUpgradeModal('generic');
      return;
    }

    setCheckoutLoading(plan.id);
    try {
      await startCheckout(priceId);
      // Tab navigates away on success — don't clear loading
    } catch (err) {
      console.error('Stripe checkout error:', err);
      openUpgradeModal('generic');
      setCheckoutLoading(null);
    }
  }, [annual, currentPlan, openUpgradeModal]);

  // Top-ups available only to subscribers who have fully used their credits
  const creditsRemaining = credits !== null && credits > 0;
  const topupsAvailable  = isSubscribed && !creditsRemaining;

  const handleTopup = useCallback(async (bundle) => {
    setTopupLoading(bundle.id);
    try {
      const priceId = await getPriceId('topup', bundle.priceKey);
      if (!priceId) { setTopupLoading(null); setPurchaseModalOpen(true); return; }
      await startCheckout(priceId);
    } catch (err) {
      console.error('Top-up checkout error:', err);
      setTopupLoading(null);
    }
  }, [setPurchaseModalOpen]);

  return (
    <div className="h-full overflow-y-auto bg-[#0b0b12]">
      <div className="max-w-5xl mx-auto px-4 py-12">

        {/* Back button */}
        <button
          onClick={() => setPage(getPrevPage() || 'chat')}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors mb-6"
        >
          <ArrowLeft size={13} /> Back
        </button>

        {/* Hero */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-400 text-xs font-medium mb-4">
            <Zap className="w-3 h-3" /> Simple, transparent pricing
          </div>
          <h1 className="text-3xl sm:text-4xl font-black text-white mb-3 tracking-tight">
            Build more. Pay less.
          </h1>
          <p className="text-slate-400 text-base max-w-xl mx-auto leading-relaxed">
            Built for individual creators and builders. Start free, upgrade when you're ready. No hidden fees, cancel anytime.
          </p>
        </div>

        {/* Billing toggle */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <span className={`text-sm font-medium transition-colors ${!annual ? 'text-slate-200' : 'text-slate-500'}`}>Monthly</span>
          <button
            onClick={() => setAnnual(v => !v)}
            className={`relative w-12 h-6 rounded-full transition-colors ${annual ? 'bg-violet-600' : 'bg-white/10'}`}
            aria-label="Toggle billing period"
          >
            <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${annual ? 'translate-x-6' : 'translate-x-0'}`} />
          </button>
          <span className={`text-sm font-medium transition-colors ${annual ? 'text-slate-200' : 'text-slate-500'}`}>Annual</span>
          {annual && (
            <span className="text-xs font-bold text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 px-2.5 py-0.5 rounded-full">
              Save up to 17%
            </span>
          )}
        </div>

        {/* Plan cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-12">
          {PLANS.map(plan => {
            const c = COLOR[plan.color];
            const Icon = plan.icon;
            const isCurrentPlan = currentPlan === plan.id;
            const monthlyEquiv  = plan.annualTotal ? (plan.annualTotal / 12).toFixed(2) : null;

            return (
              <div
                key={plan.id}
                className={`flex flex-col rounded-2xl border bg-[#111118] p-5 transition-all ${c.border} ${c.ring}`}
              >
                {plan.badge && (
                  <div className={`self-center mb-3 px-3 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${c.badge}`}>
                    {plan.badge}
                  </div>
                )}

                <div className="flex items-center gap-2 mb-3">
                  <div className={`w-8 h-8 rounded-xl ${c.bg} border ${c.border} flex items-center justify-center`}>
                    <Icon className={`w-4 h-4 ${c.text}`} />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-white">{plan.name}</p>
                    {isCurrentPlan && (
                      <p className="text-[9px] font-semibold text-emerald-400 uppercase tracking-widest">Active</p>
                    )}
                  </div>
                </div>

                <p className="text-[11px] text-slate-500 mb-3 leading-relaxed">{plan.description}</p>

                <div className="mb-4">
                  {plan.monthlyPrice === 0 ? (
                    <div className="text-3xl font-black text-white">Free</div>
                  ) : (
                    <>
                      {annual && plan.annualTotal ? (
                        <>
                          <div className="flex items-end gap-1">
                            <span className="text-3xl font-black text-white">${plan.annualTotal}</span>
                            <span className="text-xs text-slate-500 mb-1">/year</span>
                          </div>
                          <p className="text-[10px] text-emerald-400">
                            ${monthlyEquiv}/mo billed annually
                          </p>
                        </>
                      ) : (
                        <div className="flex items-end gap-1">
                          <span className="text-3xl font-black text-white">${plan.monthlyPrice}</span>
                          <span className="text-xs text-slate-500 mb-1">/mo</span>
                        </div>
                      )}
                    </>
                  )}
                  <p className={`text-[11px] font-semibold mt-1 ${c.text}`}>
                    {plan.id === 'free' ? '5 credits to start' : `${plan.credits.toLocaleString()} credits/mo`}
                  </p>
                </div>

                <button
                  onClick={() => handleCta(plan)}
                  disabled={isCurrentPlan || plan.id === 'free' || checkoutLoading === plan.id}
                  className={`w-full py-2.5 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
                    isCurrentPlan || plan.id === 'free'
                      ? 'bg-white/5 text-slate-500 cursor-default border border-white/10'
                      : checkoutLoading === plan.id
                      ? 'opacity-60 cursor-wait ' + c.btn
                      : c.btn
                  }`}
                >
                  {checkoutLoading === plan.id
                    ? <><span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Redirecting…</>
                    : isCurrentPlan ? 'Current Plan'
                    : plan.id === 'free' ? 'Always Free'
                    : <>{plan.cta} <ArrowRight className="w-3 h-3" /></>
                  }
                </button>
              </div>
            );
          })}
        </div>

        {/* Feature comparison table */}
        <div className="mb-12">
          <h2 className="text-lg font-bold text-white mb-6 text-center">Compare all features</h2>
          <div className="rounded-2xl border border-white/10 overflow-hidden">
            {/* Table header */}
            <div className="grid grid-cols-5 border-b border-white/[0.06] bg-white/[0.02]">
              <div className="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Feature</div>
              {PLANS.map(p => (
                <div key={p.id} className={`p-4 text-center text-xs font-bold ${COLOR[p.color].text}`}>
                  {p.name}
                </div>
              ))}
            </div>

            {/* Rows */}
            {FEATURE_ROWS.map((row, i) => {
              if (row.category) {
                return (
                  <div key={i} className="grid grid-cols-5 bg-white/[0.03] border-b border-white/[0.06]">
                    <div className="col-span-5 px-4 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                      {row.category}
                    </div>
                  </div>
                );
              }
              return (
                <div key={i} className={`grid grid-cols-5 border-b border-white/[0.04] hover:bg-white/[0.015] transition-colors`}>
                  <div className="p-3.5 text-xs text-slate-400 flex items-center gap-2">
                    {row.label}
                  </div>
                  {['free', 'standard', 'pro', 'max'].map(planId => {
                    const c = COLOR[PLANS.find(p => p.id === planId).color];
                    return (
                      <div key={planId} className="p-3.5 flex items-center justify-center">
                        <CellValue value={row[planId]} color={c.text} />
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>

        {/* Top-Up Credits — subscribers only, credits must be depleted */}
        <div className="mb-12">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Plus className="w-4 h-4 text-amber-400" /> Credit Top-Ups
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                One-time purchases · Never expire · Top-ups unlock after your monthly credits are used.
              </p>
            </div>
            {!isSubscribed && (
              <span className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 px-3 py-1 rounded-full font-medium">
                Subscribers only
              </span>
            )}
            {isSubscribed && creditsRemaining && (
              <span className="text-xs text-slate-400 bg-white/5 border border-white/10 px-3 py-1 rounded-full font-medium">
                {credits} credits remaining
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {TOPUP_BUNDLES.map(bundle => {
              const isLoading = topupLoading === bundle.id;
              return (
                <div
                  key={bundle.id}
                  className={`relative rounded-2xl border p-5 flex flex-col gap-3 transition-all
                    ${bundle.label === 'Best Value'
                      ? 'border-amber-500/30 bg-amber-500/5'
                      : 'border-white/10 bg-[#111118]'
                    }
                    ${topupsAvailable ? 'hover:border-amber-500/40 cursor-pointer' : 'opacity-60'}
                  `}
                >
                  {bundle.label && (
                    <div className="absolute -top-2.5 left-1/2 -translate-x-1/2">
                      <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full whitespace-nowrap
                        ${bundle.label === 'Best Value' ? 'bg-amber-500 text-black' : 'bg-cyan-500 text-black'}`}>
                        {bundle.label}
                      </span>
                    </div>
                  )}
                  <div className="text-center mt-1">
                    <p className="text-2xl font-bold text-white">
                      {bundle.credits.toLocaleString()}
                      <span className="text-sm font-medium text-slate-500 ml-1">credits</span>
                    </p>
                    <p className="text-lg font-bold text-amber-400 mt-0.5">${bundle.price}</p>
                    <p className="text-[10px] text-slate-600 font-mono mt-1">
                      ${(bundle.price / bundle.credits).toFixed(3)} / credit
                    </p>
                  </div>
                  <button
                    onClick={() => topupsAvailable && handleTopup(bundle)}
                    disabled={!topupsAvailable || !!topupLoading}
                    className={`w-full py-2.5 rounded-xl text-sm font-bold transition-all flex items-center justify-center gap-1.5
                      ${topupsAvailable
                        ? 'bg-amber-500 hover:bg-amber-400 text-black'
                        : 'bg-white/5 text-slate-600 cursor-not-allowed border border-white/10'
                      }
                      disabled:opacity-60 disabled:cursor-not-allowed`}
                  >
                    {isLoading
                      ? <><span className="w-3 h-3 border-2 border-black/30 border-t-black rounded-full animate-spin" /> Redirecting…</>
                      : !isSubscribed
                        ? <><Shield className="w-3 h-3" /> Subscribers Only</>
                        : creditsRemaining
                          ? <><Zap className="w-3 h-3" /> Use Your Credits First</>
                          : <>Buy Now <ArrowRight className="w-3 h-3" /></>
                    }
                  </button>
                </div>
              );
            })}
          </div>

          {!isSubscribed && (
            <p className="text-center text-xs text-slate-600 mt-3">
              Subscribe to a paid plan above to unlock credit top-ups.
            </p>
          )}
          {isSubscribed && creditsRemaining && (
            <p className="text-center text-xs text-slate-600 mt-3">
              You have <span className="text-slate-400 font-medium">{credits} credits</span> remaining. Top-ups unlock once your balance reaches zero.
            </p>
          )}
        </div>

        {/* Trust signals */}
        <div className="flex flex-wrap items-center justify-center gap-8 mb-12 py-6 border-y border-white/[0.06]">
          <div className="flex items-center gap-2.5">
            <Shield className="w-5 h-5 text-slate-500" />
            <div>
              <p className="text-xs font-semibold text-slate-300">Stripe Secured</p>
              <p className="text-[10px] text-slate-600">PCI-compliant payments</p>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            <Star className="w-5 h-5 text-slate-500" />
            <div>
              <p className="text-xs font-semibold text-slate-300">Cancel Anytime</p>
              <p className="text-[10px] text-slate-600">No lock-in contracts</p>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            <Zap className="w-5 h-5 text-slate-500" />
            <div>
              <p className="text-xs font-semibold text-slate-300">Instant Activation</p>
              <p className="text-[10px] text-slate-600">Credits apply immediately</p>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            <MessageSquare className="w-5 h-5 text-slate-500" />
            <div>
              <p className="text-xs font-semibold text-slate-300">Human Support</p>
              <p className="text-[10px] text-slate-600">Real team, real answers</p>
            </div>
          </div>
        </div>

        {/* FAQ */}
        <div className="max-w-2xl mx-auto mb-12">
          <h2 className="text-lg font-bold text-white mb-6 flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-slate-500" /> Frequently asked questions
          </h2>
          <div className="rounded-2xl border border-white/10 bg-[#111118] px-6">
            {FAQ.map((item, i) => (
              <FaqItem key={i} q={item.q} a={item.a} />
            ))}
          </div>
        </div>

        {/* Enterprise CTA */}
        <div className="rounded-2xl border border-white/10 bg-gradient-to-br from-violet-500/5 to-cyan-500/5 p-8 text-center">
          <h3 className="text-xl font-bold text-white mb-2">Need something custom?</h3>
          <p className="text-sm text-slate-400 mb-6 max-w-md mx-auto leading-relaxed">
            Enterprise plans with custom credit limits, SSO, dedicated infrastructure, SLAs, and volume discounts.
          </p>
          <a
            href="mailto:billing@miniassistantai.com"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/10 hover:bg-white/15 text-white text-sm font-semibold transition-colors border border-white/10"
          >
            Contact Sales <ArrowRight className="w-4 h-4" />
          </a>
        </div>

      </div>
    </div>
  );
}
