import React, { useState, useRef, useEffect } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import {
  Wand2, Loader2, Download, Eye,
  MessageSquare, Send, ChevronRight, RotateCcw, Sparkles
} from 'lucide-react';

// ── Coach system prompt ────────────────────────────────────────────────────────
const COACH_SYSTEM = `You are the App Builder Coach inside Mini Assistant. YOU are the builder — you write all the code, the user writes none.

Your ONLY job right now is to ask short, focused questions to understand what the user wants built. Nothing else.

STRICT RULES — follow every single one:
- Ask exactly ONE question per message. Never two.
- NEVER give roadmaps, timelines, phases, learning resources, tutorials, or technology recommendations.
- NEVER say anything like "since you're coding it", "here's how to build it", "you can use", or "I recommend you learn".
- NEVER use markdown tables, bullet lists of steps, or day-by-day plans.
- DO NOT suggest what tech stack the user should use — that is your decision as the builder, not theirs.
- DO NOT offer options like "Would you like me to..." — just ask the next requirement question.
- Keep every message under 3 sentences.
- Ask about: what the app does, who uses it, the key features they want, the look/feel, whether it needs login, and what data it stores.
- After 5–7 exchanges when you have enough detail, say exactly this one line:
  "I think I have enough to build this! Type BUILD to generate your app, or keep chatting to refine."

You are a requirements gatherer, not a teacher. Stay in that role.

Start by asking what they want to build.`;

