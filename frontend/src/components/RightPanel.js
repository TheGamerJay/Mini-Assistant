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
} from 'lucide-react';
import { useApp } from '../context/AppContext';

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

/** Find the latest code — live stream first, then last completed assistant message */
function getLatestCode(messages, streamingText) {
  // Live stream takes priority — extract as tokens arrive
  if (streamingText) {
    const liveBlocks = extractCodeBlocks(streamingText);
    if (liveBlocks.length > 0) return liveBlocks;
  }
  // Fall back to last completed assistant message with code
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg.role !== 'assistant') continue;
    const blocks = extractCodeBlocks(msg.content);
    if (blocks.length > 0) return blocks;
  }
  return [];
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
function PreviewPane({ blocks, previewImage = null, imageSaved = false }) {
  const iframeRef = useRef(null);
  const [key, setKey] = useState(0);
  const html = useMemo(() => buildPreviewHtml(blocks), [blocks]);

  // Show "Saved" badge briefly after a new image arrives
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

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe || !html || previewImage) return;
    const doc = iframe.contentDocument || iframe.contentWindow?.document;
    if (!doc) return;
    doc.open();
    doc.write(html);
    doc.close();
  }, [html, key, previewImage]);

  // Show generated image if present (image generation takes priority over empty code preview)
  if (previewImage) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-white/5 bg-[#0f111a]">
          <div className="flex items-center gap-1.5 flex-1 px-2 py-1 rounded bg-white/5 text-[10px] text-slate-600 font-mono">
            <Monitor size={9} />
            generated image
          </div>
          <a
            href={`data:image/png;base64,${previewImage}`}
            download="generated.png"
            className="p-1 rounded hover:bg-white/5 text-slate-600 hover:text-slate-400 transition-colors"
            title="Download image"
          >
            <Download size={12} />
          </a>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center p-4 overflow-auto gap-3">
          <img
            src={`data:image/png;base64,${previewImage}`}
            alt="Generated"
            className="max-w-full max-h-[85%] object-contain rounded-lg shadow-xl"
          />
          {showSaved && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 animate-fade-in">
              <CheckSquare size={11} className="text-emerald-400 flex-shrink-0" />
              <span className="text-[10px] text-emerald-400 font-medium">Saved to your library</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (!html) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3">
        <Monitor size={32} strokeWidth={1} />
        <p className="text-xs text-center">Preview will appear here<br />when code is generated.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-white/5 bg-[#0f111a]">
        <div className="flex items-center gap-1.5 flex-1 px-2 py-1 rounded bg-white/5 text-[10px] text-slate-600 font-mono">
          <Monitor size={9} />
          preview
        </div>
        <button
          onClick={() => setKey(k => k + 1)}
          className="p-1 rounded hover:bg-white/5 text-slate-600 hover:text-slate-400 transition-colors"
          title="Refresh preview"
        >
          <RefreshCw size={12} />
        </button>
      </div>
      <iframe
        ref={iframeRef}
        key={key}
        className="flex-1 w-full bg-white"
        sandbox="allow-scripts allow-same-origin"
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

function RightPanel({ messages = [], streamingText = null, open, onClose, previewImage = null, activeTab = null }) {
  const [tab, setTab] = useState('preview');
  const codeBlocks = useMemo(() => getLatestCode(messages, streamingText), [messages, streamingText]);

  // Auto-switch to preview when a new image arrives
  useEffect(() => {
    if (previewImage) setTab('preview');
  }, [previewImage]);

  // Allow parent to force a tab
  useEffect(() => {
    if (activeTab) setTab(activeTab);
  }, [activeTab]);

  if (!open) return null;

  return (
    <div className="flex flex-col w-[340px] flex-shrink-0 border-l border-white/[0.06] bg-[#0b0d16] overflow-hidden">
      {/* Header */}
      <div className="flex items-center h-10 px-2 border-b border-white/[0.06] flex-shrink-0">
        <div className="flex items-center gap-0.5 flex-1 overflow-x-auto">
          {TABS.map(t => (
            <TabBtn key={t.id} {...t} active={tab === t.id} onClick={setTab} />
          ))}
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
        {tab === 'preview' && <PreviewPane blocks={codeBlocks} previewImage={previewImage} />}
        {tab === 'code'    && <CodeViewer  blocks={codeBlocks} />}
        {tab === 'files'   && <FilesPane   blocks={codeBlocks} />}
        {tab === 'diff'    && <DiffPane    messages={messages} />}
        {tab === 'tasks'   && <TasksPane />}
      </div>
    </div>
  );
}

export default RightPanel;
