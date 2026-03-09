/**
 * pages/ChatPage.js
 * Main chat page. Transitions between HomeHero (no chat) and active conversation.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Loader2 } from 'lucide-react';
import { useApp, makeThumbnail } from '../context/AppContext';
import { useChat } from '../hooks/useChat';
import HomeHero from '../components/HomeHero';
import ChatMessage from '../components/ChatMessage';
import ChatInput from '../components/ChatInput';

function LoadingBubble() {
  return (
    <div className="flex items-start gap-3">
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-violet-600 flex-shrink-0 flex items-center justify-center text-[10px] font-bold text-white mt-0.5">
        MA
      </div>
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
  const [messages, setMessages] = useState([]);
  const sessionIdRef = useRef(crypto.randomUUID());
  const bottomRef = useRef(null);
  const currentChatIdRef = useRef(null);

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
      // New session per conversation
      sessionIdRef.current = crypto.randomUUID();
    }
  }, [activeChatId, chats]);

  // Auto-scroll to bottom when messages change or loading changes
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loading]);

  const handleSubmit = useCallback(async (text) => {
    let chatId = activeChatId;

    // Create new chat if none is active
    if (!chatId) {
      chatId = newChat();
      currentChatIdRef.current = chatId;
      sessionIdRef.current = crypto.randomUUID();
      // Ensure page is 'chat' (it should already be)
      setPage('chat');
    }

    // Build user message
    const userMsg = {
      role: 'user',
      type: 'text',
      content: text,
      timestamp: Date.now(),
    };

    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    updateChatMessages(chatId, nextMessages);

    try {
      const data = await send(text, sessionIdRef.current);

      const isImage = !!data.image_base64;
      let thumb = null;

      if (isImage && data.image_base64) {
        thumb = await makeThumbnail(data.image_base64);
        await addImage(thumb, text, data.image_base64);
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
        timestamp: Date.now(),
      };

      const withAssistant = [...nextMessages, assistantMsg];
      setMessages(withAssistant);
      updateChatMessages(chatId, withAssistant);
    } catch (err) {
      const errMsg = {
        role: 'assistant',
        type: 'error',
        content: err.message || 'Something went wrong. Please try again.',
        timestamp: Date.now(),
      };
      const withErr = [...nextMessages, errMsg];
      setMessages(withErr);
      updateChatMessages(chatId, withErr);
    }
  }, [activeChatId, messages, newChat, send, updateChatMessages, addImage, setPage]);

  const handleCancel = useCallback(() => {
    cancel(sessionIdRef.current);
  }, [cancel]);

  // Show hero when no active conversation
  const showHero = !activeChatId && messages.length === 0;

  if (showHero) {
    return <HomeHero onSubmit={handleSubmit} loading={loading} />;
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 md:px-12 lg:px-24 py-6 space-y-6">
        {messages.map((msg, idx) => (
          <ChatMessage key={idx} message={msg} />
        ))}
        {loading && <LoadingBubble />}
        <div ref={bottomRef} />
      </div>

      {/* Input footer */}
      <div className="flex-shrink-0 border-t border-white/5 px-4 md:px-12 lg:px-24 py-4 bg-[#0d0d12]">
        <ChatInput
          variant="chat"
          onSubmit={handleSubmit}
          loading={loading}
        />
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
