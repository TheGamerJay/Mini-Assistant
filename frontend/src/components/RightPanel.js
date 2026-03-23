/**
 * components/RightPanel.js
 * Collapsible right panel for the unified workspace.
 * Tabs: Preview · Code · Files · Logs
 *
 * Props:
 *   messages   — chat messages array (to extract latest code blocks)
 *   open       — controlled open state
 *   onClose    — callback to close
 */

import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import {
  Monitor, Code2, FolderOpen, X, RefreshCw,
  ChevronRight, File, Download, ListTodo, Diff, Plus, Trash2, CheckSquare, Square,
  Bug, Zap, CheckCircle, AlertTriangle, StopCircle, Share2, Copy, ExternalLink, Users,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { api } from '../api/client';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Extract all code blocks from a message content string */
function extractCodeBlocks(content) {
  if (!content) return [];
  const blocks = [];
  // Match ``` with optional language tag and optional whitespace before content
  const re = /```([a-zA-Z0-9_+-]*)[ \t]*\r?\n([\s\S]*?)```/g;
  let m;
  while ((m = re.exec(content)) !== null) {
    const lang = (m[1] || 'text').toLowerCase();
    const code = m[2].trim();
    if (code) blocks.push({ lang, code });
  }
  return blocks;
}

/**
 * During live streaming the closing ``` never arrives yet.
 * Grab whatever is after the opening ```html fence — even if incomplete —
 * so the preview updates in real-time as tokens arrive.
 */
function extractPartialBlock(streamingText) {
  // Match an opening fence (```html or ```) that has NOT closed yet
  const openRe = /```([a-zA-Z0-9_+-]*)[ \t]*\r?\n([\s\S]+)$/;
  const m = openRe.exec(streamingText);
  if (!m) return [];
  const lang = (m[1] || 'text').toLowerCase();
  const code = m[2]; // partial — no trailing ``` yet
  if (!code.trim()) return [];
  return [{ lang, code }];
}

/** Detect raw HTML (no code fence) — Claude sometimes skips the ```html wrapper */
function extractRawHtml(content) {
  if (!content) return [];
  const idx = content.search(/<!DOCTYPE\s+html/i);
  if (idx !== -1 && content.length > 300) {
    return [{ lang: 'html', code: content.slice(idx) }];
  }
  return [];
}

/** Find the latest code — live stream first, then last completed assistant message */
function getLatestCode(messages, streamingText) {
  // Live stream takes priority — extract as tokens arrive
  if (streamingText) {
    // Try complete blocks first (multiple code blocks in one message)
    const liveBlocks = extractCodeBlocks(streamingText);
    if (liveBlocks.length > 0) return liveBlocks;
    // Fall back to partial block (fence opened, closing ``` not yet streamed)
    const partial = extractPartialBlock(streamingText);
    if (partial.length > 0) return partial;
    // Last resort: raw HTML without a fence
    const raw = extractRawHtml(streamingText);
    if (raw.length > 0) return raw;
  }
  // Fall back to last completed assistant message with code
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg.role !== 'assistant') continue;
    const blocks = extractCodeBlocks(msg.content);
    if (blocks.length > 0) return blocks;
    // Also try raw HTML fallback for messages without fences
    const raw = extractRawHtml(msg.content);
    if (raw.length > 0) return raw;
  }
  return [];
}

/** Script injected into every iframe — error capture + DOM visual inspector */
const ERROR_CAPTURE_SCRIPT = `<script>
(function(){
  // ── Error relay ──────────────────────────────────────────────────────────
  var send = function(type, payload) {
    try { window.parent.postMessage(Object.assign({ __maType: type }, payload), '*'); } catch(e) {}
  };
  var _ce = console.error.bind(console);
  var _cw = console.warn.bind(console);
  console.error = function() { send('iframe_error', { level:'error', msg: Array.prototype.join.call(arguments,' ').slice(0,500) }); _ce.apply(console, arguments); };
  console.warn  = function() { send('iframe_error', { level:'warn',  msg: Array.prototype.join.call(arguments,' ').slice(0,500) }); _cw.apply(console, arguments); };
  window.onerror = function(msg, src, line, col, err) {
    send('iframe_error', { level:'error', msg: msg + (err ? ' | ' + (err.stack||'').split('\\n')[0] : '') + ' [line '+line+']' });
    return false;
  };
  window.addEventListener('unhandledrejection', function(e) {
    send('iframe_error', { level:'error', msg: 'Unhandled promise: ' + (e.reason && e.reason.message ? e.reason.message : String(e.reason)) });
  });

  // ── DOM Visual Inspector — runs on request ───────────────────────────────
  function buildDOMReport() {
    var lines = [];
    // 1. Buttons & clickable elements
    var btns = document.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"]');
    btns.forEach(function(el) {
      var label = (el.textContent || el.value || el.id || '?').trim().slice(0, 40);
      var hasHandler = !!(el.onclick || el._hasListener);
      var evData = el.__maListeners;
      lines.push('BUTTON "' + label + '": ' + (hasHandler || evData ? 'has handler' : 'NO HANDLER DETECTED'));
    });
    // 2. State display elements (score, lives, timer, level)
    var stateEls = document.querySelectorAll('[id*="score"],[id*="count"],[id*="life"],[id*="lives"],[id*="timer"],[id*="level"],[id*="hp"],[id*="health"],[id*="point"],[class*="score"],[class*="lives"],[class*="timer"]');
    stateEls.forEach(function(el) {
      lines.push('STATE "' + (el.id || el.className).slice(0,30) + '": "' + el.textContent.trim().slice(0,30) + '"');
    });
    // 3. Hidden elements that look like screens/modals
    var hidden = document.querySelectorAll('[style*="display:none"],[style*="display: none"],[hidden],.hidden,.game-over,.start-screen,.menu');
    hidden.forEach(function(el) {
      var id = el.id || el.className.toString().slice(0,30);
      lines.push('HIDDEN: ' + id);
    });
    // 4. Canvas elements
    var canvases = document.querySelectorAll('canvas');
    canvases.forEach(function(c) {
      lines.push('CANVAS: ' + c.width + 'x' + c.height + (c.id ? ' id=' + c.id : ''));
    });
    // 5. Inputs
    var inputs = document.querySelectorAll('input:not([type="hidden"]), textarea, select');
    inputs.forEach(function(el) {
      lines.push('INPUT "' + (el.id || el.name || el.type) + '": value="' + String(el.value).slice(0,30) + '"');
    });
    return lines.join('\\n') || 'No interactive elements found';
  }

  // Patch addEventListener to track listeners
  var _origAddEL = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function(type, fn, opts) {
    if (type === 'click' || type === 'touchstart') this.__maListeners = true;
    return _origAddEL.call(this, type, fn, opts);
  };

  // Listen for inspection requests from parent
  window.addEventListener('message', function(e) {
    if (e.data && e.data.__maCmd === 'inspect') {
      send('dom_report', { report: buildDOMReport() });
    }
  });

  send('iframe_ready', {});
})();
<\/script>`;

