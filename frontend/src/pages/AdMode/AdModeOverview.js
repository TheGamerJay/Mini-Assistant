/**
 * AdModeOverview — dashboard home tab.
 * Shows hero, campaign stats, recent ad sets, quick actions.
 */

import React, { useEffect, useState } from 'react';
import { Sparkles, Target, Download, Plus, ArrowRight, Image, Zap } from 'lucide-react';
import { api } from '../../api/client';

function StatCard({ label, value, sub }) {
  return (
    <div className="bg-white/3 border border-white/8 rounded-xl p-4">
      <p className="text-2xl font-bold text-slate-100 mb-0.5">{value ?? '—'}</p>
      <p className="text-xs text-slate-400">{label}</p>
      {sub && <p className="text-[10px] text-slate-600 mt-0.5">{sub}</p>}
    </div>
  );
}

function QuickAction({ icon: Icon, label, desc, onClick, color = 'cyan' }) {
  const colors = {
    cyan:   'bg-cyan-500/10 border-cyan-500/20 hover:border-cyan-500/40 text-cyan-400',
    violet: 'bg-violet-500/10 border-violet-500/20 hover:border-violet-500/40 text-violet-400',
    amber:  'bg-amber-500/10 border-amber-500/20 hover:border-amber-500/40 text-amber-400',
  };
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-start gap-3 p-4 rounded-xl border transition-all text-left ${colors[color]}`}
    >
      <div className="mt-0.5 flex-shrink-0"><Icon size={16} /></div>
      <div>
        <p className="text-sm font-medium text-slate-200">{label}</p>
        <p className="text-[11px] text-slate-500 mt-0.5">{desc}</p>
      </div>
      <ArrowRight size={14} className="ml-auto mt-1 text-slate-600 flex-shrink-0" />
    </button>
  );
}

export default function AdModeOverview({ onNav, profileExists, campaigns }) {
  const recentCampaigns = campaigns.slice(0, 3);
  const totalAdSets     = campaigns.reduce((s, c) => s + (c.ad_set_count || 0), 0);

  return (
    <div className="space-y-8">
      {/* Hero */}
      <div className="bg-gradient-to-br from-violet-500/10 via-transparent to-cyan-500/5 border border-white/8 rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-2">
          <Zap size={15} className="text-violet-400" />
          <span className="text-[10px] font-mono uppercase tracking-widest text-violet-400">
            Ad Mode Active
          </span>
        </div>
        <h2 className="text-xl font-bold text-slate-100 mb-1">Your ads never sleep.</h2>
        <p className="text-sm text-slate-400">
          Generate complete ad campaigns — copy, images, and creative angles — powered by Claude AI and DALL·E 3.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Campaigns" value={campaigns.length} />
        <StatCard label="Ad Sets" value={totalAdSets} />
        <StatCard label="Brand Profile" value={profileExists ? '✓' : '—'} sub={profileExists ? 'Ready' : 'Not set up'} />
      </div>

      {/* Quick actions */}
      <div>
        <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-3">
          Quick actions
        </p>
        <div className="space-y-2">
          <QuickAction
            icon={Sparkles}
            label={profileExists ? 'Edit Brand Profile' : 'Build Brand Profile'}
            desc="Define your business, audience, and tone for smarter ad generation"
            onClick={() => onNav('brand')}
            color="violet"
          />
          <QuickAction
            icon={Image}
            label="Generate Ad Set"
            desc="Create hooks, headlines, captions, CTAs and images in one shot"
            onClick={() => onNav('generate')}
            color="cyan"
          />
          <QuickAction
            icon={Target}
            label="View Saved Campaigns"
            desc="Browse, regenerate, or download your previous ad sets"
            onClick={() => onNav('campaigns')}
            color="amber"
          />
        </div>
      </div>

      {/* Recent campaigns */}
      {recentCampaigns.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
              Recent campaigns
            </p>
            <button
              onClick={() => onNav('campaigns')}
              className="text-[11px] text-slate-500 hover:text-slate-300 transition-colors"
            >
              View all →
            </button>
          </div>
          <div className="space-y-2">
            {recentCampaigns.map((c) => (
              <div
                key={c.id}
                className="flex items-center gap-3 bg-white/3 border border-white/5 rounded-xl px-4 py-3"
              >
                <div className="h-8 w-8 rounded-lg bg-violet-500/10 flex items-center justify-center flex-shrink-0">
                  <Target size={14} className="text-violet-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-200 truncate">{c.name}</p>
                  <p className="text-[10px] text-slate-500">{c.ad_set_count || 0} ad sets · {c.goal}</p>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border ${
                  c.status === 'active'
                    ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                    : 'bg-slate-500/10 border-slate-500/20 text-slate-500'
                }`}>
                  {c.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