// ── Helpers ────────────────────────────────────────────────────────────────────
const renderLinks = (text) => {
  const tokenRe = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|https?:\/\/[^\s<>"]+/g;
  const result = [];
  let last = 0; let i = 0; let match;
  while ((match = tokenRe.exec(text)) !== null) {
    if (match.index > last) result.push(<span key={i++}>{text.slice(last, match.index)}</span>);
    if (match[0].startsWith('[')) {
      result.push(<a key={i++} href={match[2]} target="_blank" rel="noopener noreferrer" className="text-cyan-400 underline hover:text-cyan-300">{match[1]}</a>);
    } else {
      result.push(<a key={i++} href={match[0]} target="_blank" rel="noopener noreferrer" className="text-cyan-400 underline hover:text-cyan-300 break-all">{match[0]}</a>);
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) result.push(<span key={i++}>{text.slice(last)}</span>);
  return result;
};

// ── Component ──────────────────────────────────────────────────────────────────
const AppBuilder = () => {
  const [mode, setMode] = useState('coach');   // 'coach' | 'build'

  // Coach state
  const [coachMessages, setCoachMessages] = useState([]);
  const [coachInput, setCoachInput] = useState('');
  const [coachLoading, setCoachLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState('');
  const [spec, setSpec] = useState('');
  const messagesEndRef = useRef(null);
  const loadingIntervalRef = useRef(null);

  // Build state
  const [description, setDescription] = useState('');
  const [buildLoading, setBuildLoading] = useState(false);
  const [buildMsg, setBuildMsg] = useState('');
  const [generatedApp, setGeneratedApp] = useState(null);

  const CHAT_LOADING_MSGS = [
    'Thinking...', 'Processing your idea...', 'Crafting the perfect question...',
    'Analyzing requirements...', 'Almost there...',
  ];
  const BUILD_LOADING_MSGS = [
    'Reading your requirements...', 'Planning the architecture...',
    'Writing the code...', 'Building components...', 'Wiring everything together...',
    'Adding finishing touches...', 'Almost done...',
  ];

  const startLoadingCycle = (msgs, setter) => {
    let i = 0;
    setter(msgs[0]);
    loadingIntervalRef.current = setInterval(() => {
      i = (i + 1) % msgs.length;
      setter(msgs[i]);
    }, 2500);
  };

  const stopLoadingCycle = (setter) => {
    clearInterval(loadingIntervalRef.current);
    setter('');
  };

  const templates = [
    { name: 'Todo App',      desc: 'Simple task management app with CRUD operations and local storage' },
    { name: 'Weather App',   desc: 'Weather dashboard with location search and 5-day forecast' },
    { name: 'Blog Platform', desc: 'Full blog with posts, comments, tags, and user profiles' },
    { name: 'E-commerce',    desc: 'Product catalog with shopping cart, checkout, and order history' },
    { name: 'Dashboard',     desc: 'Analytics dashboard with charts, metrics, and data tables' },
    { name: 'Chat App',      desc: 'Real-time messaging app with rooms, DMs, and file sharing' },
  ];

  // Start coach with opening question
  useEffect(() => {
    if (coachMessages.length === 0) {
      startCoach();
    }
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [coachMessages]);

  const startCoach = async () => {
    setCoachLoading(true);
    startLoadingCycle(CHAT_LOADING_MSGS, setLoadingMsg);
    try {
      const res = await axiosInstance.post('/chat', {
        messages: [{ role: 'user', content: 'Hello, I want to build an app.' }],
        model: 'glm-5:cloud',
        stream: false,
        system_override: COACH_SYSTEM,
      }, { timeout: 180000 });
      setCoachMessages([{ role: 'assistant', content: res.data.response }]);
    } catch {
      setCoachMessages([{
        role: 'assistant',
        content: "What do you want to build?"
      }]);
    } finally {
      stopLoadingCycle(setLoadingMsg);
      setCoachLoading(false);
    }
  };

  const sendCoachMessage = async () => {
    if (!coachInput.trim() || coachLoading) return;
    const userMsg = { role: 'user', content: coachInput };
    const updatedMsgs = [...coachMessages, userMsg];
    setCoachMessages(updatedMsgs);
    setCoachInput('');
    setCoachLoading(true);
    startLoadingCycle(CHAT_LOADING_MSGS, setLoadingMsg);

    // Check if user typed BUILD
    if (coachInput.trim().toUpperCase() === 'BUILD') {
      await compileAndBuild(updatedMsgs);
      return;
    }

    try {
      const res = await axiosInstance.post('/chat', {
        messages: [
          { role: 'system', content: COACH_SYSTEM },
          ...updatedMsgs,
        ],
        model: 'glm-5:cloud',
        stream: false,
      }, { timeout: 180000 });
      const reply = res.data.response;
      setCoachMessages(prev => [...prev, { role: 'assistant', content: reply }]);

      // Auto-detect if coach is ready to build
      if (reply.toLowerCase().includes('type build') || reply.toLowerCase().includes('enough to build')) {
        setSpec(buildSpecFromHistory([...updatedMsgs, { role: 'assistant', content: reply }]));
      }
    } catch (err) {
      const msg = err.code === 'ECONNABORTED'
        ? 'Response timed out — try again'
        : 'Assistant response failed';
      toast.error(msg);
      setCoachMessages(prev => [...prev, { role: 'assistant', content: 'Response timed out. Please try again.' }]);
    } finally {
      stopLoadingCycle(setLoadingMsg);
      setCoachLoading(false);
    }
  };

  const buildSpecFromHistory = (msgs) => {
    return msgs
      .filter(m => m.role === 'user')
      .map(m => m.content)
      .join('. ');
  };

  const compileAndBuild = async (msgs) => {
    startLoadingCycle(BUILD_LOADING_MSGS, setLoadingMsg);
    try {
      const res = await axiosInstance.post('/chat', {
        messages: [
          { role: 'system', content: COACH_SYSTEM },
          ...msgs,
          {
            role: 'user',
            content: 'Please compile everything we discussed into a single detailed app description I can use to build it. Be specific about features, tech stack, and requirements. Output only the description, no extra commentary.'
          }
        ],
        model: 'glm-5:cloud',
        stream: false,
      }, { timeout: 180000 });
      const compiled = res.data.response;
      setDescription(compiled);
      setCoachMessages(prev => [...prev, {
        role: 'assistant',
        content: `Spec compiled! Switching to Build mode...\n\n${compiled}`
      }]);
      setTimeout(() => setMode('build'), 1200);
    } catch {
      toast.error('Failed to compile spec — please try again');
    } finally {
      stopLoadingCycle(setLoadingMsg);
      setCoachLoading(false);
    }
  };

  const handleCoachKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendCoachMessage();
    }
  };

  const resetCoach = () => {
    setCoachMessages([]);
    setSpec('');
    setCoachInput('');
    startCoach();
  };

  // ── Build ────────────────────────────────────────────────────────────────────
  const generateApp = async () => {
    if (!description.trim() || buildLoading) return;
    setBuildLoading(true);
    startLoadingCycle(BUILD_LOADING_MSGS, setBuildMsg);
    try {
      const response = await axiosInstance.post('/app-builder/generate', {
        description,
        framework: 'react',
      }, { timeout: 180000 });
      setGeneratedApp(response.data);
      toast.success('App generated!');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to generate app');
    } finally {
      stopLoadingCycle(setBuildMsg);
      setBuildLoading(false);
    }
  };

  const openInBrowser = () => {
    if (!generatedApp?.html) return;
    const blob = new Blob([generatedApp.html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  };

  const downloadApp = () => {
    if (!generatedApp?.html) return;
    const blob = new Blob([generatedApp.html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${generatedApp.name || 'generated-app'}.html`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Downloaded!');
  };

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="app-builder">

      {/* Header */}
      <div className="p-5 border-b border-cyan-500/20 bg-black/40 flex-shrink-0">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Wand2 className="w-7 h-7 text-cyan-400" />
            <div>
              <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
                APP BUILDER
              </h2>
              <p className="text-xs text-slate-400 font-mono mt-0.5">AI-POWERED APPLICATION GENERATOR</p>
            </div>
          </div>

          {/* Mode toggle */}
          <div className="flex items-center bg-black/50 border border-cyan-500/20 rounded-sm overflow-hidden">
            <button
              onClick={() => setMode('coach')}
              className={`px-4 py-2 text-xs font-mono uppercase tracking-wider flex items-center gap-2 transition-all ${
                mode === 'coach'
                  ? 'bg-cyan-500/20 text-cyan-400 border-r border-cyan-500/20'
                  : 'text-slate-500 hover:text-slate-300 border-r border-slate-700/30'
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              ASSISTANT
            </button>
            <button
              onClick={() => setMode('build')}
              className={`px-4 py-2 text-xs font-mono uppercase tracking-wider flex items-center gap-2 transition-all ${
                mode === 'build'
                  ? 'bg-violet-500/20 text-violet-400'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              <Wand2 className="w-3.5 h-3.5" />
              BUILD
            </button>
          </div>
        </div>

        {/* Templates (build mode only) */}
        {mode === 'build' && (
          <div>
            <div className="text-xs text-cyan-400/70 font-mono uppercase mb-2">Quick Templates:</div>
            <div className="flex gap-2 flex-wrap">
              {templates.map((t, i) => (
                <button
                  key={i}
                  onClick={() => setDescription(t.desc)}
                  className="px-3 py-1.5 bg-black/30 border border-cyan-500/30 hover:border-violet-500/50 text-cyan-100 text-xs rounded-sm transition-all"
                >
                  {t.name}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Spec ready banner */}
        {mode === 'coach' && spec && (
          <div className="flex items-center gap-3 p-3 bg-green-500/10 border border-green-500/30 rounded-sm">
            <Sparkles className="w-4 h-4 text-green-400 flex-shrink-0" />
            <span className="text-xs text-green-400 font-mono flex-1">Spec ready — type BUILD or click below</span>
            <button
              onClick={() => compileAndBuild(coachMessages)}
              className="px-4 py-1.5 bg-green-500/20 border border-green-500/50 text-green-400 text-xs font-mono uppercase rounded-sm hover:bg-green-500/30 flex items-center gap-1.5"
            >
              <ChevronRight className="w-3.5 h-3.5" /> BUILD NOW
            </button>
          </div>
        )}
      </div>

      {/* ── COACH MODE ── */}
      {mode === 'coach' && (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {coachMessages.map((msg, idx) => (
              <div key={idx} className={`flex items-start gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-violet-600 flex items-center justify-center flex-shrink-0 overflow-hidden">
                    <img src="/Logo.png" alt="" className="w-full h-full object-contain" onError={e => { e.target.style.display='none'; }} />
                  </div>
                )}
                <div className={`max-w-[75%] px-4 py-3 rounded-lg text-sm ${
                  msg.role === 'user'
                    ? 'bg-cyan-500/20 border border-cyan-500/40 text-cyan-100'
                    : 'bg-black/40 border border-cyan-900/30 text-slate-300'
                }`}>
                  <div className="text-xs font-mono text-cyan-400/60 uppercase mb-1.5">
                    {msg.role === 'user' ? 'YOU' : 'ASSISTANT'}
                  </div>
                  <div className="whitespace-pre-wrap leading-relaxed">{renderLinks(msg.content)}</div>
                </div>
              </div>
            ))}
            {coachLoading && (
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-violet-600 flex items-center justify-center flex-shrink-0">
                  <Loader2 className="w-4 h-4 text-white animate-spin" />
                </div>
                <div className="px-4 py-3 bg-black/40 border border-cyan-900/30 rounded-lg">
                  <span className="text-xs font-mono text-cyan-400/80 animate-pulse">{loadingMsg || 'Thinking...'}</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="p-4 border-t border-cyan-500/20 bg-black/30 flex gap-3 items-end">
            <button
              onClick={resetCoach}
              title="Restart assistant"
              className="p-2.5 text-slate-500 hover:text-cyan-400 transition-colors flex-shrink-0"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <textarea
              value={coachInput}
              onChange={e => setCoachInput(e.target.value)}
              onKeyDown={handleCoachKey}
              placeholder='Tell the assistant what you want... type BUILD when ready'
              className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/40 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono text-sm p-3 outline-none resize-none"
              rows={2}
              disabled={coachLoading}
            />
            <button
              onClick={sendCoachMessage}
              disabled={coachLoading || !coachInput.trim()}
              className="p-2.5 bg-gradient-to-r from-cyan-500 to-violet-600 text-white rounded-sm hover:from-cyan-400 hover:to-violet-500 disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* ── BUILD MODE ── */}
      {mode === 'build' && (
        <div className="flex-1 flex flex-col overflow-hidden">
          {!generatedApp ? (
            <div className="p-5 space-y-4">
              <textarea
                data-testid="app-description-input"
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Describe your app in detail (or use the Coach to build a spec first)..."
                className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono p-4 outline-none resize-none"
                rows={6}
                disabled={buildLoading}
              />
              <div className="flex items-center gap-3">
                <button
                  data-testid="generate-app-btn"
                  onClick={generateApp}
                  disabled={buildLoading || !description.trim()}
                  className="px-8 py-3 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 hover:shadow-[0_0_20px_rgba(0,243,255,0.4)] uppercase tracking-wider rounded-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {buildLoading ? <><Loader2 className="w-5 h-5 animate-spin" />{buildMsg || 'GENERATING...'}</> : <><Wand2 className="w-5 h-5" />GENERATE APP</>}
                </button>
                {!spec && (
                  <button
                    onClick={() => setMode('coach')}
                    className="px-4 py-3 border border-cyan-500/30 text-cyan-400 text-sm font-mono uppercase rounded-sm hover:bg-cyan-500/10 flex items-center gap-2 transition-all"
                  >
                    <MessageSquare className="w-4 h-4" /> USE ASSISTANT
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center p-8">
              <div className="text-center space-y-6 max-w-md">
                <div className="w-20 h-20 mx-auto rounded-full bg-gradient-to-br from-cyan-500 to-violet-600 flex items-center justify-center">
                  <Wand2 className="w-10 h-10 text-white" />
                </div>
                <div>
                  <h3 className="text-2xl font-bold text-cyan-400 uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
                    Your App is Ready!
                  </h3>
                  <p className="text-slate-400 font-mono text-sm mt-1">{generatedApp.name}</p>
                </div>
                <div className="flex flex-col gap-3">
                  <button
                    onClick={openInBrowser}
                    className="w-full py-4 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 hover:shadow-[0_0_20px_rgba(0,243,255,0.4)] uppercase tracking-wider rounded-sm transition-all flex items-center justify-center gap-2 text-lg"
                  >
                    <Eye className="w-5 h-5" /> OPEN IN BROWSER
                  </button>
                  <button
                    onClick={downloadApp}
                    className="w-full py-3 bg-violet-500/20 text-violet-400 border border-violet-500/50 hover:bg-violet-500/30 rounded-sm font-semibold uppercase flex items-center justify-center gap-2 transition-all"
                  >
                    <Download className="w-4 h-4" /> DOWNLOAD .HTML
                  </button>
                  <button
                    onClick={() => { setGeneratedApp(null); setDescription(''); }}
                    className="w-full py-2 text-slate-500 hover:text-slate-300 text-sm font-mono uppercase flex items-center justify-center gap-2 transition-colors"
                  >
                    <RotateCcw className="w-3.5 h-3.5" /> BUILD ANOTHER
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default AppBuilder;
