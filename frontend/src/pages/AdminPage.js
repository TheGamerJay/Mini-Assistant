/**
 * pages/AdminPage.js
 * Standalone admin dashboard — accessible at /admin.
 * Handles its own login (no AppShell required).
 * All data comes from real backend API endpoints (/api/admin/*).
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Users, MessageSquare, ThumbsUp, ThumbsDown, Image,
  Shield, Trash2, RefreshCw, LogOut, Zap, CreditCard,
  Activity, Server, AlertCircle, CheckCircle, Clock,
  UserPlus, BarChart2, List, ChevronLeft, Bot, Cpu,
  TrendingUp, DollarSign, PieChart, Percent, ArrowUpRight,
  Code2, Rocket, GitBranch, Download,
} from 'lucide-react';
import { toast, Toaster } from 'sonner';
import { api, setToken, clearToken } from '../api/client';
import { useApp } from '../context/AppContext';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function timeAgo(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function timeStamp(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit', hour12: true,
  });
}

function fmt(n) {
  if (n === undefined || n === null) return '—';
  return n.toLocaleString();
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function StatCard({ icon: Icon, label, value, sub, color = 'cyan' }) {
  const colors = {
    cyan:    'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
    violet:  'text-violet-400 bg-violet-500/10 border-violet-500/20',
    emerald: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    amber:   'text-amber-400 bg-amber-500/10 border-amber-500/20',
    red:     'text-red-400 bg-red-500/10 border-red-500/20',
    slate:   'text-slate-400 bg-white/5 border-white/10',
    blue:    'text-blue-400 bg-blue-500/10 border-blue-500/20',
  };
  return (
    <div className={`rounded-2xl border p-5 flex items-center gap-4 ${colors[color]}`}>
      <Icon size={22} className="flex-shrink-0" />
      <div>
        <p className="text-2xl font-bold text-white">{fmt(value)}</p>
        <p className="text-xs text-slate-500 mt-0.5">{label}</p>
        {sub && <p className="text-[10px] text-slate-600 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

function StatusDot({ ok }) {
  return ok === null
    ? <span className="w-2 h-2 rounded-full bg-slate-600 inline-block" />
    : ok
      ? <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse inline-block" />
      : <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />;
}

function PlanBadge({ plan }) {
  const cfg = {
    free:     'text-slate-500 bg-white/5 border-white/10',
    standard: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
    pro:      'text-violet-400 bg-violet-500/10 border-violet-500/20',
    team:     'text-amber-400 bg-amber-500/10 border-amber-500/20',
  };
  return (
    <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${cfg[plan] || cfg.free}`}>
      {plan || 'free'}
    </span>
  );
}

function ActivityTypeBadge({ type }) {
  if (type === 'image_generated') {
    return (
      <span className="flex items-center gap-1 text-[10px] font-mono text-violet-400 bg-violet-500/10 border border-violet-500/20 px-2 py-0.5 rounded-full">
        <Image size={9} /> image
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-[10px] font-mono text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded-full">
      <MessageSquare size={9} /> chat
    </span>
  );
}

// ---------------------------------------------------------------------------
// Admin Login Form
// ---------------------------------------------------------------------------
function AdminLoginForm({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.authLogin(email.trim().toLowerCase(), password);
      if (res.user?.role !== 'admin') {
        setError('This account does not have admin access.');
        return;
      }
      setToken(res.token);
      onLogin(res.user, res.token);
    } catch (err) {
      setError(err.message || 'Login failed. Check your credentials.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#0d0d12] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo / header */}
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-amber-500 to-amber-600 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-amber-500/20">
            <Shield size={28} className="text-white" />
          </div>
          <h1 className="text-xl font-bold text-white">Admin Portal</h1>
          <p className="text-sm text-slate-500 mt-1">Mini Assistant — Restricted Access</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="admin@example.com"
              className="w-full px-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-slate-200 text-sm placeholder-slate-600 outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-all"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full px-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-slate-200 text-sm placeholder-slate-600 outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-all"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 text-red-400 text-xs bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
              <AlertCircle size={13} className="flex-shrink-0" />
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black font-semibold text-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Signing in…' : 'Sign in as Admin'}
          </button>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Admin Dashboard
