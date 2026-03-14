/**
 * pages/AdminPage.js
 * Admin-only dashboard: user stats, chat counts, message ratings.
 * Reads directly from localStorage — no backend required.
 */

import React, { useMemo } from 'react';
import { Users, MessageSquare, ThumbsUp, ThumbsDown, Image, Star } from 'lucide-react';
import { useApp } from '../context/AppContext';

function StatCard({ icon: Icon, label, value, color = 'cyan' }) {
  const colorMap = {
    cyan:    'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
    violet:  'text-violet-400 bg-violet-500/10 border-violet-500/20',
    emerald: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    amber:   'text-amber-400 bg-amber-500/10 border-amber-500/20',
    red:     'text-red-400 bg-red-500/10 border-red-500/20',
  };
  return (
    <div className={`rounded-2xl border p-5 flex items-center gap-4 ${colorMap[color]}`}>
      <div className="flex-shrink-0">
        <Icon size={22} />
      </div>
      <div>
        <p className="text-2xl font-bold text-white">{value}</p>
        <p className="text-xs text-slate-500 mt-0.5">{label}</p>
      </div>
    </div>
  );
}

export default function AdminPage() {
  const { user } = useApp();

  const stats = useMemo(() => {
    const users = JSON.parse(localStorage.getItem('ma_users') || '[]');
    let totalChats = 0;
    let totalMessages = 0;
    let thumbsUp = 0;
    let thumbsDown = 0;
    let totalImages = 0;

    const userRows = users.map(u => {
      const chats = JSON.parse(localStorage.getItem(`ma_v2_chats_${u.id}`) || '[]');
      const images = JSON.parse(localStorage.getItem(`ma_v2_images_${u.id}`) || '[]');
      let msgs = 0;
      let up = 0;
      let down = 0;
      chats.forEach(c => {
        msgs += c.messages?.length || 0;
        (c.messages || []).forEach(m => {
          if (m.rating === 1) up++;
          if (m.rating === -1) down++;
        });
      });
      totalChats += chats.length;
      totalMessages += msgs;
      thumbsUp += up;
      thumbsDown += down;
      totalImages += images.length;
      return {
        id: u.id,
        name: u.name,
        email: u.email,
        role: u.role || 'user',
        chats: chats.length,
        messages: msgs,
        images: images.length,
        thumbsUp: up,
        thumbsDown: down,
        createdAt: u.createdAt,
      };
    });

    return { users: userRows, totalChats, totalMessages, thumbsUp, thumbsDown, totalImages, totalUsers: users.length };
  }, []);

  if (user?.role !== 'admin') {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-2xl mb-2">🔒</p>
          <p className="text-slate-400 text-sm">Admin access required.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-6 md:px-10 py-8 space-y-8">
      <div>
        <h1 className="text-xl font-bold text-white">Admin Dashboard</h1>
        <p className="text-xs text-slate-500 mt-1">System overview — data from localStorage</p>
      </div>

      {/* Overview cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <StatCard icon={Users} label="Total Users" value={stats.totalUsers} color="cyan" />
        <StatCard icon={MessageSquare} label="Total Chats" value={stats.totalChats} color="violet" />
        <StatCard icon={Star} label="Total Messages" value={stats.totalMessages} color="amber" />
        <StatCard icon={ThumbsUp} label="Thumbs Up" value={stats.thumbsUp} color="emerald" />
        <StatCard icon={ThumbsDown} label="Thumbs Down" value={stats.thumbsDown} color="red" />
      </div>

      {/* Users table */}
      <div className="rounded-2xl border border-white/10 bg-[#13131f] overflow-hidden">
        <div className="px-6 py-4 border-b border-white/5 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200">Registered Users</h2>
          <span className="text-[11px] font-mono text-slate-600">{stats.users.length} accounts</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/5">
                {['Name', 'Email', 'Role', 'Chats', 'Messages', 'Images', 'Joined'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-[11px] font-mono uppercase tracking-widest text-slate-600">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stats.users.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-600 text-xs">No users found.</td></tr>
              ) : stats.users.map(u => (
                <tr key={u.id} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors">
                  <td className="px-4 py-3 text-slate-200 font-medium">{u.name}</td>
                  <td className="px-4 py-3 text-slate-500 font-mono text-xs truncate max-w-[160px]">{u.email}</td>
                  <td className="px-4 py-3">
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${
                      u.role === 'admin'
                        ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
                        : 'text-slate-500 bg-white/5 border-white/10'}`}>
                      {u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-center">{u.chats}</td>
                  <td className="px-4 py-3 text-slate-400 text-center">{u.messages}</td>
                  <td className="px-4 py-3 text-slate-400 text-center">{u.images}</td>
                  <td className="px-4 py-3 text-slate-600 text-xs font-mono">
                    {u.createdAt ? new Date(u.createdAt).toLocaleDateString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Ratings breakdown */}
      {(stats.thumbsUp + stats.thumbsDown) > 0 && (
        <div className="rounded-2xl border border-white/10 bg-[#13131f] p-6">
          <h2 className="text-sm font-semibold text-slate-200 mb-4">Response Quality</h2>
          <div className="flex items-center gap-4">
            <div className="flex-1 bg-white/5 rounded-full h-3 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all"
                style={{ width: `${Math.round(stats.thumbsUp / (stats.thumbsUp + stats.thumbsDown) * 100)}%` }}
              />
            </div>
            <span className="text-xs font-mono text-slate-400 flex-shrink-0">
              {Math.round(stats.thumbsUp / (stats.thumbsUp + stats.thumbsDown) * 100)}% positive
            </span>
          </div>
          <div className="flex items-center gap-6 mt-3">
            <span className="flex items-center gap-1.5 text-xs text-emerald-400">
              <ThumbsUp size={11} /> {stats.thumbsUp} positive
            </span>
            <span className="flex items-center gap-1.5 text-xs text-red-400">
              <ThumbsDown size={11} /> {stats.thumbsDown} negative
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
