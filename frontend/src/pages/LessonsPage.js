/**
 * pages/LessonsPage.js
 * Shows everything Mini Assistant has learned about the user across all sessions.
 * Facts can be individually deleted to correct the AI's understanding.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Brain, Trash2, RefreshCw, BookOpen } from 'lucide-react';
import { IMAGE_API } from '../api/client';

// Map fact keys to readable labels and emoji
const KEY_META = {
  language:           { label: 'Language',         emoji: '💻' },
  backend_framework:  { label: 'Backend',           emoji: '⚙️' },
  frontend_framework: { label: 'Frontend',          emoji: '🎨' },
  database:           { label: 'Database',          emoji: '🗄️' },
  project_name:       { label: 'Project',           emoji: '📁' },
  indent_style:       { label: 'Indent Style',      emoji: '↹' },
  package_manager:    { label: 'Package Manager',   emoji: '📦' },
  testing_framework:  { label: 'Testing',           emoji: '🧪' },
  deployment:         { label: 'Deployment',        emoji: '🚀' },
  preference:         { label: 'Preference',        emoji: '⭐' },
};

function timeAgo(isoStr) {
  if (!isoStr) return '';
  const s = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function LessonsPage() {
  const [facts, setFacts]     = useState([]);
  const [prefs, setPrefs]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(null); // fact_id being deleted

  const fetchFacts = useCallback(async () => {
    setLoading(true);
    try {
      const [memRes, prefsRes] = await Promise.all([
        fetch(`${IMAGE_API}/memory`),
        fetch(`${IMAGE_API}/userprefs`),
      ]);
      const memData   = await memRes.json();
      const prefsData = await prefsRes.json();
      setFacts(memData.facts || []);
      setPrefs(prefsData || null);
    } catch {
      setFacts([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchFacts(); }, [fetchFacts]);

  const handleDelete = useCallback(async (factId) => {
    setDeleting(factId);
    try {
      await fetch(`${IMAGE_API}/memory/${factId}`, { method: 'DELETE' });
      setFacts(prev => prev.filter(f => f.id !== factId));
    } catch { /* ignore */ } finally {
      setDeleting(null);
    }
  }, []);

  // Group by key
  const grouped = facts.reduce((acc, f) => {
    const group = acc[f.key] || [];
    group.push(f);
    acc[f.key] = group;
    return acc;
  }, {});

  return (
    <div className="h-full overflow-auto px-6 py-8 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.25)' }}>
            <Brain size={18} style={{ color: '#a78bfa' }} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">What I've Learned</h1>
            <p className="text-[12px] text-slate-500">Facts Mini Assistant picked up from your conversations</p>
          </div>
        </div>
        <button
          onClick={fetchFacts}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-all"
        >
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Empty state */}
      {!loading && facts.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
          <BookOpen size={40} className="text-slate-700" strokeWidth={1} />
          <p className="text-slate-500 text-sm">
            No facts learned yet.<br />
            Chat about your projects and Mini Assistant will pick up useful details automatically.
          </p>
        </div>
      )}

      {/* Style profile card */}
      {prefs && prefs.build_count > 0 && (
        <div className="mb-8 p-4 rounded-2xl space-y-3"
          style={{ background: 'rgba(139,92,246,0.05)', border: '1px solid rgba(139,92,246,0.15)' }}>
          <div className="flex items-center gap-2">
            <span className="text-base">🎨</span>
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest">Your Style Profile</span>
            <span className="ml-auto text-[10px] text-slate-600 font-mono">{prefs.build_count} build{prefs.build_count !== 1 ? 's' : ''}</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {prefs.themes?.map(t => (
              <span key={t} className="px-2.5 py-1 rounded-full text-[10px] font-medium"
                style={{ background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.2)', color: '#a78bfa' }}>
                {t}
              </span>
            ))}
            {prefs.app_types?.map(t => (
              <span key={t} className="px-2.5 py-1 rounded-full text-[10px] font-medium"
                style={{ background: 'rgba(34,211,238,0.08)', border: '1px solid rgba(34,211,238,0.2)', color: '#22d3ee' }}>
                {t}
              </span>
            ))}
            {prefs.color_palette?.map(c => (
              <span key={c} className="px-2.5 py-1 rounded-full text-[10px] font-medium"
                style={{ background: 'rgba(244,114,182,0.08)', border: '1px solid rgba(244,114,182,0.2)', color: '#f472b6' }}>
                {c}
              </span>
            ))}
            {prefs.style_signals?.map(s => (
              <span key={s} className="px-2.5 py-1 rounded-full text-[10px] font-medium"
                style={{ background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.2)', color: '#fbbf24' }}>
                {s}
              </span>
            ))}
            {(!prefs.themes?.length && !prefs.app_types?.length) && (
              <span className="text-[11px] text-slate-600">Keep building — style preferences will appear here automatically.</span>
            )}
          </div>
        </div>
      )}

      {/* Fact groups */}
      <div className="space-y-6">
        {Object.entries(grouped).map(([key, keyFacts]) => {
          const meta = KEY_META[key] || { label: key, emoji: '💡' };
          return (
            <div key={key}>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-base leading-none">{meta.emoji}</span>
                <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest">{meta.label}</span>
              </div>
              <div className="space-y-2">
                {keyFacts.map(fact => (
                  <div
                    key={fact.id}
                    className="flex items-center gap-3 px-4 py-3 rounded-xl group"
                    style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}
                  >
                    {/* Confidence bar */}
                    <div className="w-1 self-stretch rounded-full flex-shrink-0" style={{
                      background: `linear-gradient(to bottom, rgba(139,92,246,${fact.confidence}), rgba(99,102,241,${fact.confidence * 0.6}))`,
                    }} />
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] text-slate-200 font-medium truncate">{fact.value}</div>
                      <div className="text-[10px] text-slate-600 mt-0.5 flex items-center gap-2">
                        <span className="capitalize">{fact.source}</span>
                        <span>·</span>
                        <span>{timeAgo(fact.updated_at)}</span>
                        <span>·</span>
                        <span>{Math.round(fact.confidence * 100)}% confident</span>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDelete(fact.id)}
                      disabled={deleting === fact.id}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded-lg text-slate-700 hover:text-red-400 hover:bg-red-500/10 transition-all flex-shrink-0"
                      title="Forget this fact"
                    >
                      {deleting === fact.id
                        ? <RefreshCw size={13} className="animate-spin" />
                        : <Trash2 size={13} />}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {!loading && facts.length > 0 && (
        <p className="text-center text-[10px] text-slate-700 mt-10 font-mono">
          {facts.length} fact{facts.length !== 1 ? 's' : ''} stored · hover a fact to delete it
        </p>
      )}
    </div>
  );
}
