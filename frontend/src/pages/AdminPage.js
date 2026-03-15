/**
 * pages/AdminPage.js
 * Standalone admin dashboard — accessible at /admin.
 * Handles its own login (no AppShell required).
 * All data comes from real backend API endpoints (/api/admin/*).
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Users, MessageSquare, ThumbsUp, ThumbsDown, Image,
  Shield, Trash2, ChevronLeft, RefreshCw, LogOut,
  Activity, Server, AlertCircle, CheckCircle, Clock,
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
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [loadingStats, setLoadingStats] = useState(true);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [serverStatus, setServerStatus] = useState({ backend: null, ollama: null, comfyui: null });
  const [deletingId, setDeletingId] = useState(null);
  const [togglingId, setTogglingId] = useState(null);
  const [activeTab, setActiveTab] = useState('overview'); // 'overview' | 'users'

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

  const checkStatus = useCallback(async () => {
    try {
      const data = await api.mainHealth();
      setServerStatus({
        backend: true,
        ollama: data.ollama === 'connected',
        comfyui: data.comfyui === 'connected',
      });
    } catch {
      setServerStatus({ backend: false, ollama: false, comfyui: false });
    }
  }, []);

  useEffect(() => {
    loadStats();
    loadUsers();
    checkStatus();
  }, [loadStats, loadUsers, checkStatus]);

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
            <span className="flex items-center gap-1.5"><StatusDot ok={serverStatus.ollama} /> AI</span>
            <span className="flex items-center gap-1.5"><StatusDot ok={serverStatus.comfyui} /> ComfyUI</span>
          </div>
          <button
            onClick={() => { loadStats(); loadUsers(); checkStatus(); }}
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
      <div className="flex-shrink-0 flex items-center gap-1 px-6 pt-4 pb-0">
        {[
          { id: 'overview', label: 'Overview', icon: Activity },
          { id: 'users',    label: `Users (${users.length})`, icon: Users },
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
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="rounded-2xl border border-white/5 bg-white/[0.02] p-5 h-20 animate-pulse" />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                <StatCard icon={Users}         label="Total Users"    value={stats?.total_users}    sub={`${stats?.total_admins || 0} admin(s)`} color="cyan" />
                <StatCard icon={MessageSquare} label="Total Chats"    value={stats?.total_chats}    color="violet" />
                <StatCard icon={Activity}      label="Total Messages" value={stats?.total_messages} color="amber" />
                <StatCard icon={Image}         label="Image Sessions" value={stats?.total_image_docs} color="slate" />
                <StatCard icon={ThumbsUp}      label="Thumbs Up"      value={stats?.thumbs_up}      color="emerald" />
                <StatCard icon={ThumbsDown}    label="Thumbs Down"    value={stats?.thumbs_down}    color="red" />
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
                  { key: 'backend', label: 'Backend API', desc: 'Railway server' },
                  { key: 'ollama',  label: 'AI Engine',   desc: 'Local inference' },
                  { key: 'comfyui', label: 'ComfyUI',     desc: 'Image generation' },
                ].map(({ key, label, desc }) => {
                  const ok = serverStatus[key];
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
                      {['User', 'Email', 'Role', 'Joined', 'Actions'].map(h => (
                        <th key={h} className="px-4 py-3 text-left text-[11px] font-mono uppercase tracking-widest text-slate-600">{h}</th>
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
                            <span className="text-slate-200 font-medium text-sm">{u.name}</span>
                            {u.id === adminUser.id && (
                              <span className="text-[9px] font-mono text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded-full border border-amber-500/20">you</span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-slate-500 font-mono text-xs">{u.email}</td>
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
                        <td className="px-4 py-3 text-slate-600 text-xs font-mono">{timeAgo(u.created_at)}</td>
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
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AdminPage — root export, handles auth state independently
// ---------------------------------------------------------------------------
export default function AdminPage() {
  const { user, loginWithCredentials, logout, setPage } = useApp();
  const [localAdmin, setLocalAdmin] = useState(null); // used only when AppContext user isn't set yet

  // The effective admin is either the AppContext user (if already logged in) or localAdmin
  const effectiveUser = (user?.role === 'admin' ? user : null) || localAdmin;

  async function handleLogin(userData, token) {
    // Use loginWithCredentials to update AppContext (triggers data reload etc.)
    try {
      await loginWithCredentials(userData.email, ''); // This won't work without password
    } catch { /* ignore */ }
    // Fallback: set local state with the already-verified user data
    setLocalAdmin(userData);
  }

  function handleLogout() {
    setLocalAdmin(null);
    logout();
    setPage('chat');
    // Clear URL back to root
    try { window.history.pushState({}, '', '/'); } catch {}
  }

  // Update URL when on admin page
  useEffect(() => {
    try { window.history.pushState({}, '', '/admin'); } catch {}
    return () => {
      try { window.history.pushState({}, '', '/'); } catch {}
    };
  }, []);

  // Not authenticated or authenticated but not admin → show login
  if (!effectiveUser) {
    return (
      <>
        <AdminLoginForm
          onLogin={(userData, token) => {
            setLocalAdmin(userData);
          }}
        />
        {/* Back to app link */}
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
