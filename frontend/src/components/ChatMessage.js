/**
 * components/ChatMessage.js
 * Renders a single chat message bubble (user or assistant).
 * Props: { message, onRetry?, onRate?, onFork? }
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  RotateCcw, Copy, Check, Volume2, VolumeX,
  ThumbsUp, ThumbsDown, GitFork, Share2, MoreHorizontal, Clock, X, ChevronLeft, ChevronRight,
  Bookmark, PanelRight, Play, Loader2, Terminal, Monitor,
} from 'lucide-react';
import { toast } from 'sonner';
import { useApp } from '../context/AppContext';
import { api } from '../api/client';
import AvatarMedia from './AvatarMedia';
import ImageCard from './ImageCard';
import IntelligencePanel from './IntelligencePanel';

// ---------------------------------------------------------------------------
// Lightweight syntax tokenizer (no external deps)
// ---------------------------------------------------------------------------
const KEYWORDS = {
  js:     ['const','let','var','function','return','if','else','for','while','do','class','new','this','typeof','import','export','default','from','async','await','try','catch','finally','throw','of','in','true','false','null','undefined','switch','case','break','continue','extends','super','static','get','set','delete','void','yield'],
  ts:     ['const','let','var','function','return','if','else','for','while','do','class','new','this','typeof','import','export','default','from','async','await','try','catch','finally','throw','of','in','true','false','null','undefined','switch','case','break','continue','extends','super','static','get','set','delete','void','yield','type','interface','enum','namespace','as','keyof','readonly','abstract','implements','declare','any','never','unknown','string','number','boolean','object'],
  python: ['def','class','return','if','elif','else','for','while','import','from','as','try','except','finally','raise','with','yield','lambda','pass','break','continue','in','is','not','and','or','True','False','None','async','await','self','print','len','range','type','list','dict','set','tuple','str','int','float','bool'],
  go:     ['func','var','const','type','package','import','return','if','else','for','range','switch','case','default','break','continue','go','defer','select','chan','map','struct','interface','nil','true','false','error','string','int','int64','float64','bool','byte','rune','make','new','append','len','cap','close','panic','recover'],
  rust:   ['fn','let','mut','const','struct','enum','impl','trait','use','mod','pub','priv','return','if','else','match','for','while','loop','break','continue','in','as','ref','move','async','await','dyn','where','type','true','false','None','Some','Ok','Err','self','Self','super','crate','Box','Vec','String','Option','Result'],
  java:   ['class','interface','extends','implements','new','return','if','else','for','while','do','switch','case','break','continue','import','package','public','private','protected','static','final','void','try','catch','finally','throw','throws','this','super','null','true','false','int','long','double','float','boolean','char','byte','short','String'],
  bash:   ['if','then','else','fi','for','do','done','while','case','esac','function','return','exit','echo','export','local','readonly','source','alias','cd','ls','grep','awk','sed'],
  sql:    ['SELECT','FROM','WHERE','JOIN','ON','GROUP','BY','ORDER','HAVING','INSERT','INTO','VALUES','UPDATE','SET','DELETE','CREATE','TABLE','INDEX','DROP','ALTER','ADD','COLUMN','PRIMARY','KEY','FOREIGN','REFERENCES','NOT','NULL','UNIQUE','DEFAULT','AND','OR','IN','IS','LIKE','BETWEEN','EXISTS','AS','DISTINCT','LIMIT','OFFSET','UNION','ALL'],
};

function tokenizeLine(line, keywords, lang) {
  if (!line) return [{ t: '', cls: '' }];
  if (lang === 'css' || lang === 'html' || lang === 'markup') return [{ t: line, cls: 'text-slate-300' }];

  const tokens = [];
  let i = 0;
  const commentPrefix = (lang === 'python' || lang === 'bash' || lang === 'yaml') ? '#' : (lang === 'sql') ? '--' : '//';

  while (i < line.length) {
    if (line.slice(i, i + commentPrefix.length) === commentPrefix) {
      tokens.push({ t: line.slice(i), cls: 'text-slate-500 italic' });
      break;
    }
    if (line[i] === '"' || line[i] === "'" || line[i] === '`') {
      const q = line[i]; let j = i + 1;
      while (j < line.length && line[j] !== q) { if (line[j] === '\\') j++; j++; }
      tokens.push({ t: line.slice(i, j + 1), cls: 'text-amber-300' });
      i = j + 1; continue;
    }
    if (/[0-9]/.test(line[i]) && (i === 0 || /\W/.test(line[i - 1]))) {
      let j = i;
      while (j < line.length && /[0-9._xXa-fA-FbBoO]/.test(line[j])) j++;
      tokens.push({ t: line.slice(i, j), cls: 'text-purple-300' });
      i = j; continue;
    }
    if (/[a-zA-Z_$]/.test(line[i])) {
      let j = i;
      while (j < line.length && /[a-zA-Z0-9_$]/.test(line[j])) j++;
      const word = line.slice(i, j);
      const kw = lang === 'sql' ? keywords.includes(word.toUpperCase()) : keywords.includes(word);
      const isPascal = /^[A-Z][a-zA-Z0-9]*$/.test(word);
      tokens.push({ t: word, cls: kw ? 'text-cyan-300 font-medium' : isPascal ? 'text-emerald-300' : 'text-slate-200' });
      i = j; continue;
    }
    tokens.push({ t: line[i], cls: 'text-slate-400' });
    i++;
  }
  return tokens;
}

function tokenize(code, lang) {
  const l = (lang || '').toLowerCase();
  const kws = KEYWORDS[l] || KEYWORDS['js'];
  return code.split('\n').map((line, idx) => ({ idx, tokens: tokenizeLine(line, kws, l) }));
}

// ---------------------------------------------------------------------------
// AppBuilderCard — compact badge replacing full HTML code in chat
// ---------------------------------------------------------------------------
function AppBuilderCard({ code }) {
  const [copied, setCopied] = useState(false);
  const { isSubscribed } = useApp();
  const lineCount = code.split('\n').length;
  return (
    <div className="my-3 rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-4 py-3 flex items-center gap-3">
      <Monitor size={15} className="text-cyan-400 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-cyan-300 font-medium">App built</p>
        <p className="text-[10px] text-slate-500 mt-0.5">{lineCount} lines · open the Preview tab →</p>
      </div>
      {isSubscribed ? (
        <button
          onClick={() => { navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 1800); }}
          className="flex items-center gap-1 text-[10px] font-mono text-slate-500 hover:text-slate-300 transition-colors"
          title="Copy code"
        >
          {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      ) : (
        <span className="text-[9px] text-amber-400/60 border border-amber-400/20 bg-amber-400/5 px-1.5 py-0.5 rounded font-mono">PRO</span>
      )}
    </div>
  );
}

// CodeBlock
// ---------------------------------------------------------------------------
const RUNNABLE_LANGS = new Set(['python', 'py', 'javascript', 'js']);

function CodeBlock({ lang, code }) {
  const [copied, setCopied] = useState(false);
  const [running, setRunning] = useState(false);
  const [execResult, setExecResult] = useState(null); // { output, error, exit_code }

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); }).catch(() => {});
  }, [code]);

  const normalizedLang = (lang || '').toLowerCase() === 'py' ? 'python' : (lang || '').toLowerCase();
  const canRun = RUNNABLE_LANGS.has((lang || '').toLowerCase());

  const handleRun = useCallback(async () => {
    setRunning(true);
    setExecResult(null);
    try {
      const res = await api.executeCode(code, normalizedLang);
      setExecResult(res);
    } catch (err) {
      setExecResult({ output: '', error: String(err), exit_code: 1 });
    } finally {
      setRunning(false);
    }
  }, [code, normalizedLang]);

  const lines = tokenize(code, lang);
  return (
    <div className="my-3 rounded-xl overflow-hidden border border-white/10 bg-[#0d0f1a]">
      <div className="flex items-center justify-between px-4 py-2 bg-white/[0.04] border-b border-white/[0.06]">
        <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">{lang || 'code'}</span>
        <div className="flex items-center gap-2">
          {canRun && (
            <button
              onClick={handleRun}
              disabled={running}
              className="flex items-center gap-1 text-[10px] font-mono text-emerald-500 hover:text-emerald-300 disabled:opacity-50 transition-colors"
            >
              {running ? <Loader2 size={10} className="animate-spin" /> : <Play size={10} />}
              {running ? 'Running…' : 'Run'}
            </button>
          )}
          <button onClick={handleCopy} className="flex items-center gap-1.5 text-[10px] font-mono text-slate-500 hover:text-slate-300 transition-colors">
            {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      </div>
      <pre className="overflow-x-auto px-4 py-3 text-[12px] leading-[1.7]">
        {lines.map(({ idx, tokens }) => (
          <div key={idx} className="table-row">
            <span className="table-cell select-none text-slate-600 text-right pr-4 w-8 text-[11px]">{idx + 1}</span>
            <span className="table-cell">{tokens.map((tok, ti) => <span key={ti} className={tok.cls}>{tok.t}</span>)}</span>
          </div>
        ))}
      </pre>
      {execResult && (
        <div className="border-t border-white/[0.06] bg-black/30">
          <div className="flex items-center gap-1.5 px-4 py-1.5 border-b border-white/[0.04]">
            <Terminal size={10} className={execResult.exit_code === 0 ? 'text-emerald-500' : 'text-red-500'} />
            <span className={`text-[10px] font-mono ${execResult.exit_code === 0 ? 'text-emerald-500' : 'text-red-500'}`}>
              {execResult.exit_code === 0 ? 'Output' : `Error (exit ${execResult.exit_code})`}
            </span>
            <button onClick={() => setExecResult(null)} className="ml-auto text-slate-600 hover:text-slate-400 transition-colors">
              <X size={10} />
            </button>
          </div>
          <pre className="px-4 py-3 text-[11px] font-mono overflow-x-auto whitespace-pre-wrap">
            {execResult.output && <span className="text-slate-300">{execResult.output}</span>}
            {execResult.error && <span className="text-red-400">{execResult.error}</span>}
            {!execResult.output && !execResult.error && <span className="text-slate-600">(no output)</span>}
          </pre>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline markdown renderer
// ---------------------------------------------------------------------------
function renderInline(text) {
  const pattern = /(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^\)]+)\)|(https?:\/\/[^\s]+))/g;
  const parts = []; let lastIdx = 0; let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIdx) parts.push(text.slice(lastIdx, match.index));
    if (match[2]) parts.push(<strong key={match.index} className="font-semibold text-slate-100">{match[2]}</strong>);
    else if (match[3]) parts.push(<em key={match.index} className="italic text-slate-300">{match[3]}</em>);
    else if (match[4]) parts.push(<code key={match.index} className="font-mono text-[12px] bg-cyan-500/10 text-cyan-300 px-1.5 py-0.5 rounded">{match[4]}</code>);
    else if (match[5] && match[6]) parts.push(<a key={match.index} href={match[6]} target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2 transition-colors">{match[5]}</a>);
    else if (match[7]) parts.push(<a key={match.index} href={match[7]} target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2 transition-colors break-all">{match[7]}</a>);
    lastIdx = match.index + match[0].length;
  }
  if (lastIdx < text.length) parts.push(text.slice(lastIdx));
  return parts.length ? parts : text;
}

// ---------------------------------------------------------------------------
// Text renderer: headings, lists, paragraphs
// ---------------------------------------------------------------------------
function renderText(text) {
  if (!text) return null;
  const lines = text.split('\n');
  const out = []; let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { out.push(<div key={i} className="h-2" />); i++; continue; }
    const hm = line.match(/^(#{1,3})\s+(.+)$/);
    if (hm) {
      const level = hm[1].length;
      const cls = level === 1 ? 'text-base font-bold text-slate-100 mt-3 mb-1' : level === 2 ? 'text-sm font-semibold text-slate-200 mt-2 mb-0.5' : 'text-sm font-medium text-slate-300 mt-1.5';
      out.push(<p key={i} className={cls}>{renderInline(hm[2])}</p>); i++; continue;
    }
    if (/^[-*•]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^[-*•]\s+/.test(lines[i])) { items.push(lines[i].replace(/^[-*•]\s+/, '')); i++; }
      out.push(<ul key={`ul-${i}`} className="my-1.5 ml-4 space-y-0.5 list-none">{items.map((item, ii) => (<li key={ii} className="flex items-start gap-2 text-slate-300"><span className="text-cyan-500 mt-1 flex-shrink-0 text-[8px]">▸</span><span>{renderInline(item)}</span></li>))}</ul>);
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const items = []; let num = 1;
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) { items.push({ n: num++, text: lines[i].replace(/^\d+\.\s+/, '') }); i++; }
      out.push(<ol key={`ol-${i}`} className="my-1.5 ml-4 space-y-0.5 list-none">{items.map((item) => (<li key={item.n} className="flex items-start gap-2 text-slate-300"><span className="text-cyan-500/70 font-mono text-[11px] flex-shrink-0 mt-0.5 w-4 text-right">{item.n}.</span><span>{renderInline(item.text)}</span></li>))}</ol>);
      continue;
    }
    out.push(<span key={i}>{renderInline(line)}{i < lines.length - 1 && lines[i + 1] && !/^[-*•\d#]/.test(lines[i + 1]) && <br />}</span>);
    i++;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Top-level content renderer: splits out fenced code blocks first
// ---------------------------------------------------------------------------
function renderContent(text) {
  if (!text) return null;
  const fenceRe = /```([^\n]*)\n([\s\S]*?)```/g;
  const parts = []; let lastIdx = 0; let match; let key = 0;
  while ((match = fenceRe.exec(text)) !== null) {
    if (match.index > lastIdx) parts.push(<React.Fragment key={key++}>{renderText(text.slice(lastIdx, match.index))}</React.Fragment>);
    const lang = (match[1] || '').trim();
    const code = match[2].replace(/\n$/, '');
    // Large HTML apps → compact card; everything else → full code block
    const isHtmlApp = (lang === 'html' || lang === 'markup' || lang === '') && /<!DOCTYPE|<html/i.test(code) && code.length > 200;
    parts.push(isHtmlApp ? <AppBuilderCard key={key++} code={code} /> : <CodeBlock key={key++} lang={lang} code={code} />);
    lastIdx = match.index + match[0].length;
  }
  if (lastIdx < text.length) parts.push(<React.Fragment key={key++}>{renderText(text.slice(lastIdx))}</React.Fragment>);
  return parts.length ? parts : renderText(text);
}

// ---------------------------------------------------------------------------
// Shared small action button
// ---------------------------------------------------------------------------
function ActionBtn({ onClick, title, active, activeClass, children }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={`p-1.5 rounded-lg transition-colors hover:bg-white/5
        ${active && activeClass ? activeClass : 'text-slate-600 hover:text-slate-300'}`}
    >
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Bottom message action bar  (copy · thumbs · speaker · share · ⋯)
// ---------------------------------------------------------------------------
function MessageActions({ content, rating, onRate, onRetry, onFork, onPin, onSendToBuilder, pinned, timestamp }) {
  const [speaking, setSpeaking]   = useState(false);
  const [copied, setCopied]       = useState(false);
  const [menuOpen, setMenuOpen]   = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [menuOpen]);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(content)
      .then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); })
      .catch(() => {});
  }, [content]);

  const [sharing, setSharing] = useState(false);
  const handleShare = useCallback(async () => {
    if (sharing) return;
    setSharing(true);
    try {
      const result = await api.createShare('text', content, '', '');
      await navigator.clipboard.writeText(result.url);
      toast.success('Share link copied!', { description: result.url });
    } catch (err) {
      toast.error('Could not create share link');
    } finally {
      setSharing(false);
    }
  }, [content, sharing]);

  const handleTTS = useCallback(() => {
    if (speaking) { window.speechSynthesis.cancel(); setSpeaking(false); return; }
    const utt = new SpeechSynthesisUtterance(content);
    utt.onend  = () => setSpeaking(false);
    utt.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(utt);
    setSpeaking(true);
  }, [speaking, content]);

  const timeLabel = timestamp
    ? new Date(timestamp).toLocaleString([], {
        weekday: 'short', month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    : null;

  return (
    <div className="flex items-center gap-0.5 mt-3 pt-2 border-t border-white/5">
      {/* Copy */}
      <ActionBtn onClick={handleCopy} title={copied ? 'Copied!' : 'Copy message'} active={copied} activeClass="text-emerald-400">
        {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
      </ActionBtn>

      {/* Thumbs up */}
      <ActionBtn
        onClick={() => onRate && onRate(rating === 1 ? null : 1)}
        title="Good response"
        active={rating === 1}
        activeClass="text-emerald-400"
      >
        <ThumbsUp size={12} className={rating === 1 ? 'text-emerald-400' : ''} />
      </ActionBtn>

      {/* Thumbs down */}
      <ActionBtn
        onClick={() => onRate && onRate(rating === -1 ? null : -1)}
        title="Poor response"
        active={rating === -1}
        activeClass="text-red-400"
      >
        <ThumbsDown size={12} className={rating === -1 ? 'text-red-400' : ''} />
      </ActionBtn>

      {/* Speaker / TTS */}
      {'speechSynthesis' in window && (
        <ActionBtn onClick={handleTTS} title={speaking ? 'Stop reading' : 'Read aloud'} active={speaking} activeClass="text-cyan-400">
          {speaking ? <VolumeX size={12} className="text-cyan-400" /> : <Volume2 size={12} />}
        </ActionBtn>
      )}

      {/* Share — create public link */}
      <ActionBtn onClick={handleShare} title="Create share link" active={sharing} activeClass="text-violet-400">
        {sharing ? <Loader2 size={12} className="animate-spin" /> : <Share2 size={12} />}
      </ActionBtn>

      {/* Pin message */}
      {onPin && (
        <ActionBtn onClick={onPin} title={pinned ? 'Unpin message' : 'Pin message'} active={pinned} activeClass="text-amber-400">
          <Bookmark size={12} className={pinned ? 'text-amber-400 fill-amber-400' : ''} />
        </ActionBtn>
      )}

      {/* Send to Builder */}
      {onSendToBuilder && (
        <ActionBtn onClick={onSendToBuilder} title="Open in Preview panel">
          <PanelRight size={12} />
        </ActionBtn>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* 3-dot menu */}
      <div className="relative" ref={menuRef}>
        <ActionBtn onClick={() => setMenuOpen(v => !v)} title="More options" active={menuOpen} activeClass="text-slate-300 bg-white/5">
          <MoreHorizontal size={12} />
        </ActionBtn>

        {menuOpen && (
          <div className="absolute bottom-full right-0 mb-1 w-52 rounded-xl bg-[#13131f] border border-white/10 shadow-2xl z-50 overflow-hidden">
            {/* Timestamp */}
            {timeLabel && (
              <div className="flex items-center gap-2 px-3 py-2.5 text-[10px] font-mono text-slate-500 border-b border-white/5">
                <Clock size={10} className="flex-shrink-0" />
                {timeLabel}
              </div>
            )}

            {/* Retry */}
            {onRetry && (
              <button
                onClick={() => { setMenuOpen(false); onRetry(); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-colors"
              >
                <RotateCcw size={11} />
                Retry
              </button>
            )}

            {/* Branch in new chat */}
            {onFork && (
              <button
                onClick={() => { setMenuOpen(false); onFork(); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-slate-400 hover:text-violet-400 hover:bg-white/5 transition-colors"
              >
                <GitFork size={11} />
                Branch in new chat
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Route info badges
// ---------------------------------------------------------------------------
function RouteInfo({ route_result, generation_time_ms }) {
  if (!route_result) return null;
  const intent = route_result.intent || route_result.route || null;
  const checkpoint = route_result.checkpoint || route_result.checkpoint_file || null;
  const confidence = route_result.confidence != null ? `${Math.round(route_result.confidence * 100)}%` : null;
  const timeS = generation_time_ms ? `${(generation_time_ms / 1000).toFixed(1)}s` : null;
  const intentColor = intent === 'image' || intent === 'image_generation'
    ? 'text-violet-400/80 bg-violet-500/10 border-violet-500/20'
    : intent === 'coding' || intent === 'code'
    ? 'text-amber-400/80 bg-amber-500/10 border-amber-500/20'
    : 'text-slate-400/80 bg-white/5 border-white/10';
  return (
    <div className="flex flex-wrap items-center gap-1 mt-2">
      {intent && intent !== 'chat' && <span className={`text-[10px] font-mono rounded px-1.5 py-0.5 border ${intentColor}`}>{intent}</span>}
      {checkpoint && <span className="text-[10px] font-mono rounded px-1.5 py-0.5 border text-cyan-400/70 bg-cyan-500/5 border-cyan-500/20 truncate max-w-[120px]">{checkpoint}</span>}
      {confidence && <span className="text-[10px] font-mono rounded px-1.5 py-0.5 border text-slate-400/70 bg-white/5 border-white/10">{confidence}</span>}
      {timeS && <span className="text-[10px] font-mono rounded px-1.5 py-0.5 border text-slate-500/70 bg-white/5 border-white/10">{timeS}</span>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Model + memory metadata bar
// ---------------------------------------------------------------------------
function MetaBar({ model_used, memory_stored }) {
  const hasModel = !!model_used;
  const memCount = memory_stored ? memory_stored.length : 0;
  if (!hasModel && memCount === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1 mt-2">
      {hasModel && <span className="text-[10px] font-mono rounded px-1.5 py-0.5 border text-cyan-400/60 bg-cyan-500/5 border-cyan-500/15" title={model_used}>{model_used.split('/').pop().split(':')[0]}</span>}
      {memCount > 0 && <span className="text-[10px] font-mono rounded px-1.5 py-0.5 border text-emerald-400/60 bg-emerald-500/5 border-emerald-500/15" title={memory_stored.map(f => `${f.key}: ${f.value}`).join(', ')}>+{memCount} mem</span>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Image Lightbox
// ---------------------------------------------------------------------------
function ImageLightbox({ images, startIndex, onClose }) {
  const [idx, setIdx] = useState(startIndex);

  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft') setIdx(i => Math.max(0, i - 1));
      if (e.key === 'ArrowRight') setIdx(i => Math.min(images.length - 1, i + 1));
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [images.length, onClose]);

  return (
    <div
      className="fixed inset-0 z-[999] bg-black/90 flex items-center justify-center"
      onClick={onClose}
    >
      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors"
      >
        <X size={20} />
      </button>

      {images.length > 1 && (
        <>
          <button
            onClick={(e) => { e.stopPropagation(); setIdx(i => Math.max(0, i - 1)); }}
            disabled={idx === 0}
            className="absolute left-4 p-2 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors disabled:opacity-30"
          >
            <ChevronLeft size={24} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); setIdx(i => Math.min(images.length - 1, i + 1)); }}
            disabled={idx === images.length - 1}
            className="absolute right-4 p-2 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors disabled:opacity-30"
          >
            <ChevronRight size={24} />
          </button>
        </>
      )}

      <img
        src={`data:image/jpeg;base64,${images[idx]}`}
        alt={`Image ${idx + 1}`}
        className="max-w-[90vw] max-h-[90vh] object-contain rounded-xl"
        onClick={(e) => e.stopPropagation()}
      />

      {images.length > 1 && (
        <div className="absolute bottom-4 flex gap-1.5">
          {images.map((_, i) => (
            <button
              key={i}
              onClick={(e) => { e.stopPropagation(); setIdx(i); }}
              className={`w-2 h-2 rounded-full transition-colors ${i === idx ? 'bg-white' : 'bg-white/30'}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Interactive multi-choice questions
// Detects numbered questions with "(e.g., opt1, opt2)" or "a) b) c)" options
// ---------------------------------------------------------------------------
function parseQuestions(text) {
  if (!text) return null;
  // Match: "1. Question text (e.g., opt1, opt2, opt3)" or "1. **Question**"
  const lines = text.split('\n');
  const questions = [];
  const egRe = /\(e\.g\.[,.]?\s*([^)]+)\)/i;
  const abcRe = /^\s*[a-dA-D][).]\s+(.+)/;

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const numMatch = line.match(/^(\d+)\.\s+\*?\*?(.+?)\*?\*?(\s*\(e\.g\.[,.]?\s*[^)]+\))?$/);
    if (numMatch) {
      const questionText = numMatch[2].trim();
      let options = [];
      // Extract from "(e.g., ...)" inline
      const egMatch = line.match(egRe);
      if (egMatch) {
        options = egMatch[1].split(',').map(o => o.trim().replace(/^["']|["']$/g, '')).filter(o => o.length > 1);
      }
      // Also look for a) b) c) on next lines
      let j = i + 1;
      while (j < lines.length && abcRe.test(lines[j])) {
        const m = lines[j].match(abcRe);
        if (m) options.push(m[1].trim());
        j++;
      }
      questions.push({ num: parseInt(numMatch[1]), text: questionText, options });
      i = j;
    } else {
      i++;
    }
  }
  return questions.length >= 2 ? questions : null;
}

function InteractiveChoices({ text, onSuggest }) {
  const questions = parseQuestions(text);
  const [selected, setSelected] = useState({});
  if (!questions) return null;

  const toggle = (qi, opt) =>
    setSelected(prev => ({ ...prev, [qi]: prev[qi] === opt ? null : opt }));

  const handleSubmit = () => {
    const answers = questions
      .map((q, i) => selected[i] ? `${q.num}. ${selected[i]}` : null)
      .filter(Boolean)
      .join('  |  ');
    if (answers && onSuggest) onSuggest(answers);
  };

  const anySelected = Object.values(selected).some(Boolean);

  return (
    <div className="mt-3 space-y-3 border-t border-white/5 pt-3">
      {questions.map((q, qi) => (
        <div key={qi}>
          <p className="text-[11px] text-slate-400 font-medium mb-1.5">
            {q.num}. {q.text}
          </p>
          {q.options.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {q.options.map((opt, oi) => (
                <button
                  key={oi}
                  onClick={() => toggle(qi, opt)}
                  className={`text-[11px] px-3 py-1 rounded-full border transition-all text-left ${
                    selected[qi] === opt
                      ? 'border-violet-500/70 bg-violet-500/20 text-violet-300 shadow-sm shadow-violet-500/20'
                      : 'border-slate-600/40 bg-slate-800/50 text-slate-400 hover:border-violet-400/40 hover:text-violet-400'
                  }`}
                >
                  {opt}
                </button>
              ))}
            </div>
          )}
          {q.options.length === 0 && (
            <p className="text-[10px] text-slate-600 italic">Type your answer below</p>
          )}
        </div>
      ))}
      {anySelected && (
        <button
          onClick={handleSubmit}
          className="text-[11px] px-4 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white transition-colors font-medium"
        >
          Send my answers ↵
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Suggestion pills
// ---------------------------------------------------------------------------
function SuggestionPills({ suggestions, onSuggest }) {
  if (!suggestions || suggestions.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mt-3">
      {suggestions.map((s, i) => (
        <button
          key={i}
          onClick={() => onSuggest && onSuggest(s)}
          className="text-[11px] px-3 py-1 rounded-full border border-cyan-500/20 bg-cyan-500/5 text-cyan-400/80 hover:bg-cyan-500/15 hover:text-cyan-300 hover:border-cyan-500/40 transition-colors text-left"
        >
          {s}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChatMessage
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Rate limit countdown
// ---------------------------------------------------------------------------
function RateLimitCountdown({ seconds, onDone }) {
  const [remaining, setRemaining] = useState(seconds);
  useEffect(() => {
    if (remaining <= 0) { onDone?.(); return; }
    const t = setTimeout(() => setRemaining(r => r - 1), 1000);
    return () => clearTimeout(t);
  }, [remaining, onDone]);

  const pct = Math.max(0, remaining / seconds);
  const circumference = 2 * Math.PI * 18;

  return (
    <div className="mt-3 flex items-center gap-3 p-3 rounded-xl bg-red-500/5 border border-red-500/15">
      {/* Circular timer */}
      <div className="relative flex-shrink-0 w-12 h-12">
        <svg className="w-12 h-12 -rotate-90" viewBox="0 0 40 40">
          <circle cx="20" cy="20" r="18" fill="none" stroke="rgba(239,68,68,0.15)" strokeWidth="3" />
          <circle
            cx="20" cy="20" r="18" fill="none"
            stroke="rgba(239,68,68,0.7)" strokeWidth="3"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - pct)}
            strokeLinecap="round"
            style={{ transition: 'stroke-dashoffset 0.9s linear' }}
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-[13px] font-bold text-red-400">
          {remaining}
        </span>
      </div>
      <div>
        <p className="text-xs font-medium text-red-400">Hold on! Let me catch up…</p>
        <p className="text-[10px] text-slate-500 mt-0.5">
          {remaining > 0 ? `Ready in ${remaining}s` : 'Good to go! Hit Retry.'}
        </p>
      </div>
    </div>
  );
}

function ChatMessage({ message, onRetry, onRate, onFork, onPin, onSendToBuilder, onSuggest }) {
  const { settings, user, avatar } = useApp();
  const { role, type, content, image_base64, prompt, route_result, generation_time_ms, retry_used, prompt_warnings, model_used, memory_stored, rating, pinned, timestamp, suggestions } = message;
  const { images_base64 } = message;
  const [rateLimitDone, setRateLimitDone] = useState(false);
  const allImages = images_base64 && images_base64.length > 1 ? images_base64 : (image_base64 ? [image_base64] : []);
  const [lightboxIdx, setLightboxIdx] = useState(null);

  // Compaction summary divider — rendered before user/assistant bubbles
  if (type === 'summary' || message._is_summary) {
    return (
      <div className="flex items-center gap-3 my-4 msg-enter">
        <div className="flex-1 h-px bg-white/5" />
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#151520] border border-white/8 text-[11px] text-slate-500 font-mono">
          <span className="w-1.5 h-1.5 rounded-full bg-violet-500/60 flex-shrink-0" />
          <span className="text-violet-400/70 font-semibold mr-1">Compacted</span>
          <span className="max-w-[320px] truncate" title={content}>{content}</span>
        </div>
        <div className="flex-1 h-px bg-white/5" />
      </div>
    );
  }

  if (role === 'user') {
    const initial = user?.name ? user.name[0].toUpperCase() : 'U';
    return (
      <div className="flex justify-end items-start gap-2 msg-enter">
        {lightboxIdx !== null && (
          <ImageLightbox images={allImages} startIndex={lightboxIdx} onClose={() => setLightboxIdx(null)} />
        )}
        <div className="max-w-[75%] flex flex-col items-end gap-2">
          {type === 'image_input' && allImages.length > 0 && (
            <div className="flex flex-wrap gap-2 justify-end">
              {allImages.map((b64, i) => (
                <img key={i} src={`data:image/jpeg;base64,${b64}`} alt={`Attached ${i + 1}`}
                  onClick={() => setLightboxIdx(i)}
                  className="max-h-40 max-w-[180px] rounded-xl border border-cyan-500/20 object-contain bg-black/30 cursor-zoom-in hover:border-cyan-400/50 transition-colors" />
              ))}
            </div>
          )}
          {content && (
            <div className="px-5 py-3 rounded-2xl rounded-tr-sm bg-[#1e2a3a] border border-cyan-500/20 text-slate-200 text-sm leading-relaxed">
              {renderText(content)}
            </div>
          )}
        </div>
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0 mt-1 select-none overflow-hidden">
          {avatar ? <AvatarMedia src={avatar} className="w-full h-full object-cover" fallback={<span>{initial}</span>} /> : initial}
        </div>
      </div>
    );
  }

  if (type === 'image_generating') {
    return (
      <div className="flex items-start gap-3 msg-enter">
        <div className="w-10 h-10 rounded-xl bg-[#0d0d18] flex items-center justify-center overflow-hidden flex-shrink-0 mt-1 border border-violet-500/20">
          <img src="/mascot.png?v=2" alt="Mini Assistant" className="w-full h-full object-contain" onError={e => { e.target.style.display = 'none'; }} />
        </div>
        <div className="max-w-[80%] w-72 px-5 py-4 rounded-2xl rounded-tl-sm border bg-[#151520] border-white/5">
          <p className="text-xs text-violet-400/80 font-mono mb-3 flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse inline-block" />
            {content || 'Rendering image...'}
          </p>
          <div className="image-shimmer" />
        </div>
      </div>
    );
  }

  const isImage = type === 'image' || !!image_base64;
  const isError = type === 'error';

  return (
    <div className="flex items-start gap-3 msg-enter">
      <div className="w-10 h-10 rounded-xl bg-[#0d0d18] flex items-center justify-center overflow-hidden flex-shrink-0 mt-1 border border-violet-500/20">
        <img src="/mascot.png?v=2" alt="Mini Assistant" className="w-full h-full object-contain"
          onError={e => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex'; }} />
        <span style={{display:'none'}} className="text-white text-xs font-bold w-full h-full items-center justify-center">MA</span>
      </div>

      <div className={`relative group max-w-[80%] px-5 py-4 rounded-2xl rounded-tl-sm border text-sm leading-relaxed
        ${isError ? 'bg-red-900/20 border-red-500/20 text-red-300' : pinned ? 'bg-[#151520] border-amber-500/20 text-slate-200' : 'bg-[#151520] border-white/5 text-slate-200'}`}
      >
        {pinned && (
          <div className="absolute top-2 right-2">
            <Bookmark size={10} className="text-amber-400 fill-amber-400" />
          </div>
        )}

        {isImage ? (
          <>
            <p className="text-slate-400 text-sm mb-3">Here's your image:</p>
            <ImageCard image_base64={image_base64} prompt={prompt || content} route_result={route_result}
              generation_time_ms={generation_time_ms} retry_used={retry_used} dry_run={false} />
          </>
        ) : (
          renderContent(content)
        )}


        {prompt_warnings && prompt_warnings.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {prompt_warnings.map((w, i) => <span key={i} className="text-[10px] text-amber-500/60 font-mono">{w}</span>)}
          </div>
        )}


        {/* Bottom action bar — copy, thumbs, speaker, share, 3-dot */}
        {!isError && !isImage && content && (
          <MessageActions
            content={content}
            rating={rating}
            onRate={onRate}
            onRetry={onRetry}
            onFork={onFork}
            onPin={onPin}
            onSendToBuilder={onSendToBuilder}
            pinned={pinned}
            timestamp={timestamp}
          />
        )}

        {/* Interactive multiple-choice for numbered Q&A — only for real responses */}
        {!isError && !isImage && role === 'assistant' && onSuggest && content && content.length > 80 && (
          <InteractiveChoices text={content} onSuggest={onSuggest} />
        )}

        {/* Follow-up suggestion pills */}
        {!isError && !isImage && (
          <SuggestionPills suggestions={suggestions} onSuggest={onSuggest} />
        )}

        {/* Error retry button / rate limit countdown */}
        {isError && message._retryAfter && !rateLimitDone && (
          <RateLimitCountdown seconds={message._retryAfter} onDone={() => setRateLimitDone(true)} />
        )}
        {isError && onRetry && (!message._retryAfter || rateLimitDone) && (
          <button onClick={onRetry}
            className="mt-3 flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 px-2.5 py-1.5 rounded-lg transition-colors">
            <RotateCcw size={11} />
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

export default ChatMessage;
