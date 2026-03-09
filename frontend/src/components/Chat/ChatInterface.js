import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Send, Loader2, Trash2, Image, Cpu, Zap } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const IMAGE_API = `${BACKEND_URL}/image-api/api`;

// Renders text with clickable markdown links
const renderMessage = (text) => {
  if (!text) return null;
  const tokenRe = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|https?:\/\/[^\s<>"]+/g;
  const result = [];
  let last = 0;
  let i = 0;
  let match;
  while ((match = tokenRe.exec(text)) !== null) {
    if (match.index > last) result.push(<span key={i++}>{text.slice(last, match.index)}</span>);
    if (match[0].startsWith('[')) {
      result.push(
        <a key={i++} href={match[2]} target="_blank" rel="noopener noreferrer"
           className="text-cyan-400 underline hover:text-cyan-300 break-all">{match[1]}</a>
      );
    } else {
      result.push(
        <a key={i++} href={match[0]} target="_blank" rel="noopener noreferrer"
           className="text-cyan-400 underline hover:text-cyan-300 break-all">{match[0]}</a>
      );
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) result.push(<span key={i++}>{text.slice(last)}</span>);
  return result;
};

// Intent badge shown under assistant messages
const IntentBadge = ({ route_result }) => {
  if (!route_result) return null;
  const { intent, selected_checkpoint, confidence } = route_result;
  if (!intent) return null;
  const colors = {
    image_generation: 'text-violet-400 border-violet-500/40 bg-violet-500/10',
    image_edit: 'text-violet-400 border-violet-500/40 bg-violet-500/10',
    coding: 'text-amber-400 border-amber-500/40 bg-amber-500/10',
    chat: 'text-slate-500 border-slate-700/40 bg-slate-800/20',
    planning: 'text-teal-400 border-teal-500/40 bg-teal-500/10',
  };
  const cls = colors[intent] || colors.chat;
  return (
    <div className={`mt-2 flex flex-wrap gap-2 text-[10px] font-mono`}>
      <span className={`px-2 py-0.5 rounded border uppercase tracking-widest ${cls}`}>{intent.replace('_', ' ')}</span>
      {selected_checkpoint && (
        <span className="px-2 py-0.5 rounded border border-cyan-900/40 text-cyan-700 bg-cyan-900/10 uppercase tracking-widest">
          {selected_checkpoint}
        </span>
      )}
      {typeof confidence === 'number' && (
        <span className="px-2 py-0.5 rounded border border-slate-700/40 text-slate-600 bg-slate-800/20">
          conf {(confidence * 100).toFixed(0)}%
        </span>
      )}
    </div>
  );
};

// Image output card
const ImageCard = ({ image_base64, prompt, route_result, generation_time_ms, retry_used }) => {
  const src = `data:image/png;base64,${image_base64}`;
  const ck = route_result?.selected_checkpoint || '';
  const wf = route_result?.selected_workflow || '';

  const downloadImage = () => {
    const a = document.createElement('a');
    a.href = src;
    a.download = `mini-assistant-${Date.now()}.png`;
    a.click();
  };

  return (
    <div className="mt-3 rounded-lg overflow-hidden border border-violet-500/30 bg-black/40">
      <img src={src} alt={prompt} className="w-full max-w-md object-contain" />
      <div className="px-4 py-2 flex items-center justify-between gap-2 text-[10px] font-mono text-slate-500">
        <div className="flex flex-wrap gap-2">
          {ck && <span className="text-violet-400/70">{ck}</span>}
          {wf && <span>{wf}</span>}
          {retry_used && <span className="text-amber-500/70">retried</span>}
          {generation_time_ms && <span>{(generation_time_ms / 1000).toFixed(1)}s</span>}
        </div>
        <button
          onClick={downloadImage}
          className="px-2 py-1 rounded border border-violet-500/30 text-violet-400 hover:text-violet-300 hover:border-violet-400/50 transition-colors uppercase tracking-widest"
        >
          Save
        </button>
      </div>
    </div>
  );
};

const ChatInterface = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [imageServerUp, setImageServerUp] = useState(null); // null=unknown, true, false
  const messagesEndRef = useRef(null);
  const sessionId = useRef(null);

  // Restore chat history
  useEffect(() => {
    const saved = localStorage.getItem('imageSystemChatMessages');
    if (saved) {
      try { setMessages(JSON.parse(saved)); } catch (_) {}
    }
  }, []);

  useEffect(() => {
    localStorage.setItem('imageSystemChatMessages', JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Check if image server is reachable
  useEffect(() => {
    axios.get(`${IMAGE_API}/health`, { timeout: 3000 })
      .then(() => setImageServerUp(true))
      .catch(() => setImageServerUp(false));
  }, []);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    if (!sessionId.current) sessionId.current = crypto.randomUUID();

    const userText = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userText }]);
    setLoading(true);

    try {
      const res = await axios.post(`${IMAGE_API}/chat`, {
        message: userText,
        session_id: sessionId.current,
      }, { timeout: 360_000 });

      const data = res.data;

      // Image generation response
      if (data.image_base64) {
        setMessages(prev => [...prev, {
          role: 'assistant',
          type: 'image',
          image_base64: data.image_base64,
          prompt: userText,
          route_result: data.route_result,
          generation_time_ms: data.generation_time_ms,
          retry_used: data.retry_used,
          prompt_warnings: data.prompt_warnings,
        }]);
        return;
      }

      // Text / coding response
      const reply = data.reply || data.route_result?.text_reply || '(no response)';
      setMessages(prev => [...prev, {
        role: 'assistant',
        type: 'text',
        content: reply,
        route_result: data.route_result,
        generation_time_ms: data.generation_time_ms,
        prompt_warnings: data.prompt_warnings,
      }]);

    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      toast.error(`Error: ${detail}`);
      setMessages(prev => [...prev, {
        role: 'assistant',
        type: 'text',
        content: `Connection error: ${detail}. Make sure the image server is running at port 7860.`,
        route_result: null,
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const clearChat = () => {
    setMessages([]);
    sessionId.current = null;
    localStorage.removeItem('imageSystemChatMessages');
    toast.success('Chat cleared');
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="chat-interface">

      {/* Header */}
      <div className="p-6 border-b border-cyan-500/20 bg-black/40 backdrop-blur-sm flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-cyan-400 uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
            AI CHAT
          </h2>
          <p className="text-xs text-slate-400 font-mono mt-1 flex items-center gap-2">
            <Cpu className="w-3 h-3" />
            LOCAL OLLAMA + COMFYUI
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* Server status dot */}
          <div className="flex items-center gap-2 px-3 py-2 bg-black/40 border border-cyan-500/30 rounded-sm">
            <div className={`w-2 h-2 rounded-full ${
              imageServerUp === null ? 'bg-slate-500 animate-pulse' :
              imageServerUp ? 'bg-cyan-400 animate-pulse' : 'bg-red-500'
            }`} />
            <span className="text-xs font-mono text-cyan-400 uppercase tracking-widest">
              {imageServerUp === null ? 'CHECKING' : imageServerUp ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>
          <button
            onClick={clearChat}
            className="p-2 text-slate-400 hover:text-red-400 transition-colors"
            title="Clear chat"
          >
            <Trash2 className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Offline warning */}
      {imageServerUp === false && (
        <div className="mx-6 mt-4 p-3 bg-red-900/20 border border-red-500/40 rounded-sm text-xs font-mono text-red-400">
          Image server offline. Start it with:{' '}
          <code className="bg-black/40 px-1 py-0.5 rounded">
            uvicorn backend.image_system.api.server:app --port 7860
          </code>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4" data-testid="messages-container">
        {messages.length === 0 && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <div className="w-20 h-20 mx-auto rounded-full bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center">
                <div className="text-4xl">🎨</div>
              </div>
              <p className="text-slate-400 font-mono text-sm">Local AI — chat, code, or generate images</p>
              <div className="flex flex-wrap justify-center gap-2 mt-2">
                {[
                  'draw a shonen anime warrior',
                  'realistic portrait photo',
                  'fantasy dragon at sunset',
                  'write a python function',
                ].map(s => (
                  <button
                    key={s}
                    onClick={() => setInput(s)}
                    className="px-3 py-1 text-xs font-mono border border-cyan-900/40 text-cyan-700 hover:text-cyan-400 hover:border-cyan-500/40 rounded-sm transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            data-testid={`message-${msg.role}`}
            className={`flex items-start gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'assistant' && (
              <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-cyan-500 via-violet-500 to-violet-600 flex items-center justify-center overflow-hidden flex-shrink-0 mt-1">
                <img src="/Logo.png" alt="Mini Assistant" className="w-full h-full object-contain"
                     onError={(e) => { e.target.style.display = 'none'; }} />
              </div>
            )}

            <div className={`max-w-[80%] px-6 py-4 rounded-lg backdrop-blur-sm ${
              msg.role === 'user'
                ? 'bg-cyan-500/20 border border-cyan-500/50 text-cyan-100'
                : 'bg-black/40 border border-cyan-900/30 text-slate-300'
            }`}>
              <div className="text-xs font-mono text-cyan-400/70 uppercase mb-2">
                {msg.role === 'user' ? 'YOU' : 'MINI ASSISTANT'}
              </div>

              {/* Image response */}
              {msg.type === 'image' && (
                <>
                  <p className="text-slate-400 text-sm mb-1">Here's your image:</p>
                  <ImageCard
                    image_base64={msg.image_base64}
                    prompt={msg.prompt}
                    route_result={msg.route_result}
                    generation_time_ms={msg.generation_time_ms}
                    retry_used={msg.retry_used}
                  />
                </>
              )}

              {/* Text response */}
              {msg.type === 'text' && (
                <div className="whitespace-pre-wrap font-sans">{renderMessage(msg.content)}</div>
              )}

              {/* Plain user message */}
              {!msg.type && (
                <div className="whitespace-pre-wrap font-sans">{renderMessage(msg.content)}</div>
              )}

              {/* Warnings */}
              {msg.prompt_warnings?.length > 0 && (
                <div className="mt-2 text-[10px] font-mono text-amber-500/60">
                  {msg.prompt_warnings.join(' · ')}
                </div>
              )}

              {/* Intent badge (assistant messages only) */}
              {msg.role === 'assistant' && <IntentBadge route_result={msg.route_result} />}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex items-center gap-3 justify-start" data-testid="loading-indicator">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-cyan-500 via-violet-500 to-violet-600 flex items-center justify-center overflow-hidden flex-shrink-0">
              <img src="/Logo.png" alt="Mini Assistant" className="w-full h-full object-contain"
                   onError={(e) => { e.target.style.display = 'none'; }} />
            </div>
            <div className="max-w-[80%] px-6 py-4 rounded-lg bg-black/40 border border-cyan-900/30 backdrop-blur-sm">
              <div className="flex items-center gap-3">
                <Loader2 className="w-5 h-5 animate-spin text-cyan-400" />
                <span className="text-slate-400 font-mono text-sm">Thinking... (image gen can take 30–120s)</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-6 border-t border-cyan-500/20 bg-black/40 backdrop-blur-sm">
        <div className="flex gap-4">
          <textarea
            data-testid="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Chat, ask to generate an image, write code... (Shift+Enter for new line)"
            className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono p-4 resize-none outline-none"
            rows={3}
            disabled={loading}
          />
          <button
            data-testid="send-message-btn"
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="px-8 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 hover:shadow-[0_0_20px_rgba(0,243,255,0.5),0_0_15px_rgba(147,51,234,0.3)] uppercase tracking-wider rounded-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
        <p className="text-[10px] font-mono text-slate-700 mt-2">
          Powered by local Ollama + ComfyUI · Models: qwen3:14b router · qwen2.5vl:7b vision · nomic-embed embeddings
        </p>
      </div>
    </div>
  );
};

export default ChatInterface;
