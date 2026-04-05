/**
 * components/Git/RepoInspector.js
 * GitHub Repo Inspector — lets users paste a GitHub URL and have the
 * GitHub Brain scan it, then sends the result to chat as context.
 */

import React, { useState } from 'react';
import { Github, Search, Zap, ChevronDown, ChevronRight, FileCode, Layers, AlertTriangle, ArrowRight, CheckCircle } from 'lucide-react';
import { api } from '../../api/client';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

export default function RepoInspector() {
  const [url, setUrl]           = useState('');
  const [token, setToken]       = useState('');
  const [focus, setFocus]       = useState('');
  const [loading, setLoading]   = useState(false);
  const [report, setReport]     = useState(null);
  const [error, setError]       = useState('');
  const [expanded, setExpanded] = useState({ files: true, features: true, patches: true, dupes: false });

  const toggle = key => setExpanded(p => ({ ...p, [key]: !p[key] }));

  const inspect = async () => {
    const trimmed = url.trim();
    if (!trimmed) { toast.error('Paste a GitHub URL first'); return; }
    if (!trimmed.includes('github.com')) { toast.error('Must be a github.com URL'); return; }

    setLoading(true);
    setReport(null);
    setError('');

    try {
      const res = await fetch(`${BACKEND_URL}/image-api/api/repo/inspect`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(localStorage.getItem('ma_token') ? { Authorization: `Bearer ${localStorage.getItem('ma_token')}` } : {}),
        },
        body: JSON.stringify({ github_url: trimmed, focus: focus.trim(), api_key_gh: token.trim() }),
      });

      const data = await res.json();
      if (!res.ok || data.status === 'error') {
        setError(data.error || data.detail || 'Inspection failed');
        return;
      }
      setReport(data);
      toast.success('Repo scanned — ready to chat about it');
    } catch (err) {
      setError(err.message || 'Network error');
    } finally {
      setLoading(false);
    }
  };

  const sendToChat = () => {
    if (!report) return;
    // Store in sessionStorage — ChatPage picks it up on next message
    try {
      sessionStorage.setItem('ma_repo_context', JSON.stringify({
        url:          url.trim(),
        project_type: report.project_type,
        tech_stack:   report.tech_stack,
        features:     report.existing_features,
        patch_targets: report.recommended_patch_targets,
        file_count:   report.relevant_files?.length,
      }));
      toast.success('Repo context loaded — go to chat and describe what you want to do');
    } catch {
      toast.error('Could not save context — try again');
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-[#0a0a10] text-slate-200">
      {/* Header */}
      <div className="px-6 pt-6 pb-4 border-b border-white/5">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-cyan-500 flex items-center justify-center">
            <Github size={16} className="text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white tracking-wide">GITHUB BRAIN</h1>
            <p className="text-[10px] text-slate-500 font-mono uppercase tracking-widest">REPO INSPECTION</p>
          </div>
        </div>
        <p className="text-xs text-slate-500 mt-2 leading-relaxed">
          Paste any public GitHub repo URL. Mini Assistant will scan the code, detect the stack,
          map existing features, and load everything as context before building or fixing anything.
        </p>
      </div>

      <div className="px-6 py-5 space-y-4">
        {/* URL input */}
        <div>
          <label className="block text-[10px] font-mono text-slate-500 uppercase tracking-widest mb-1.5">
            GitHub Repo URL
          </label>
          <input
            value={url}
            onChange={e => setUrl(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && inspect()}
            placeholder="https://github.com/owner/repo"
            className="w-full bg-[#111118] border border-white/8 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-500/50 transition-colors font-mono"
          />
        </div>

        {/* What you want to do */}
        <div>
          <label className="block text-[10px] font-mono text-slate-500 uppercase tracking-widest mb-1.5">
            What do you want to do? <span className="text-slate-600">(optional — helps Brain focus)</span>
          </label>
          <input
            value={focus}
            onChange={e => setFocus(e.target.value)}
            placeholder="e.g. add a scoreboard, fix the login page, add dark mode…"
            className="w-full bg-[#111118] border border-white/8 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-500/50 transition-colors"
          />
        </div>

        {/* GitHub token (private repos) */}
        <div>
          <label className="block text-[10px] font-mono text-slate-500 uppercase tracking-widest mb-1.5">
            GitHub Token <span className="text-slate-600">(only needed for private repos)</span>
          </label>
          <input
            type="password"
            value={token}
            onChange={e => setToken(e.target.value)}
            placeholder="ghp_••••••••••••••••"
            className="w-full bg-[#111118] border border-white/8 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-500/50 transition-colors font-mono"
          />
          <p className="text-[10px] text-slate-600 mt-1">
            Generate at github.com → Settings → Developer settings → Personal access tokens → read:repo scope
          </p>
        </div>

        {/* Scan button */}
        <button
          onClick={inspect}
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-gradient-to-r from-violet-500 to-cyan-500 hover:from-violet-400 hover:to-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-bold transition-all"
        >
          {loading ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Scanning repo…
            </>
          ) : (
            <>
              <Search size={14} />
              Scan Repository
            </>
          )}
        </button>

        {/* Error */}
        {error && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-red-500/8 border border-red-500/20">
            <AlertTriangle size={13} className="text-red-400 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-red-300">{error}</p>
          </div>
        )}

        {/* Report */}
        {report && (
          <div className="space-y-3 pt-1">

            {/* Summary card */}
            <div className="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle size={13} className="text-emerald-400" />
                <span className="text-xs font-bold text-emerald-300">Scan complete</span>
              </div>
              <p className="text-xs text-slate-300 font-semibold mb-0.5">{report.project_type}</p>
              <div className="flex flex-wrap gap-1 mt-1.5">
                {(report.tech_stack || []).map(s => (
                  <span key={s} className="px-1.5 py-0.5 rounded text-[10px] bg-violet-500/15 text-violet-300 border border-violet-500/20 font-mono">
                    {s}
                  </span>
                ))}
              </div>
              <p className="text-[10px] text-slate-500 mt-2">{report.file_tree_summary}</p>
            </div>

            {/* Existing features */}
            {report.existing_features?.length > 0 && (
              <div className="rounded-lg border border-white/6 overflow-hidden">
                <button onClick={() => toggle('features')} className="w-full flex items-center justify-between px-3 py-2 bg-white/3 hover:bg-white/5 transition-colors">
                  <span className="text-[10px] font-mono text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
                    <Layers size={11} /> Detected Features
                  </span>
                  {expanded.features ? <ChevronDown size={11} className="text-slate-500" /> : <ChevronRight size={11} className="text-slate-500" />}
                </button>
                {expanded.features && (
                  <div className="px-3 py-2 flex flex-wrap gap-1.5">
                    {report.existing_features.map(f => (
                      <span key={f} className="px-2 py-0.5 rounded-full text-[10px] bg-cyan-500/10 text-cyan-300 border border-cyan-500/15">
                        {f.replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Patch targets */}
            {report.recommended_patch_targets?.length > 0 && (
              <div className="rounded-lg border border-white/6 overflow-hidden">
                <button onClick={() => toggle('patches')} className="w-full flex items-center justify-between px-3 py-2 bg-white/3 hover:bg-white/5 transition-colors">
                  <span className="text-[10px] font-mono text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
                    <FileCode size={11} /> Recommended Patch Targets
                  </span>
                  {expanded.patches ? <ChevronDown size={11} className="text-slate-500" /> : <ChevronRight size={11} className="text-slate-500" />}
                </button>
                {expanded.patches && (
                  <div className="px-3 py-2 space-y-1">
                    {report.recommended_patch_targets.slice(0, 8).map(f => (
                      <p key={f} className="text-[10px] font-mono text-slate-400 truncate">
                        <span className="text-violet-400 mr-1">→</span>{f}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Key files */}
            {report.relevant_files?.length > 0 && (
              <div className="rounded-lg border border-white/6 overflow-hidden">
                <button onClick={() => toggle('files')} className="w-full flex items-center justify-between px-3 py-2 bg-white/3 hover:bg-white/5 transition-colors">
                  <span className="text-[10px] font-mono text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
                    <FileCode size={11} /> Files Inspected ({report.relevant_files.length})
                  </span>
                  {expanded.files ? <ChevronDown size={11} className="text-slate-500" /> : <ChevronRight size={11} className="text-slate-500" />}
                </button>
                {expanded.files && (
                  <div className="px-3 py-2 space-y-2 max-h-48 overflow-y-auto">
                    {report.relevant_files.map((f, i) => (
                      <div key={i}>
                        <p className="text-[10px] font-mono text-cyan-400 truncate">{f.path}</p>
                        <p className="text-[10px] text-slate-500">{f.purpose}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Duplicate risks */}
            {report.duplicate_candidates?.length > 0 && (
              <div className="rounded-lg border border-amber-500/15 overflow-hidden">
                <button onClick={() => toggle('dupes')} className="w-full flex items-center justify-between px-3 py-2 bg-amber-500/5 hover:bg-amber-500/8 transition-colors">
                  <span className="text-[10px] font-mono text-amber-400 uppercase tracking-widest flex items-center gap-1.5">
                    <AlertTriangle size={11} /> Duplicate Risks ({report.duplicate_candidates.length})
                  </span>
                  {expanded.dupes ? <ChevronDown size={11} className="text-amber-500" /> : <ChevronRight size={11} className="text-amber-500" />}
                </button>
                {expanded.dupes && (
                  <div className="px-3 py-2 space-y-2">
                    {report.duplicate_candidates.map((d, i) => (
                      <div key={i}>
                        <p className="text-[10px] text-amber-300 font-semibold capitalize">{d.concern.replace(/_/g, ' ')}</p>
                        {(d.files || []).slice(0, 4).map(f => (
                          <p key={f} className="text-[10px] font-mono text-slate-500 truncate ml-2">· {f}</p>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Notes */}
            {report.notes?.length > 0 && (
              <div className="p-2 rounded-lg bg-slate-800/40 border border-white/5">
                {report.notes.map((n, i) => (
                  <p key={i} className="text-[10px] text-slate-500">{n}</p>
                ))}
              </div>
            )}

            {/* Send to Chat CTA */}
            <button
              onClick={sendToChat}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-gradient-to-r from-violet-500 to-cyan-500 hover:from-violet-400 hover:to-cyan-400 text-white text-sm font-bold transition-all"
            >
              <Zap size={14} />
              Load as Chat Context
              <ArrowRight size={13} />
            </button>
            <p className="text-[10px] text-slate-600 text-center">
              After clicking, go to Chat and describe what you want to build or fix.
              Mini Assistant will use this repo as its starting point.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
