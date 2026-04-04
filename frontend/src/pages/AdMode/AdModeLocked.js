/**
 * AdModeLocked — shown when user does not have Ad Mode access.
 * Clean premium locked screen with pricing and checkout CTAs.
 */

import React from 'react';
import { Sparkles, Image, Target, TrendingUp, Download, Lock, ArrowRight } from 'lucide-react';
import { useApp } from '../../context/AppContext';

const FEATURES = [
  { icon: Sparkles, text: 'AI-generated ad copy — hooks, headlines, CTAs' },
  { icon: Image,    text: 'DALL·E 3 ad images matched to your brand' },
  { icon: Target,   text: 'Multiple ad angles: emotional, benefit, curiosity, urgency' },
  { icon: TrendingUp, text: 'Brand profile generation from your business info' },
  { icon: Download, text: 'Download creatives ready for ads manager' },
];

export default function AdModeLocked() {
  const { setPage } = useApp();

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-lg mx-auto px-6 py-12">

        {/* Hero */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 bg-violet-500/10 border border-violet-500/20 rounded-full px-4 py-1.5 text-xs text-violet-400 font-medium mb-6">
            <Lock size={11} /> Add-On Required
          </div>
          <h1 className="text-3xl font-bold text-slate-100 mb-3 leading-tight">
            Campaign Lab
          </h1>
          <p className="text-slate-400 text-base leading-relaxed max-w-md mx-auto">
            Create high-converting ads in seconds — powered by AI.
            Included as an add-on with your Mini Assistant subscription.
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

        {/* CTA */}
        <button
          onClick={() => setPage('pricing')}
          className="w-full py-3 rounded-2xl bg-gradient-to-r from-violet-600 to-cyan-600 text-white text-sm font-bold hover:opacity-90 transition-all flex items-center justify-center gap-2 shadow-lg mb-3"
        >
          View Plans <ArrowRight size={14} />
        </button>
        <p className="text-center text-[11px] text-slate-600">
          Cancel anytime · Powered by Stripe
        </p>

      </div>
    </div>
  );
}
