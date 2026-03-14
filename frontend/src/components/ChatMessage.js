/**
 * components/ChatMessage.js
 * Renders a single chat message bubble (user or assistant).
 * Props: { message, onRetry?, onRate? }
 */

import React, { useState, useCallback } from 'react';
import { RotateCcw, Copy, Check, Volume2, VolumeX, ThumbsUp, ThumbsDown } from 'lucide-react';
import { useApp } from '../context/AppContext';
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
// CodeBlock
// ---------------------------------------------------------------------------
function CodeBlock({ lang, code }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); }).catch(() => {});
  }, [code]);

  const lines = tokenize(code, lang);
  return (
    <div className="my-3 rounded-xl overflow-hidden border border-white/10 bg-[#0d0f1a]">
      <div className="flex items-center justify-between px-4 py-2 bg-white/[0.04] border-b border-white/[0.06]">
        <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">{lang || 'code'}</span>
        <button onClick={handleCopy} className="flex items-center gap-1.5 text-[10px] font-mono text-slate-500 hover:text-slate-300 transition-colors">
          {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="overflow-x-auto px-4 py-3 text-[12px] leading-[1.7]">
        {lines.map(({ idx, tokens }) => (
          <div key={idx} className="table-row">
            <span className="table-cell select-none text-slate-600 text-right pr-4 w-8 text-[11px]">{idx + 1}</span>
            <span className="table-cell">{tokens.map((tok, ti) => <span key={ti} className={tok.cls}>{tok.t}</span>)}</span>
          </div>
        ))}
      </pre>
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
    parts.push(<CodeBlock key={key++} lang={lang} code={code} />);
    lastIdx = match.index + match[0].length;
  }
  if (lastIdx < text.length) parts.push(<React.Fragment key={key++}>{renderText(text.slice(lastIdx))}</React.Fragment>);
  return parts.length ? parts : renderText(text);
}

