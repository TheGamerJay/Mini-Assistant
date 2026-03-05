import React, { useState, useRef, useEffect } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Send, Loader2, Trash2 } from 'lucide-react';

const ChatInterface = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState('llama3.2');
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await axiosInstance.post('/chat', {
        messages: [...messages, userMessage],
        model: model,
        stream: false
      });

      const assistantMessage = { role: 'assistant', content: response.data.response };
      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Chat error occurred');
      console.error('Chat error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const clearChat = () => {
    setMessages([]);
    toast.success('Chat cleared');
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="chat-interface">
      {/* Chat Header */}
      <div className="p-6 border-b border-cyan-500/20 bg-black/40 backdrop-blur-sm flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-cyan-400 uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
            AI CHAT
          </h2>
          <p className="text-xs text-slate-400 font-mono mt-1">LOCAL OLLAMA ASSISTANT</p>
        </div>
        <div className="flex items-center gap-4">
          <select
            data-testid="model-select"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="bg-black/50 border border-cyan-500/50 text-cyan-100 px-4 py-2 rounded-sm font-mono text-sm focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 outline-none"
          >
            <option value="llama3.2">LLAMA 3.2</option>
            <option value="llama3.2:1b">LLAMA 3.2:1B</option>
            <option value="llama3.2:3b">LLAMA 3.2:3B</option>
            <option value="mistral">MISTRAL</option>
            <option value="phi3">PHI-3</option>
          </select>
          <button
            data-testid="clear-chat-btn"
            onClick={clearChat}
            className="p-2 text-slate-400 hover:text-red-400 transition-colors"
            title="Clear chat"
          >
            <Trash2 className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Messages Container */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4" data-testid="messages-container">
        {messages.length === 0 && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <div className="w-20 h-20 mx-auto rounded-full bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center">
                <div className="text-4xl">💬</div>
              </div>
              <p className="text-slate-400 font-mono text-sm">Start a conversation with your local AI assistant</p>
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            data-testid={`message-${msg.role}`}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] px-6 py-4 rounded-lg backdrop-blur-sm ${
                msg.role === 'user'
                  ? 'bg-cyan-500/20 border border-cyan-500/50 text-cyan-100'
                  : 'bg-black/40 border border-cyan-900/30 text-slate-300'
              }`}
            >
              <div className="text-xs font-mono text-cyan-400/70 uppercase mb-2">
                {msg.role === 'user' ? 'YOU' : 'MINI ASSISTANT'}
              </div>
              <div className="whitespace-pre-wrap font-sans">{msg.content}</div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start" data-testid="loading-indicator">
            <div className="max-w-[80%] px-6 py-4 rounded-lg bg-black/40 border border-cyan-900/30 backdrop-blur-sm">
              <div className="flex items-center gap-3">
                <Loader2 className="w-5 h-5 animate-spin text-cyan-400" />
                <span className="text-slate-400 font-mono text-sm">Processing...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-6 border-t border-cyan-500/20 bg-black/40 backdrop-blur-sm">
        <div className="flex gap-4">
          <textarea
            data-testid="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type your message... (Shift+Enter for new line)"
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
      </div>
    </div>
  );
};

export default ChatInterface;