/**
 * pages/UserDashboard.js
 * Personal usage dashboard — credits, plan, usage analytics, activity history.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Zap, MessageSquare, Image, Star, Clock,
  BarChart2, RefreshCw, ChevronRight, Shield,
  TrendingUp, Folder, Calendar, Code2, Cpu,
  Rocket, GitBranch, Download, Activity, Gift, Copy, Check, ArrowLeft,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import api from '../api/client';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const PLAN_CONFIG = {
  free:     { label: 'Free',     color: 'text-slate-400',  bg: 'bg-white/5 border-white/10',             dot: 'bg-slate-500',  limit: 50 },
  standard: { label: 'Standard', color: 'text-cyan-400',   bg: 'bg-cyan-500/10 border-cyan-500/20',      dot: 'bg-cyan-400',   limit: 500 },
  pro:      { label: 'Pro',      color: 'text-violet-400', bg: 'bg-violet-500/10 border-violet-500/20',  dot: 'bg-violet-400', limit: 2000 },
  team:     { label: 'Team',     color: 'text-amber-400',  bg: 'bg-amber-500/10 border-amber-500/20',    dot: 'bg-amber-400',  limit: 10000 },
  max:      { label: 'Max',      color: 'text-amber-400',  bg: 'bg-amber-500/10 border-amber-500/20',    dot: 'bg-amber-400',  limit: 10000 },
};

const ACTION_META = {
  chat_message:    { label: 'Chat',       icon: MessageSquare, color: 'text-cyan-400',   bg: 'bg-cyan-500/10' },
  chat_stream:     { label: 'Chat',       icon: MessageSquare, color: 'text-cyan-400',   bg: 'bg-cyan-500/10' },
  image_generated: { label: 'Image Gen',  icon: Image,         color: 'text-violet-400', bg: 'bg-violet-500/10' },
  app_build:       { label: 'App Build',  icon: Code2,         color: 'text-emerald-400',bg: 'bg-emerald-500/10' },
  code_review:     { label: 'Code Review',icon: BarChart2,     color: 'text-amber-400',  bg: 'bg-amber-500/10' },
  export_zip:      { label: 'Export',     icon: Download,      color: 'text-slate-400',  bg: 'bg-white/5' },
  github_push:     { label: 'GitHub',     icon: GitBranch,     color: 'text-slate-400',  bg: 'bg-white/5' },
  deploy_vercel:   { label: 'Deploy',     icon: Rocket,        color: 'text-slate-400',  bg: 'bg-white/5' },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function timeStamp(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString('en-US', {
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
// MiniBar — tiny inline bar chart (CSS, no lib)
// ---------------------------------------------------------------------------
function MiniBarChart({ data }) {
  if (!data?.length) return (
    <div className="flex items-end gap-1 h-12">
      {Array.from({ length: 7 }).map((_, i) => (
        <div key={i} className="flex-1 bg-white/5 rounded-sm" style={{ height: '20%' }} />
      ))}
    </div>
  );

  const maxVal = Math.max(...data.map(d => d.requests), 1);

  return (
    <div className="flex items-end gap-1 h-12">
      {data.map((d, i) => {
        const pct = Math.max(6, (d.requests / maxVal) * 100);
        return (
          <div key={i} className="flex-1 flex flex-col items-center gap-0.5 group relative">
            <div
              className="w-full bg-gradient-to-t from-cyan-600 to-cyan-400 rounded-sm transition-all group-hover:from-violet-600 group-hover:to-violet-400"
              style={{ height: `${pct}%` }}
            />
            {/* Tooltip */}
            <div className="absolute bottom-full mb-1.5 left-1/2 -translate-x-1/2 hidden group-hover:flex flex-col items-center z-10 pointer-events-none">
              <div className="bg-[#1a1a2e] border border-white/10 rounded-lg px-2 py-1 text-[9px] text-slate-300 whitespace-nowrap shadow-xl">
                <p className="font-mono">{d.date?.slice(5)}</p>
                <p className="text-cyan-400">{d.requests} req · {d.credits} cr</p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// StatCard
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
    <div className={`rounded-2xl border p-4 flex items-center gap-3 ${colors[color]}`}>
      <Icon size={18} className="flex-shrink-0" />
      <div className="min-w-0">
        <p className="text-lg font-bold text-white leading-none">{fmt(value)}</p>
        <p className="text-[11px] text-slate-500 mt-0.5 leading-none">{label}</p>
        {sub && <p className="text-[10px] text-slate-600 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ActivityRow
// ---------------------------------------------------------------------------
function ActivityRow({ item }) {
  const meta = ACTION_META[item.action_type || item.type] || ACTION_META.chat_message;
  const Icon = meta.icon;
  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-white/[0.04] last:border-0">
      <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${meta.bg}`}>
        <Icon size={13} className={meta.color} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-slate-300 font-medium">{meta.label}</p>
        <p className="text-[11px] text-slate-600 font-mono">{timeStamp(item.timestamp)}</p>
      </div>
      {item.credits_used > 0 && (
        <span className="flex items-center gap-1 text-[11px] font-mono text-amber-400 flex-shrink-0">
          <Zap size={10} /> {item.credits_used}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CreditBar
// ---------------------------------------------------------------------------
function CreditBar({ credits, plan, isSubscribed, onBuyCredits, onTopUp, onUpgrade }) {
  const planCfg = PLAN_CONFIG[plan] || PLAN_CONFIG.free;
  const limit = planCfg.limit;
  const pct = Math.min(100, (credits / limit) * 100);
  const low = pct < 20;
  const mid = pct >= 20 && pct < 50;
  const barColor = isSubscribed
    ? (low ? 'bg-amber-500' : 'bg-gradient-to-r from-cyan-500 to-violet-500')
    : (low ? 'bg-red-500' : mid ? 'bg-amber-500' : 'bg-cyan-500');

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

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-400">Credits remaining</span>
          <span className={`text-xl font-bold font-mono ${isSubscribed && !low ? 'text-cyan-400' : low ? 'text-amber-400' : mid ? 'text-amber-400' : 'text-white'}`}>
            {fmt(credits)} <span className="text-slate-600 text-sm font-normal">/ {limit.toLocaleString()}</span>
          </span>
        </div>
        <div className="h-2 rounded-full bg-white/10 overflow-hidden">
          <div className={`h-full rounded-full transition-all duration-700 ${barColor}`} style={{ width: `${Math.max(2, pct)}%` }} />
        </div>
        <p className="text-[11px] text-slate-600">
          1 credit = 1 chat · 3 credits = 1 image · 5 credits = 1 app build
          {isSubscribed && ' · Credits reset monthly'}
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          {isSubscribed ? (
            <>
              <button
                onClick={onTopUp}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-black text-xs font-bold transition-all"
              >
                <Zap size={12} /> Top-Up Credits
              </button>
              <button
                onClick={onUpgrade}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 text-xs font-medium transition-all"
              >
                <TrendingUp size={12} /> Change Plan
              </button>
            </>
          ) : (
            <>
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
                <TrendingUp size={12} /> Upgrade Plan
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Monthly Usage Panel
// ---------------------------------------------------------------------------
function MonthlyUsagePanel({ data }) {
  const meta = data?.most_used_feature
    ? (ACTION_META[data.most_used_feature] || ACTION_META.chat_message)
    : null;
  const MFIcon = meta?.icon || Activity;

  return (
    <div className="rounded-2xl border border-white/10 bg-[#13131f] p-6">
      <h2 className="text-sm font-semibold text-slate-200 mb-5 flex items-center gap-2">
        <BarChart2 size={14} className="text-cyan-400" /> This Month
      </h2>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3 text-center">
          <p className="text-lg font-bold text-white">{fmt(data?.credits_used_month ?? 0)}</p>
          <p className="text-[10px] text-slate-500 mt-0.5">Credits used</p>
        </div>
        <div className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3 text-center">
          <p className="text-lg font-bold text-white">{fmt(data?.requests_this_month ?? 0)}</p>
          <p className="text-[10px] text-slate-500 mt-0.5">Requests</p>
        </div>
        <div className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3 text-center">
          {meta ? (
            <>
              <div className={`w-6 h-6 rounded-lg ${meta.bg} flex items-center justify-center mx-auto mb-1`}>
                <MFIcon size={12} className={meta.color} />
              </div>
              <p className="text-[10px] text-slate-500">{meta.label}</p>
            </>
          ) : (
            <p className="text-[10px] text-slate-600 mt-3">No data</p>
          )}
          <p className="text-[9px] text-slate-600 mt-0.5">Top feature</p>
        </div>
      </div>

      {/* Daily bar chart */}
      <div>
        <p className="text-[10px] text-slate-500 mb-2 flex items-center gap-1.5">
          <Activity size={10} /> Last 7 days
        </p>
        <MiniBarChart data={data?.daily_trend || []} />
        {!data?.daily_trend?.length && (
          <p className="text-[10px] text-slate-700 text-center mt-1">No activity yet this week</p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function UserDashboard() {
  const { user, avatar, credits, plan, isSubscribed, setPage, setPurchaseModalOpen, openUpgradeModal, getPrevPage } = useApp();
  const [data, setData]           = useState(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [billingLoading, setBillingLoading] = useState(false);
  const [referral, setReferral]   = useState(null);
  const [copied, setCopied]       = useState(false);

  const handleManageBilling = useCallback(async () => {
    setBillingLoading(true);
    try {
      const { portal_url } = await api.stripeOpenPortal();
      window.open(portal_url, '_blank', 'noopener');
    } catch {
      setPage('pricing');
    } finally {
      setBillingLoading(false);
    }
  }, [setPage]);

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

  useEffect(() => {
    api.authReferral().then(setReferral).catch(() => {});
  }, []);

  const copyReferralLink = useCallback(() => {
    if (!referral?.referral_code) return;
    const link = `${window.location.origin}?ref=${referral.referral_code}`;
    navigator.clipboard.writeText(link).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [referral]);

  const planCfg = PLAN_CONFIG[plan] || PLAN_CONFIG.free;

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-4 md:px-8 py-8 space-y-5">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setPage(getPrevPage())}
              className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-all flex-shrink-0"
              title="Back"
            >
              <ArrowLeft size={16} />
            </button>
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
              onClick={isSubscribed ? handleManageBilling : () => setPage('pricing')}
              disabled={billingLoading}
              className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium text-violet-400 bg-violet-500/10 border border-violet-500/20 hover:bg-violet-500/20 transition-all disabled:opacity-60"
            >
              <TrendingUp size={11} /> {billingLoading ? 'Loading…' : isSubscribed ? 'Manage Billing' : 'Upgrade'}
            </button>
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
          onBuyCredits={() => setPage('pricing')}
          onTopUp={() => setPurchaseModalOpen(true)}
          onUpgrade={() => setPage('pricing')}
        />

        {/* Monthly usage panel */}
        {loading ? (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-6 h-44 animate-pulse" />
        ) : (
          <MonthlyUsagePanel data={data} />
        )}

        {/* All-time stat cards */}
        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="rounded-2xl border border-white/5 bg-white/[0.02] p-4 h-16 animate-pulse" />
            ))}
          </div>
        ) : error ? (
          <div className="text-center text-red-400 text-sm py-4">{error}</div>
        ) : (
          <div>
            <p className="text-[11px] text-slate-600 uppercase tracking-widest font-mono mb-3">All time</p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <StatCard icon={MessageSquare} label="Chats Sent"      value={data?.total_chats_sent}   color="cyan" />
              <StatCard icon={Image}         label="Images Made"     value={data?.total_images_made}  color="violet" />
              <StatCard icon={Zap}           label="Credits Used"    value={data?.total_credits_used} color="amber" />
              <StatCard icon={Folder}        label="Saved Chats"     value={data?.saved_chats}        color="slate" />
              <StatCard icon={TrendingUp}    label="Saved Images"    value={data?.saved_images}       color="slate" />
              <StatCard icon={Calendar}      label="Member Since"    value={memberSince(data?.member_since)} color="slate" />
            </div>
          </div>
        )}

        {/* Account info card */}
        <div className="rounded-2xl border border-white/10 bg-[#13131f] p-6">
          <h2 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
            <BarChart2 size={14} className="text-cyan-400" /> Account
          </h2>
          <div className="space-y-2">
            {[
              { label: 'Plan',         value: planCfg.label,                          color: planCfg.color },
              { label: 'Role',         value: user?.role === 'admin' ? 'Admin' : 'User' },
              { label: 'Member Since', value: memberSince(data?.member_since) },
              { label: 'Email',        value: user?.email },
            ].map(({ label, value, color }) => (
              <div key={label} className="flex items-center justify-between py-1.5 border-b border-white/[0.04] last:border-0">
                <span className="text-xs text-slate-500">{label}</span>
                <span className={`text-xs font-medium font-mono truncate max-w-[60%] text-right ${color || 'text-slate-300'}`}>{value}</span>
              </div>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <button onClick={() => setPage('profile')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-slate-200 bg-white/5 hover:bg-white/10 transition-all">
              Edit Profile <ChevronRight size={11} />
            </button>
            <button onClick={() => setPage('settings')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-slate-200 bg-white/5 hover:bg-white/10 transition-all">
              Settings <ChevronRight size={11} />
            </button>
            <button
              onClick={isSubscribed ? handleManageBilling : () => setPage('pricing')}
              disabled={billingLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-violet-400 bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/20 transition-all disabled:opacity-60">
              <TrendingUp size={11} /> {billingLoading ? 'Loading…' : isSubscribed ? 'Billing' : 'Plans'}
            </button>
            {user?.role === 'admin' && (
              <button onClick={() => setPage('admin')}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-amber-400 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 transition-all">
                <Shield size={11} /> Admin
              </button>
            )}
          </div>
        </div>

        {/* Referral card */}
        <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-6">
          <h2 className="text-sm font-semibold text-slate-200 mb-1 flex items-center gap-2">
            <Gift size={14} className="text-emerald-400" /> Refer a Friend
          </h2>
          <p className="text-xs text-slate-500 mb-4">
            Share your link. When a friend subscribes, you both get <span className="text-emerald-400 font-medium">+50 credits</span>. Max 3 referrals = 150 bonus credits.
          </p>
          {referral ? (
            <div className="space-y-3">
              {/* Progress bar with completed + pending segments */}
              <div className="flex items-center gap-2">
                {Array.from({ length: referral.max_rewards }).map((_, i) => {
                  const isCompleted = i < referral.referrals_rewarded_count;
                  const isPending   = !isCompleted && i < (referral.referrals_rewarded_count + (referral.referrals_pending_count || 0));
                  const allDone     = referral.referrals_rewarded_count >= referral.max_rewards;
                  return (
                    <div
                      key={i}
                      className={`h-2 flex-1 rounded-full transition-colors ${
                        isCompleted
                          ? allDone
                            ? 'bg-emerald-400 shadow-[0_0_8px_2px_rgba(52,211,153,0.55)] animate-pulse'
                            : 'bg-emerald-500'
                          : isPending ? 'bg-amber-400/60' : 'bg-white/10'
                      }`}
                    />
                  );
                })}
                <span className="text-xs text-slate-500 ml-1 flex-shrink-0 whitespace-nowrap">
                  {referral.referrals_rewarded_count}/{referral.max_rewards} done
                  {referral.referrals_pending_count > 0 && (
                    <span className="text-amber-400 ml-1">· {referral.referrals_pending_count} pending</span>
                  )}
                </span>
              </div>

              {/* One-away nudge — subtle, shown only when exactly 1 slot left */}
              {referral.referrals_rewarded_count === referral.max_rewards - 1 && (
                <div className="px-3 py-2 rounded-xl bg-emerald-500/8 border border-emerald-500/20 text-center">
                  <p className="text-[11px] font-medium text-emerald-300">
                    {referral.max_rewards <= 3
                      ? `Only 1 more referral to unlock your full ${referral.max_rewards * referral.sub_bonus} credit bonus 👀`
                      : referral.max_rewards <= 6
                      ? `Just 1 more referral to unlock your full ${referral.max_rewards * referral.sub_bonus} credit bonus 🔥`
                      : "You're one step away from maxing out your referral rewards 🚀"
                    }
                  </p>
                </div>
              )}

              {/* Generic urgency text for earlier stages */}
              {referral.referrals_rewarded_count < referral.max_rewards - 1 && (
                <p className="text-[11px] text-slate-500 text-center">
                  {referral.slots_remaining === referral.max_rewards
                    ? <>Invite <span className="text-emerald-400 font-semibold">3 friends</span> who subscribe to unlock your full <span className="text-emerald-400 font-semibold">150 credit bonus</span> 🚀</>
                    : <>Just <span className="text-emerald-400 font-semibold">{referral.slots_remaining} more</span> friend{referral.slots_remaining > 1 ? 's' : ''} to unlock your full bonus!</>
                  }
                </p>
              )}

              {/* Credits earned stat — only show once at least 1 completed */}
              {referral.referrals_rewarded_count > 0 && (
                <div className="flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-emerald-500/5 border border-emerald-500/10">
                  <Zap size={11} className="text-emerald-400" />
                  <span className="text-[11px] text-slate-400">
                    Credits earned from referrals:{' '}
                    <span className="text-emerald-400 font-bold font-mono">
                      +{referral.referrals_rewarded_count * referral.sub_bonus}
                    </span>
                  </span>
                </div>
              )}

              {/* Copy link button */}
              <button
                onClick={copyReferralLink}
                className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-xl bg-white/5 border border-white/10 hover:border-emerald-500/30 hover:bg-emerald-500/5 transition-all text-xs"
              >
                <span className="text-slate-400 font-mono truncate">
                  {window.location.origin}?ref={referral.referral_code}
                </span>
                <span className={`flex items-center gap-1 flex-shrink-0 font-medium ${copied ? 'text-emerald-400' : 'text-slate-400'}`}>
                  {copied ? <><Check size={12} /> Copied!</> : <><Copy size={12} /> Copy</>}
                </span>
              </button>

              {referral.referrals_rewarded_count >= referral.max_rewards && (
                <div className="text-center space-y-2">
                  <p className="text-xs text-amber-400/80">🎉 You've maxed out your referral rewards — nice work!</p>
                  {referral.can_unlock_more && (
                    <button
                      onClick={() => setPage('pricing')}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-violet-300 bg-violet-500/10 border border-violet-500/20 hover:bg-violet-500/20 transition-all"
                    >
                      <TrendingUp size={11} /> Upgrade to unlock more referral slots
                    </button>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="h-16 bg-white/5 rounded-xl animate-pulse" />
          )}
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
              No activity yet. Start a chat or build an app!
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
