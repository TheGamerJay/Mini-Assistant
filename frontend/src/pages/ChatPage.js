/**
 * pages/ChatPage.js
 * Main chat page. Transitions between HomeHero (no chat) and active conversation.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { useApp, makeThumbnail } from '../context/AppContext';
import { useChat } from '../hooks/useChat';
import HomeHero from '../components/HomeHero';
import ChatMessage from '../components/ChatMessage';
import ChatInput from '../components/ChatInput';
import MiniOrb from '../components/MiniOrb';
import CognitiveStream from '../components/CognitiveStream';
import ApprovalModal from '../components/ApprovalModal';
import api from '../api/client';

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

function ChatPage() {
  const {
    activeChatId,
    chats,
    newChat,
    updateChatMessages,
    addImage,
    setPage,
  } = useApp();

  const { send, cancel, loading } = useChat();
  const [messages, setMessages]   = useState([]);
  const [pendingApproval, setPendingApproval] = useState(null);

  // Cognitive stream state
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

  // Auto-scroll to bottom on new message or loading change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, streamActive]);

  const handleSubmit = useCallback(async (text, imageBase64 = null, preferredModel = null) => {
    if (submittingRef.current || loading) return;
    if (!text || text.trim().length < 3) {
      toast.warning('Message too short (min 3 characters)');
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

    // Build user message — include image preview if attached
    const userMsg = {
      role: 'user',
      type: imageBase64 ? 'image_input' : 'text',
      content: text,
      image_base64: imageBase64 || null,
      timestamp: Date.now(),
    };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    updateChatMessages(chatId, nextMessages);

    // Kick off the cognitive stream
    setStreamPrompt(text);
    setStreamResponse(null);
    setStreamActive(true);

    try {
      const history = nextMessages.slice(0, -1).map(m => ({ role: m.role, content: m.content }));
      const data = await send(text, sessionIdRef.current, history, imageBase64, preferredModel);

      // Pass real response data to the stream so stages can show actual results
      setStreamResponse(data);

      const isImage = !!data.image_base64;
      let thumb = null;
      if (isImage && data.image_base64) {
        thumb = await makeThumbnail(data.image_base64);
        await addImage(thumb, text, data.image_base64);
      }

      // Check if the reply contains a pending approval request
      const approvalIdMatch = data.reply && data.reply.match(/Approval ID: `([^`]+)`/);
      if (approvalIdMatch) {
        try {
          const approvals = await api.listApprovals(sessionIdRef.current);
          const found = (approvals.approvals || []).find(a => a.id === approvalIdMatch[1]);
          if (found) setPendingApproval(found);
        } catch (_) { /* non-fatal */ }
      }

      const assistantMsg = {
        role: 'assistant',
        type: isImage ? 'image' : 'text',
        content: data.reply || (isImage ? '' : 'Done.'),
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
      const errMsg = {
        role: 'assistant',
        type: 'error',
        content: err.message || 'Something went wrong. Please try again.',
        timestamp: Date.now(),
      };
      const withErr = [...nextMessages, errMsg];
      setMessages(withErr);
      updateChatMessages(chatId, withErr);
    } finally {
      submittingRef.current = false;
    }
  }, [activeChatId, loading, messages, newChat, send, updateChatMessages, addImage, setPage]);

  const handleCancel = useCallback(() => {
    cancel(sessionIdRef.current);
    setStreamActive(false);
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
    <div className="flex flex-col h-full">
      {/* Phase 8: Tool Approval Modal */}
      {pendingApproval && (
        <ApprovalModal
          approval={pendingApproval}
          onApprove={handleApprove}
          onDeny={handleDeny}
        />
      )}
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 md:px-12 lg:px-24 py-6 space-y-6">
        {messages.map((msg, idx) => (
          <ChatMessage
            key={idx}
            message={msg}
            onRetry={msg.type === 'error' ? () => handleSubmit(lastUserTextRef.current) : undefined}
          />
        ))}

        {/* Cognitive stream + dots bubble while loading */}
        {loading && (
          <div className="space-y-3">
            <CognitiveStream
              active={streamActive}
              prompt={streamPrompt}
              response={streamResponse}
              onDone={handleStreamDone}
            />
            {/* Dots bubble only when stream has collapsed or hasn't mounted yet */}
            {!streamActive && <LoadingBubble />}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input footer */}
      <div className="flex-shrink-0 border-t border-white/5 px-4 md:px-12 lg:px-24 py-4 bg-[#0d0d12]">
        <div className="relative">
          <ChatInput
            variant="chat"
            onSubmit={handleSubmit}
            loading={loading}
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
        {loading && (
          <div className="flex justify-center mt-2">
            <button
              onClick={handleCancel}
              className="text-[11px] text-slate-600 hover:text-slate-400 transition-colors font-mono"
            >
              Stop generating
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default ChatPage;
