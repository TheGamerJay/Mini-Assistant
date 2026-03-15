/**
 * pages/ChatPage.js
 * Main chat page. Transitions between HomeHero (no chat) and active conversation.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { XCircle, PanelRight, Download, ChevronDown } from 'lucide-react';
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
      <div className="max-w-[80%] px-5 py-4 rounded-2xl rounded-tl-sm border bg-[#151520] border-white/5 text-sm leading-relaxed text-slate-200 whitespace-pre-wrap">
        {text || <span className="text-slate-600 text-xs italic">Thinking…</span>}
        <span className="inline-block w-0.5 h-3.5 bg-cyan-400 ml-0.5 align-middle animate-pulse" />
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
    addImage,
    setPage,
    rateMessage,
    pinMessage,
    forkChat,
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
          const thumb = await makeThumbnail(data.image_base64);
          await addImage(thumb, text, data.image_base64);
        }

        const assistantMsg = {
          role: 'assistant',
          type: isImg ? 'image' : 'text',
          content: data.reply || (isImg ? '' : 'Done.'),
          image_base64: data.image_base64 || null,
          prompt: text,
          route_result: data.route_result || null,
          generation_time_ms: data.generation_time_ms || null,
          retry_used: data.retry_used || false,
          prompt_warnings: data.prompt_warnings || [],
          model_used: data.model_used || null,
          memory_stored: data.memory_stored || [],
          timestamp: Date.now(),
        };
        const withAssistant = [...nextMessages, assistantMsg];
        setMessages(withAssistant);
        updateChatMessages(chatId, withAssistant);
      } catch (err) {
        setStreamActive(false);
        const withErr = [...nextMessages, {
          role: 'assistant', type: 'error',
          content: err.message || 'Something went wrong.', timestamp: Date.now(),
        }];
        setMessages(withErr);
        updateChatMessages(chatId, withErr);
      } finally {
        submittingRef.current = false;
      }
      return;
    }

    // ── TEXT path: try local Ollama first when images are attached ────────
    // Bypasses the Railway→Cloudflare→Ollama tunnel for image analysis,
    // which avoids 524 timeouts. Falls back to SSE stream if local fails.
    if (imgs.length > 0) {
      setStreamingText('');
      try {
        const localReply = await api.tryLocalOllamaChat(text, imgs[0]);
        const localMsg = {
          role: 'assistant', type: 'text',
          content: localReply,
          model_used: 'gemma3:4b (local)',
          timestamp: Date.now(),
        };
        const withLocal = [...nextMessages, localMsg];
        responseCountRef.current += 1;
        setMessages(withLocal);
        updateChatMessages(chatId, withLocal);
        setStreamingText(null);
        submittingRef.current = false;
        return;
      } catch {
        // Local Ollama unavailable — fall through to SSE stream below
        setStreamingText(null);
      }
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
            const data = await send(text, sessionIdRef.current, history, null, preferredModel);
            setStreamResponse(data);
            const isImg = !!data.image_base64;
            if (isImg) {
              const thumb = await makeThumbnail(data.image_base64);
              await addImage(thumb, text, data.image_base64);
            }
            const assistantMsg = {
              role: 'assistant', type: isImg ? 'image' : 'text',
              content: data.reply || '', image_base64: data.image_base64 || null,
              prompt: text, route_result: data.route_result || null,
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

        const finalMsg = {
          role: 'assistant', type: 'text',
          content: meta.reply || '',
          route_result: meta.route_result || null,
          model_used: meta.model_used || null,
          memory_stored: meta.memory_stored || [],
          timestamp: Date.now(),
        };
        const withFinal = [...nextMessages, finalMsg];
        setMessages(withFinal);
        updateChatMessages(chatIdRef_local, withFinal);
        setStreamingText(null);
        submittingRef.current = false;

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
        const withErr = [...nextMessages, {
          role: 'assistant', type: 'error',
          content: err.message || 'Something went wrong.', timestamp: Date.now(),
        }];
        setMessages(withErr);
        updateChatMessages(chatIdRef_local, withErr);
        setStreamingText(null);
        submittingRef.current = false;
      },
    });
  }, [activeChatId, chats, loading, messages, newChat, renameChat, send, sendStream, updateChatMessages, addImage, setPage]);

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

  const showHero = !activeChatId && messages.length === 0;

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
        <div ref={scrollContainerRef} className="h-full overflow-y-auto px-4 md:px-10 lg:px-16 py-6 space-y-6">
          {messages.map((msg, idx) => (
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
            />
          ))}

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
              placeholder={rightPanelOpen ? 'Describe changes or chat…' : 'Message Mini Assistant, or say /build to create an app…'}
            />
            {loading && (
              <button
                onClick={handleCancel}
                title="Stop generating"
                className="absolute right-[-44px] bottom-2 p-2 rounded-xl text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
              >
                <XCircle size={18} />
              </button>
            )}
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
      />
    </div>
  );
}

export default ChatPage;
