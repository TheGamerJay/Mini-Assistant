/**
 * pages/ChatPage.js
 * Main chat page. Transitions between HomeHero (no chat) and active conversation.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { PanelRight, Download, ChevronDown, Zap, Star } from 'lucide-react';
import { toast } from 'sonner';
import { useApp, makeThumbnail } from '../context/AppContext';
import { useChat } from '../hooks/useChat';
import HomeHero from '../components/HomeHero';
import ChatMessage from '../components/ChatMessage';
import ChatInput from '../components/ChatInput';
import MiniOrb from '../components/MiniOrb';
import CognitiveStream from '../components/CognitiveStream';
import ApprovalModal from '../components/ApprovalModal';
import RightPanel from '../components/RightPanel';
import ComparisonBubble from '../components/ComparisonBubble';
import api from '../api/client';

const FREE_IMAGE_LIMIT = 2;

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
          <h2 className="text-xl font-bold text-white mb-1">You've used your free images.</h2>
          <p className="text-slate-400 text-sm mb-2">
            You've seen how powerful image generation can be.
          </p>
          <p className="text-slate-300 text-sm font-medium mb-6">
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
  return /\b(draw|paint|generate|create|make|render|design|illustrate|sketch|produce)\b.{0,50}\b(image|photo|picture|illustration|artwork|portrait|landscape|anime|realistic|wallpaper|avatar|banner|logo|thumbnail)\b|\b(image|picture|photo)\s+of\b|\banime\b|\bdigital art\b|\bphoto realistic\b/i.test(text);
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

/** Blinking cursor appended while streaming */
function StreamingBubble({ text }) {
  return (
    <div className="flex items-start gap-3 msg-enter">
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 via-violet-500 to-violet-600 flex items-center justify-center overflow-hidden flex-shrink-0 mt-1">
        <img src="/Logo.png" alt="Mini Assistant" className="w-full h-full object-contain"
          onError={e => { e.target.style.display = 'none'; }} />
      </div>
      <div className="max-w-[92%] sm:max-w-[82%] px-3 sm:px-5 py-3 sm:py-4 rounded-2xl rounded-tl-sm border bg-[#151520] border-white/5 text-sm leading-relaxed text-slate-200 whitespace-pre-wrap">
        {text || <span className="text-slate-600 text-xs italic">Thinking…</span>}
        <span className="inline-block w-0.5 h-3.5 bg-cyan-400 ml-0.5 align-middle animate-pulse" />
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
    images,
    isSubscribed,
    plan,
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
  const [rightPanelOpen, setRightPanelOpen]   = useState(false);
  const [imageLimitOpen, setImageLimitOpen]   = useState(false);
  const [vibeMode, setVibeMode]               = useState(false);
  const [previewImage, setPreviewImage]       = useState(null); // latest generated image → shown in RightPanel

  // Streaming text state (non-image responses)
  const [streamingText, setStreamingText] = useState(null); // null = not streaming

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
  const compactingRef     = useRef(false); // prevents double-compaction while summarize is in-flight

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

    // Image generation limit gate for free users
    const _imgLimit = plan === 'standard' ? 50 : plan === 'pro' ? 200 : plan === 'team' || plan === 'max' ? 1000 : FREE_IMAGE_LIMIT;
    const _isImgRequest = imgs.length > 0 || isImageIntent(text);
    if (!isSubscribed && _isImgRequest && (images || []).length >= _imgLimit) {
      setImageLimitOpen(true);
      submittingRef.current = false;
      return;
    }

    submittingRef.current = true;
    lastUserTextRef.current = text;

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

    if (isBuildIntent(text, null)) setRightPanelOpen(true);

    const imageIntentDetected = isImageIntent(text);

    // ── IMAGE path: non-streaming endpoint (generation only, not analysis) ──
    if (imageIntentDetected && !imgs.length) {
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
        const data = await send(text, sessionIdRef.current, history, imgs.length ? imgs : null, preferredModel);
        setStreamResponse(data);

        const isImg = !!data.image_base64;
        if (isImg) {
          // Show image in Preview panel, not in chat — persist per-chat
          setPreviewImage(data.image_base64);
          setRightPanelOpen(true);
          updateChatPreviewImage(chatId, data.image_base64);
          const thumb = await makeThumbnail(data.image_base64);
          await addImage(thumb, text, data.image_base64);
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
            ? 'Slow down a little! Too many requests. Try again in ~30 seconds.'
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

    const chatIdRef_local = chatId; // capture for callbacks
    const history = nextMessages.slice(0, -1).map(m => {
      if (m._is_summary) return { role: 'user', content: `[EARLIER CONVERSATION SUMMARY]\n${m.content}` };
      return { role: m.role, content: m.content };
    });

    await sendStream(text, sessionIdRef.current, history, imgs.length ? imgs : null, {
      vibeMode,
      onToken(token) {
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
            const data = await send(text, sessionIdRef.current, history, imgs.length ? imgs : null, preferredModel);
            setStreamResponse(data);
            const isImg = !!data.image_base64;
            if (isImg) {
              setPreviewImage(data.image_base64);
              setRightPanelOpen(true);
              updateChatPreviewImage(chatIdRef_local, data.image_base64);
              const thumb = await makeThumbnail(data.image_base64);
              await addImage(thumb, text, data.image_base64);
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
          content: meta.reply || '',
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

        // Auto-compact: when conversation hits 30 messages, summarize old ones
        const COMPACT_THRESHOLD = 30;
        const KEEP_RECENT = 8;
        if (withFinal.length >= COMPACT_THRESHOLD && !compactingRef.current) {
          compactingRef.current = true;
          const toSummarize = withFinal.slice(0, withFinal.length - KEEP_RECENT);
          const toKeep = withFinal.slice(withFinal.length - KEEP_RECENT);
          api.summarizeMessages(toSummarize)
            .then(data => {
              if (!data.summary) return;
              const summaryMsg = {
                role: 'system',
                type: 'summary',
                content: data.summary,
                timestamp: Date.now(),
                _is_summary: true,
              };
              const compacted = [summaryMsg, ...toKeep];
              setMessages(compacted);
              updateChatMessages(chatIdRef_local, compacted);
              toast.info('Conversation compacted — older messages summarized.', { duration: 3500 });
            })
            .catch(() => { /* non-fatal */ })
            .finally(() => { compactingRef.current = false; });
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
            ? `Slow down a little! Too many requests. Try again in ~${retryAfter} seconds.`
            : (err.message || 'Something went wrong.'),
          timestamp: Date.now(),
          _outOfCredits: isOutOfCredits,
        }];
        setMessages(withErr);
        updateChatMessages(chatIdRef_local, withErr);
        setStreamingText(null);
        submittingRef.current = false;
      },
    });
  }, [activeChatId, chats, loading, messages, newChat, renameChat, send, sendStream, updateChatMessages, addImage, setPage, vibeMode, images, isSubscribed, plan]);

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
            return (
              <ChatMessage
                key={idx}
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
            );
          })}

          {/* Live streaming text bubble */}
          {streamingText !== null && (
            <StreamingBubble text={streamingText} />
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
          <div className="relative">
            <ChatInput
              variant="chat"
              onSubmit={handleSubmit}
              loading={loading}
              placeholder={vibeMode ? '⚡ Vibe Code ON — describe or show what you want built…' : rightPanelOpen ? 'Describe changes or chat…' : 'Message Mini Assistant, or say /build to create an app…'}
              vibeMode={vibeMode}
              onVibeModeToggle={() => setVibeMode(v => !v)}
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
      />
    </div>
  );
}

export default ChatPage;
