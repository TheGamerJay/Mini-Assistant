/* LEGACY: this component is superseded by pages/ChatPage.js. Safe to remove once confirmed unused. */
import React, { useState, useRef, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Send, Loader2, Trash2, Plus, Search, Image, FolderOpen,
  MessageSquare, ChevronDown, ChevronRight, X, Edit2, Check,
  Download, Cpu, MoreHorizontal,
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const IMAGE_API = `${BACKEND_URL}/image-api/api`;

// ── localStorage helpers ────────────────────────────────────────────────────

const LS_CHATS    = 'ma_chats_v1';
const LS_PROJECTS = 'ma_projects_v1';
const LS_IMAGES   = 'ma_images_v1';

const lsGet = (key, fallback) => {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
};
const lsSet = (key, val) => {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch (_) {}
};

const uuid = () => crypto.randomUUID();

// Shrink an image_base64 to a thumbnail (120×120 JPEG ~5-8 KB) via canvas
const makeThumbnail = (base64) =>
  new Promise((resolve) => {
    try {
      const img = new window.Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        const SIZE = 120;
        canvas.width = SIZE; canvas.height = SIZE;
        const ctx = canvas.getContext('2d');
        const s = Math.min(img.width, img.height);
        const sx = (img.width - s) / 2;
        const sy = (img.height - s) / 2;
        ctx.drawImage(img, sx, sy, s, s, 0, 0, SIZE, SIZE);
        resolve(canvas.toDataURL('image/jpeg', 0.45));
      };
      img.onerror = () => resolve(null);
      img.src = `data:image/png;base64,${base64}`;
    } catch { resolve(null); }
  });

// ── Sub-components ──────────────────────────────────────────────────────────