/** Inject error capture into an HTML string */
function injectErrorCapture(html) {
  if (!html) return html;
  if (html.includes('<head>')) return html.replace('<head>', '<head>' + ERROR_CAPTURE_SCRIPT);
  if (html.includes('<body>')) return html.replace('<body>', ERROR_CAPTURE_SCRIPT + '<body>');
  return ERROR_CAPTURE_SCRIPT + html;
}

/** Try to build a renderable HTML doc from code blocks */
function buildPreviewHtml(blocks) {
  // Look for explicit HTML block first (covers html, htm, markup)
  const htmlBlock = blocks.find(b => ['html', 'htm', 'markup', 'xhtml'].includes(b.lang));
  if (htmlBlock) return htmlBlock.code;

  // Assemble from parts
  const css  = blocks.filter(b => b.lang === 'css').map(b => b.code).join('\n');
  const js   = blocks.filter(b => ['javascript', 'js', 'jsx', 'ts', 'tsx'].includes(b.lang)).map(b => b.code).join('\n');
  const skipLangs = new Set(['css', 'javascript', 'js', 'jsx', 'ts', 'tsx', 'python', 'py', 'bash', 'sh', 'json', 'yaml', 'yml', 'text', 'txt']);
  const html = blocks.filter(b => !skipLangs.has(b.lang)).map(b => b.code).join('\n');

  if (!html && !css && !js) return null;

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body { font-family: system-ui, sans-serif; background: #fff; color: #111; margin: 0; padding: 16px; }
  ${css}
</style>
</head>
<body>
${html}
<script>
try {
  ${js}
} catch(e) { console.error(e); }
</script>
</body>
</html>`;
}

// ---------------------------------------------------------------------------
// Tab button
// ---------------------------------------------------------------------------
function TabBtn({ id, label, icon: Icon, active, onClick }) {
  return (
    <button
      onClick={() => onClick(id)}
      className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 transition-colors
        ${active
          ? 'border-cyan-400 text-cyan-300'
          : 'border-transparent text-slate-500 hover:text-slate-300'}`}
    >
      <Icon size={12} />
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Code viewer
// ---------------------------------------------------------------------------
function CodeViewer({ blocks }) {
  const [selected, setSelected] = useState(0);

  if (blocks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3">
        <Code2 size={32} strokeWidth={1} />
        <p className="text-xs text-center">No code generated yet.<br />Ask Mini Assistant to build something.</p>
      </div>
    );
  }

  const block = blocks[selected] || blocks[0];

  return (
    <div className="flex flex-col h-full">
      {blocks.length > 1 && (
        <div className="flex gap-1 px-3 py-2 border-b border-white/5 flex-wrap">
          {blocks.map((b, i) => (
            <button
              key={i}
              onClick={() => setSelected(i)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors
                ${i === selected ? 'bg-cyan-500/20 text-cyan-300' : 'bg-white/5 text-slate-500 hover:text-slate-300'}`}
            >
              {b.lang}
            </button>
          ))}
        </div>
      )}
      <pre className="flex-1 overflow-auto p-4 text-[12px] font-mono text-slate-300 leading-5">
        <code>{block.code}</code>
      </pre>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Preview
// ---------------------------------------------------------------------------
const MAX_AUTOFIX_ITERATIONS = 5;

function PreviewPane({ blocks, previewImage = null, onClearImage, isStreaming = false, sessionId = null, onFixedHtml = null }) {
  const [key, setKey] = useState(0);
  const iframeRef = useRef(null);
  const rawHtml = useMemo(() => buildPreviewHtml(blocks), [blocks]);
  const lastHtmlRef = useRef(null);
  if (rawHtml) lastHtmlRef.current = rawHtml;
  const html = rawHtml || lastHtmlRef.current;

  // Remount iframe when streaming ends (Play buttons work after full code arrives)
  const prevIsStreamingRef = useRef(false);
  useEffect(() => {
    const wasStreaming = prevIsStreamingRef.current;
    prevIsStreamingRef.current = isStreaming;
    if (wasStreaming && !isStreaming && html) {
      setKey(k => k + 1);
      // Auto-run debug agent after every build — give iframe 1.8s to mount first
      const t = setTimeout(() => {
        if (!fixingRef.current) runFixLoop();
      }, 1800);
      return () => clearTimeout(t);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStreaming, html]);

  // Saved badge for new images
  const [showSaved, setShowSaved] = useState(false);
  const prevImageRef = useRef(null);
  useEffect(() => {
    if (previewImage && previewImage !== prevImageRef.current) {
      prevImageRef.current = previewImage;
      setShowSaved(true);
      const t = setTimeout(() => setShowSaved(false), 4000);
      return () => clearTimeout(t);
    }
  }, [previewImage]);

  // ── Error capture: listen for postMessage from iframe ──────────────────
  const [iframeErrors, setIframeErrors] = useState([]);
  useEffect(() => {
    const handler = (e) => {
      if (!e.data || e.data.__maType !== 'iframe_error') return;
      const msg = e.data.msg || '';
      if (!msg) return;
      setIframeErrors(prev => {
        if (prev.some(p => p === msg)) return prev;
        return [...prev, msg].slice(-20);
      });
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, []);

  // Clear errors when new code loads (key changes = iframe remounted)
  useEffect(() => { setIframeErrors([]); }, [key]);

  // ── DOM Visual Inspector — request a snapshot from iframe ─────────────
  const requestDomReport = useCallback(() => {
    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        window.removeEventListener('message', handler);
        resolve('');
      }, 2000);
      const handler = (e) => {
        if (e.data?.__maType === 'dom_report') {
          clearTimeout(timeout);
          window.removeEventListener('message', handler);
          resolve(e.data.report || '');
        }
      };
      window.addEventListener('message', handler);
      try {
        iframeRef.current?.contentWindow?.postMessage({ __maCmd: 'inspect' }, '*');
      } catch {
        clearTimeout(timeout);
        window.removeEventListener('message', handler);
        resolve('');
      }
    });
  }, []);

  // ── Share state ────────────────────────────────────────────────────────
  const [shareLoading, setShareLoading] = useState(false);
  const [shareToast, setShareToast] = useState(null); // { url, copied }
  const [communityLoading, setCommunityLoading] = useState(false);
  const [communityToast, setCommunityToast] = useState(null); // 'success' | 'error' | null

  const handleShare = useCallback(async () => {
    const shareHtml = currentFixHtml || html;
    if (!shareHtml || shareLoading) return;
    setShareLoading(true);
    try {
      const { IMAGE_API } = await import('../api/client');
      const res = await fetch(`${IMAGE_API}/share`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ html: shareHtml }),
      });
      if (!res.ok) throw new Error('Share failed');
      const data = await res.json();
      const url = data.url;
      try { await navigator.clipboard.writeText(url); } catch {}
      setShareToast({ url, copied: true });
      setTimeout(() => setShareToast(null), 6000);
    } catch (e) {
      setShareToast({ url: null, copied: false, error: true });
      setTimeout(() => setShareToast(null), 4000);
    } finally {
      setShareLoading(false);
    }
  }, [currentFixHtml, html, shareLoading]);

  const handleCommunity = useCallback(async () => {
    const shareHtml = currentFixHtml || html;
    if (!shareHtml || communityLoading) return;
    setCommunityLoading(true);
    try {
      const { IMAGE_API } = await import('../api/client');
      // First share to get an ID
      const shareRes = await fetch(`${IMAGE_API}/share`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ html: shareHtml }),
      });
      if (!shareRes.ok) throw new Error('Share failed');
      const shareData = await shareRes.json();
      // Then add to community
      const comRes = await fetch(`${IMAGE_API}/community`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          share_id: shareData.id,
          title: 'Community App',
          author_name: 'Mini Assistant User',
        }),
      });
      if (!comRes.ok) throw new Error('Community post failed');
      setCommunityToast('success');
      setTimeout(() => setCommunityToast(null), 4000);
    } catch {
      setCommunityToast('error');
      setTimeout(() => setCommunityToast(null), 3000);
    } finally {
      setCommunityLoading(false);
    }
  }, [currentFixHtml, html, communityLoading]);

  // ── Auto-Fix loop state ────────────────────────────────────────────────
  const [fixing, setFixing] = useState(false);
  const [fixLog, setFixLog] = useState([]);          // [{pass, text, allClear}]
  const [fixIteration, setFixIteration] = useState(0);
  const [currentFixHtml, setCurrentFixHtml] = useState(null); // live patched HTML
  const [liveToken, setLiveToken] = useState('');
  const fixAbortRef = useRef(null);
  const fixingRef = useRef(false);

  const stopFix = useCallback(() => {
    fixAbortRef.current?.abort();
    fixingRef.current = false;
    setFixing(false);
  }, []);

  const runFixLoop = useCallback(async () => {
    if (fixing || isStreaming) return;
    const startHtml = currentFixHtml || html;
    if (!startHtml) return;

    setFixing(true);
    fixingRef.current = true;
    setFixLog([]);
    setFixIteration(0);
    setLiveToken('');

    let workingHtml = startHtml;
    let errors = [...iframeErrors];

    for (let pass = 1; pass <= MAX_AUTOFIX_ITERATIONS; pass++) {
      if (!fixingRef.current) break;
      setFixIteration(pass);
      setLiveToken('');

      let accumulated = '';
      let allClear = false;
      let passError = null;

      try {
        const ctrl = new AbortController();
        fixAbortRef.current = ctrl;
        // Capture DOM snapshot before sending to Claude
        const domReport = await requestDomReport();
        const res = await api.autofixStream(workingHtml, errors, domReport, pass, sessionId, ctrl.signal);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop();
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const raw = line.slice(6).trim();
            if (!raw) continue;
            try {
              const evt = JSON.parse(raw);
              if (evt.done) {
                allClear = evt.meta?.all_clear || false;
                passError = evt.meta?.error || null;
              } else if (evt.t) {
                accumulated += evt.t;
                setLiveToken(accumulated);
              }
            } catch {}
          }
        }
      } catch (err) {
        if (err.name === 'AbortError') break;
        passError = err.message;
      }

      // Extract fixed HTML from Claude's response
      // Use greedy match so we capture to the LAST closing ```, not the first
      const fenceMatch = /```html\s*\n([\s\S]+)```/.exec(accumulated);
      const rawMatch = /<!DOCTYPE\s+html/i.exec(accumulated);
      let newHtml = null;
      if (fenceMatch) newHtml = fenceMatch[1].trim();
      else if (rawMatch) {
        // Strip anything after the closing </html> tag
        const slice = accumulated.slice(rawMatch.index);
        const endTag = /(<\/html\s*>)/i.exec(slice);
        newHtml = endTag ? slice.slice(0, endTag.index + endTag[1].length) : slice;
      }

      if (newHtml) {
        workingHtml = newHtml;
        setCurrentFixHtml(newHtml);
        // Give iframe 2.5s to run and capture new errors
        await new Promise(r => setTimeout(r, 2500));
        errors = [...iframeErrors]; // collect fresh errors from new render
      }

      setFixLog(prev => [...prev, {
        pass,
        text: passError ? `Pass ${pass} error: ${passError}` : accumulated,
        allClear,
        fixed: !!newHtml,
      }]);

      if (allClear || passError) break;
      if (!newHtml) break; // Claude found nothing to fix — treat as all clear
    }

    // Notify parent with final code so it can add to chat history
    if (onFixedHtml && workingHtml !== startHtml) onFixedHtml(workingHtml);

    // Remount iframe so fixed code runs from a clean state (clears stale JS)
    if (workingHtml !== startHtml) setKey(k => k + 1);

    fixingRef.current = false;
    setFixing(false);
    setLiveToken('');
  }, [fixing, isStreaming, html, currentFixHtml, iframeErrors, sessionId, onFixedHtml]);

  // Build the srcDoc — inject error capture into every render
  const srcDoc = useMemo(() => {
    const src = currentFixHtml || html;
    return src ? injectErrorCapture(src) : null;
  }, [html, currentFixHtml]);

  // ── Image mode ─────────────────────────────────────────────────────────
  if (previewImage) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-white/5 bg-[#0f111a]">
          <div className="flex items-center gap-1.5 flex-1 px-2 py-1 rounded bg-white/5 text-[10px] text-slate-600 font-mono">
            <Monitor size={9} />
            generated image
          </div>
          <a href={`data:image/png;base64,${previewImage}`} download="generated.png"
            className="p-1 rounded hover:bg-white/5 text-slate-600 hover:text-slate-400 transition-colors" title="Download image">
            <Download size={12} />
          </a>
          {onClearImage && (
            <button onClick={onClearImage} className="p-1 rounded hover:bg-red-500/20 text-slate-600 hover:text-red-400 transition-colors" title="Clear image">
              <X size={12} />
            </button>
          )}
        </div>
        <div className="flex-1 flex flex-col items-center justify-center p-4 overflow-auto gap-3">
          <img src={`data:image/png;base64,${previewImage}`} alt="Generated"
            className="max-w-full max-h-[85%] object-contain rounded-lg shadow-xl" />
          {showSaved && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20">
              <CheckSquare size={11} className="text-emerald-400 flex-shrink-0" />
              <span className="text-[10px] text-emerald-400 font-medium">Saved to your library</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (!srcDoc) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3">
        <Monitor size={32} strokeWidth={1} />
        <p className="text-xs text-center">Preview will appear here<br />when code is generated.</p>
      </div>
    );
  }

  const lastLog = fixLog[fixLog.length - 1];
  const isAllClear = lastLog?.allClear;

  return (
    <div className="flex flex-col h-full relative">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-white/5 bg-[#0f111a] flex-shrink-0">
        <div className="flex items-center gap-1.5 flex-1 px-2 py-1 rounded bg-white/5 text-[10px] text-slate-600 font-mono">
          <Monitor size={9} />
          preview
          {iframeErrors.length > 0 && !fixing && (
            <span className="ml-1.5 px-1.5 py-0.5 rounded-full bg-red-500/20 text-red-400 text-[9px]">
              {iframeErrors.length} error{iframeErrors.length > 1 ? 's' : ''}
            </span>
          )}
          {isAllClear && (
            <span className="ml-1.5 px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 text-[9px]">
              ✅ all clear
            </span>
          )}
        </div>
        {fixing && (
          <button
            onClick={stopFix}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/20 transition-all"
            title="Stop debug agent"
          >
            <StopCircle size={10} />
            Stop
          </button>
        )}
        <button
          onClick={handleShare}
          disabled={shareLoading || isStreaming}
          className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20 border border-cyan-500/20 transition-all disabled:opacity-40"
          title="Share this app — anyone gets the game, not the code"
        >
          {shareLoading
            ? <RefreshCw size={10} className="animate-spin" />
            : <Share2 size={10} />}
          Share
        </button>
        <button
          onClick={handleCommunity}
          disabled={communityLoading || isStreaming}
          className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500/20 border border-indigo-500/20 transition-all disabled:opacity-40"
          title="Share to community showcase — your name stays visible"
        >
          {communityLoading
            ? <RefreshCw size={10} className="animate-spin" />
            : <Users size={10} />}
          Community
        </button>
        <button onClick={() => { setCurrentFixHtml(null); setKey(k => k + 1); setIframeErrors([]); setFixLog([]); }}
          className="p-1 rounded hover:bg-white/5 text-slate-600 hover:text-slate-400 transition-colors" title="Refresh preview">
          <RefreshCw size={12} />
        </button>
      </div>

      {/* Share toast */}
      {shareToast && (
        <div
          className="absolute top-12 right-3 z-20 rounded-xl border shadow-2xl overflow-hidden"
          style={{
            background: shareToast.error ? 'rgba(239,68,68,0.12)' : 'rgba(6,182,212,0.10)',
            borderColor: shareToast.error ? 'rgba(239,68,68,0.3)' : 'rgba(6,182,212,0.25)',
            backdropFilter: 'blur(10px)',
            minWidth: 240,
            animation: 'ma-slide-up 0.25s cubic-bezier(.22,1,.36,1) forwards',
          }}
        >
          {shareToast.error ? (
            <div className="flex items-center gap-2 px-4 py-3">
              <AlertTriangle size={13} className="text-red-400 flex-shrink-0" />
              <span className="text-[11px] text-red-300">Couldn't create share link</span>
            </div>
          ) : (
            <div className="px-4 py-3 space-y-2">
              <div className="flex items-center gap-2">
                <CheckCircle size={13} style={{ color: '#34d399' }} className="flex-shrink-0" />
                <span className="text-[11px] text-emerald-300 font-medium">Link copied to clipboard!</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="flex-1 text-[10px] font-mono text-cyan-300/70 truncate">{shareToast.url}</span>
                <a href={shareToast.url} target="_blank" rel="noreferrer"
                  className="p-1 rounded hover:bg-white/10 text-cyan-400 flex-shrink-0" title="Open in new tab">
                  <ExternalLink size={10} />
                </a>
              </div>
              <p className="text-[9px] text-slate-500">Viewers see the game — source code is hidden.</p>
            </div>
          )}
        </div>
      )}

      {/* Community toast */}
      {communityToast && (
        <div
          className="absolute top-12 right-3 z-20 rounded-xl border shadow-2xl overflow-hidden"
          style={{
            background: communityToast === 'error' ? 'rgba(239,68,68,0.12)' : 'rgba(99,102,241,0.10)',
            borderColor: communityToast === 'error' ? 'rgba(239,68,68,0.3)' : 'rgba(99,102,241,0.25)',
            backdropFilter: 'blur(10px)',
            minWidth: 200,
            animation: 'ma-slide-up 0.25s cubic-bezier(.22,1,.36,1) forwards',
          }}
        >
          {communityToast === 'error' ? (
            <div className="flex items-center gap-2 px-4 py-3">
              <AlertTriangle size={13} className="text-red-400 flex-shrink-0" />
              <span className="text-[11px] text-red-300">Couldn't post to community</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 px-4 py-3">
              <CheckCircle size={13} style={{ color: '#34d399' }} className="flex-shrink-0" />
              <span className="text-[11px] text-indigo-300 font-medium">Added to community showcase!</span>
            </div>
          )}
        </div>
      )}

      {/* Debug overlay animations */}
      <style>{`
        @keyframes ma-slide-up {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes ma-wave {
          0%, 60%, 100% { transform: translateY(0); }
          30% { transform: translateY(-5px); }
        }
        @keyframes ma-shimmer {
          0%   { background-position: -200% center; }
          100% { background-position:  200% center; }
        }
        @keyframes ma-scan {
          0%   { top: 0%; opacity: 0; }
          5%   { opacity: 1; }
          95%  { opacity: 1; }
          100% { top: 100%; opacity: 0; }
        }
        @keyframes ma-blink { 0%,100%{opacity:1} 50%{opacity:0} }
        @keyframes ma-pulse-glow {
          0%,100% { box-shadow: 0 0 0 0 rgba(139,92,246,0.4), inset 0 0 0 0 rgba(139,92,246,0); }
          50%     { box-shadow: 0 0 12px 2px rgba(139,92,246,0.25), inset 0 0 8px 0 rgba(139,92,246,0.05); }
        }
        @keyframes ma-border-pulse {
          0%,100% { border-color: rgba(139,92,246,0.2); }
          50%     { border-color: rgba(139,92,246,0.55); }
        }
        @keyframes ma-err-pulse {
          0%,100% { border-color: rgba(239,68,68,0.2); }
          50%     { border-color: rgba(239,68,68,0.5); }
        }
        .ma-slide-up { animation: ma-slide-up 0.28s cubic-bezier(.22,1,.36,1) forwards; }
        .ma-shimmer  {
          background: linear-gradient(90deg, transparent 0%, rgba(139,92,246,0.18) 50%, transparent 100%);
          background-size: 200% 100%;
          animation: ma-shimmer 1.8s linear infinite;
        }
        .ma-cursor::after { content:'▋'; animation: ma-blink 1s step-end infinite; margin-left:2px; }
      `}</style>

      {/* Auto-fix overlay — shown while fixing or when log exists */}
      {(fixing || fixLog.length > 0) && (
        <div
          className="absolute inset-x-0 top-[41px] z-10 border-b border-violet-500/20 p-3 space-y-2 max-h-[55%] overflow-y-auto"
          style={{
            background: 'rgba(11,13,22,0.97)',
            backdropFilter: 'blur(8px)',
            animation: fixing ? 'ma-pulse-glow 2.5s ease-in-out infinite' : undefined,
          }}
        >
          {/* Scanning line — only while active */}
          {fixing && (
            <div className="absolute inset-x-0 top-0 h-full overflow-hidden pointer-events-none" style={{ zIndex: 0 }}>
              <div style={{
                position: 'absolute', left: 0, right: 0, height: '2px',
                background: 'linear-gradient(90deg, transparent, rgba(139,92,246,0.7), transparent)',
                animation: 'ma-scan 2s ease-in-out infinite',
              }} />
            </div>
          )}

          {/* Header */}
          <div className="relative flex items-center gap-2 mb-1" style={{ zIndex: 1 }}>
            <Zap
              size={11}
              className="flex-shrink-0"
              style={{
                color: fixing ? '#a78bfa' : '#6d28d9',
                filter: fixing ? 'drop-shadow(0 0 4px rgba(139,92,246,0.8))' : undefined,
                animation: fixing ? 'ma-blink 2s ease-in-out infinite' : undefined,
              }}
            />
            <span
              className="text-[10px] font-mono font-semibold uppercase tracking-widest"
              style={{
                background: fixing
                  ? 'linear-gradient(90deg, #c4b5fd, #818cf8, #c4b5fd)'
                  : '#7c3aed',
                backgroundSize: '200% 100%',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: fixing ? 'transparent' : undefined,
                animation: fixing ? 'ma-shimmer 2s linear infinite' : undefined,
              }}
            >
              Debug Agent {fixing ? `— Pass ${fixIteration}/${MAX_AUTOFIX_ITERATIONS}` : '— Done'}
            </span>
            {fixing && (
              <div className="flex items-end gap-[3px] ml-auto" style={{ height: 12 }}>
                {[0, 1, 2].map(i => (
                  <div
                    key={i}
                    style={{
                      width: 4, height: 4, borderRadius: '50%',
                      background: '#a78bfa',
                      boxShadow: '0 0 6px rgba(167,139,250,0.8)',
                      animation: `ma-wave 1.1s ease-in-out ${i * 0.18}s infinite`,
                    }}
                  />
                ))}
              </div>
            )}
            {!fixing && fixLog.length > 0 && (
              <>
                <span
                  className="text-[9px] font-mono px-2 py-0.5 rounded-full"
                  style={{
                    background: fixLog[fixLog.length-1]?.allClear
                      ? 'rgba(16,185,129,0.15)' : 'rgba(139,92,246,0.15)',
                    color: fixLog[fixLog.length-1]?.allClear ? '#34d399' : '#a78bfa',
                    border: `1px solid ${fixLog[fixLog.length-1]?.allClear ? 'rgba(16,185,129,0.3)' : 'rgba(139,92,246,0.3)'}`,
                  }}
                >
                  {fixLog[fixLog.length-1]?.allClear ? '✓ clean' : `${fixLog.length} pass${fixLog.length > 1 ? 'es' : ''}`}
                </span>
                <button
                  onClick={() => setFixLog([])}
                  className="ml-auto p-0.5 rounded hover:bg-white/10 transition-colors"
                  title="Dismiss"
                  style={{ color: '#475569' }}
                >
                  <X size={11} />
                </button>
              </>
            )}
          </div>

          {/* Completed passes */}
          {fixLog.map((log, i) => (
            <div
              key={i}
              className="ma-slide-up rounded-lg p-2 border text-[10px] font-mono leading-relaxed relative overflow-hidden"
              style={{
                animationDelay: `${i * 0.06}s`,
                opacity: 0,
                background: log.allClear
                  ? 'rgba(16,185,129,0.08)' : log.fixed
                  ? 'rgba(139,92,246,0.08)' : 'rgba(245,158,11,0.08)',
                borderColor: log.allClear
                  ? 'rgba(16,185,129,0.25)' : log.fixed
                  ? 'rgba(139,92,246,0.2)' : 'rgba(245,158,11,0.2)',
              }}
            >
              {/* Top accent line */}
              <div style={{
                position: 'absolute', top: 0, left: 0, right: 0, height: 1,
                background: log.allClear
                  ? 'linear-gradient(90deg, transparent, rgba(16,185,129,0.6), transparent)'
                  : log.fixed
                  ? 'linear-gradient(90deg, transparent, rgba(139,92,246,0.6), transparent)'
                  : 'linear-gradient(90deg, transparent, rgba(245,158,11,0.6), transparent)',
              }} />
              <div className="flex items-center gap-1.5 mb-1">
                {(log.allClear && log.fixed)
                  ? <CheckCircle size={10} style={{ color: '#34d399', filter: 'drop-shadow(0 0 3px rgba(52,211,153,0.6))' }} />
                  : log.fixed
                  ? <Zap size={10} style={{ color: '#a78bfa', filter: 'drop-shadow(0 0 3px rgba(167,139,250,0.6))' }} />
                  : log.allClear
                  ? <CheckCircle size={10} style={{ color: '#64748b' }} />
                  : <AlertTriangle size={10} style={{ color: '#fbbf24', filter: 'drop-shadow(0 0 3px rgba(251,191,36,0.6))' }} />}
                <span style={{ color: log.fixed ? '#c4b5fd' : log.allClear ? '#94a3b8' : '#fcd34d', fontWeight: 600 }}>
                  Pass {log.pass}
                </span>
                {log.allClear && log.fixed && <span style={{ color: '#34d399' }}> — Patched & clean</span>}
                {log.fixed && !log.allClear && <span style={{ color: '#a78bfa' }}> — Patched</span>}
                {log.allClear && !log.fixed && <span style={{ color: '#94a3b8' }}> — No issues found</span>}
                {!log.fixed && !log.allClear && <span style={{ color: '#fbbf24' }}> — No output</span>}
              </div>
              <div className="text-slate-500 line-clamp-2">
                {log.text.replace(/```html[\s\S]*?```/g, '[fixed code]').slice(0, 200)}
              </div>
            </div>
          ))}

          {/* Live streaming of current pass */}
          {fixing && (
            <div
              className="rounded-lg p-2 text-[10px] font-mono text-slate-400 max-h-28 overflow-hidden relative"
              style={{
                background: '#0d0f1e',
                border: '1px solid',
                animation: 'ma-border-pulse 1.8s ease-in-out infinite',
              }}
            >
              {/* Shimmer overlay */}
              <div className="ma-shimmer absolute inset-0 rounded-lg pointer-events-none" />
              <div className="relative" style={{ zIndex: 1 }}>
                <div className="flex items-center gap-1.5 mb-1.5">
                  <div style={{
                    width: 5, height: 5, borderRadius: '50%',
                    background: '#818cf8',
                    boxShadow: '0 0 8px rgba(129,140,248,0.9)',
                    animation: 'ma-blink 1s ease-in-out infinite',
                  }} />
                  <span className="text-[9px] uppercase tracking-widest" style={{ color: '#818cf8' }}>
                    {liveToken ? 'Analysing' : 'Scanning errors…'}
                  </span>
                </div>
                <div className={`line-clamp-4 whitespace-pre-wrap leading-relaxed ${liveToken ? 'ma-cursor' : ''}`} style={{ color: '#94a3b8' }}>
                  {liveToken
                    ? liveToken.replace(/```html[\s\S]*/g, '[writing fix…]').slice(0, 400)
                    : '…'}
                </div>
              </div>
            </div>
          )}

          {/* Error list */}
          {iframeErrors.length > 0 && (
            <div
              className="rounded-lg p-2 text-[9px] font-mono space-y-0.5"
              style={{
                background: 'rgba(239,68,68,0.05)',
                border: '1px solid',
                animation: fixing ? 'ma-err-pulse 1.8s ease-in-out infinite' : undefined,
                borderColor: 'rgba(239,68,68,0.25)',
                color: '#f87171',
              }}
            >
              <div className="flex items-center gap-1.5 mb-1" style={{ color: 'rgba(239,68,68,0.6)' }}>
                <div style={{
                  width: 4, height: 4, borderRadius: '50%',
                  background: '#ef4444',
                  boxShadow: fixing ? '0 0 6px rgba(239,68,68,0.8)' : undefined,
                  animation: fixing ? 'ma-blink 1s step-end infinite' : undefined,
                }} />
                <span className="uppercase tracking-widest">Live JS Errors</span>
                <span className="ml-auto px-1 rounded-full" style={{ background: 'rgba(239,68,68,0.15)', color: '#f87171' }}>
                  {iframeErrors.length}
                </span>
              </div>
              {iframeErrors.slice(0, 5).map((e, i) => (
                <div key={i} className="truncate opacity-80">{e}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* iframe */}
      <iframe
        key={key}
        ref={iframeRef}
        srcDoc={srcDoc}
        className="flex-1 w-full bg-white"
        sandbox="allow-scripts allow-same-origin allow-modals allow-pointer-lock allow-forms"
        title="App Preview"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Files pane
// ---------------------------------------------------------------------------
function FilesPane({ blocks }) {
  const files = useMemo(() => {
    const exts = { html: 'index.html', css: 'styles.css', javascript: 'script.js', js: 'script.js', python: 'main.py', typescript: 'index.ts', ts: 'index.ts' };
    return blocks.map((b, i) => ({
      name: exts[b.lang] || `file_${i + 1}.${b.lang}`,
      lang: b.lang,
      code: b.code,
      size: b.code.length,
    }));
  }, [blocks]);

  const langColor = { html: 'text-orange-400', css: 'text-blue-400', javascript: 'text-yellow-400', js: 'text-yellow-400', python: 'text-green-400', typescript: 'text-cyan-400', ts: 'text-cyan-400' };

  const handleDownload = useCallback((f) => {
    const mimeMap = { html: 'text/html', css: 'text/css', javascript: 'text/javascript', js: 'text/javascript', python: 'text/x-python', typescript: 'text/typescript', ts: 'text/typescript' };
    const mime = mimeMap[f.lang] || 'text/plain';
    const blob = new Blob([f.code], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = f.name;
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  if (files.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3">
        <FolderOpen size={32} strokeWidth={1} />
        <p className="text-xs text-center">No files yet.</p>
      </div>
    );
  }

  return (
    <div className="p-3 space-y-1">
      <div className="flex items-center gap-1.5 px-1 py-1 mb-2">
        <ChevronRight size={11} className="text-slate-600" />
        <FolderOpen size={12} className="text-amber-500/60" />
        <span className="text-[11px] text-slate-500">project</span>
      </div>
      {files.map((f, i) => (
        <div key={i} className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-white/5 transition-colors group">
          <File size={12} className={langColor[f.lang] || 'text-slate-500'} />
          <span className="flex-1 text-xs text-slate-400 truncate">{f.name}</span>
          <span className="text-[10px] text-slate-600">{(f.size / 1024).toFixed(1)}k</span>
          <button
            onClick={() => handleDownload(f)}
            title={`Download ${f.name}`}
            className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded hover:text-slate-300 text-slate-600"
          >
            <Download size={10} />
          </button>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tasks pane
// ---------------------------------------------------------------------------
function TasksPane() {
  const { tasks, addTask, toggleTask, deleteTask } = useApp();
  const [input, setInput] = useState('');

  const handleAdd = useCallback(() => {
    const text = input.trim();
    if (!text) return;
    addTask(text);
    setInput('');
  }, [input, addTask]);

  const handleKey = useCallback((e) => {
    if (e.key === 'Enter') handleAdd();
  }, [handleAdd]);

  const done = tasks.filter(t => t.done);
  const pending = tasks.filter(t => !t.done);

  return (
    <div className="flex flex-col h-full">
      {/* Input */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-white/5">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Add a task…"
          className="flex-1 text-xs bg-transparent text-slate-300 placeholder:text-slate-600 outline-none"
        />
        <button
          onClick={handleAdd}
          disabled={!input.trim()}
          className="p-1 rounded hover:bg-white/5 text-slate-600 hover:text-cyan-400 disabled:opacity-30 transition-colors"
        >
          <Plus size={13} />
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
        {tasks.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3 py-8">
            <ListTodo size={28} strokeWidth={1} />
            <p className="text-xs text-center">No tasks yet.</p>
          </div>
        )}
        {pending.map(t => (
          <div key={t.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-white/5 group">
            <button onClick={() => toggleTask(t.id)} className="flex-shrink-0 text-slate-600 hover:text-cyan-400 transition-colors">
              <Square size={13} />
            </button>
            <span className="flex-1 text-xs text-slate-300 leading-snug">{t.text}</span>
            <button onClick={() => deleteTask(t.id)} className="opacity-0 group-hover:opacity-100 flex-shrink-0 text-slate-700 hover:text-red-400 transition-colors">
              <Trash2 size={11} />
            </button>
          </div>
        ))}
        {done.length > 0 && (
          <>
            <div className="px-2 py-1 mt-2">
              <span className="text-[10px] font-mono text-slate-600 uppercase tracking-widest">Done ({done.length})</span>
            </div>
            {done.map(t => (
              <div key={t.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-white/5 group opacity-50">
                <button onClick={() => toggleTask(t.id)} className="flex-shrink-0 text-emerald-500/60 hover:text-emerald-400 transition-colors">
                  <CheckSquare size={13} />
                </button>
                <span className="flex-1 text-xs text-slate-500 line-through leading-snug">{t.text}</span>
                <button onClick={() => deleteTask(t.id)} className="opacity-0 group-hover:opacity-100 flex-shrink-0 text-slate-700 hover:text-red-400 transition-colors">
                  <Trash2 size={11} />
                </button>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Diff pane — LCS-based line diff between previous and current code blocks
// ---------------------------------------------------------------------------
function computeDiff(oldLines, newLines) {
  // Build LCS table
  const m = oldLines.length, n = newLines.length;
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--)
    for (let j = n - 1; j >= 0; j--)
      dp[i][j] = oldLines[i] === newLines[j] ? 1 + dp[i + 1][j + 1] : Math.max(dp[i + 1][j], dp[i][j + 1]);

  // Backtrack
  const diff = []; let i = 0, j = 0;
  while (i < m || j < n) {
    if (i < m && j < n && oldLines[i] === newLines[j]) {
      diff.push({ type: 'same', line: oldLines[i] }); i++; j++;
    } else if (j < n && (i >= m || dp[i][j + 1] >= dp[i + 1][j])) {
      diff.push({ type: 'add', line: newLines[j] }); j++;
    } else {
      diff.push({ type: 'remove', line: oldLines[i] }); i++;
    }
  }
  return diff;
}

function DiffPane({ messages }) {
  // Find last two assistant messages with code blocks
  const [blockA, blockB] = useMemo(() => {
    const withCode = [];
    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i];
      if (msg.role !== 'assistant') continue;
      const blocks = msg.content ? (() => {
        const re = /```([a-zA-Z0-9_+-]*)[ \t]*\r?\n([\s\S]*?)```/g;
        const b = []; let m;
        while ((m = re.exec(msg.content)) !== null) { const code = m[2].trim(); if (code) b.push(code); }
        return b;
      })() : [];
      if (blocks.length > 0) withCode.push(blocks[0]);
    }
    if (withCode.length >= 2) return [withCode[withCode.length - 2], withCode[withCode.length - 1]];
    if (withCode.length === 1) return ['', withCode[0]];
    return ['', ''];
  }, [messages]);

  if (!blockB) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3">
        <Diff size={32} strokeWidth={1} />
        <p className="text-xs text-center">No code versions to diff yet.</p>
      </div>
    );
  }

  const diff = computeDiff(blockA.split('\n'), blockB.split('\n'));
  const hasChanges = diff.some(d => d.type !== 'same');

  if (!hasChanges) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3">
        <Diff size={32} strokeWidth={1} />
        <p className="text-xs text-center">No changes between versions.</p>
      </div>
    );
  }

  return (
    <pre className="h-full overflow-auto p-3 text-[11px] font-mono leading-5">
      {diff.map((d, i) => (
        <div
          key={i}
          className={
            d.type === 'add'    ? 'bg-emerald-500/10 text-emerald-400' :
            d.type === 'remove' ? 'bg-red-500/10 text-red-400' :
            'text-slate-600'
          }
        >
          <span className="select-none mr-2 w-4 inline-block text-right">
            {d.type === 'add' ? '+' : d.type === 'remove' ? '−' : ' '}
          </span>
          {d.line}
        </div>
      ))}
    </pre>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
const TABS = [
  { id: 'preview', label: 'Preview', icon: Monitor },
  { id: 'code',    label: 'Code',    icon: Code2 },
  { id: 'files',   label: 'Files',   icon: FolderOpen },
  { id: 'diff',    label: 'Diff',    icon: Diff },
  { id: 'tasks',   label: 'Tasks',   icon: ListTodo },
];

function RightPanel({ messages = [], streamingText = null, open, onClose, previewImage = null, onClearImage, activeTab = null, sessionId = null, onFixedHtml = null }) {
  const [tab, setTab] = useState('preview');
  const { isSubscribed } = useApp();
  const codeBlocks = useMemo(() => getLatestCode(messages, streamingText), [messages, streamingText]);

  // Auto-switch to preview when a new image arrives
  useEffect(() => {
    if (previewImage) setTab('preview');
  }, [previewImage]);

  // Allow parent to force a tab
  useEffect(() => {
    if (activeTab) setTab(activeTab);
  }, [activeTab]);

  // Free users can only see Preview and Tasks
  const CODE_TABS = new Set(['code', 'files', 'diff']);
  const visibleTabs = isSubscribed ? TABS : TABS.filter(t => !CODE_TABS.has(t.id));

  // If free user somehow ends up on a locked tab, bounce to preview
  useEffect(() => {
    if (!isSubscribed && CODE_TABS.has(tab)) setTab('preview');
  }, [isSubscribed, tab]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null;

  return (
    <div className="flex flex-col w-[340px] flex-shrink-0 border-l border-white/[0.06] bg-[#0b0d16] overflow-hidden">
      {/* Header */}
      <div className="flex items-center h-10 px-2 border-b border-white/[0.06] flex-shrink-0">
        <div className="flex items-center gap-0.5 flex-1 overflow-x-auto">
          {visibleTabs.map(t => (
            <TabBtn key={t.id} {...t} active={tab === t.id} onClick={setTab} />
          ))}
          {/* Lock badge — shown to free users so they know code tabs exist */}
          {!isSubscribed && (
            <span className="ml-1 px-1.5 py-0.5 rounded text-[9px] text-amber-400/70 border border-amber-400/20 bg-amber-400/5 font-mono flex-shrink-0">
              PRO
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-red-500/20 text-slate-500 hover:text-red-400 transition-colors flex-shrink-0 ml-1"
          title="Close preview"
        >
          <X size={14} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-hidden">
        {tab === 'preview' && <PreviewPane blocks={codeBlocks} previewImage={previewImage} onClearImage={onClearImage} isStreaming={!!streamingText} sessionId={sessionId} onFixedHtml={onFixedHtml} />}
        {tab === 'code'    && isSubscribed && <CodeViewer  blocks={codeBlocks} />}
        {tab === 'files'   && isSubscribed && <FilesPane   blocks={codeBlocks} />}
        {tab === 'diff'    && isSubscribed && <DiffPane    messages={messages} />}
        {tab === 'tasks'   && <TasksPane />}
      </div>
    </div>
  );
}

export default RightPanel;
