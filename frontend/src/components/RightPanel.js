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

import React, { useState, useMemo, useRef, useEffect } from 'react';
import {
  Monitor, Code2, FolderOpen, FileText, X, RefreshCw,
  Maximize2, ChevronRight, File, Download,
} from 'lucide-react';

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

/** Find the last assistant message that contains code */
function getLatestCode(messages) {
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
function PreviewPane({ blocks }) {
  const iframeRef = useRef(null);
  const [key, setKey] = useState(0);
  const html = useMemo(() => buildPreviewHtml(blocks), [blocks]);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe || !html) return;
    const doc = iframe.contentDocument || iframe.contentWindow?.document;
    if (!doc) return;
    doc.open();
    doc.write(html);
    doc.close();
  }, [html, key]);

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
      size: b.code.length,
    }));
  }, [blocks]);

  const langColor = { html: 'text-orange-400', css: 'text-blue-400', javascript: 'text-yellow-400', js: 'text-yellow-400', python: 'text-green-400', typescript: 'text-cyan-400', ts: 'text-cyan-400' };

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
        <div key={i} className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-white/5 cursor-pointer transition-colors group">
          <File size={12} className={langColor[f.lang] || 'text-slate-500'} />
          <span className="flex-1 text-xs text-slate-400 truncate">{f.name}</span>
          <span className="text-[10px] text-slate-600">{(f.size / 1024).toFixed(1)}k</span>
          <Download size={10} className="text-slate-600 opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
const TABS = [
  { id: 'preview', label: 'Preview', icon: Monitor },
  { id: 'code',    label: 'Code',    icon: Code2 },
  { id: 'files',   label: 'Files',   icon: FolderOpen },
];

function RightPanel({ messages = [], open, onClose }) {
  const [tab, setTab] = useState('preview');
  const codeBlocks = useMemo(() => getLatestCode(messages), [messages]);

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
          className="p-1 rounded hover:bg-white/5 text-slate-600 hover:text-slate-400 transition-colors flex-shrink-0 ml-1"
          title="Close panel"
        >
          <X size={13} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-hidden">
        {tab === 'preview' && <PreviewPane blocks={codeBlocks} />}
        {tab === 'code'    && <CodeViewer  blocks={codeBlocks} />}
        {tab === 'files'   && <FilesPane   blocks={codeBlocks} />}
      </div>
    </div>
  );
}

export default RightPanel;
