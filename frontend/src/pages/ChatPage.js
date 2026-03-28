/**
 * pages/ChatPage.js
 * Main chat page. Transitions between HomeHero (no chat) and active conversation.
 */

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { PanelRight, Download, ChevronDown, Zap, Star } from 'lucide-react';
import { toast } from 'sonner';
import { useApp, makeThumbnail, canGenerateImage } from '../context/AppContext';
import { useChat } from '../hooks/useChat';
import HomeHero from '../components/HomeHero';
import ChatMessage from '../components/ChatMessage';
import ChatInput from '../components/ChatInput';
import MiniOrb from '../components/MiniOrb';
import CognitiveStream from '../components/CognitiveStream';
import ApprovalModal from '../components/ApprovalModal';
import RightPanel from '../components/RightPanel';
import ComparisonBubble from '../components/ComparisonBubble';
import ThinkingSequence from '../components/orchestration/ThinkingSequence';
import TaskSummaryCard from '../components/orchestration/TaskSummaryCard';
import { useOrchestration, ORCH_STATUS } from '../hooks/useOrchestration';
import ExportRecordModal from '../components/creation/ExportRecordModal';
import api from '../api/client';

// ---------------------------------------------------------------------------
// Image Limit Modal
// ---------------------------------------------------------------------------
function ImageLimitModal({ onClose, onUpgrade }) {
  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-md rounded-2xl bg-[#0f1020] border border-white/10 shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Gradient top bar */}
        <div className="h-1 w-full bg-gradient-to-r from-violet-500 via-cyan-400 to-violet-500" />

        <div className="px-8 py-8">
          {/* Heading */}
          <h2 className="text-xl font-bold text-white mb-1">You've used your image limit.</h2>
          <p className="text-slate-400 text-sm mb-6">
            Unlock full access to continue creating.
          </p>

          {/* Value highlights */}
          <div className="bg-white/[0.04] border border-white/[0.06] rounded-xl px-5 py-4 mb-6">
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest mb-3">With a plan, you can:</p>
            <ul className="space-y-2">
              {[
                'Generate unlimited images',
                'Refine and iterate freely',
                'Build and export complete projects',
              ].map(item => (
                <li key={item} className="flex items-center gap-2.5 text-sm text-slate-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-violet-400 flex-shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          {/* CTAs */}
          <button
            onClick={onUpgrade}
            className="w-full py-3 rounded-xl bg-gradient-to-r from-violet-600 to-cyan-500 text-white text-sm font-bold hover:opacity-90 active:scale-[0.98] transition-all mb-3"
          >
            Unlock Full Access
          </button>
          <button
            onClick={onClose}
            className="w-full py-2 text-slate-500 text-xs hover:text-slate-300 transition-colors"
          >
            Learn more about plans
          </button>
        </div>
      </div>
    </div>
  );
}

/** Detect if a message looks like an image generation request */
function isImageIntent(text) {
  if (!text) return false;
  // Action verb + subject ("generate an image of...")
  if (/\b(draw|paint|generate|create|make|render|design|illustrate|sketch|produce)\b.{0,50}\b(image|photo|picture|illustration|artwork|portrait|landscape|anime|realistic|wallpaper|avatar|banner|logo|thumbnail)\b|\b(image|picture|photo)\s+of\b|\banime\b|\bdigital art\b|\bphoto realistic\b/i.test(text)) return true;
  // Pure descriptive prompt — quality/style keywords used in image generation
  return /\b(8k|4k|ultra[\s-]?detailed|masterpiece|cinematic lighting|volumetric light|photorealistic|hyper[\s-]?realistic|concept art|digital painting|unreal engine|octane render|artstation|highly detailed|studio lighting|depth of field|bokeh|ray tracing|smooth anatomy|realistic proportions|full.?body shot|head[\s-]to[\s-]toe)\b/i.test(text);
}

/** Detect if a message/prompt suggests app-building intent */
function isBuildIntent(text, routeResult) {
  if (routeResult === 'app_builder') return true;
  if (!text) return false;
  return /\/build|build me|build it|create (a|an|the) (app|website|page|ui|component|form|dashboard)|make (a|an) (web|react|html)|make it|do it|generate (a|an) (app|website|page)|update it|add (a|an|the) (button|section|feature|page|component|form)|can you (build|make|create|add|update)/i.test(text);
}

function LoadingBubble() {
  return (
    <div className="flex items-start gap-3">
      <MiniOrb state="thinking" size="sm" />
      <div className="px-5 py-4 rounded-2xl rounded-tl-sm border bg-[#151520] border-white/5">
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  );
}

// Syntax colour for a single code line
function lineColor(line) {
  if (/^\s*(\/\/|\/\*|#)/.test(line))                                                          return 'text-slate-600';
  if (/^\s*(function|const|let|var|if|else|for|while|return|class|import|export|async|await|def|self)\b/.test(line)) return 'text-violet-400';
  if (/^\s*[\w-]+\s*\(/.test(line))                                                            return 'text-yellow-300/80';
  if (/^\s*[\w-]+\s*[:=]/.test(line))                                                          return 'text-cyan-300';
  if (/[<>{}]/.test(line))                                                                     return 'text-amber-300/70';
  return 'text-slate-400';
}

// Clip a line to max N chars — intentionally short so nothing is grab-able
const CLIP = 36;
function clip(line) {
  const trimmed = line.trimStart();
  return trimmed.length > CLIP ? trimmed.slice(0, CLIP) + ' …' : trimmed;
}

/** Live code-terminal shown while the app builder streams */
function BuildingTerminal({ codeText, linesBuilt }) {
  // Sample 4 lines: newest 2 + 2 from middle of what's built (gives variety)
  const allLines = codeText.split('\n').filter(l => l.trim());
  const mid = Math.floor(allLines.length / 2);
  const sample = [
    ...(allLines.length > 6 ? allLines.slice(mid - 1, mid + 1) : []),
    ...allLines.slice(-2),
  ].slice(-4); // max 4 lines shown at once

  // Progress bar width — caps at 95% (we don't know total lines ahead of time)
  const progress = Math.min(95, Math.round((linesBuilt / 7) * 10) / 10);

  return (
    <div className="rounded-xl border border-cyan-500/20 bg-[#07080f] overflow-hidden w-full">
      {/* Title bar with progress */}
      <div className="flex items-center gap-2 px-3 py-2 bg-[#0c0e1c] border-b border-white/[0.05]">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
        <span className="text-[10px] text-cyan-400 font-mono font-semibold flex-1 tracking-wide">building…</span>
        <span className="text-[10px] text-slate-600 font-mono tabular-nums">{linesBuilt} lines</span>
      </div>

      {/* Progress bar */}
      <div className="h-0.5 bg-white/[0.04]">
        <div
          className="h-full bg-gradient-to-r from-cyan-500 to-violet-500 transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Scrolling snippet lines — clipped so nothing is copy-useful */}
      <div className="px-3 py-2.5 space-y-1">
        {sample.map((line, i) => {
          const isLast = i === sample.length - 1;
          const opacity = i === 0 && sample.length === 4 ? 'opacity-30' : i === 1 && sample.length === 4 ? 'opacity-55' : i === 2 ? 'opacity-80' : '';
          return (
            <div
              key={`${linesBuilt}-${i}`}
              className={`text-[11px] font-mono leading-5 ${isLast ? 'text-white' : lineColor(line)} ${opacity} transition-all duration-200`}
            >
              {clip(line)}
              {isLast && <span className="inline-block w-0.5 h-3 bg-cyan-400 ml-0.5 align-middle animate-pulse" />}
            </div>
          );
        })}
        {sample.length === 0 && (
          <div className="text-[11px] text-slate-700 font-mono">initialising…</div>
        )}
      </div>

      {/* Bottom fade — hides bottom of lines so nothing is fully readable */}
      <div className="h-3 bg-gradient-to-t from-[#07080f] to-transparent -mt-3 pointer-events-none relative z-10" />
    </div>
  );
}

/** Scanning animation — shown while Claude reads existing code to find the bug */
function CodeScanner({ existingCode }) {
  const [scanLine, setScanLine] = useState(0);
  const [elapsed, setElapsed]   = useState(0);
  const allLines = existingCode ? existingCode.split('\n').filter(l => l.trim()) : [];
  const total = allLines.length;

  // Scan forward then loop back — keeps looking alive even if Claude takes a long time
  useEffect(() => {
    if (!total) return;
    const t = setInterval(() => setScanLine(n => (n + 1) % total), 110);
    return () => clearInterval(t);
  }, [total]);

  useEffect(() => {
    const t = setInterval(() => setElapsed(s => s + 1), 1000);
    return () => clearInterval(t);
  }, []);

  if (!total) return null;

  // Progress bar: one full pass = 100%, then wraps back
  const progress = Math.round(((scanLine + 1) / total) * 100);

  const statusLabel =
    elapsed < 6  ? 'scanning code…'       :
    elapsed < 14 ? 'digging in…'           :
    elapsed < 25 ? 'found something…'      :
    elapsed < 40 ? 'fixing it now…'        :
                   'almost done, hang on…';

  // Show 4 lines around the scan cursor
  const win = [scanLine - 1, scanLine, scanLine + 1, scanLine + 2]
    .map(i => ({ line: allLines[Math.max(0, Math.min(i, total - 1))], isActive: i === scanLine }));

  return (
    <div className="rounded-xl border border-violet-500/20 bg-[#07080f] overflow-hidden w-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 bg-[#0c0e1c] border-b border-white/[0.05]">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
        <span className="text-[10px] text-violet-300 font-mono font-semibold flex-1 tracking-wide">{statusLabel}</span>
        <span className="text-[10px] text-slate-600 font-mono tabular-nums">{elapsed}s · {progress}%</span>
      </div>

      {/* Progress bar */}
      <div className="h-0.5 bg-white/[0.04]">
        <div
          className="h-full bg-gradient-to-r from-violet-500 to-cyan-500 transition-all duration-100"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Scrolling lines */}
      <div className="px-3 py-2.5 space-y-1">
        {win.map(({ line, isActive }, i) => (
          <div
            key={i}
            className={`text-[11px] font-mono leading-5 truncate transition-all duration-100 ${
              isActive
                ? 'text-violet-200 bg-violet-500/10 px-1.5 -mx-1.5 rounded'
                : i === 0 ? 'text-slate-700 opacity-40' : 'text-slate-500 opacity-70'
            }`}
          >
            {(line || ' ').trimStart().slice(0, 44)}
            {isActive && <span className="inline-block w-0.5 h-3 bg-violet-400 ml-0.5 align-middle animate-pulse" />}
          </div>
        ))}
      </div>
      <div className="h-3 bg-gradient-to-t from-[#07080f] to-transparent -mt-3 pointer-events-none relative z-10" />
    </div>
  );
}

/** Blinking cursor appended while streaming */
function StreamingBubble({ text, existingCode }) {
  // Detect build start: either a ```html fence OR raw <!DOCTYPE html> (Claude sometimes skips the fence)
  const htmlFenceIdx = text ? text.indexOf('```html') : -1;
  const rawHtmlIdx   = text ? text.search(/<!DOCTYPE\s+html/i) : -1;
  const buildIdx = htmlFenceIdx !== -1 ? htmlFenceIdx : rawHtmlIdx;
  const isBuildingApp = buildIdx !== -1;
  const preCodeText = isBuildingApp ? text.slice(0, buildIdx).trim() : null;
  const codeText = isBuildingApp ? text.slice(buildIdx) : '';
  const linesBuilt = codeText.split('\n').length;

  // "Thinking" phase: not yet outputting code — show scanner if prior code exists
  const isThinking = !isBuildingApp && !text;
  const hasThinkingText = !isBuildingApp && !!text;

  return (
    <div className="flex items-start gap-3 msg-enter">
      <div className="w-10 h-10 rounded-xl bg-[#0d0d18] flex items-center justify-center overflow-hidden flex-shrink-0 mt-1 border border-violet-500/20">
        <img src="/mascot.png?v=2" alt="Mini Assistant" className="w-full h-full object-contain"
          onError={e => { e.target.style.display = 'none'; }} />
      </div>
      <div className="max-w-[92%] sm:max-w-[82%] px-3 sm:px-5 py-3 sm:py-4 rounded-2xl rounded-tl-sm border bg-[#151520] border-white/5 text-sm leading-relaxed text-slate-200 w-full">
        {isBuildingApp ? (
          <div className="flex flex-col gap-2">
            {preCodeText && <span className="whitespace-pre-wrap text-slate-300">{preCodeText}</span>}
            <BuildingTerminal codeText={codeText} linesBuilt={linesBuilt} />
          </div>
        ) : isThinking && existingCode ? (
          <CodeScanner existingCode={existingCode} />
        ) : (
          <span className="whitespace-pre-wrap">
            {text || <span className="text-slate-600 text-xs italic">Thinking…</span>}
            <span className="inline-block w-0.5 h-3.5 bg-cyan-400 ml-0.5 align-middle animate-pulse" />
          </span>
        )}
      </div>
    </div>
  );
}

function OutOfCreditsCard({ onBuy, onUpgrade }) {
  return (
    <div className="flex items-start gap-3">
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500 to-amber-600 flex items-center justify-center flex-shrink-0 mt-1">
        <Zap size={15} className="text-black" />
      </div>
      <div className="flex-1 max-w-lg rounded-2xl rounded-tl-sm border border-amber-500/20 bg-amber-500/5 p-4">
        <p className="text-sm font-semibold text-amber-300 mb-0.5">You've used all your Mini Credits</p>
        <p className="text-xs text-slate-400 mb-3">
          Get more credits to keep building, or subscribe for unlimited access.
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={onBuy}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-black text-xs font-bold transition-all"
          >
            <Zap size={11} /> + Get Credits
          </button>
          <button
            onClick={onUpgrade}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 text-xs font-medium transition-all"
          >
            <Star size={11} /> View Plans
          </button>
        </div>
      </div>
    </div>
  );
}

function ChatPage() {
  const {
    activeChatId,
    chats,
    newChat,
    renameChat,
    updateChatMessages,
    updateChatPreviewImage,
    addImage,
    setPage,
    rateMessage,
    pinMessage,
    forkChat,
    setPurchaseModalOpen,
    openUpgradeModal,
    isSubscribed,
    plan,
    imageUsage,
    incrementImageUsage,
  } = useApp();

  const handleExport = useCallback((format = 'md') => {
    const chat = chats.find(c => c.id === activeChatId);
    if (!chat) return;
    const slug = chat.title.replace(/[^a-z0-9]/gi, '_').toLowerCase();
    if (format === 'html') {
      const rows = chat.messages
        .filter(m => (m.role === 'user' || m.role === 'assistant') && m.type !== 'image_generating')
        .map(m => {
          const who = m.role === 'user' ? 'You' : 'Mini';
          const cls = m.role === 'user' ? 'user' : 'assistant';
          const body = (m.content || '').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
          return `<div class="msg ${cls}"><strong>${who}:</strong><div>${body}</div></div>`;
        }).join('\n');
      const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${chat.title}</title><style>
body{font-family:system-ui,sans-serif;max-width:800px;margin:40px auto;padding:0 20px;background:#0d0d12;color:#ccc}
h1{color:#fff;margin-bottom:24px}.msg{margin-bottom:20px;padding:12px 16px;border-radius:12px;line-height:1.6}
.user{background:#1e2a3a;border:1px solid #1e4a7a}.assistant{background:#151520;border:1px solid #1e1e30}
strong{color:#7dd3fc;display:block;margin-bottom:4px;font-size:12px}
</style></head><body><h1>${chat.title}</h1>${rows}</body></html>`;
      const blob = new Blob([html], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `${slug}.html`; a.click();
      URL.revokeObjectURL(url);
    } else {
      const lines = [`# ${chat.title}`, ''];
      chat.messages.forEach(m => {
        if (m.role === 'user') lines.push(`**You:** ${m.content || ''}`, '');
        else if (m.role === 'assistant' && m.type !== 'image_generating') lines.push(`**Mini:** ${m.content || ''}`, '');
      });
      const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `${slug}.md`; a.click();
      URL.revokeObjectURL(url);
    }
  }, [chats, activeChatId]);

  const { send, sendStream, cancel, loading } = useChat();
  const [messages, setMessages]       = useState([]);
  const [pendingApproval, setPendingApproval] = useState(null);

  // ── Orchestration (Phase 1) ─────────────────────────────────────────────
  const { analyze: orchAnalyze, analysis: orchAnalysis, status: orchStatus, reset: orchReset } = useOrchestration();
  const [orchPendingSubmit, setOrchPendingSubmit] = useState(null); // holds {text, imgs, preferredModel} waiting for user approval

  // ── Creation Record Export ───────────────────────────────────────────────
  const [showExportRecordModal, setShowExportRecordModal] = useState(false);
  const [rightPanelOpen, setRightPanelOpen]   = useState(() => localStorage.getItem('rightPanelOpen') === 'true');
  const [imageLimitOpen, setImageLimitOpen]   = useState(false);
  const [chatMode, setChatMode]               = useState(() => {
    const saved = localStorage.getItem('chatMode');
    return ['image', 'build', 'chat'].includes(saved) ? saved : null;
  }); // null | 'image' | 'build' | 'chat' — persisted across refreshes
  const vibeMode = chatMode === 'build'; // legacy compat — still used in sendStream body
  const [previewImage, setPreviewImage]       = useState(null); // latest generated image → shown in RightPanel

  // Streaming text state (non-image responses)
  const [streamingText, setStreamingText] = useState(null); // null = not streaming

  // Reasoning timer — elapsed seconds while extended thinking runs (streamingText === '')
  const [thinkingSeconds, setThinkingSeconds] = useState(0);
  const thinkingTimerRef = useRef(null);
  useEffect(() => {
    if (streamingText === '' && loading) {
      setThinkingSeconds(0);
      thinkingTimerRef.current = setInterval(() => setThinkingSeconds(s => s + 1), 1000);
    } else {
      clearInterval(thinkingTimerRef.current);
      thinkingTimerRef.current = null;
    }
    return () => clearInterval(thinkingTimerRef.current);
  }, [streamingText, loading]);

  // Cognitive stream state (image / loading visual)
  const [streamActive, setStreamActive]     = useState(false);
  const [streamPrompt, setStreamPrompt]     = useState('');
  const [streamResponse, setStreamResponse] = useState(null);

  const sessionIdRef      = useRef(crypto.randomUUID());
  const bottomRef         = useRef(null);
  const scrollContainerRef = useRef(null);
  const currentChatIdRef  = useRef(null);
  const submittingRef     = useRef(false);
  const lastUserTextRef   = useRef('');
  const responseCountRef  = useRef(0); // increments per assistant response; compare triggers at multiples of 10
  const pendingMsgRef     = useRef(null); // queued message while a response is in-flight
  const streamAccumRef    = useRef(''); // accumulates all streamed tokens — fallback if meta.reply is empty
  const lastHtmlRef       = useRef(null); // always holds the most recently built HTML app

  // Context meter — estimate token usage from character counts (chars/4 ≈ tokens)
  const CONTEXT_MAX_TOKENS = 32000;
  const contextPct = useMemo(() => {
    if (!messages.length) return 0;
    const chars = messages.reduce((sum, m) => sum + (m.content?.length || 0), 0);
    const tokens = Math.round(chars / 4);
    return Math.min(100, Math.round((tokens / CONTEXT_MAX_TOKENS) * 100));
  }, [messages]);

  // Track last built HTML so the AI always has its code even after compaction
  useEffect(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const c = messages[i]?.content || '';
      const fenced = /```html\s*\n([\s\S]+?)```/.exec(c);
      if (fenced) { lastHtmlRef.current = fenced[1]; break; }
      const raw = /<!DOCTYPE\s+html/i.exec(c);
      if (raw) { lastHtmlRef.current = c.slice(raw.index); break; }
    }
  }, [messages]);


  // Comparison state — set when it's time for a showdown
  const [compareData, setCompareData]     = useState(null); // {replyA, modelA, replyB, modelB, nextMessages, chatId}
  const [compareLoading, setCompareLoading] = useState(false);

  // Scroll-to-bottom button — visible when user scrolls > 200px from bottom
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  // Load messages when active chat changes
  useEffect(() => {
    if (activeChatId !== currentChatIdRef.current) {
      currentChatIdRef.current = activeChatId;
      if (activeChatId) {
        const chat = chats.find((c) => c.id === activeChatId);
        setMessages(chat ? chat.messages : []);
      } else {
        setMessages([]);
      }
      sessionIdRef.current = crypto.randomUUID();
      responseCountRef.current = 0;
      setCompareData(null);
      setCompareLoading(false);
      // Restore this chat's preview image (null if none was generated yet)
      const chat = chats.find((c) => c.id === activeChatId);
      setPreviewImage(chat?.previewImage || null);
    }
  }, [activeChatId, chats]);

  // Auto-scroll to bottom on new message, loading change, or streaming text
  useEffect(() => {
    if (!showScrollBtn) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loading, streamActive, streamingText, showScrollBtn]);

  // Show/hide scroll-to-bottom button based on distance from bottom
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const onScroll = () => {
      const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      setShowScrollBtn(distFromBottom > 200);
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  // Persist right panel open/closed state across refreshes
  useEffect(() => {
    localStorage.setItem('rightPanelOpen', rightPanelOpen ? 'true' : 'false');
  }, [rightPanelOpen]);

  // Keyboard shortcuts: Ctrl+K = new chat, Esc = cancel generation
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape' && loading) {
        cancel(sessionIdRef.current);
        setStreamActive(false);
        setStreamingText(null);
        submittingRef.current = false;
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        newChat();
        setPage('chat');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [loading, cancel, newChat, setPage]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-fire queued message once loading finishes
  useEffect(() => {
    if (!loading && !submittingRef.current && pendingMsgRef.current) {
      const pending = pendingMsgRef.current;
      pendingMsgRef.current = null;
      handleSubmit(pending.text, pending.imagesBase64, pending.preferredModel);
    }
  }, [loading]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = useCallback(async (text, imagesBase64 = null, preferredModel = null) => {
    if (submittingRef.current || loading) {
      // Queue the message — auto-sent when current response finishes
      pendingMsgRef.current = { text, imagesBase64, preferredModel };
      toast.info('Queued — will send when Mini finishes responding.', { duration: 2000 });
      return;
    }
    const imgs = Array.isArray(imagesBase64) ? imagesBase64.filter(Boolean) : (imagesBase64 ? [imagesBase64] : []);
    if (!text && !imgs.length) return;

    // Image generation limit gate — uses server-authoritative imageUsage (not localStorage)
    // Only block if this is a pure generation request (no reference image attached).
    // When a reference image is attached the message falls through to the vision/chat brain,
    // which can analyze/describe the image without consuming an image credit.
    const _isImgRequest = !imgs.length && (chatMode === 'image' || isImageIntent(text));
    if (_isImgRequest && !canGenerateImage(imageUsage)) {
      setImageLimitOpen(true);
      toast.error(`Image limit reached (${imageUsage.used}/${imageUsage.limit}). Upgrade for more.`);
      submittingRef.current = false;
      return;
    }

    submittingRef.current = true;
    lastUserTextRef.current = text;

    // ── Phase 1 Orchestration gate ───────────────────────────────────────────
    // Only run for builder mode or when there's existing code — chat is always fast-path.
    const _orchMode = chatMode === 'build' ? 'builder' : chatMode === 'image' ? 'image' : 'chat';
    const _hasCode  = !!lastHtmlRef.current;
    const _needsOrch = (_orchMode === 'builder') && !vibeMode && !imgs.length;

    if (_needsOrch) {
      // Run analysis in background — don't block user message appearing
      orchAnalyze({
        message:         text,
        sessionId:       sessionIdRef.current,
        mode:            _orchMode,
        history:         messages,
        hasExistingCode: _hasCode,
        vibeMode,
      }).then(result => {
        if (!result) return;
        // Fast path: act immediately — no card needed
        if (result.proceed_immediately && result.decision === 'act') {
          orchReset();
          return;
        }
        // Slow path: show card — pause execution until user confirms
        submittingRef.current = false;
        setOrchPendingSubmit({ text, imgs, preferredModel });
      });
    }

    // Generate a unique request_id for this submission (used for image deduplication)
    const requestId = crypto.randomUUID();

    let chatId = activeChatId;
    if (!chatId) {
      chatId = newChat();
      currentChatIdRef.current = chatId;
      sessionIdRef.current = crypto.randomUUID();
      setPage('chat');
    }

    const userMsg = {
      role: 'user',
      type: imgs.length ? 'image_input' : 'text',
      content: text,
      image_base64: imgs[0] || null,
      images_base64: imgs.length > 1 ? imgs : null,
      timestamp: Date.now(),
    };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    updateChatMessages(chatId, nextMessages);

    if (chatMode === 'build' || isBuildIntent(text, null)) setRightPanelOpen(true);

    // chatMode overrides all auto-detection:
    // 'image' → always generate image (unless a reference image is attached — DALL-E 3 can't do img2img,
    //            so fall through to vision brain which can analyse/describe the reference)
    // 'build' → always stream to builder
    const imageIntentDetected = chatMode === 'image' || (chatMode === null && isImageIntent(text));

    // ── IMAGE path: non-streaming endpoint (generation only, not analysis) ──
    // Blocked when a reference image is attached (DALL-E 3 has no img2img) or in build mode
    if (imageIntentDetected && !imgs.length && chatMode !== 'build') {
      if (imageIntentDetected) {
        setMessages([...nextMessages, {
          role: 'assistant', type: 'image_generating',
          content: 'Rendering your image...', timestamp: Date.now(), _placeholder: true,
        }]);
      }
      setStreamPrompt(text);
      setStreamResponse(null);
      setStreamActive(true);

      try {
        const history = nextMessages.slice(0, -1).map(m => ({ role: m.role, content: m.content }));
        const data = await send(text, sessionIdRef.current, history, imgs.length ? imgs : null, preferredModel, requestId);
        setStreamResponse(data);

        const isImg = !!data.image_base64;
        if (isImg) {
          // Show image in Preview panel, not in chat — persist per-chat
          setPreviewImage(data.image_base64);
          setRightPanelOpen(true);
          updateChatPreviewImage(chatId, data.image_base64);
          const thumb = await makeThumbnail(data.image_base64);
          await addImage(thumb, text, data.image_base64);
          incrementImageUsage();
        }

        const assistantMsg = {
          role: 'assistant',
          type: 'text',
          content: isImg
            ? '🎨 Image generated! Check the **Preview** panel →'
            : (data.reply || 'Done.'),
          route_result: data.route_result || null,
          generation_time_ms: data.generation_time_ms || null,
          model_used: data.model_used || null,
          memory_stored: data.memory_stored || [],
          timestamp: Date.now(),
        };
        const withAssistant = [...nextMessages, assistantMsg];
        setMessages(withAssistant);
        updateChatMessages(chatId, withAssistant);
      } catch (err) {
        setStreamActive(false);
        const _isRL = err.status === 429 || err.message?.includes('rate limit');
        const withErr = [...nextMessages, {
          role: 'assistant', type: 'error',
          content: _isRL
            ? 'Hold on! Let me catch up — try again in a few seconds.'
            : (err.message || 'Something went wrong.'),
          timestamp: Date.now(),
        }];
        setMessages(withErr);
        updateChatMessages(chatId, withErr);
      } finally {
        submittingRef.current = false;
      }
      return;
    }

    // ── TEXT path: streaming ───────────────────────────────────────────────
    // Show a live-updating streaming bubble immediately
    setStreamingText('');
    streamAccumRef.current = ''; // reset accumulator for this response

    const chatIdRef_local = chatId; // capture for callbacks
    const history = nextMessages.slice(0, -1).map(m => {
      if (m._is_summary) return { role: 'user', content: `[EARLIER CONVERSATION SUMMARY]\n${m.content}` };
      return { role: m.role, content: m.content };
    });

    // If no HTML code is visible in current history (e.g. after compaction) but we have
    // one stored, inject it as a pinned assistant message so the AI can always patch it.
    const historyHasHtml = history.some(m => m.role === 'assistant' && /```html/i.test(m.content || ''));
    if (!historyHasHtml && lastHtmlRef.current) {
      history.push({
        role: 'assistant',
        content: `Here is the current app code:\n\`\`\`html\n${lastHtmlRef.current}\n\`\`\``,
      });
    }

    await sendStream(text, sessionIdRef.current, history, imgs.length ? imgs : null, {
      vibeMode,
      chatMode,
      onToken(token) {
        streamAccumRef.current += token;
        setStreamingText(prev => (prev === null ? token : prev + token));
      },

      async onDone(meta) {
        // Backend signalled image redirect — fall back to non-streaming
        if (meta.type === 'image_redirect') {
          setStreamingText(null);
          setStreamPrompt(text);
          setStreamResponse(null);
          setStreamActive(true);
          setMessages([...nextMessages, {
            role: 'assistant', type: 'image_generating',
            content: 'Rendering your image...', timestamp: Date.now(), _placeholder: true,
          }]);
          try {
            const data = await send(text, sessionIdRef.current, history, imgs.length ? imgs : null, preferredModel, requestId);
            setStreamResponse(data);
            const isImg = !!data.image_base64;
            if (isImg) {
              setPreviewImage(data.image_base64);
              setRightPanelOpen(true);
              updateChatPreviewImage(chatIdRef_local, data.image_base64);
              const thumb = await makeThumbnail(data.image_base64);
              await addImage(thumb, text, data.image_base64);
              incrementImageUsage();
            }
            const assistantMsg = {
              role: 'assistant', type: 'text',
              content: isImg
                ? '🎨 Image generated! Check the **Preview** panel →'
                : (data.reply || ''),
              route_result: data.route_result || null,
              generation_time_ms: data.generation_time_ms || null,
              model_used: data.model_used || null, memory_stored: data.memory_stored || [],
              timestamp: Date.now(),
            };
            const withA = [...nextMessages, assistantMsg];
            setMessages(withA);
            updateChatMessages(chatIdRef_local, withA);
          } catch (err) {
            const withErr = [...nextMessages, {
              role: 'assistant', type: 'error',
              content: err.message || 'Something went wrong.', timestamp: Date.now(),
            }];
            setMessages(withErr);
            updateChatMessages(chatIdRef_local, withErr);
          }
          setStreamingText(null);
          submittingRef.current = false;
          return;
        }

        // Normal text done — finalise message with metadata
        responseCountRef.current += 1;
        const isCompareRound = responseCountRef.current % 10 === 0;

        const _msgId = crypto.randomUUID();
        const finalMsg = {
          role: 'assistant', type: 'text',
          content: meta.reply || streamAccumRef.current || '',
          route_result: meta.route_result || null,
          model_used: meta.model_used || null,
          memory_stored: meta.memory_stored || [],
          timestamp: Date.now(),
          _id: _msgId,
          suggestions: [],
        };
        const withFinal = [...nextMessages, finalMsg];
        setMessages(withFinal);
        updateChatMessages(chatIdRef_local, withFinal);
        setStreamingText(null);
        submittingRef.current = false;

        // Background: fetch follow-up suggestions (non-blocking)
        // Skip if the reply is an error message — suggestions would be irrelevant
        const _isErrorReply = meta.reply && (
          meta.reply.startsWith('Mini Assistant ran into') ||
          meta.reply.startsWith('Mini Assistant may be offline') ||
          meta.reply.startsWith('Mini Assistant is taking longer') ||
          meta.reply.startsWith('The AI model isn')
        );
        if (meta.reply && text && !_isErrorReply) {
          api.getSuggestions(text, meta.reply).then(data => {
            if (data?.suggestions?.length) {
              setMessages(prev => prev.map(m => m._id === _msgId ? { ...m, suggestions: data.suggestions } : m));
            }
          }).catch(() => {});
        }

        // Auto-title: on first response, rename 'New Chat' to truncated user message
        if (responseCountRef.current === 1 && text) {
          const currentChat = chats.find(c => c.id === chatIdRef_local);
          if (currentChat && currentChat.title === 'New Chat') {
            const autoTitle = text.trim().slice(0, 45) + (text.trim().length > 45 ? '…' : '');
            renameChat(chatIdRef_local, autoTitle);
          }
        }

        // Every 10th response: kick off a model showdown in the background
        if (isCompareRound) {
          setCompareLoading(true);
          setCompareData(null);
          api.chatCompare(text, sessionIdRef.current, history)
            .then(data => {
              setCompareData({
                replyA: data.reply_a,
                modelA: data.model_a,
                replyB: data.reply_b,
                modelB: data.model_b,
                nextMessages: withFinal,
                chatId: chatIdRef_local,
              });
            })
            .catch(() => { /* non-fatal — skip compare quietly */ })
            .finally(() => setCompareLoading(false));
        }

        // Check for tool approval
        const approvalIdMatch = meta.reply && meta.reply.match(/Approval ID: `([^`]+)`/);
        if (approvalIdMatch) {
          try {
            const approvals = await api.listApprovals(sessionIdRef.current);
            const found = (approvals.approvals || []).find(a => a.id === approvalIdMatch[1]);
            if (found) setPendingApproval(found);
          } catch (_) { /* non-fatal */ }
        }
        if (isBuildIntent(text, meta.route_result)) setRightPanelOpen(true);
      },

      onError(err) {
        const isOutOfCredits = err.message === 'out_of_credits';
        const isRateLimit = err.message?.startsWith('rate_limit:') || err.status === 429 || err.message?.includes('rate limit');
        const retryAfter = isRateLimit
          ? (err.message?.startsWith('rate_limit:') ? parseInt(err.message.split(':')[1], 10) : 30)
          : null;
        const withErr = [...nextMessages, {
          role: 'assistant', type: 'error',
          content: isOutOfCredits
            ? '⚡ You\'ve used all your Mini Credits. Subscribe to keep building.'
            : isRateLimit
            ? 'Hold on! Let me catch up…'
            : (err.message || 'Something went wrong.'),
          timestamp: Date.now(),
          _outOfCredits: isOutOfCredits,
          _retryAfter: retryAfter,
        }];
        setMessages(withErr);
        updateChatMessages(chatIdRef_local, withErr);
        setStreamingText(null);
        submittingRef.current = false;
      },
    });
  }, [activeChatId, chats, loading, messages, newChat, renameChat, send, sendStream, updateChatMessages, addImage, setPage, chatMode, vibeMode, imageUsage, isSubscribed, plan]);

  const handleCancel = useCallback(() => {
    cancel(sessionIdRef.current);
    setStreamActive(false);
    setStreamingText(null);
    submittingRef.current = false;
  }, [cancel]);

  const handleApprove = useCallback(async (approvalId) => {
    setPendingApproval(null);
    try {
      const result = await api.approveTool(approvalId);
      const resultMsg = {
        role: 'assistant',
        type: 'text',
        content: result.status === 'success'
          ? `\`\`\`\n${result.output || '(no output)'}\n\`\`\``
          : `❌ Error (exit ${result.exit_code}):\n\`\`\`\n${result.error || result.output}\n\`\`\``,
        timestamp: Date.now(),
      };
      setMessages(prev => {
        const next = [...prev, resultMsg];
        if (activeChatId) updateChatMessages(activeChatId, next);
        return next;
      });
    } catch (err) {
      toast.error(`Tool execution failed: ${err.message}`);
    }
  }, [activeChatId, updateChatMessages]);

  const handleDeny = useCallback(async (approvalId) => {
    setPendingApproval(null);
    try {
      await api.denyTool(approvalId);
      toast.info('Tool execution denied.');
    } catch (_) { /* non-fatal */ }
  }, []);

  // Called when user picks a preferred response in the comparison bubble
  const handleComparePick = useCallback((reply, modelUsed) => {
    if (!compareData) return;
    const pickedMsg = {
      role: 'assistant', type: 'text',
      content: reply,
      model_used: modelUsed,
      timestamp: Date.now(),
      _from_compare: true,
    };
    const withPicked = [...compareData.nextMessages, pickedMsg];
    setMessages(withPicked);
    updateChatMessages(compareData.chatId, withPicked);
    setCompareData(null);
  }, [compareData, updateChatMessages]);

  // Called by CognitiveStream after its auto-collapse animation finishes
  const handleStreamDone = useCallback(() => {
    setStreamActive(false);
    setStreamResponse(null);
    setStreamPrompt('');
  }, []);

  const showHero = messages.length === 0;

  if (showHero) {
    return (
      <HomeHero
        onSubmit={handleSubmit}
        loading={loading}
        lastTopic={lastUserTextRef.current || null}
        chatMode={chatMode}
        onChatModeChange={mode => { setChatMode(mode); if (mode) localStorage.setItem('chatMode', mode); else localStorage.removeItem('chatMode'); }}
      />
    );
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Phase 8: Tool Approval Modal */}
      {pendingApproval && (
        <ApprovalModal
          approval={pendingApproval}
          onApprove={handleApprove}
          onDeny={handleDeny}
        />
      )}

      {/* Image limit reached modal */}
      {imageLimitOpen && (
        <ImageLimitModal
          onClose={() => setImageLimitOpen(false)}
          onUpgrade={() => { setImageLimitOpen(false); setPage('pricing'); }}
        />
      )}

      {/* Creation Record Export modal */}
      {showExportRecordModal && (() => {
        const _chat = chats.find(c => c.id === activeChatId);
        return (
          <ExportRecordModal
            projectTitle={_chat?.title || 'Chat Export'}
            onCancel={() => setShowExportRecordModal(false)}
            onExport={async ({ creatorName, description, notes }) => {
              setShowExportRecordModal(false);
              try {
                const history = (_chat?.messages || [])
                  .filter(m => m.role === 'user' || m.role === 'assistant')
                  .map(m => ({ role: m.role, content: m.content || '' }));
                const res = await api.post('/api/creation/export', {
                  project_id:    activeChatId,
                  project_title: _chat?.title || 'Chat',
                  created_at:    _chat?.createdAt || new Date().toISOString(),
                  history,
                  creator_name:  creatorName,
                  description,
                  notes,
                  export_format: 'json',
                });
                const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
                const url  = URL.createObjectURL(blob);
                const slug = (_chat?.title || 'record').replace(/[^a-z0-9]/gi, '_').toLowerCase();
                const a    = document.createElement('a');
                a.href     = url;
                a.download = `${slug}_creation_record.json`;
                a.click();
                URL.revokeObjectURL(url);
                toast.success('Creation record exported.');
              } catch (err) {
                console.error('[CreationRecord] export failed:', err);
                toast.error('Export failed — please try again.');
              }
            }}
          />
        );
      })()}

      {/* ── Chat center column ── */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Chat header — title + export */}
        {activeChatId && (
          <div className="flex items-center justify-between px-4 md:px-10 lg:px-16 py-2 border-b border-white/5 flex-shrink-0">
            <span className="text-[11px] font-mono text-slate-600 truncate">
              {chats.find(c => c.id === activeChatId)?.title || 'Chat'}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => handleExport('md')}
                title="Export as Markdown"
                className="flex items-center gap-1 text-[11px] text-slate-600 hover:text-slate-300 transition-colors px-2 py-1 rounded hover:bg-white/5"
              >
                <Download size={12} />
                MD
              </button>
              <button
                onClick={() => handleExport('html')}
                title="Export as HTML"
                className="flex items-center gap-1 text-[11px] text-slate-600 hover:text-slate-300 transition-colors px-2 py-1 rounded hover:bg-white/5"
              >
                <Download size={12} />
                HTML
              </button>
              <button
                onClick={() => setShowExportRecordModal(true)}
                title="Export Creation Record"
                className="flex items-center gap-1 text-[11px] text-slate-600 hover:text-violet-400 transition-colors px-2 py-1 rounded hover:bg-white/5"
              >
                <Download size={12} />
                Record
              </button>
            </div>
          </div>
        )}

        {/* Messages */}
        <div className="relative flex-1 overflow-hidden">
        <div ref={scrollContainerRef} className="h-full overflow-y-auto px-3 sm:px-6 md:px-10 lg:px-16 py-4 sm:py-6 space-y-4 sm:space-y-6">
          {messages.map((msg, idx) => {
            if (msg._outOfCredits) {
              return (
                <OutOfCreditsCard
                  key={idx}
                  onBuy={() => setPurchaseModalOpen(true)}
                  onUpgrade={() => openUpgradeModal('credits')}
                />
              );
            }
            const isBuildResponse = msg.role === 'assistant' && (
              msg.content?.includes('```html') || msg.content?.includes('<!DOCTYPE')
            );
            // Show "Agent Finished" separator after build responses (not after the last message if still streaming)
            const showFinishedSep = isBuildResponse && (idx < messages.length - 1 || !loading);
            return (
              <React.Fragment key={idx}>
                <ChatMessage
                  message={msg}
                  onRetry={msg.role === 'assistant' ? () => {
                    const prevUser = messages.slice(0, idx).reverse().find(m => m.role === 'user');
                    if (prevUser) handleSubmit(
                      prevUser.content,
                      prevUser.images_base64 || (prevUser.image_base64 ? [prevUser.image_base64] : null)
                    );
                  } : undefined}
                  onRate={msg.role === 'assistant' ? (rating) => rateMessage(activeChatId, idx, rating) : undefined}
                  onFork={msg.role === 'assistant' && activeChatId ? () => forkChat(activeChatId, idx) : undefined}
                  onSendToBuilder={msg.role === 'assistant' && msg.content?.includes('```') ? () => setRightPanelOpen(true) : undefined}
                  onPin={activeChatId ? () => pinMessage(activeChatId, idx) : undefined}
                  onSuggest={msg.role === 'assistant' ? (text) => handleSubmit(text) : undefined}
                />
                {showFinishedSep && (
                  <div className="flex items-center gap-3 py-1">
                    <div className="flex-1 h-px bg-emerald-500/20" />
                    <span className="text-[9px] font-mono text-emerald-500/60 uppercase tracking-widest flex items-center gap-1.5">
                      <span style={{ display:'inline-block', width:5, height:5, borderRadius:'50%', background:'#10b981', boxShadow:'0 0 6px rgba(16,185,129,0.8)' }} />
                      Agent Finished
                    </span>
                    <div className="flex-1 h-px bg-emerald-500/20" />
                  </div>
                )}
              </React.Fragment>
            );
          })}

          {/* Extended thinking indicator — shown while Claude reasons before first token */}
          {streamingText === '' && loading && (
            <div className="flex items-center gap-3 px-4 py-3 rounded-2xl max-w-xs"
              style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.18)' }}>
              <div className="flex items-center gap-[5px]">
                {[0,1,2,3].map(i => (
                  <div key={i} style={{
                    width: 5, height: 5, borderRadius: '50%',
                    background: 'linear-gradient(135deg,#818cf8,#a78bfa)',
                    animation: `pulse 1.4s ease-in-out ${i * 0.18}s infinite`,
                    opacity: 0.8,
                  }} />
                ))}
              </div>
              <span className="text-[11px] font-medium" style={{ color: '#a5b4fc' }}>
                Reasoning through your request…
                {thinkingSeconds > 0 && (
                  <span style={{ color: '#7c3aed', marginLeft: 6, fontVariantNumeric: 'tabular-nums', fontSize: 10 }}>
                    {thinkingSeconds}s
                  </span>
                )}
              </span>
            </div>
          )}

          {/* Live streaming text bubble */}
          {streamingText !== null && streamingText !== '' && (
            <StreamingBubble
              text={streamingText}
              existingCode={(() => {
                // Find the last HTML app code in message history for the scanner
                for (let i = messages.length - 1; i >= 0; i--) {
                  const c = messages[i]?.content || '';
                  const m = /```html\s*\n([\s\S]+?)```/.exec(c);
                  if (m) return m[1];
                  const raw = /<!DOCTYPE\s+html/i.exec(c);
                  if (raw) return c.slice(raw.index);
                }
                return null;
              })()}
            />
          )}

          {/* Cognitive stream + dots bubble while loading (image/non-streaming path) */}
          {loading && streamingText === null && (
            <div className="space-y-3">
              <CognitiveStream
                active={streamActive}
                prompt={streamPrompt}
                response={streamResponse}
                onDone={handleStreamDone}
              />
              {!streamActive && <LoadingBubble />}
            </div>
          )}

          {/* Model comparison bubble — shown every 10 responses */}
          {(compareData || compareLoading) && (
            <ComparisonBubble
              replyA={compareData?.replyA || ''}
              modelA={compareData?.modelA || 'Model A'}
              replyB={compareData?.replyB || ''}
              modelB={compareData?.modelB || 'Model B'}
              loading={compareLoading}
              onPick={handleComparePick}
            />
          )}

          <div ref={bottomRef} />
        </div>

        {/* Scroll-to-bottom floating button */}
        {showScrollBtn && (
          <button
            onClick={() => {
              setShowScrollBtn(false);
              bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
            }}
            className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-3 py-1.5 rounded-full
              bg-[#1a1a2e] border border-white/10 text-slate-400 hover:text-slate-200 hover:border-cyan-500/30
              text-xs shadow-lg transition-all hover:bg-[#1e1e35] z-10"
          >
            <ChevronDown size={13} />
            Scroll to bottom
          </button>
        )}
        </div>

        {/* Input footer */}
        <div className="flex-shrink-0 border-t border-white/5 px-4 md:px-10 lg:px-16 py-4 bg-[#0d0d12]">
          {/* Context meter */}
          {contextPct > 0 && (
            <div className="mb-3 flex items-center gap-2">
              <div className={`flex-1 relative h-[3px] rounded-full overflow-hidden ${contextPct >= 90 ? 'animate-pulse' : ''}`} style={{ background: 'rgba(255,255,255,0.05)' }}>
                <div
                  className="absolute left-0 top-0 h-full rounded-full transition-all duration-700"
                  style={{
                    width: `${contextPct}%`,
                    background: contextPct >= 90
                      ? 'linear-gradient(90deg, #f97316, #ef4444)'
                      : contextPct >= 70
                      ? 'linear-gradient(90deg, #eab308, #f97316)'
                      : contextPct >= 40
                      ? 'linear-gradient(90deg, #06b6d4, #6366f1)'
                      : 'linear-gradient(90deg, #22d3ee, #818cf8)',
                    boxShadow: contextPct >= 90
                      ? '0 0 6px rgba(239,68,68,0.6)'
                      : contextPct >= 70
                      ? '0 0 6px rgba(234,179,8,0.5)'
                      : '0 0 4px rgba(99,102,241,0.4)',
                  }}
                />
              </div>
              <span
                className="text-[9px] font-mono tabular-nums flex-shrink-0"
                style={{
                  color: contextPct >= 90 ? '#f87171'
                    : contextPct >= 70 ? '#fbbf24'
                    : '#64748b',
                }}
              >
                {contextPct}%
              </span>
            </div>
          )}
          {/* ── Orchestration UI (Phase 1) ─────────────────────────────── */}
          {orchStatus === ORCH_STATUS.ANALYZING && (
            <div className="px-2 pb-2">
              <ThinkingSequence status={orchStatus} />
            </div>
          )}
          {orchStatus === ORCH_STATUS.DONE && orchAnalysis && !orchAnalysis.proceed_immediately && (
            <div className="px-2 pb-2">
              <TaskSummaryCard
                analysis={orchAnalysis}
                onProceed={() => {
                  const pending = orchPendingSubmit;
                  orchReset();
                  setOrchPendingSubmit(null);
                  if (pending) handleSubmit(pending.text, pending.imgs, pending.preferredModel);
                }}
                onModify={() => {
                  orchReset();
                  setOrchPendingSubmit(null);
                  submittingRef.current = false;
                }}
                onSplit={() => {
                  // Auto-split: add "[split into steps]" suffix and re-submit
                  const pending = orchPendingSubmit;
                  orchReset();
                  setOrchPendingSubmit(null);
                  if (pending) handleSubmit(`${pending.text}\n\n[Please break this into clear numbered steps and do them one at a time, pausing to confirm after each.]`, pending.imgs, pending.preferredModel);
                }}
                onClarify={(choice) => {
                  // User selected an interpretation — re-submit with chosen wording
                  const pending = orchPendingSubmit;
                  orchReset();
                  setOrchPendingSubmit(null);
                  if (pending) handleSubmit(choice, pending.imgs, pending.preferredModel);
                }}
                onDismiss={() => {
                  orchReset();
                  setOrchPendingSubmit(null);
                  submittingRef.current = false;
                }}
              />
            </div>
          )}

          <div className="relative">
            <ChatInput
              variant="chat"
              onSubmit={handleSubmit}
              loading={loading}
              placeholder={
                chatMode === 'image' ? '🎨 Image Mode — describe what you want to generate…' :
                chatMode === 'build' ? '🔨 Build Mode — describe the app you want built…' :
                rightPanelOpen ? 'Describe changes or chat…' :
                'Message Mini Assistant…'
              }
              chatMode={chatMode}
              onChatModeChange={mode => { setChatMode(mode); if (mode) localStorage.setItem('chatMode', mode); else localStorage.removeItem('chatMode'); }}
            />
          </div>
          <div className="flex items-center justify-between mt-2">
            {loading && (
              <button
                onClick={handleCancel}
                className="text-[11px] text-slate-600 hover:text-slate-400 transition-colors font-mono"
              >
                Stop generating
              </button>
            )}
            {!loading && <div />}
            <button
              onClick={() => setRightPanelOpen(v => !v)}
              title={rightPanelOpen ? 'Close preview panel' : 'Open preview panel'}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] transition-colors
                ${rightPanelOpen
                  ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20'
                  : 'bg-white/5 text-slate-500 hover:text-slate-300 border border-white/5'}`}
            >
              <PanelRight size={12} />
              {rightPanelOpen ? 'Hide Preview' : 'Show Preview'}
            </button>
          </div>
        </div>
      </div>

      {/* ── Right panel ── */}
      <RightPanel
        messages={messages}
        streamingText={streamingText}
        open={rightPanelOpen}
        onClose={() => setRightPanelOpen(false)}
        previewImage={previewImage}
        onClearImage={() => { setPreviewImage(null); updateChatPreviewImage(activeChatId, null); }}
        sessionId={sessionIdRef.current}
        onFixedHtml={(fixedHtml) => {
          // Add the auto-fixed code to chat history so it becomes the new "latest version"
          const fixMsg = {
            role: 'assistant', type: 'text',
            content: `🔧 Auto-Fix complete:\n\`\`\`html\n${fixedHtml}\n\`\`\`\n\nAll bugs patched — give it a try! 🎮`,
            timestamp: Date.now(),
          };
          setMessages(prev => {
            const updated = [...prev, fixMsg];
            if (activeChatId) updateChatMessages(activeChatId, updated);
            return updated;
          });
        }}
        onRestoreCode={(restoredHtml) => {
          const restoreMsg = {
            role: 'assistant', type: 'text',
            content: `↩️ Restored to previous version:\n\`\`\`html\n${restoredHtml}\n\`\`\``,
            timestamp: Date.now(),
          };
          setMessages(prev => {
            const updated = [...prev, restoreMsg];
            if (activeChatId) updateChatMessages(activeChatId, updated);
            return updated;
          });
        }}
        onBuildScreenshot={(screenshotB64, analysisText) => {
          const shotMsg = {
            role: 'assistant', type: 'screenshot',
            content: analysisText || '📸 Here\'s what was built:',
            imageB64: screenshotB64,
            timestamp: Date.now(),
          };
          setMessages(prev => {
            const updated = [...prev, shotMsg];
            if (activeChatId) updateChatMessages(activeChatId, updated);
            return updated;
          });
        }}
        onDebugSummary={(passes) => {
          if (!passes?.length) return;
          const lines = passes.map(p =>
            p.pass === 'visual'
              ? (p.fixed ? '🎨 Visual — Layout fixed' : '🎨 Visual — Looks good ✅')
              : p.allClear && p.fixed ? `Pass ${p.pass} — Patched & clean ✅`
              : p.fixed ? `Pass ${p.pass} — Bug patched 🔧`
              : p.allClear ? `Pass ${p.pass} — No issues ✅`
              : `Pass ${p.pass} — No output ⚠️`
          );
          const allGood = passes[passes.length - 1]?.allClear;
          const jsPasses = passes.filter(p => p.pass !== 'visual').length;
          const debugMsg = {
            role: 'assistant', type: 'debug',
            content: `🔍 **Debug Agent** — ${jsPasses} JS pass${jsPasses !== 1 ? 'es' : ''} + visual QA\n${lines.join('\n')}${allGood ? '\n\nAll clear — your app is running clean.' : ''}`,
            timestamp: Date.now(),
          };
          setMessages(prev => {
            const updated = [...prev, debugMsg];
            if (activeChatId) updateChatMessages(activeChatId, updated);
            return updated;
          });
        }}
      />
    </div>
  );
}

export default ChatPage;
