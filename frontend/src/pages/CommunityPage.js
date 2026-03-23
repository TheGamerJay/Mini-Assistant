/**
 * pages/CommunityPage.js
 * Community showcase — opt-in shared apps from all users.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Users, Play, RefreshCw, Globe } from 'lucide-react';
import { IMAGE_API } from '../api/client';

function timeAgo(ts) {
  const s = Math.floor(Date.now() / 1000) - ts;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function CommunityPage() {
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchApps = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${IMAGE_API}/community`);
      const data = await res.json();
      setApps(data.apps || []);
    } catch {
      setApps([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchApps(); }, [fetchApps]);

  return (
    <div className="h-full overflow-auto px-6 py-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: 'rgba(99,102,241,0.15)', border: '1px solid rgba(99,102,241,0.25)' }}>
            <Users size={18} style={{ color: '#818cf8' }} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">Community Showcase</h1>
            <p className="text-[12px] text-slate-500">Apps shared by the Mini Assistant community</p>
          </div>
        </div>
        <button
          onClick={fetchApps}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-all"
        >
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Empty state */}
      {!loading && apps.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
          <Globe size={40} className="text-slate-700" strokeWidth={1} />
          <p className="text-slate-500 text-sm">No apps shared yet.<br />Build something and share it to the community!</p>
        </div>
      )}

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {apps.map(app => (
          <div
            key={app.id}
            className="flex flex-col rounded-2xl overflow-hidden transition-all duration-200 hover:-translate-y-0.5"
            style={{
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid rgba(255,255,255,0.07)',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(99,102,241,0.3)'; e.currentTarget.style.background = 'rgba(99,102,241,0.06)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.07)'; e.currentTarget.style.background = 'rgba(255,255,255,0.03)'; }}
          >
            {/* Preview thumbnail or placeholder */}
            <div className="h-36 overflow-hidden relative flex items-center justify-center flex-shrink-0"
              style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.08), rgba(34,211,238,0.05))' }}>
              {app.thumbnail ? (
                <img
                  src={`data:image/jpeg;base64,${app.thumbnail}`}
                  alt={app.title}
                  className="w-full h-full object-cover"
                  style={{ opacity: 0.92 }}
                />
              ) : (
                <span className="text-3xl">⚡</span>
              )}
              {/* Subtle gradient overlay at bottom */}
              <div className="absolute inset-x-0 bottom-0 h-8 pointer-events-none"
                style={{ background: 'linear-gradient(to bottom, transparent, rgba(10,11,20,0.7))' }} />
            </div>

            {/* Info */}
            <div className="p-4 flex flex-col gap-3 flex-1">
              <div>
                <div className="text-[13px] font-semibold text-white truncate">{app.title}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  by <span className="text-slate-400">{app.author_name}</span> · {timeAgo(app.timestamp)}
                </div>
              </div>
              <a
                href={app.play_url}
                target="_blank"
                rel="noreferrer"
                className="mt-auto flex items-center justify-center gap-1.5 py-2 rounded-xl text-[12px] font-semibold transition-all"
                style={{
                  background: 'rgba(34,211,238,0.1)',
                  border: '1px solid rgba(34,211,238,0.2)',
                  color: '#22d3ee',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = 'rgba(34,211,238,0.18)'; }}
                onMouseLeave={e => { e.currentTarget.style.background = 'rgba(34,211,238,0.1)'; }}
              >
                <Play size={11} fill="currentColor" />
                Play
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