const renderText = (text) => {
  if (!text) return null;
  const re = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|https?:\/\/[^\s<>"]+/g;
  const out = []; let last = 0; let i = 0; let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(<span key={i++}>{text.slice(last, m.index)}</span>);
    out.push(m[0].startsWith('[')
      ? <a key={i++} href={m[2]} target="_blank" rel="noopener noreferrer" className="text-cyan-400 underline">{m[1]}</a>
      : <a key={i++} href={m[0]} target="_blank" rel="noopener noreferrer" className="text-cyan-400 underline">{m[0]}</a>
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(<span key={i++}>{text.slice(last)}</span>);
  return out;
};

const IntentBadge = ({ route_result }) => {
  if (!route_result?.intent) return null;
  const { intent, selected_checkpoint, confidence } = route_result;
  const colors = {
    image_generation: 'text-violet-400 border-violet-500/40 bg-violet-500/10',
    image_edit: 'text-violet-400 border-violet-500/40 bg-violet-500/10',
    coding: 'text-amber-400 border-amber-500/40 bg-amber-500/10',
    chat: 'text-slate-500 border-slate-700 bg-transparent',
    planning: 'text-teal-400 border-teal-500/40 bg-teal-500/10',
  };
  return (
    <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] font-mono">
      <span className={`px-2 py-0.5 rounded border uppercase ${colors[intent] || colors.chat}`}>
        {intent.replace('_', ' ')}
      </span>
      {selected_checkpoint && (
        <span className="px-2 py-0.5 rounded border border-cyan-900/40 text-cyan-700 bg-cyan-900/10 uppercase">
          {selected_checkpoint}
        </span>
      )}
      {typeof confidence === 'number' && (
        <span className="px-2 py-0.5 rounded border border-slate-700 text-slate-600">
          {(confidence * 100).toFixed(0)}%
        </span>
      )}
    </div>
  );
};

const ImageCard = ({ image_base64, prompt, route_result, generation_time_ms, retry_used }) => {
  const src = `data:image/png;base64,${image_base64}`;
  const download = () => {
    const a = document.createElement('a');
    a.href = src; a.download = `mini-assistant-${Date.now()}.png`; a.click();
  };
  return (
    <div className="mt-2 rounded-lg overflow-hidden border border-violet-500/30 bg-black/40 max-w-sm">
      <img src={src} alt={prompt} className="w-full object-contain" />
      <div className="px-3 py-1.5 flex items-center justify-between text-[10px] font-mono text-slate-500">
        <div className="flex flex-wrap gap-2">
          {route_result?.selected_checkpoint && (
            <span className="text-violet-400/70">{route_result.selected_checkpoint}</span>
          )}
          {retry_used && <span className="text-amber-500/70">retried</span>}
          {generation_time_ms && <span>{(generation_time_ms / 1000).toFixed(1)}s</span>}
        </div>
        <button onClick={download} className="px-2 py-0.5 rounded border border-violet-500/30 text-violet-400 hover:text-violet-300 transition-colors uppercase">
          <Download className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
};

// Collapsible sidebar section
const Section = ({ title, icon: Icon, defaultOpen = true, count, children, action }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="mb-1">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-[11px] font-mono uppercase tracking-widest text-slate-500 hover:text-slate-300 transition-colors"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <Icon className="w-3 h-3" />
        <span className="flex-1 text-left">{title}</span>
        {count != null && <span className="text-slate-600">{count}</span>}
        {action && <span onClick={e => { e.stopPropagation(); action.fn(); }} className="text-slate-600 hover:text-cyan-400 transition-colors">{action.icon}</span>}
      </button>
      {open && <div className="pb-1">{children}</div>}
    </div>
  );
};

// ── Main component ──────────────────────────────────────────────────────────

const ChatInterface = () => {
  // Persisted state
  const [chats, setChats]       = useState(() => lsGet(LS_CHATS, []));
  const [projects, setProjects] = useState(() => lsGet(LS_PROJECTS, []));
  const [images, setImages]     = useState(() => lsGet(LS_IMAGES, [])); // [{id,thumb,prompt,ts}]

  // Session state
  const [activeChatId, setActiveChatId] = useState(null);
  const [messages, setMessages]         = useState([]);
  const [input, setInput]               = useState('');
  const [loading, setLoading]           = useState(false);
  const [imageServerUp, setImageServerUp] = useState(null);
  const [search, setSearch]             = useState('');
  const [lightbox, setLightbox]         = useState(null); // full base64 for modal
  const [editingProject, setEditingProject] = useState(null); // {id, name}
  const [renamingChat, setRenamingChat] = useState(null); // {id, title}

  const sessionRef  = useRef(null);
  const messagesEnd = useRef(null);
  const inputRef    = useRef(null);

  // Persist whenever they change
  useEffect(() => { lsSet(LS_CHATS, chats); }, [chats]);
  useEffect(() => { lsSet(LS_PROJECTS, projects); }, [projects]);
  useEffect(() => { lsSet(LS_IMAGES, images); }, [images]);

  // Auto-scroll
  useEffect(() => { messagesEnd.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  // Health check
  useEffect(() => {
    axios.get(`${IMAGE_API}/health`, { timeout: 3000 })
      .then(() => setImageServerUp(true))
      .catch(() => setImageServerUp(false));
  }, []);

  // ── Chat management ────────────────────────────────────────────────────────

  const startNewChat = useCallback(() => {
    const id = uuid();
    const newChat = { id, title: 'New Chat', messages: [], projectId: null, createdAt: Date.now(), updatedAt: Date.now() };
    setChats(prev => [newChat, ...prev]);
    setActiveChatId(id);
    setMessages([]);
    sessionRef.current = uuid();
    inputRef.current?.focus();
  }, []);

  const loadChat = useCallback((chat) => {
    setActiveChatId(chat.id);
    setMessages(chat.messages || []);
    sessionRef.current = uuid();
    inputRef.current?.focus();
  }, []);

  const deleteChat = useCallback((id, e) => {
    e?.stopPropagation();
    setChats(prev => prev.filter(c => c.id !== id));
    if (activeChatId === id) {
      setActiveChatId(null);
      setMessages([]);
    }
  }, [activeChatId]);

  const renameChat = useCallback((id, newTitle) => {
    setChats(prev => prev.map(c => c.id === id ? { ...c, title: newTitle } : c));
    setRenamingChat(null);
  }, []);

  // Derive title from first user message
  const autoTitle = (msgs) => {
    const first = msgs.find(m => m.role === 'user');
    if (!first) return 'New Chat';
    const t = first.content?.trim() || '';
    return t.length > 40 ? t.slice(0, 40) + '…' : t || 'New Chat';
  };

  const saveMessages = useCallback((chatId, msgs) => {
    setChats(prev => prev.map(c =>
      c.id === chatId ? { ...c, messages: msgs, title: c.title === 'New Chat' ? autoTitle(msgs) : c.title, updatedAt: Date.now() } : c
    ));
  }, []);

  // ── Project management ─────────────────────────────────────────────────────

  const newProject = () => {
    const name = window.prompt('Project name:');
    if (!name?.trim()) return;
    setProjects(prev => [{ id: uuid(), name: name.trim(), createdAt: Date.now() }, ...prev]);
  };

  const deleteProject = (id, e) => {
    e?.stopPropagation();
    setProjects(prev => prev.filter(p => p.id !== id));
    setChats(prev => prev.map(c => c.projectId === id ? { ...c, projectId: null } : c));
  };

  const assignChatToProject = (chatId, projectId) => {
    setChats(prev => prev.map(c => c.id === chatId ? { ...c, projectId } : c));
  };

  // ── Send message ───────────────────────────────────────────────────────────

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    if (input.trim().length < 3) {
      toast.warning('Message too short (min 3 characters)');
      return;
    }

    // Ensure a chat exists
    let chatId = activeChatId;
    if (!chatId) {
      const id = uuid();
      const newChat = { id, title: 'New Chat', messages: [], projectId: null, createdAt: Date.now(), updatedAt: Date.now() };
      setChats(prev => [newChat, ...prev]);
      setActiveChatId(id);
      chatId = id;
    }
    if (!sessionRef.current) sessionRef.current = uuid();

    const text = input.trim();
    setInput('');

    const userMsg = { role: 'user', content: text };
    const nextMsgs = [...messages, userMsg];
    setMessages(nextMsgs);
    saveMessages(chatId, nextMsgs);
    setLoading(true);

    try {
      const res = await axios.post(`${IMAGE_API}/chat`, {
        message: text,
        session_id: sessionRef.current,
      }, { timeout: 360_000 });

      const data = res.data;
      let assistantMsg;

      if (data.image_base64) {
        assistantMsg = {
          role: 'assistant', type: 'image',
          image_base64: data.image_base64,
          prompt: text,
          route_result: data.route_result,
          generation_time_ms: data.generation_time_ms,
          retry_used: data.retry_used,
          prompt_warnings: data.prompt_warnings,
        };
        // Store thumbnail
        makeThumbnail(data.image_base64).then(thumb => {
          if (thumb) {
            setImages(prev => [{
              id: uuid(), thumb, prompt: text,
              ts: Date.now(), full: data.image_base64,
            }, ...prev].slice(0, 50));
          }
        });
      } else {
        assistantMsg = {
          role: 'assistant', type: 'text',
          content: data.reply || data.route_result?.text_reply || '(no response)',
          route_result: data.route_result,
          generation_time_ms: data.generation_time_ms,
          prompt_warnings: data.prompt_warnings,
          suggested_retry_prompts: data.suggested_retry_prompts || [],
        };
      }

      const finalMsgs = [...nextMsgs, assistantMsg];
      setMessages(finalMsgs);
      saveMessages(chatId, finalMsgs);
    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      toast.error(`Error: ${detail}`);
      const errMsg = { role: 'assistant', type: 'text', content: `Error: ${detail}` };
      const finalMsgs = [...nextMsgs, errMsg];
      setMessages(finalMsgs);
      saveMessages(chatId, finalMsgs);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  // ── Filtered chats ─────────────────────────────────────────────────────────

  const filteredChats = chats.filter(c =>
    !search || c.title.toLowerCase().includes(search.toLowerCase())
  );
  const unassignedChats  = filteredChats.filter(c => !c.projectId);
  const chatsForProject  = (pid) => filteredChats.filter(c => c.projectId === pid);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="h-full flex" data-testid="chat-interface">

      {/* ─── LEFT SIDEBAR ─────────────────────────────────────────────────── */}
      <aside className="w-64 flex-shrink-0 flex flex-col bg-black/60 border-r border-cyan-500/15 overflow-hidden">

        {/* New Chat */}
        <div className="p-3 border-b border-cyan-500/10">
          <button
            onClick={startNewChat}
            className="w-full flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-cyan-500/15 to-violet-500/15 border border-cyan-500/30 rounded-sm text-sm font-semibold text-cyan-400 hover:from-cyan-500/25 hover:to-violet-500/25 hover:border-cyan-400/50 transition-all uppercase tracking-wider"
          >
            <Plus className="w-4 h-4" />
            New Chat
          </button>
        </div>

        {/* Search */}
        <div className="px-3 py-2 border-b border-cyan-500/10">
          <div className="flex items-center gap-2 px-3 py-2 bg-black/40 border border-cyan-900/30 rounded-sm">
            <Search className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search chats..."
              className="flex-1 bg-transparent text-xs font-mono text-slate-300 placeholder:text-slate-600 outline-none"
            />
            {search && (
              <button onClick={() => setSearch('')}><X className="w-3 h-3 text-slate-500 hover:text-slate-300" /></button>
            )}
          </div>
        </div>

        {/* Scrollable sections */}
        <div className="flex-1 overflow-y-auto py-1 scrollbar-thin">

          {/* Images section */}
          <Section title="Images" icon={Image} defaultOpen={true} count={images.length}>
            {images.length === 0 ? (
              <p className="px-5 py-1 text-[11px] font-mono text-slate-600">No images yet</p>
            ) : (
              <div className="px-3 grid grid-cols-3 gap-1 pb-1">
                {images.slice(0, 12).map(img => (
                  <button
                    key={img.id}
                    onClick={() => setLightbox(img.full || img.thumb)}
                    className="aspect-square rounded overflow-hidden border border-violet-900/30 hover:border-violet-500/50 transition-colors"
                    title={img.prompt}
                  >
                    <img src={img.thumb} alt={img.prompt} className="w-full h-full object-cover" />
                  </button>
                ))}
              </div>
            )}
          </Section>

          {/* Projects section */}
          <Section
            title="Projects"
            icon={FolderOpen}
            defaultOpen={true}
            count={projects.length}
            action={{ icon: <Plus className="w-3 h-3" />, fn: newProject }}
          >
            {projects.length === 0 ? (
              <p className="px-5 py-1 text-[11px] font-mono text-slate-600">No projects yet</p>
            ) : projects.map(proj => (
              <div key={proj.id}>
                {editingProject?.id === proj.id ? (
                  <div className="flex items-center gap-1 px-3 py-1">
                    <input
                      autoFocus
                      value={editingProject.name}
                      onChange={e => setEditingProject(v => ({ ...v, name: e.target.value }))}
                      onKeyDown={e => {
                        if (e.key === 'Enter') {
                          setProjects(prev => prev.map(p => p.id === proj.id ? { ...p, name: editingProject.name } : p));
                          setEditingProject(null);
                        }
                        if (e.key === 'Escape') setEditingProject(null);
                      }}
                      className="flex-1 bg-black/40 border border-cyan-500/30 rounded px-2 py-0.5 text-xs text-cyan-300 outline-none font-mono"
                    />
                    <button onClick={() => {
                      setProjects(prev => prev.map(p => p.id === proj.id ? { ...p, name: editingProject.name } : p));
                      setEditingProject(null);
                    }}>
                      <Check className="w-3 h-3 text-cyan-400" />
                    </button>
                  </div>
                ) : (
                  <div className="group flex items-center gap-2 px-4 py-1.5 hover:bg-white/5 rounded-sm mx-1 cursor-pointer">
                    <FolderOpen className="w-3.5 h-3.5 text-amber-500/70 flex-shrink-0" />
                    <span className="flex-1 text-xs font-mono text-slate-300 truncate">{proj.name}</span>
                    <div className="hidden group-hover:flex items-center gap-1">
                      <button onClick={() => setEditingProject({ id: proj.id, name: proj.name })}>
                        <Edit2 className="w-3 h-3 text-slate-500 hover:text-slate-300" />
                      </button>
                      <button onClick={e => deleteProject(proj.id, e)}>
                        <X className="w-3 h-3 text-slate-500 hover:text-red-400" />
                      </button>
                    </div>
                  </div>
                )}
                {/* Chats in this project */}
                {chatsForProject(proj.id).map(chat => (
                  <ChatRow
                    key={chat.id} chat={chat} active={activeChatId === chat.id}
                    onLoad={() => loadChat(chat)}
                    onDelete={e => deleteChat(chat.id, e)}
                    renaming={renamingChat?.id === chat.id ? renamingChat : null}
                    onStartRename={() => setRenamingChat({ id: chat.id, title: chat.title })}
                    onRename={(t) => renameChat(chat.id, t)}
                    onCancelRename={() => setRenamingChat(null)}
                    indented
                  />
                ))}
              </div>
            ))}
          </Section>

          {/* Your Chats section */}
          <Section title="Your Chats" icon={MessageSquare} defaultOpen={true} count={unassignedChats.length}>
            {unassignedChats.length === 0 ? (
              <p className="px-5 py-1 text-[11px] font-mono text-slate-600">
                {search ? 'No matches' : 'No chats yet — start one!'}
              </p>
            ) : unassignedChats.map(chat => (
              <ChatRow
                key={chat.id} chat={chat} active={activeChatId === chat.id}
                onLoad={() => loadChat(chat)}
                onDelete={e => deleteChat(chat.id, e)}
                renaming={renamingChat?.id === chat.id ? renamingChat : null}
                onStartRename={() => setRenamingChat({ id: chat.id, title: chat.title })}
                onRename={(t) => renameChat(chat.id, t)}
                onCancelRename={() => setRenamingChat(null)}
              />
            ))}
          </Section>

        </div>

        {/* Bottom: server status */}
        <div className="px-4 py-2 border-t border-cyan-500/10 flex items-center gap-2">
          <Cpu className="w-3.5 h-3.5 text-slate-600" />
          <div className={`w-1.5 h-1.5 rounded-full ${
            imageServerUp === null ? 'bg-slate-600 animate-pulse' :
            imageServerUp ? 'bg-cyan-400 animate-pulse' : 'bg-red-500'
          }`} />
          <span className="text-[10px] font-mono text-slate-600 uppercase tracking-wider">
            {imageServerUp === null ? 'checking' : imageServerUp ? 'local ai online' : 'server offline'}
          </span>
        </div>
      </aside>

      {/* ─── CHAT WINDOW ──────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* Chat header */}
        <div className="px-6 py-4 border-b border-cyan-500/15 bg-black/30 flex items-center justify-between flex-shrink-0">
          <div>
            <h2 className="text-lg font-bold text-cyan-400 uppercase tracking-wider" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
              {activeChatId ? (chats.find(c => c.id === activeChatId)?.title || 'Chat') : 'Mini Assistant'}
            </h2>
            <p className="text-[10px] font-mono text-slate-500 mt-0.5">Ollama · ComfyUI · Local AI</p>
          </div>
          {activeChatId && (
            <button
              onClick={e => deleteChat(activeChatId, e)}
              className="p-2 text-slate-600 hover:text-red-400 transition-colors"
              title="Delete this chat"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Offline warning */}
        {imageServerUp === false && (
          <div className="mx-6 mt-3 p-2.5 bg-red-900/20 border border-red-500/30 rounded-sm text-[11px] font-mono text-red-400">
            Server offline —{' '}
            <code className="bg-black/40 px-1 rounded">uvicorn backend.image_system.api.server:app --port 7860</code>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="h-full flex items-center justify-center">
              <div className="text-center space-y-4 max-w-md">
                <div className="w-16 h-16 mx-auto rounded-full bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-3xl">🎨</div>
                <p className="text-slate-400 font-mono text-sm">Chat, generate images, or write code</p>
                <div className="flex flex-wrap justify-center gap-2">
                  {['draw a shonen anime warrior', 'realistic portrait photo', 'explain async/await', 'fantasy dragon at dusk'].map(s => (
                    <button key={s} onClick={() => setInput(s)}
                      className="px-3 py-1.5 text-xs font-mono border border-cyan-900/40 text-cyan-700 hover:text-cyan-400 hover:border-cyan-500/40 rounded-sm transition-colors">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div key={idx} data-testid={`message-${msg.role}`}
              className={`flex items-start gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>

              {msg.role === 'assistant' && (
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 via-violet-500 to-violet-600 flex items-center justify-center overflow-hidden flex-shrink-0 mt-1">
                  <img src="/Logo.png" alt="MA" className="w-full h-full object-contain"
                    onError={e => { e.target.style.display = 'none'; }} />
                </div>
              )}

              <div className={`max-w-[75%] px-5 py-3.5 rounded-lg ${
                msg.role === 'user'
                  ? 'bg-cyan-500/15 border border-cyan-500/40 text-cyan-100'
                  : 'bg-black/40 border border-cyan-900/20 text-slate-300'
              }`}>
                <div className="text-[10px] font-mono text-cyan-400/60 uppercase mb-1.5">
                  {msg.role === 'user' ? 'You' : 'Mini Assistant'}
                </div>

                {msg.type === 'image' ? (
                  <>
                    <p className="text-sm text-slate-400 mb-1">Generated:</p>
                    <ImageCard
                      image_base64={msg.image_base64} prompt={msg.prompt}
                      route_result={msg.route_result} generation_time_ms={msg.generation_time_ms}
                      retry_used={msg.retry_used}
                    />
                  </>
                ) : (
                  <div className="whitespace-pre-wrap text-sm leading-relaxed">{renderText(msg.content)}</div>
                )}

                {msg.prompt_warnings?.length > 0 && (
                  <div className="mt-1.5 text-[10px] font-mono text-amber-500/50">
                    {msg.prompt_warnings.join(' · ')}
                  </div>
                )}

                {msg.role === 'assistant' && <IntentBadge route_result={msg.route_result} />}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 via-violet-500 to-violet-600 flex items-center justify-center overflow-hidden flex-shrink-0">
                <img src="/Logo.png" alt="MA" className="w-full h-full object-contain"
                  onError={e => { e.target.style.display = 'none'; }} />
              </div>
              <div className="px-5 py-3.5 rounded-lg bg-black/40 border border-cyan-900/20">
                <div className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
                  <span className="text-slate-400 font-mono text-xs">Thinking… image gen can take 30–120s</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEnd} />
        </div>

        {/* Input */}
        <div className="px-6 py-4 border-t border-cyan-500/15 bg-black/30 flex-shrink-0">
          <div className="flex gap-3">
            <textarea
              ref={inputRef}
              data-testid="chat-input"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message Mini Assistant… (Shift+Enter for new line)"
              className="flex-1 bg-black/50 border border-cyan-900/40 text-cyan-100 placeholder:text-slate-700 focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 rounded-sm font-mono text-sm p-3.5 resize-none outline-none"
              rows={3}
              disabled={loading}
            />
            <button
              data-testid="send-message-btn"
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="px-6 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 transition-all rounded-sm disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>

      {/* ─── IMAGE LIGHTBOX ────────────────────────────────────────────────── */}
      {lightbox && (
        <div
          className="fixed inset-0 bg-black/90 backdrop-blur-sm z-50 flex items-center justify-center p-6"
          onClick={() => setLightbox(null)}
        >
          <button onClick={() => setLightbox(null)} className="absolute top-4 right-4 p-2 text-slate-400 hover:text-white">
            <X className="w-6 h-6" />
          </button>
          <img
            src={lightbox.startsWith('data:') ? lightbox : `data:image/png;base64,${lightbox}`}
            alt="Generated"
            className="max-w-full max-h-full object-contain rounded-lg shadow-2xl"
            onClick={e => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
};

// ── ChatRow sub-component ───────────────────────────────────────────────────

const ChatRow = ({ chat, active, onLoad, onDelete, renaming, onStartRename, onRename, onCancelRename, indented }) => (
  <div className={`group relative flex items-center gap-2 mx-1 px-${indented ? 6 : 4} py-1.5 rounded-sm cursor-pointer transition-colors ${
    active ? 'bg-cyan-500/10 border border-cyan-500/20' : 'hover:bg-white/5 border border-transparent'
  }`}>
    {renaming ? (
      <input
        autoFocus
        value={renaming.title}
        onChange={e => onRename({ ...renaming, title: e.target.value }.title)}
        onKeyDown={e => {
          if (e.key === 'Enter') onRename(e.target.value);
          if (e.key === 'Escape') onCancelRename();
        }}
        onBlur={e => onRename(e.target.value)}
        className="flex-1 bg-black/40 border border-cyan-500/30 rounded px-2 py-0.5 text-xs text-cyan-300 outline-none font-mono"
        onClick={e => e.stopPropagation()}
      />
    ) : (
      <span onClick={onLoad} className="flex-1 text-xs font-mono text-slate-400 truncate hover:text-slate-200 transition-colors">
        {chat.title}
      </span>
    )}
    <div className="hidden group-hover:flex items-center gap-1 flex-shrink-0">
      <button onClick={onStartRename} title="Rename">
        <Edit2 className="w-3 h-3 text-slate-600 hover:text-slate-300" />
      </button>
      <button onClick={onDelete} title="Delete">
        <X className="w-3 h-3 text-slate-600 hover:text-red-400" />
      </button>
    </div>
  </div>
);

export default ChatInterface;