// ---------------------------------------------------------------------------
function AdminDashboard({ adminUser, onLogout }) {
  const [stats, setStats]               = useState(null);
  const [users, setUsers]               = useState([]);
  const [activity, setActivity]         = useState([]);
  const [loadingStats, setLoadingStats] = useState(true);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [loadingActivity, setLoadingActivity] = useState(false);
  const [serverStatus, setServerStatus] = useState({ backend: null, openai: null });
  const [deletingId, setDeletingId]     = useState(null);
  const [analytics, setAnalytics]       = useState(null);
  const [loadingAnalytics, setLoadingAnalytics] = useState(false);
  const [optimizer, setOptimizer]       = useState(null);
  const [loadingOptimizer, setLoadingOptimizer] = useState(false);
  const [togglingId, setTogglingId]     = useState(null);
  const [grantingId, setGrantingId]     = useState(null);
  const [grantInput, setGrantInput]     = useState({}); // { [userId]: string }
  const [activeTab, setActiveTab]       = useState('overview'); // 'overview' | 'users' | 'activity'

  const loadStats = useCallback(async () => {
    setLoadingStats(true);
    try {
      const data = await api.adminGetStats();
      setStats(data);
    } catch (err) {
      toast.error('Failed to load stats: ' + (err.message || 'unknown error'));
    } finally {
      setLoadingStats(false);
    }
  }, []);

  const loadUsers = useCallback(async () => {
    setLoadingUsers(true);
    try {
      const data = await api.adminGetUsers();
      setUsers(data.users || []);
    } catch (err) {
      toast.error('Failed to load users: ' + (err.message || 'unknown error'));
    } finally {
      setLoadingUsers(false);
    }
  }, []);

  const loadActivity = useCallback(async () => {
    setLoadingActivity(true);
    try {
      const data = await api.adminGetActivity(100);
      setActivity(data.activity || []);
    } catch (err) {
      toast.error('Failed to load activity: ' + (err.message || 'unknown error'));
    } finally {
      setLoadingActivity(false);
    }
  }, []);

  const loadAnalytics = useCallback(async () => {
    setLoadingAnalytics(true);
    try {
      const data = await api.adminGetAnalytics();
      setAnalytics(data);
    } catch (err) {
      toast.error('Failed to load analytics: ' + (err.message || 'unknown error'));
    } finally {
      setLoadingAnalytics(false);
    }
  }, []);

  const loadOptimizer = useCallback(async () => {
    setLoadingOptimizer(true);
    try {
      const data = await api.adminGetPricingOptimizer();
      setOptimizer(data);
    } catch (err) {
      toast.error('Failed to load pricing optimizer: ' + (err.message || 'unknown error'));
    } finally {
      setLoadingOptimizer(false);
    }
  }, []);

  const checkStatus = useCallback(async () => {
    try {
      const data = await api.mainHealth();
      setServerStatus({
        backend: true,
        openai: data.openai === 'connected',
      });
    } catch {
      setServerStatus({ backend: false, openai: false });
    }
  }, []);

  useEffect(() => {
    loadStats();
    loadUsers();
    checkStatus();
  }, [loadStats, loadUsers, checkStatus]);

  // Load activity when that tab is first opened
  useEffect(() => {
    if (activeTab === 'activity' && activity.length === 0) loadActivity();
    if (activeTab === 'revenue' && !analytics) loadAnalytics();
    if (activeTab === 'profit' && !optimizer) loadOptimizer();
    if (activeTab === 'profit' && !analytics) loadAnalytics();
  }, [activeTab, activity.length, analytics, optimizer, loadActivity, loadAnalytics, loadOptimizer]);

  async function handleDeleteUser(u) {
    if (!window.confirm(`Delete ${u.name} (${u.email})? This removes all their data and cannot be undone.`)) return;
    setDeletingId(u.id);
    try {
      await api.adminDeleteUser(u.id);
      setUsers(prev => prev.filter(x => x.id !== u.id));
      toast.success(`${u.name} deleted.`);
      loadStats();
    } catch (err) {
      toast.error(err.message || 'Failed to delete user.');
    } finally {
      setDeletingId(null);
    }
  }

  async function handleToggleRole(u) {
    const newRole = u.role === 'admin' ? 'user' : 'admin';
    setTogglingId(u.id);
    try {
      await api.adminSetRole(u.id, newRole);
      setUsers(prev => prev.map(x => x.id === u.id ? { ...x, role: newRole } : x));
      toast.success(`${u.name} is now ${newRole}.`);
    } catch (err) {
      toast.error(err.message || 'Failed to update role.');
    } finally {
      setTogglingId(null);
    }
  }

  async function handleGrantCredits(u) {
    const raw = grantInput[u.id];
    const credits = parseInt(raw, 10);
    if (isNaN(credits) || credits < 0) {
      toast.error('Enter a valid credit amount (0 or more).');
      return;
    }
    setGrantingId(u.id);
    try {
      await api.adminSetCredits(u.id, credits);
      setUsers(prev => prev.map(x => x.id === u.id ? { ...x, credits } : x));
      setGrantInput(prev => ({ ...prev, [u.id]: '' }));
      toast.success(`Set ${u.name}'s credits to ${credits}.`);
    } catch (err) {
      toast.error(err.message || 'Failed to set credits.');
    } finally {
      setGrantingId(null);
    }
  }

  const positiveRate = stats && (stats.thumbs_up + stats.thumbs_down) > 0
    ? Math.round(stats.thumbs_up / (stats.thumbs_up + stats.thumbs_down) * 100)
    : null;

  return (
    <div className="min-h-screen bg-[#0d0d12] text-white flex flex-col">
      {/* Top bar */}
      <div className="flex-shrink-0 flex items-center justify-between px-6 py-4 border-b border-white/5 bg-[#0d0d12]/80 backdrop-blur sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500 to-amber-600 flex items-center justify-center">
            <Shield size={16} className="text-black" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white">Admin Dashboard</h1>
            <p className="text-[11px] text-slate-600">Signed in as <span className="text-amber-400">{adminUser.email}</span></p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* Server status pills */}
          <div className="hidden md:flex items-center gap-3 text-[11px] text-slate-500 font-mono">
            <span className="flex items-center gap-1.5"><StatusDot ok={serverStatus.backend} /> Backend</span>
            <span className="flex items-center gap-1.5"><StatusDot ok={serverStatus.openai} /> Claude API</span>
          </div>
          <button
            onClick={() => {
            loadStats(); loadUsers(); checkStatus();
            if (activeTab === 'activity') loadActivity();
            if (activeTab === 'revenue') loadAnalytics();
            if (activeTab === 'profit') { loadAnalytics(); loadOptimizer(); }
          }}
            className="p-2 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-all"
            title="Refresh"
          >
            <RefreshCw size={15} />
          </button>
          <button
            onClick={onLogout}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-red-400 hover:bg-red-500/10 border border-white/8 hover:border-red-500/20 transition-all"
          >
            <LogOut size={13} /> Sign out
          </button>
        </div>
      </div>

      {/* Tab nav */}
      <div className="flex-shrink-0 flex items-center gap-1 px-6 pt-4 pb-0 overflow-x-auto">
        {[
          { id: 'overview',  label: 'Overview',              icon: BarChart2 },
          { id: 'users',     label: `Users (${users.length})`, icon: Users },
          { id: 'activity',  label: 'Activity',              icon: List },
          { id: 'revenue',   label: 'Revenue',               icon: DollarSign },
          { id: 'profit',    label: 'Profit & Cost',         icon: TrendingUp },
        ].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all
              ${activeTab === id
                ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                : 'text-slate-500 hover:text-slate-300 hover:bg-white/5'}`}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">

        {/* ── OVERVIEW TAB ── */}
        {activeTab === 'overview' && (
          <>
            {/* Stats grid */}
            {loadingStats ? (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="rounded-2xl border border-white/5 bg-white/[0.02] p-5 h-20 animate-pulse" />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                <StatCard icon={Users}         label="Total Users"         value={stats?.total_users}             sub={`${stats?.total_admins || 0} admin(s)`} color="cyan" />
                <StatCard icon={UserPlus}      label="New This Week"       value={stats?.new_users_week}          color="emerald" />
                <StatCard icon={MessageSquare} label="Chat Messages"       value={stats?.total_chat_messages}     color="violet" />
                <StatCard icon={Image}         label="Images Generated"    value={stats?.total_images_generated}  color="blue" />
                <StatCard icon={Zap}           label="Credits Remaining"   value={stats?.total_credits_remaining} sub="across all free users" color="amber" />
                <StatCard icon={Activity}      label="Total Activity"      value={stats?.total_activity_events}   color="slate" />
                <StatCard icon={ThumbsUp}      label="Thumbs Up"           value={stats?.thumbs_up}               color="emerald" />
                <StatCard icon={ThumbsDown}    label="Thumbs Down"         value={stats?.thumbs_down}             color="red" />
              </div>
            )}

            {/* Response quality */}
            {positiveRate !== null && (
              <div className="rounded-2xl border border-white/10 bg-[#13131f] p-6">
                <h2 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
                  <Activity size={14} className="text-emerald-400" /> Response Quality
                </h2>
                <div className="flex items-center gap-4">
                  <div className="flex-1 bg-white/5 rounded-full h-3 overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all duration-700"
                      style={{ width: `${positiveRate}%` }}
                    />
                  </div>
                  <span className="text-xs font-mono text-slate-300 flex-shrink-0 font-semibold">{positiveRate}% positive</span>
                </div>
                <div className="flex items-center gap-6 mt-3">
                  <span className="flex items-center gap-1.5 text-xs text-emerald-400"><ThumbsUp size={11} /> {fmt(stats?.thumbs_up)} positive</span>
                  <span className="flex items-center gap-1.5 text-xs text-red-400"><ThumbsDown size={11} /> {fmt(stats?.thumbs_down)} negative</span>
                </div>
              </div>
            )}

            {/* Server status card */}
            <div className="rounded-2xl border border-white/10 bg-[#13131f] p-6">
              <h2 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
                <Server size={14} className="text-cyan-400" /> Service Status
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {[
                  { key: 'backend', label: 'Backend API',  desc: 'Railway server',       icon: Server },
                  { key: 'openai',  label: 'Claude API',   desc: 'Anthropic / Claude',   icon: Bot },
                  { key: 'dalle',   label: 'DALL-E 3',     desc: 'OpenAI image API',     icon: Image },
                ].map(({ key, label, desc, icon: Icon }) => {
                  // dalle mirrors openai status since both go through OpenAI
                  const ok = key === 'dalle' ? serverStatus.openai : serverStatus[key];
                  return (
                    <div key={key} className={`flex items-center gap-3 p-3 rounded-xl border ${ok === true ? 'border-emerald-500/20 bg-emerald-500/5' : ok === false ? 'border-red-500/20 bg-red-500/5' : 'border-white/5 bg-white/[0.02]'}`}>
                      {ok === true
                        ? <CheckCircle size={16} className="text-emerald-400 flex-shrink-0" />
                        : ok === false
                          ? <AlertCircle size={16} className="text-red-400 flex-shrink-0" />
                          : <Clock size={16} className="text-slate-600 flex-shrink-0" />}
                      <div>
                        <p className="text-xs font-medium text-slate-200">{label}</p>
                        <p className="text-[10px] text-slate-600">{desc}</p>
                      </div>
                      <span className={`ml-auto text-[10px] font-mono font-semibold ${ok === true ? 'text-emerald-400' : ok === false ? 'text-red-400' : 'text-slate-600'}`}>
                        {ok === null ? 'checking' : ok ? 'online' : 'offline'}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}

        {/* ── USERS TAB ── */}
        {activeTab === 'users' && (
          <div className="rounded-2xl border border-white/10 bg-[#13131f] overflow-hidden">
            <div className="px-6 py-4 border-b border-white/5 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-200">Registered Users</h2>
              <span className="text-[11px] font-mono text-slate-600">{users.length} accounts</span>
            </div>

            {loadingUsers ? (
              <div className="px-6 py-10 text-center text-slate-600 text-sm">Loading users…</div>
            ) : users.length === 0 ? (
              <div className="px-6 py-10 text-center text-slate-600 text-sm">No users found.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/5">
                      {['User', 'Email', 'Auth', 'Role', 'Plan', 'Credits', 'Grant Credits', 'Joined', 'Actions'].map(h => (
                        <th key={h} className="px-4 py-3 text-left text-[11px] font-mono uppercase tracking-widest text-slate-600 whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {users.map(u => (
                      <tr key={u.id} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors">

                        {/* Avatar + name */}
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2.5">
                            <div className="w-7 h-7 rounded-full overflow-hidden flex-shrink-0 bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center text-white text-xs font-bold">
                              {u.avatar
                                ? <img src={u.avatar} alt="" className="w-full h-full object-cover" />
                                : (u.name?.[0] || '?').toUpperCase()}
                            </div>
                            <span className="text-slate-200 font-medium text-sm whitespace-nowrap">{u.name}</span>
                            {u.id === adminUser.id && (
                              <span className="text-[9px] font-mono text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded-full border border-amber-500/20">you</span>
                            )}
                          </div>
                        </td>

                        {/* Email */}
                        <td className="px-4 py-3 text-slate-500 font-mono text-xs whitespace-nowrap">{u.email}</td>

                        {/* Auth method */}
                        <td className="px-4 py-3">
                          {u.google_linked
                            ? <span className="text-[10px] font-mono text-blue-400 bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 rounded-full">Google</span>
                            : <span className="text-[10px] font-mono text-slate-600 bg-white/5 border border-white/10 px-2 py-0.5 rounded-full">Email</span>
                          }
                        </td>

                        {/* Role badge + toggle */}
                        <td className="px-4 py-3">
                          <button
                            disabled={u.id === adminUser.id || togglingId === u.id}
                            onClick={() => handleToggleRole(u)}
                            className={`text-[10px] font-mono px-2 py-0.5 rounded-full border transition-all
                              ${u.role === 'admin'
                                ? 'text-amber-400 bg-amber-500/10 border-amber-500/20 hover:bg-amber-500/20'
                                : 'text-slate-500 bg-white/5 border-white/10 hover:border-cyan-500/30 hover:text-cyan-400'}
                              disabled:opacity-40 disabled:cursor-not-allowed`}
                            title={u.id === adminUser.id ? "Can't change your own role" : `Click to make ${u.role === 'admin' ? 'user' : 'admin'}`}
                          >
                            {togglingId === u.id ? '…' : u.role}
                          </button>
                        </td>

                        {/* Plan */}
                        <td className="px-4 py-3">
                          <PlanBadge plan={u.plan} />
                        </td>

                        {/* Credits */}
                        <td className="px-4 py-3">
                          <span className={`text-sm font-mono font-semibold ${
                            u.plan && u.plan !== 'free' ? 'text-emerald-400' :
                            u.credits > 5 ? 'text-slate-300' :
                            u.credits > 0 ? 'text-amber-400' : 'text-red-400'
                          }`}>
                            {u.plan && u.plan !== 'free' ? '∞' : fmt(u.credits ?? 0)}
                          </span>
                        </td>

                        {/* Grant credits input */}
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1.5">
                            <input
                              type="number"
                              min="0"
                              placeholder="amount"
                              value={grantInput[u.id] || ''}
                              onChange={e => setGrantInput(prev => ({ ...prev, [u.id]: e.target.value }))}
                              className="w-20 px-2 py-1 rounded-lg bg-white/5 border border-white/10 text-slate-200 text-xs font-mono outline-none focus:border-cyan-500/40 transition-all"
                            />
                            <button
                              disabled={grantingId === u.id || !grantInput[u.id]}
                              onClick={() => handleGrantCredits(u)}
                              className="px-2 py-1 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-[10px] font-mono hover:bg-cyan-500/20 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              {grantingId === u.id ? '…' : 'Set'}
                            </button>
                          </div>
                        </td>

                        {/* Joined */}
                        <td className="px-4 py-3 text-slate-600 text-xs font-mono whitespace-nowrap">{timeAgo(u.created_at)}</td>

                        {/* Delete */}
                        <td className="px-4 py-3">
                          {u.id !== adminUser.id && (
                            <button
                              disabled={deletingId === u.id}
                              onClick={() => handleDeleteUser(u)}
                              className="p-1.5 rounded-lg text-slate-600 hover:text-red-400 hover:bg-red-500/10 transition-all disabled:opacity-40"
                              title={`Delete ${u.name}`}
                            >
                              {deletingId === u.id ? <RefreshCw size={13} className="animate-spin" /> : <Trash2 size={13} />}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ── REVENUE TAB ── */}
        {activeTab === 'revenue' && (
          <>
            {loadingAnalytics ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="rounded-2xl border border-white/5 bg-white/[0.02] p-5 h-20 animate-pulse" />
                ))}
              </div>
            ) : analytics && (
              <>
                {/* Revenue KPIs */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <StatCard icon={DollarSign}  label="MRR Estimate"        value={`$${analytics.mrr_estimate_usd?.toFixed(2)}`}      color="emerald" />
                  <StatCard icon={Percent}      label="Conversion Rate"     value={`${analytics.conversion_rate_pct}%`}               color="cyan" />
                  <StatCard icon={Users}        label="Paying Users"        value={analytics.paying_users}                            color="violet" />
                  <StatCard icon={UserPlus}     label="New This Month"      value={analytics.new_users_this_month}                    color="amber" />
                </div>

                {/* Users by plan */}
                <div className="rounded-2xl border border-white/10 bg-[#13131f] p-6">
                  <h2 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
                    <PieChart size={14} className="text-cyan-400" /> Users by Plan
                  </h2>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {[
                      { plan: 'free',     color: 'border-slate-500/30 bg-white/[0.03]',            text: 'text-slate-400'  },
                      { plan: 'standard', color: 'border-cyan-500/30 bg-cyan-500/5',              text: 'text-cyan-400'   },
                      { plan: 'pro',      color: 'border-violet-500/30 bg-violet-500/5',          text: 'text-violet-400' },
                      { plan: 'team',     color: 'border-amber-500/30 bg-amber-500/5',            text: 'text-amber-400'  },
                    ].map(({ plan, color, text }) => {
                      const count = analytics.users_by_plan?.[plan] || 0;
                      const pct = analytics.total_users > 0 ? Math.round(count / analytics.total_users * 100) : 0;
                      const price = { free: 0, standard: 9, pro: 19, team: 49 }[plan];
                      return (
                        <div key={plan} className={`rounded-xl border p-4 ${color}`}>
                          <p className={`text-2xl font-bold text-white`}>{fmt(count)}</p>
                          <p className={`text-xs font-semibold capitalize mt-0.5 ${text}`}>{plan}</p>
                          <p className="text-[10px] text-slate-600 mt-1">{pct}% of users</p>
                          {price > 0 && (
                            <p className={`text-[10px] mt-0.5 ${text}`}>${(count * price).toFixed(0)}/mo est.</p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Daily usage chart */}
                <div className="rounded-2xl border border-white/10 bg-[#13131f] p-6">
                  <h2 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
                    <Activity size={14} className="text-violet-400" /> Daily Requests — Last 30 Days
                  </h2>
                  {analytics.daily_usage?.length > 0 ? (
                    <div>
                      {(() => {
                        const maxR = Math.max(...analytics.daily_usage.map(d => d.requests), 1);
                        return (
                          <div className="flex items-end gap-0.5 h-20 overflow-x-auto pb-2">
                            {analytics.daily_usage.map((d, i) => {
                              const pct = Math.max(4, (d.requests / maxR) * 100);
                              return (
                                <div key={i} className="flex-1 min-w-[6px] flex flex-col items-center gap-0.5 group relative">
                                  <div
                                    className="w-full bg-gradient-to-t from-violet-600 to-violet-400 rounded-sm"
                                    style={{ height: `${pct}%` }}
                                  />
                                  <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:block z-10 pointer-events-none">
                                    <div className="bg-[#1a1a2e] border border-white/10 rounded-lg px-2 py-1 text-[9px] text-slate-300 whitespace-nowrap shadow-xl">
                                      <p className="font-mono">{d.date}</p>
                                      <p className="text-violet-400">{d.requests} reqs · {d.credits} cr</p>
                                      <p className="text-red-400">${d.cost_usd?.toFixed(3)} cost</p>
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        );
                      })()}
                    </div>
                  ) : (
                    <p className="text-slate-600 text-sm text-center py-4">No usage data yet.</p>
                  )}
                </div>

                {/* Usage by action */}
                <div className="rounded-2xl border border-white/10 bg-[#13131f] p-6">
                  <h2 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
                    <BarChart2 size={14} className="text-amber-400" /> Usage by Action (All Time)
                  </h2>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-white/5">
                          {['Action', 'Requests', 'Credits', 'AI Cost (USD)'].map(h => (
                            <th key={h} className="px-3 py-2.5 text-left text-[10px] font-mono uppercase tracking-widest text-slate-600">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {analytics.usage_by_action?.map((row, i) => (
                          <tr key={i} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                            <td className="px-3 py-2.5 text-xs text-slate-300 font-mono">{row.action}</td>
                            <td className="px-3 py-2.5 text-xs text-slate-400">{fmt(row.requests)}</td>
                            <td className="px-3 py-2.5 text-xs text-amber-400 font-mono">{fmt(row.credits)}</td>
                            <td className="px-3 py-2.5 text-xs text-red-400 font-mono">${row.cost_usd?.toFixed(4)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}
          </>
        )}

        {/* ── PROFIT & COST TAB ── */}
        {activeTab === 'profit' && (
          <>
            {(loadingAnalytics || loadingOptimizer) ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="rounded-2xl border border-white/5 bg-white/[0.02] p-5 h-20 animate-pulse" />
                ))}
              </div>
            ) : (
              <>
                {/* P&L summary */}
                {analytics && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <StatCard icon={DollarSign}  label="MRR Estimate"       value={`$${analytics.mrr_estimate_usd?.toFixed(2)}`}       color="emerald" />
                    <StatCard icon={Activity}     label="AI Cost This Month" value={`$${analytics.ai_cost_this_month_usd?.toFixed(2)}`} color="red" />
                    <StatCard icon={TrendingUp}   label="Net Profit Est."    value={`$${analytics.net_profit_estimate_usd?.toFixed(2)}`} color={analytics.net_profit_estimate_usd > 0 ? 'emerald' : 'red'} />
                    <StatCard icon={Percent}      label="Profit Margin"      value={`${analytics.profit_margin_pct}%`}                  color="cyan" />
                  </div>
                )}

                {/* Profit bar */}
                {analytics && analytics.mrr_estimate_usd > 0 && (
                  <div className="rounded-2xl border border-white/10 bg-[#13131f] p-6">
                    <h2 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
                      <TrendingUp size={14} className="text-emerald-400" /> Revenue vs Cost (This Month)
                    </h2>
                    <div className="space-y-3">
                      {[
                        { label: 'MRR (Estimated Revenue)', value: analytics.mrr_estimate_usd, color: 'bg-emerald-500', max: analytics.mrr_estimate_usd },
                        { label: 'AI API Cost',             value: analytics.ai_cost_this_month_usd, color: 'bg-red-500', max: analytics.mrr_estimate_usd },
                        { label: 'Net Profit',              value: Math.max(0, analytics.net_profit_estimate_usd), color: 'bg-cyan-500', max: analytics.mrr_estimate_usd },
                      ].map(({ label, value, color, max }) => (
                        <div key={label}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs text-slate-500">{label}</span>
                            <span className="text-xs font-mono text-slate-300">${value?.toFixed(2)}</span>
                          </div>
                          <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${color} transition-all`}
                              style={{ width: `${Math.min(100, (value / max) * 100)}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Pricing optimizer */}
                {optimizer && (
                  <div className="rounded-2xl border border-white/10 bg-[#13131f] p-6">
                    <div className="flex items-center justify-between mb-4">
                      <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                        <Zap size={14} className="text-amber-400" /> Credit Pricing Optimizer
                      </h2>
                      <div className="flex items-center gap-4 text-[10px] font-mono text-slate-500">
                        <span>Target margin: <span className="text-amber-400">{optimizer.target_margin_pct}%</span></span>
                        <span>Rev/credit: <span className="text-emerald-400">${optimizer.revenue_per_credit_usd?.toFixed(4)}</span></span>
                      </div>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-white/5">
                            {['Action', 'Current Credits', 'Avg AI Cost', 'Current Margin', 'Recommended Credits', '30d Requests'].map(h => (
                              <th key={h} className="px-3 py-2.5 text-left text-[10px] font-mono uppercase tracking-widest text-slate-600 whitespace-nowrap">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {optimizer.analysis?.map((row, i) => {
                            const marginOk = row.current_margin_pct >= optimizer.target_margin_pct;
                            return (
                              <tr key={i} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                                <td className="px-3 py-2.5 text-xs text-slate-300 font-mono">{row.action}</td>
                                <td className="px-3 py-2.5 text-xs text-amber-400 font-mono">{row.credit_cost}</td>
                                <td className="px-3 py-2.5 text-xs text-red-400 font-mono">${row.avg_ai_cost_usd}</td>
                                <td className="px-3 py-2.5">
                                  <span className={`text-xs font-mono font-semibold ${marginOk ? 'text-emerald-400' : 'text-red-400'}`}>
                                    {row.current_margin_pct}%
                                  </span>
                                </td>
                                <td className="px-3 py-2.5">
                                  <span className={`text-xs font-mono font-bold ${row.recommended_credits !== row.credit_cost ? 'text-violet-400' : 'text-slate-500'}`}>
                                    {row.recommended_credits}
                                  </span>
                                </td>
                                <td className="px-3 py-2.5 text-xs text-slate-500 font-mono">{fmt(row.total_requests_30d)}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    <p className="text-[10px] text-slate-600 mt-3">
                      Recommended credit costs achieve the {optimizer.target_margin_pct}% target margin.
                      Platform margin estimate: <span className="text-emerald-400 font-semibold">{optimizer.platform_profit_margin_pct}%</span>
                    </p>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {/* ── ACTIVITY TAB ── */}
        {activeTab === 'activity' && (
          <div className="rounded-2xl border border-white/10 bg-[#13131f] overflow-hidden">
            <div className="px-6 py-4 border-b border-white/5 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <List size={14} className="text-amber-400" /> Recent Activity
              </h2>
              <div className="flex items-center gap-3">
                <span className="text-[11px] font-mono text-slate-600">{activity.length} events</span>
                <button
                  onClick={loadActivity}
                  className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-all"
                  title="Refresh activity"
                >
                  <RefreshCw size={13} className={loadingActivity ? 'animate-spin' : ''} />
                </button>
              </div>
            </div>

            {loadingActivity ? (
              <div className="px-6 py-10 text-center text-slate-600 text-sm">Loading activity…</div>
            ) : activity.length === 0 ? (
              <div className="px-6 py-10 text-center text-slate-600 text-sm">No activity recorded yet.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/5">
                      {['User', 'Email', 'Action', 'Credits Used', 'Timestamp'].map(h => (
                        <th key={h} className="px-4 py-3 text-left text-[11px] font-mono uppercase tracking-widest text-slate-600 whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {activity.map((a, i) => (
                      <tr key={i} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors">
                        <td className="px-4 py-3 text-slate-200 text-sm font-medium whitespace-nowrap">{a.user_name || '—'}</td>
                        <td className="px-4 py-3 text-slate-500 font-mono text-xs whitespace-nowrap">{a.user_email || '—'}</td>
                        <td className="px-4 py-3">
                          <ActivityTypeBadge type={a.type} />
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-xs font-mono text-amber-400 flex items-center gap-1">
                            <Zap size={10} /> {a.credits_used ?? '—'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-600 text-xs font-mono whitespace-nowrap">
                          {timeStamp(a.timestamp)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AdminPage — root export, handles auth state independently
// ---------------------------------------------------------------------------
export default function AdminPage() {
  const { user, logout, setPage } = useApp();
  const [localAdmin, setLocalAdmin] = useState(null);

  // The effective admin is either the AppContext user (if already logged in as admin) or localAdmin
  const effectiveUser = (user?.role === 'admin' ? user : null) || localAdmin;

  function handleLogout() {
    setLocalAdmin(null);
    logout();
    setPage('chat');
    try { window.history.pushState({}, '', '/'); } catch {}
  }

  // Update URL when on admin page
  useEffect(() => {
    try { window.history.pushState({}, '', '/admin'); } catch {}
    return () => {
      try { window.history.pushState({}, '', '/'); } catch {}
    };
  }, []);

  if (!effectiveUser) {
    return (
      <>
        <Toaster richColors position="bottom-right" />
        <AdminLoginForm onLogin={(userData) => setLocalAdmin(userData)} />
        <button
          onClick={() => { setPage('chat'); try { window.history.pushState({}, '', '/'); } catch {} }}
          className="fixed bottom-4 left-4 flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-400 transition-colors"
        >
          <ChevronLeft size={13} /> Back to app
        </button>
      </>
    );
  }

  return (
    <>
      <Toaster richColors position="bottom-right" />
      <AdminDashboard adminUser={effectiveUser} onLogout={handleLogout} />
      <button
        onClick={() => { setPage('chat'); try { window.history.pushState({}, '', '/'); } catch {} }}
        className="fixed bottom-4 left-4 flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-400 transition-colors"
      >
        <ChevronLeft size={13} /> Back to app
      </button>
    </>
  );
}
