/**
 * pages/UserDashboard.js
 * Personal usage dashboard — credits, plan, activity history, stats.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Zap, MessageSquare, Image, Star, Clock,
  BarChart2, RefreshCw, ChevronRight, Shield,
  TrendingUp, Folder, Calendar,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { api } from '../api/client';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const PLAN_CONFIG = {
  free:     { label: 'Free',     color: 'text-slate-400',  bg: 'bg-white/5 border-white/10',             dot: 'bg-slate-500' },
  standard: { label: 'Standard', color: 'text-cyan-400',   bg: 'bg-cyan-500/10 border-cyan-500/20',      dot: 'bg-cyan-400' },
  pro:      { label: 'Pro',      color: 'text-violet-400', bg: 'bg-violet-500/10 border-violet-500/20',  dot: 'bg-violet-400' },
  team:     { label: 'Team',     color: 'text-amber-400',  bg: 'bg-amber-500/10 border-amber-500/20',    dot: 'bg-amber-400' },
};

function timeStamp(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit', hour12: true,
  });
}

function memberSince(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleDateString('en-US', {
    month: 'long', day: 'numeric', year: 'numeric',
  });
}

function fmt(n) {
  if (n === undefined || n === null) return '—';
  return n.toLocaleString();
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------
function StatCard({ icon: Icon, label, value, sub, color = 'slate' }) {
  const colors = {
    cyan:    'text-cyan-400   bg-cyan-500/10   border-cyan-500/20',
    violet:  'text-violet-400 bg-violet-500/10 border-violet-500/20',
    amber:   'text-amber-400  bg-amber-500/10  border-amber-500/20',
    emerald: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    slate:   'text-slate-400  bg-white/5       border-white/10',
  };
  return (
    <div className={`rounded-2xl border p-5 flex items-center gap-4 ${colors[color]}`}>
      <Icon size={20} className="flex-shrink-0" />
      <div>
        <p className="text-xl font-bold text-white">{fmt(value)}</p>
        <p className="text-xs text-slate-500 mt-0.5">{label}</p>
        {sub && <p className="text-[10px] text-slate-600 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Activity row
// ---------------------------------------------------------------------------
function ActivityRow({ item }) {
  const isImage = item.type === 'image_generated';
  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-white/[0.04] last:border-0">
      <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${isImage ? 'bg-violet-500/10' : 'bg-cyan-500/10'}`}>
        {isImage
          ? <Image size={13} className="text-violet-400" />
          : <MessageSquare size={13} className="text-cyan-400" />}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-slate-300 font-medium">
          {isImage ? 'Image generated' : 'Chat message sent'}
        </p>
        <p className="text-[11px] text-slate-600 font-mono">{timeStamp(item.timestamp)}</p>
      </div>
      <span className="flex items-center gap-1 text-[11px] font-mono text-amber-400 flex-shrink-0">
        <Zap size={10} /> {item.credits_used}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Credit bar
// ---------------------------------------------------------------------------
function CreditBar({ credits, plan, isSubscribed, onBuyCredits, onUpgrade }) {
  const planCfg = PLAN_CONFIG[plan] || PLAN_CONFIG.free;
  const pct = isSubscribed ? 100 : Math.min(100, (credits / 10) * 100);
  const barColor = isSubscribed ? 'bg-cyan-500' : credits > 5 ? 'bg-cyan-500' : credits > 2 ? 'bg-amber-500' : 'bg-red-500';

  return (
    <div className="rounded-2xl border border-white/10 bg-[#13131f] p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
          <Zap size={14} className="text-amber-400" /> Credits &amp; Plan
        </h2>
        <span className={`text-[11px] font-mono font-semibold px-2.5 py-0.5 rounded-full border ${planCfg.bg} ${planCfg.color}`}>
          {planCfg.label}
        </span>
      </div>

      {isSubscribed ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-400">Credits remaining</span>
            <span className="text-lg font-bold text-cyan-400 font-mono">Unlimited</span>
          </div>
          <div className="h-2 rounded-full bg-white/5 overflow-hidden">
            <div className="h-full w-full bg-gradient-to-r from-cyan-500 to-violet-500 rounded-full" />
          </div>
          <p className="text-[11px] text-slate-600">
            Your {planCfg.label} plan includes unlimited credits. Enjoy building!
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-400">Credits remaining</span>
            <span className={`text-lg font-bold font-mono ${credits > 5 ? 'text-white' : credits > 2 ? 'text-amber-400' : 'text-red-400'}`}>
              {fmt(credits)}
            </span>
          </div>
          <div className="h-2 rounded-full bg-white/10 overflow-hidden">
            <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${pct}%` }} />
          </div>
          <p className="text-[11px] text-slate-600">
            1 credit = 1 chat message · 3 credits = 1 image
          </p>
          <div className="flex gap-2 pt-1">
            <button
              onClick={onBuyCredits}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-black text-xs font-bold transition-all"
            >
              <Zap size={12} /> Buy Credits
            </button>
            <button
              onClick={onUpgrade}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 text-xs font-medium transition-all"
            >
              <Star size={12} /> Upgrade Plan
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function UserDashboard() {
  const { user, avatar, credits, plan, isSubscribed, setPage, setPurchaseModalOpen } = useApp();
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.authDashboard();
      setData(res);
    } catch (err) {
      setError(err.message || 'Failed to load dashboard.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const planCfg = PLAN_CONFIG[plan] || PLAN_CONFIG.free;

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-4 md:px-8 py-8 space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-cyan-500 to-violet-600 flex items-center justify-center overflow-hidden flex-shrink-0">
              {avatar
                ? <img src={avatar} alt="" className="w-full h-full object-cover" />
                : <span className="text-lg font-bold text-white">{(user?.name?.[0] || '?').toUpperCase()}</span>
              }
            </div>
            <div>
              <h1 className="text-base font-bold text-white">{user?.name || 'My Dashboard'}</h1>
              <p className="text-xs text-slate-500">{user?.email}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={load}
              disabled={loading}
              className="p-2 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-all"
              title="Refresh"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        {/* Plan + credits bar */}
        <CreditBar
          credits={data?.credits ?? credits ?? 0}
          plan={data?.plan ?? plan}
          isSubscribed={data?.is_subscribed ?? isSubscribed}
          onBuyCredits={() => setPurchaseModalOpen(true)}
          onUpgrade={() => setPage('settings')}
        />

        {/* Stat cards */}
        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="rounded-2xl border border-white/5 bg-white/[0.02] p-5 h-20 animate-pulse" />
            ))}
          </div>
        ) : error ? (
          <div className="text-center text-red-400 text-sm py-4">{error}</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <StatCard icon={MessageSquare} label="Chats Sent"      value={data?.total_chats_sent}  color="cyan" />
            <StatCard icon={Image}         label="Images Made"     value={data?.total_images_made} color="violet" />
            <StatCard icon={Zap}           label="Credits Used"    value={data?.total_credits_used} sub="all time" color="amber" />
            <StatCard icon={Folder}        label="Saved Chats"     value={data?.saved_chats}       color="slate" />
            <StatCard icon={TrendingUp}    label="Saved Images"    value={data?.saved_images}      color="slate" />
            <StatCard icon={Calendar}      label="Member Since"    value={memberSince(data?.member_since)} color="slate" />
          </div>
        )}

        {/* Account info card */}
        <div className="rounded-2xl border border-white/10 bg-[#13131f] p-6">
          <h2 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
            <BarChart2 size={14} className="text-cyan-400" /> Account Info
          </h2>
          <div className="space-y-3">
            {[
              { label: 'Plan',         value: planCfg.label,              color: planCfg.color },
              { label: 'Role',         value: user?.role === 'admin' ? 'Admin' : 'User' },
              { label: 'Member Since', value: memberSince(data?.member_since) },
              { label: 'Email',        value: user?.email },
            ].map(({ label, value, color }) => (
              <div key={label} className="flex items-center justify-between py-1.5 border-b border-white/[0.04] last:border-0">
                <span className="text-xs text-slate-500">{label}</span>
                <span className={`text-xs font-medium font-mono ${color || 'text-slate-300'}`}>{value}</span>
              </div>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              onClick={() => setPage('profile')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-slate-200 bg-white/5 hover:bg-white/10 transition-all"
            >
              Edit Profile <ChevronRight size={11} />
            </button>
            <button
              onClick={() => setPage('settings')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-slate-200 bg-white/5 hover:bg-white/10 transition-all"
            >
              Settings <ChevronRight size={11} />
            </button>
            {user?.role === 'admin' && (
              <button
                onClick={() => setPage('admin')}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-amber-400 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 transition-all"
              >
                <Shield size={11} /> Admin Dashboard
              </button>
            )}
          </div>
        </div>

        {/* Recent activity */}
        <div className="rounded-2xl border border-white/10 bg-[#13131f] p-6">
          <h2 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
            <Clock size={14} className="text-violet-400" /> Recent Activity
          </h2>
          {loading ? (
            <div className="text-center text-slate-600 text-sm py-4">Loading…</div>
          ) : !data?.recent_activity?.length ? (
            <div className="text-center text-slate-600 text-sm py-4">
              No activity yet. Start a chat or generate an image!
            </div>
          ) : (
            <div>
              {data.recent_activity.map((item, i) => (
                <ActivityRow key={i} item={item} />
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