// ---------------------------------------------------------------------------
// TTS button
// ---------------------------------------------------------------------------
function TTSButton({ text }) {
  const [speaking, setSpeaking] = useState(false);
  const handle = useCallback(() => {
    if (speaking) { window.speechSynthesis.cancel(); setSpeaking(false); return; }
    const utt = new SpeechSynthesisUtterance(text);
    utt.onend = () => setSpeaking(false);
    utt.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(utt);
    setSpeaking(true);
  }, [speaking, text]);

  if (!('speechSynthesis' in window)) return null;
  return (
    <button
      onClick={handle}
      title={speaking ? 'Stop reading' : 'Read aloud'}
      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded text-slate-600 hover:text-slate-300"
    >
      {speaking ? <VolumeX size={12} /> : <Volume2 size={12} />}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Thumbs up / down rating bar
// ---------------------------------------------------------------------------
function ThumbsBar({ rating, onRate }) {
  if (!onRate) return null;
  return (
    <div className="flex items-center gap-0.5 mt-2 pt-2 border-t border-white/5">
      <button
        onClick={() => onRate(rating === 1 ? null : 1)}
        title="Good response"
        className={`p-1 rounded transition-colors ${rating === 1 ? 'text-emerald-400' : 'text-slate-600 hover:text-slate-400'}`}
      >
        <ThumbsUp size={11} />
      </button>
      <button
        onClick={() => onRate(rating === -1 ? null : -1)}
        title="Poor response"
        className={`p-1 rounded transition-colors ${rating === -1 ? 'text-red-400' : 'text-slate-600 hover:text-slate-400'}`}
      >
        <ThumbsDown size={11} />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Copy full message button
// ---------------------------------------------------------------------------
function CopyMessageButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handle = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); }).catch(() => {});
  }, [text]);
  return (
    <button
      onClick={handle}
      className="opacity-0 group-hover:opacity-100 transition-opacity absolute -top-2 right-0 flex items-center gap-1 text-[10px] font-mono text-slate-500 hover:text-slate-300 bg-[#1a1c2e] border border-white/10 px-2 py-1 rounded-lg shadow"
    >
      {copied ? <Check size={10} className="text-emerald-400" /> : <Copy size={10} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
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
      {intent && <span className={`text-[10px] font-mono rounded px-1.5 py-0.5 border ${intentColor}`}>{intent}</span>}
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
    <div className="flex flex-wrap items-center gap-1 mt-2 pt-2 border-t border-white/5">
      {hasModel && <span className="text-[10px] font-mono rounded px-1.5 py-0.5 border text-cyan-400/60 bg-cyan-500/5 border-cyan-500/15 truncate max-w-[140px]" title={model_used}>{model_used}</span>}
      {memCount > 0 && <span className="text-[10px] font-mono rounded px-1.5 py-0.5 border text-emerald-400/60 bg-emerald-500/5 border-emerald-500/15" title={memory_stored.map(f => `${f.key}: ${f.value}`).join(', ')}>+{memCount} mem</span>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChatMessage
// ---------------------------------------------------------------------------
function ChatMessage({ message, onRetry, onRate }) {
  const { settings, user } = useApp();
  const { role, type, content, image_base64, prompt, route_result, generation_time_ms, retry_used, prompt_warnings, model_used, memory_stored, rating } = message;

  if (role === 'user') {
    const initial = user?.name ? user.name[0].toUpperCase() : 'U';
    return (
      <div className="flex justify-end items-start gap-2 msg-enter">
        <div className="max-w-[75%] flex flex-col items-end gap-2">
          {type === 'image_input' && image_base64 && (
            <img src={`data:image/jpeg;base64,${image_base64}`} alt="Attached"
              className="max-h-48 max-w-xs rounded-xl border border-cyan-500/20 object-contain bg-black/30" />
          )}
          {content && (
            <div className="px-5 py-3 rounded-2xl rounded-tr-sm bg-[#1e2a3a] border border-cyan-500/20 text-slate-200 text-sm leading-relaxed">
              {renderText(content)}
            </div>
          )}
        </div>
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0 mt-1 select-none">
          {initial}
        </div>
      </div>
    );
  }

  if (type === 'image_generating') {
    return (
      <div className="flex items-start gap-3 msg-enter">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 via-violet-500 to-violet-600 flex items-center justify-center overflow-hidden flex-shrink-0 mt-1">
          <img src="/Logo.png" alt="Mini Assistant" className="w-full h-full object-contain" onError={e => { e.target.style.display = 'none'; }} />
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
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 via-violet-500 to-violet-600 flex items-center justify-center overflow-hidden flex-shrink-0 mt-1">
        <img src="/Logo.png" alt="Mini Assistant" className="w-full h-full object-contain"
          onError={e => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex'; }} />
        <span style={{display:'none'}} className="text-white text-xs font-bold w-full h-full items-center justify-center">MA</span>
      </div>

      <div className={`relative group max-w-[80%] px-5 py-4 rounded-2xl rounded-tl-sm border text-sm leading-relaxed
        ${isError ? 'bg-red-900/20 border-red-500/20 text-red-300' : 'bg-[#151520] border-white/5 text-slate-200'}`}
      >
        {/* Top-right action buttons (copy + TTS) */}
        {!isError && !isImage && content && (
          <div className="absolute -top-2 right-0 flex items-center gap-1">
            <TTSButton text={content} />
            <CopyMessageButton text={content} />
          </div>
        )}

        {role === 'assistant' && route_result && route_result.intent !== 'chat' && (
          <IntelligencePanel route_result={route_result} generation_time_ms={generation_time_ms} />
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

        {settings.showRouteInfo && !isError && (
          <RouteInfo route_result={route_result} generation_time_ms={generation_time_ms} />
        )}

        {prompt_warnings && prompt_warnings.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {prompt_warnings.map((w, i) => <span key={i} className="text-[10px] text-amber-500/60 font-mono">{w}</span>)}
          </div>
        )}

        {!isError && <MetaBar model_used={model_used} memory_stored={memory_stored} />}

        {/* Thumbs up/down — only on non-error assistant text messages */}
        {!isError && !isImage && <ThumbsBar rating={rating} onRate={onRate} />}

        {isError && onRetry && (
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
