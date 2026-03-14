/**
 * components/ChatMessage.js
 * Renders a single chat message bubble (user or assistant).
 * Props: { message: { role, type, content, image_base64, prompt, route_result,
 *                     generation_time_ms, retry_used, prompt_warnings },
 *          onRetry?: () => void }
 */

import React from 'react';
import { RotateCcw } from 'lucide-react';
import { useApp } from '../context/AppContext';
import ImageCard from './ImageCard';
import IntelligencePanel from './IntelligencePanel';

// ---------------------------------------------------------------------------
// Minimal markdown-aware text renderer
// Handles: **bold**, *italic*, `code`, [links], bare URLs, line breaks
// ---------------------------------------------------------------------------
function renderText(text) {
  if (!text) return null;
  // Split on newlines first
  const lines = text.split('\n');
  return lines.map((line, li) => (
    <React.Fragment key={li}>
      {renderInline(line)}
      {li < lines.length - 1 && <br />}
    </React.Fragment>
  ));
}

function renderInline(text) {
  // Patterns: **bold**, *italic*, `code`, [text](url), https?://...
  const pattern = /(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^\)]+)\)|(https?:\/\/[^\s]+))/g;
  const parts = [];
  let lastIdx = 0;
  let match;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIdx) {
      parts.push(text.slice(lastIdx, match.index));
    }

    if (match[2]) {
      parts.push(<strong key={match.index} className="font-semibold text-slate-100">{match[2]}</strong>);
    } else if (match[3]) {
      parts.push(<em key={match.index} className="italic text-slate-300">{match[3]}</em>);
    } else if (match[4]) {
      parts.push(
        <code key={match.index} className="font-mono text-[12px] bg-cyan-500/10 text-cyan-300 px-1.5 py-0.5 rounded">
          {match[4]}
        </code>
      );
    } else if (match[5] && match[6]) {
      parts.push(
        <a key={match.index} href={match[6]} target="_blank" rel="noopener noreferrer"
          className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2 transition-colors">
          {match[5]}
        </a>
      );
    } else if (match[7]) {
      parts.push(
        <a key={match.index} href={match[7]} target="_blank" rel="noopener noreferrer"
          className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2 transition-colors break-all">
          {match[7]}
        </a>
      );
    }

    lastIdx = match.index + match[0].length;
  }

  if (lastIdx < text.length) {
    parts.push(text.slice(lastIdx));
  }

  return parts.length ? parts : text;
}

