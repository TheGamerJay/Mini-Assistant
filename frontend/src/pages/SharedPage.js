/**
 * SharedPage.js
 * Public view for shared Mini Assistant outputs.
 * Rendered when URL path is /s/{id} — no auth required.
 *
 * Content types: 'text' (markdown), 'app' (HTML preview), 'image'
 */

import React, { useEffect, useState } from 'react';
import { Copy, Check, ExternalLink, Eye, Zap } from 'lucide-react';

const BASE = process.env.REACT_APP_API_URL || '';
const APP_URL = process.env.REACT_APP_FRONTEND_URL || 'https://www.miniassistantai.com';

// ---------------------------------------------------------------------------
// Simple markdown → HTML (bold, italic, code, line breaks — no heavy lib)
// ---------------------------------------------------------------------------
function mdToHtml(text) {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\n/g, '<br />');
}

// ---------------------------------------------------------------------------
// App preview in sandboxed iframe
// ---------------------------------------------------------------------------
function AppPreview({ html }) {
  return (
    <iframe
      srcDoc={html}
      sandbox="allow-scripts allow-same-origin"
      className="w-full rounded-xl border border-white/10"
      style={{ height: '70vh', background: '#fff' }}
      title="App preview"
    />
  );
}

// ---------------------------------------------------------------------------
// Copy button
// ---------------------------------------------------------------------------
function CopyButton({ text, label = 'Copy' }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try { await navigator.clipboard.writeText(text); } catch { return; }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white/8 hover:bg-white/12 border border-white/10 text-sm text-slate-300 hover:text-white transition-all"
    >
      {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
      {copied ? 'Copied!' : label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// SharedPage
// ---------------------------------------------------------------------------
export default function SharedPage({ shareId }) {
  const [data, setData]     = useState(null);
  const [error, setError]   = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!shareId) { setError('Invalid share link.'); setLoading(false); return; }
    fetch(`${BASE}/api/share/${shareId}`)
      .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e.detail || 'Not found')))
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(typeof e === 'string' ? e : 'Could not load this share.'); setLoading(false); });
  }, [shareId]);

  // ── Loading ──
  if (loading) {
    return (
      <div className="min-h-screen bg-[#0b0b12] flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-violet-500/30 border-t-violet-500 rounded-full animate-spin" />
      </div>
    );
  }

  // ── Error ──
  if (error) {
    return (
      <div className="min-h-screen bg-[#0b0b12] flex flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="text-4xl">🔗</div>
        <h1 className="text-xl font-bold text-slate-200">Share not found</h1>
        <p className="text-sm text-slate-500 max-w-sm">{error}</p>
        <a href={APP_URL} className="mt-2 px-5 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold transition-colors">
          Go to Mini Assistant AI
        </a>
      </div>
    );
  }

  const isApp   = data.content_type === 'app';
  const isImage = data.content_type === 'image';
  const isText  = data.content_type === 'text';

  const formattedDate = new Date(data.created_at * 1000).toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
  });

  return (
    <div className="min-h-screen bg-[#0b0b12] text-white flex flex-col">

      {/* ── Top bar ── */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06] bg-[#0d0d14]">
        <a href={APP_URL} className="flex items-center gap-2 group">
          <img src="/Logo.png" alt="Mini Assistant AI" className="w-7 h-7 object-contain" />
          <span className="text-sm font-semibold text-slate-300 group-hover:text-white transition-colors">
            Mini Assistant AI
          </span>
        </a>
        <div className="flex items-center gap-2">
          {data.views > 0 && (
            <span className="flex items-center gap-1 text-[11px] text-slate-600">
              <Eye size={11} /> {data.views.toLocaleString()}
            </span>
          )}
          <a
            href={`${APP_URL}?utm_source=share&utm_medium=shared_page&utm_content=${shareId}`}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-gradient-to-r from-violet-600 to-cyan-600 text-white text-xs font-bold hover:opacity-90 transition-all shadow-lg shadow-violet-900/30"
          >
            <Zap size={12} />
            Create your own
          </a>
        </div>
      </header>

      {/* ── Content ── */}
      <main className="flex-1 max-w-4xl mx-auto w-full px-4 sm:px-6 py-8">

        {/* Meta */}
        <div className="mb-6">
          {data.title && (
            <h1 className="text-2xl font-bold text-white mb-1">{data.title}</h1>
          )}
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
            <span>By <span className="text-slate-400 font-medium">{data.author_name}</span></span>
            <span>·</span>
            <span>{formattedDate}</span>
            <span>·</span>
            <span className="capitalize px-2 py-0.5 rounded-full bg-white/5 border border-white/8">
              {isApp ? 'App' : isImage ? 'Image' : 'AI response'}
            </span>
          </div>
          {data.prompt && (
            <p className="mt-3 text-sm text-slate-500 italic leading-relaxed">
              "{data.prompt}"
            </p>
          )}
        </div>

        {/* Content block */}
        <div className="rounded-2xl border border-white/8 bg-[#0f0f1a] overflow-hidden mb-6">

          {isText && (
            <div
              className="px-6 py-5 text-sm text-slate-200 leading-relaxed prose-invert max-w-none"
              style={{ lineHeight: '1.75' }}
              dangerouslySetInnerHTML={{ __html: mdToHtml(data.content) }}
            />
          )}

          {isApp && <AppPreview html={data.content} />}

          {isImage && (
            <div className="flex items-center justify-center p-6 bg-[#0d0d12]">
              <img
                src={data.content}
                alt={data.title || 'Generated image'}
                className="max-w-full max-h-[70vh] rounded-xl object-contain"
              />
            </div>
          )}
        </div>

        {/* Action bar */}
        <div className="flex flex-wrap items-center gap-3">
          <CopyButton
            text={data.content}
            label={isApp ? 'Copy HTML' : isImage ? 'Copy URL' : 'Copy text'}
          />
          {isApp && (
            <button
              onClick={() => {
                // Redirect to app with edit prompt → conversion gate
                window.location.href = `${APP_URL}?utm_source=share&utm_medium=edit_gate`;
              }}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white/5 hover:bg-violet-500/15 border border-white/10 hover:border-violet-500/30 text-sm text-slate-400 hover:text-violet-300 transition-all"
            >
              <ExternalLink size={14} />
              Edit this app
            </button>
          )}
        </div>

      </main>

      {/* ── Footer / CTA ── */}
      <footer className="border-t border-white/[0.06] px-6 py-8">
        <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-slate-300">Made with Mini Assistant AI</p>
            <p className="text-xs text-slate-600 mt-0.5">
              Build apps, generate images, and write code with AI — free to start.
            </p>
          </div>
          <a
            href={`${APP_URL}?utm_source=share&utm_medium=footer_cta&utm_content=${shareId}`}
            className="flex-shrink-0 flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-cyan-600 text-white text-sm font-bold hover:opacity-90 transition-all shadow-lg shadow-violet-900/30"
          >
            <Zap size={14} />
            Create your own — it's free
          </a>
        </div>
      </footer>

    </div>
  );
}
