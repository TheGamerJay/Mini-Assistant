/**
 * pages/ChatPage.js
 * Main chat page. Transitions between HomeHero (no chat) and active conversation.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { XCircle, PanelRight, Download } from 'lucide-react';
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
  return /\/build|build me|create (a|an|the) (app|website|page|ui|component|form|dashboard)|make (a|an) (web|react|html)|generate (a|an) (app|website|page)/i.test(text);
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
    updateChatMessages,
    addImage,
    setPage,
    rateMessage,
    forkChat,
  } = useApp();

  const handleExport = useCallback(() => {
    const chat = chats.find(c => c.id === activeChatId);
    if (!chat) return;
    const lines = [`# ${chat.title}`, ''];
    chat.messages.forEach(m => {
      if (m.role === 'user') lines.push(`**You:** ${m.content || ''}`, '');
      else if (m.role === 'assistant' && m.type !== 'image_generating') lines.push(`**Mini:** ${m.content || ''}`, '');
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${chat.title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.md`;
    a.click();
    URL.revokeObjectURL(url);
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
  const currentChatIdRef  = useRef(null);
  const submittingRef     = useRef(false);
  const lastUserTextRef   = useRef('');

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
    }
  }, [activeChatId, chats]);

  // Auto-scroll to bottom on new message, loading change, or streaming text
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, streamActive, streamingText]);

  const handleSubmit = useCallback(async (text, imagesBase64 = null, preferredModel = null) => {
    if (submittingRef.current || loading) return;
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

    // ── TEXT path: streaming ───────────────────────────────────────────────
    // Show a live-updating streaming bubble immediately
    setStreamingText('');

    const chatIdRef_local = chatId; // capture for callbacks
    const history = nextMessages.slice(0, -1).map(m => ({ role: m.role, content: m.content }));

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
  }, [activeChatId, loading, messages, newChat, send, sendStream, updateChatMessages, addImage, setPage]);

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
            <button
              onClick={handleExport}
              title="Export chat as Markdown"
              className="flex items-center gap-1.5 text-[11px] text-slate-600 hover:text-slate-300 transition-colors px-2 py-1 rounded hover:bg-white/5"
            >
              <Download size={12} />
              Export
            </button>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 md:px-10 lg:px-16 py-6 space-y-6">
          {messages.map((msg, idx) => (
            <ChatMessage
              key={idx}
              message={msg}
              onRetry={msg.type === 'error' ? () => handleSubmit(lastUserTextRef.current) : undefined}
              onRate={msg.role === 'assistant' ? (rating) => rateMessage(activeChatId, idx, rating) : undefined}
              onFork={msg.role === 'assistant' && activeChatId ? () => forkChat(activeChatId, idx) : undefined}
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

          <div ref={bottomRef} />
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
        open={rightPanelOpen}
        onClose={() => setRightPanelOpen(false)}
      />
    </div>
  );
}

export default ChatPage;