// ---------------------------------------------------------------------------
// Route info badges
// ---------------------------------------------------------------------------
function RouteInfo({ route_result, generation_time_ms }) {
  if (!route_result) return null;

  const intent = route_result.intent || route_result.route || null;
  const checkpoint = route_result.checkpoint || route_result.checkpoint_file || null;
  const confidence = route_result.confidence != null
    ? `${Math.round(route_result.confidence * 100)}%`
    : null;
  const timeS = generation_time_ms ? `${(generation_time_ms / 1000).toFixed(1)}s` : null;

  const intentColor =
    intent === 'image' || intent === 'image_generation'
      ? 'text-violet-400/80 bg-violet-500/10 border-violet-500/20'
      : intent === 'coding' || intent === 'code'
      ? 'text-amber-400/80 bg-amber-500/10 border-amber-500/20'
      : 'text-slate-400/80 bg-white/5 border-white/10';

  return (
    <div className="flex flex-wrap items-center gap-1 mt-2">
      {intent && (
        <span className={`text-[10px] font-mono rounded px-1.5 py-0.5 border ${intentColor}`}>
          {intent}
        </span>
      )}
      {checkpoint && (
        <span className="text-[10px] font-mono rounded px-1.5 py-0.5 border text-cyan-400/70 bg-cyan-500/5 border-cyan-500/20 truncate max-w-[120px]">
          {checkpoint}
        </span>
      )}
      {confidence && (
        <span className="text-[10px] font-mono rounded px-1.5 py-0.5 border text-slate-400/70 bg-white/5 border-white/10">
          {confidence}
        </span>
      )}
      {timeS && (
        <span className="text-[10px] font-mono rounded px-1.5 py-0.5 border text-slate-500/70 bg-white/5 border-white/10">
          {timeS}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChatMessage
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Model + memory metadata bar
// ---------------------------------------------------------------------------
function MetaBar({ model_used, memory_stored }) {
  const hasModel  = !!model_used;
  const memCount  = memory_stored ? memory_stored.length : 0;
  if (!hasModel && memCount === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1 mt-2 pt-2 border-t border-white/5">
      {hasModel && (
        <span className="text-[10px] font-mono rounded px-1.5 py-0.5 border text-cyan-400/60 bg-cyan-500/5 border-cyan-500/15 truncate max-w-[140px]"
          title={model_used}>
          {model_used}
        </span>
      )}
      {memCount > 0 && (
        <span className="text-[10px] font-mono rounded px-1.5 py-0.5 border text-emerald-400/60 bg-emerald-500/5 border-emerald-500/15"
          title={memory_stored.map(f => `${f.key}: ${f.value}`).join(', ')}>
          +{memCount} mem
        </span>
      )}
    </div>
  );
}

function ChatMessage({ message, onRetry }) {
  const { settings, user } = useApp();
  const { role, type, content, image_base64, prompt, route_result, generation_time_ms, retry_used, prompt_warnings, model_used, memory_stored } = message;

  if (role === 'user') {
    const initial = user?.name ? user.name[0].toUpperCase() : 'U';
    return (
      <div className="flex justify-end items-start gap-2 msg-enter">
        <div className="max-w-[75%] flex flex-col items-end gap-2">
          {type === 'image_input' && image_base64 && (
            <img
              src={`data:image/jpeg;base64,${image_base64}`}
              alt="Attached"
              className="max-h-48 max-w-xs rounded-xl border border-cyan-500/20 object-contain bg-black/30"
            />
          )}
          {content && (
            <div className="px-5 py-3 rounded-2xl rounded-tr-sm bg-[#1e2a3a] border border-cyan-500/20 text-slate-200 text-sm leading-relaxed">
              {renderText(content)}
            </div>
          )}
        </div>
        {/* User avatar */}
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0 mt-1 select-none">
          {initial}
        </div>
      </div>
    );
  }

  // Image generating placeholder
  if (type === 'image_generating') {
    return (
      <div className="flex items-start gap-3 msg-enter">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 via-violet-500 to-violet-600 flex items-center justify-center overflow-hidden flex-shrink-0 mt-1">
          <img src="/Logo.png" alt="Mini Assistant" className="w-full h-full object-contain"
            onError={e => { e.target.style.display = 'none'; }} />
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

  // Assistant message
  const isImage = type === 'image' || !!image_base64;
  const isError = type === 'error';

  return (
    <div className="flex items-start gap-3 msg-enter">
      {/* Avatar */}
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 via-violet-500 to-violet-600 flex items-center justify-center overflow-hidden flex-shrink-0 mt-1">
        <img src="/Logo.png" alt="Mini Assistant" className="w-full h-full object-contain"
          onError={e => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex'; }} />
        <span style={{display:'none'}} className="text-white text-xs font-bold w-full h-full items-center justify-center">MA</span>
      </div>

      {/* Content card */}
      <div className={`max-w-[80%] px-5 py-4 rounded-2xl rounded-tl-sm border text-sm leading-relaxed
        ${isError
          ? 'bg-red-900/20 border-red-500/20 text-red-300'
          : 'bg-[#151520] border-white/5 text-slate-200'}`}
      >
        {/* Intelligence panel for non-chat intents */}
        {role === 'assistant' && route_result && route_result.intent !== 'chat' && (
          <IntelligencePanel route_result={route_result} generation_time_ms={generation_time_ms} />
        )}

        {isImage ? (
          <>
            <p className="text-slate-400 text-sm mb-3">Here's your image:</p>
            <ImageCard
              image_base64={image_base64}
              prompt={prompt || content}
              route_result={route_result}
              generation_time_ms={generation_time_ms}
              retry_used={retry_used}
              dry_run={false}
            />
          </>
        ) : (
          renderText(content)
        )}

        {/* Route info */}
        {settings.showRouteInfo && !isError && (
          <RouteInfo route_result={route_result} generation_time_ms={generation_time_ms} />
        )}

        {/* Prompt warnings */}
        {prompt_warnings && prompt_warnings.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {prompt_warnings.map((w, i) => (
              <span key={i} className="text-[10px] text-amber-500/60 font-mono">{w}</span>
            ))}
          </div>
        )}

        {/* Model used + memory facts stored */}
        {!isError && (
          <MetaBar model_used={model_used} memory_stored={memory_stored} />
        )}

        {/* Retry button for errors */}
        {isError && onRetry && (
          <button
            onClick={onRetry}
            className="mt-3 flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 px-2.5 py-1.5 rounded-lg transition-colors"
          >
            <RotateCcw size={11} />
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

export default ChatMessage;
