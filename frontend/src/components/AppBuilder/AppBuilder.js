import React, { useState, useRef, useEffect } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import {
  Wand2, Loader2, Download, Eye,
  MessageSquare, Send, ChevronRight, RotateCcw, Sparkles, Pencil, CheckCircle,
  Trash2, FolderOpen, Clock, Package, Undo2, History, MonitorPlay,
  FileCode, Palette, Code2, BookmarkPlus, X, Pin, Archive, Search,
  SortAsc, RefreshCw, Redo2, Upload, BookOpen, AlertTriangle, AlertCircle,
  ShieldCheck, ArchiveRestore
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

// ── Helpers ──────────────────────────────────────────────────────────────────
/**
 * Merge structured project files back into a single self-contained HTML string
 * for the iframe preview and single-file downloads.
 */
const reconstructHtml = (project) => {
  if (!project) return '';
  let html = project.index_html || '';
  const css = project.style_css || '';
  const js  = project.script_js || '';
  html = html.replace('<link rel="stylesheet" href="style.css">', `<style>${css}</style>`);
  html = html.replace('<script src="script.js"></script>',        `<script>${js}</script>`);
  // Fallback: inline if placeholders weren't found
  if (!html.includes(`<style>${css}`) && css.trim()) {
    html = html.replace('</head>', `<style>${css}</style>\n</head>`);
  }
  if (!html.includes(`<script>${js}`) && js.trim()) {
    html = html.replace('</body>', `<script>${js}</script>\n</body>`);
  }
  return html;
};

// ── Diff computation (LCS-based, line-level) ───────────────────────────────────
const computeDiff = (oldStr, newStr) => {
  const a = (oldStr || '').split('\n').slice(0, 400);
  const b = (newStr || '').split('\n').slice(0, 400);
  const n = a.length, m = b.length;
  // Build LCS table
  const lcs = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      lcs[i][j] = a[i] === b[j] ? 1 + lcs[i + 1][j + 1] : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  // Trace back
  const result = [];
  let i = 0, j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && a[i] === b[j]) { result.push({ t: 'eq', s: a[i] }); i++; j++; }
    else if (j < m && (i >= n || lcs[i + 1][j] >= lcs[i][j + 1])) { result.push({ t: 'add', s: b[j] }); j++; }
    else { result.push({ t: 'del', s: a[i] }); i++; }
  }
  return result;
};

// ── Session health badge ───────────────────────────────────────────────────────
const getHealthBadge = (session) => {
  if (session.is_archived)
    return { label: 'Archived', cls: 'text-slate-500 border-slate-700', Icon: Archive };
  const edits = session.editHistory || [];
  const errors = edits.filter(m => m.role === 'assistant' && m.content?.startsWith('Error:'));
  if (errors.length >= 2)
    return { label: 'Needs Fix', cls: 'text-red-400 border-red-800', Icon: AlertCircle };
  if (errors.length === 1)
    return { label: 'Warning', cls: 'text-amber-400 border-amber-800', Icon: AlertTriangle };
  if ((session.versions || []).some(v => v.name?.toLowerCase().includes('restor')))
    return { label: 'Restored', cls: 'text-violet-400 border-violet-800', Icon: ArchiveRestore };
  return { label: 'Ready', cls: 'text-emerald-400 border-emerald-800', Icon: ShieldCheck };
};

// ── Component ──────────────────────────────────────────────────────────────────
const SESSIONS_KEY = 'appbuilder_sessions';

const loadSessionsLocal = () => {
  try { return JSON.parse(localStorage.getItem(SESSIONS_KEY) || '[]'); } catch { return []; }
};

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

  // Edit state
  const [editInput, setEditInput] = useState('');
  const [editLoading, setEditLoading] = useState(false);
  const [editMsg, setEditMsg] = useState('');
  const [editHistory, setEditHistory] = useState([]);
  const editLoadingIntervalRef = useRef(null);
  const editEndRef = useRef(null);

  // Undo / Redo / version history
  const [undoStack, setUndoStack] = useState([]);
  const [redoStack, setRedoStack] = useState([]);
  const [versions, setVersions] = useState([]);
  const [showVersions, setShowVersions] = useState(false);
  const [versionName, setVersionName] = useState('');
  const [diffView, setDiffView] = useState(null);  // {verA, verB, file} | null

  // File tabs
  const [activeTab, setActiveTab] = useState('preview'); // 'preview'|'html'|'css'|'js'|'readme'

  // Import refs
  const importHtmlRef = useRef(null);
  const importZipRef  = useRef(null);

  // Saved sessions
  const [savedSessions, setSavedSessions] = useState(loadSessionsLocal);
  const [sessionSearch, setSessionSearch] = useState('');
  const [sessionSort, setSessionSort] = useState('newest');
  const [showArchived, setShowArchived] = useState(false);

  const EDIT_LOADING_MSGS = [
    'Reading your app...', 'Finding what to change...', 'Applying changes...',
    'Rewriting affected code...', 'Putting it back together...', 'Almost done...',
  ];

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
    // Apps
    { name: 'Todo App',        cat: 'App',  desc: 'Task manager with categories, priorities, due dates, drag-to-reorder, and localStorage persistence' },
    { name: 'Kanban Board',    cat: 'App',  desc: 'Drag-and-drop Kanban board with columns (Backlog, In Progress, Done), card creation, and local save' },
    { name: 'Markdown Editor', cat: 'App',  desc: 'Split-pane markdown editor with live HTML preview, syntax highlighting, and export to HTML' },
    { name: 'Budget Tracker',  cat: 'App',  desc: 'Personal finance tracker with income/expense categories, monthly charts, and balance summary' },
    { name: 'Pomodoro Timer',  cat: 'App',  desc: 'Focus timer with 25/5 minute sessions, session history, sound alerts, and streak counter' },
    { name: 'Password Gen',    cat: 'App',  desc: 'Secure password generator with length/symbol/number controls, strength meter, and copy button' },
    // Games
    { name: 'Platformer Game', cat: 'Game', desc: 'Side-scrolling platformer with animated character, moving platforms, enemies, coins, score, lives, and game over screen. Sound effects and particle effects.' },
    { name: 'Three.js Game',   cat: 'Game', desc: '3D browser game using Three.js with a player character, terrain, collectables, obstacles, score, and smooth camera follow. Keyboard and touch controls.' },
    { name: 'Snake',           cat: 'Game', desc: 'Classic snake game with grid, growing snake, food, speed scaling, high score saved to localStorage, and game over screen' },
    { name: 'Breakout',        cat: 'Game', desc: 'Breakout/Arkanoid brick-breaker with multiple brick rows, ball physics, paddle, lives, score, and power-ups' },
    { name: 'Space Shooter',   cat: 'Game', desc: 'Vertical space shooter with player ship, enemy waves, bullets, explosions, shield, score, and boss every 5 levels' },
    // Visual / Creative
    { name: 'Drawing Canvas',  cat: 'Creative', desc: 'Drawing app with brush, eraser, shapes, color picker, size slider, layers, undo, and PNG export' },
    { name: 'Music Visualizer', cat: 'Creative', desc: 'Audio visualizer that reacts to microphone input or uploaded music using Web Audio API + Canvas' },
    // Data / Dashboards
    { name: 'Analytics Dashboard', cat: 'Dashboard', desc: 'Dark analytics dashboard with line/bar/pie charts using Chart.js, KPI cards, date filter, and responsive grid layout' },
    { name: 'Landing Page',    cat: 'Dashboard', desc: 'Product landing page with hero section, features grid, testimonials, pricing table, and contact form. Smooth scroll animations.' },
    { name: 'Weather App',     cat: 'Dashboard', desc: 'Weather dashboard with city search, 7-day forecast cards, hourly chart, UV index, humidity, and wind speed' },
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

  useEffect(() => {
    editEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [editHistory, editLoading]);

  // Load sessions from backend (Postgres) on mount; fall back to localStorage
  useEffect(() => {
    axiosInstance.get('/app-builder/sessions').then(res => {
      if (Array.isArray(res.data) && res.data.length > 0) {
        setSavedSessions(res.data);
        try { localStorage.setItem(SESSIONS_KEY, JSON.stringify(res.data)); } catch {}
      }
    }).catch(() => {
      // Postgres unavailable — keep localStorage sessions already loaded
    });
  }, []);

  // Auto-save to Postgres (and localStorage as fallback) whenever app or edit history changes
  useEffect(() => {
    if (!generatedApp) return;
    const existing = savedSessions.find(s => s.id === (generatedApp.build_id || generatedApp.name));
    const session = {
      id: generatedApp.build_id || generatedApp.name,
      name: generatedApp.name,
      description: generatedApp.description || '',
      html: generatedApp.html,
      project: generatedApp.project || null,
      editHistory,
      versions,
      build_id: generatedApp.build_id,
      preview_url: generatedApp.full_preview_url || null,
      project_type: generatedApp.project_type || 'app',
      is_pinned: existing?.is_pinned || false,
      is_archived: existing?.is_archived || false,
      edit_count: editHistory.filter(m => m.role === 'user').length,
      last_edited_file: editHistory.filter(m => m.role === 'assistant' && m.file_changed).slice(-1)[0]?.file_changed || null,
      savedAt: new Date().toISOString(),
    };
    // Persist to Postgres
    axiosInstance.post('/app-builder/sessions', session).catch(() => {});
    // Also keep localStorage as fallback
    setSavedSessions(prev => {
      const filtered = prev.filter(s => s.id !== session.id);
      const updated = [session, ...filtered].slice(0, 20);
      try { localStorage.setItem(SESSIONS_KEY, JSON.stringify(updated)); } catch {}
      return updated;
    });
  }, [generatedApp, editHistory, versions]);

  const resumeSession = (session) => {
    const html = session.project ? reconstructHtml(session.project) : session.html;
    setGeneratedApp({
      name: session.name,
      description: session.description,
      html,
      project: session.project || null,
      build_id: session.build_id,
      full_preview_url: session.preview_url || session.full_preview_url,
    });
    setEditHistory(session.editHistory || []);
    setVersions(session.versions || []);
    setMode('build');
  };

  const deleteSession = (id) => {
    axiosInstance.delete(`/app-builder/sessions/${id}`).catch(() => {});
    setSavedSessions(prev => {
      const updated = prev.filter(s => s.id !== id);
      try { localStorage.setItem(SESSIONS_KEY, JSON.stringify(updated)); } catch {}
      return updated;
    });
  };

  const pinSession = (id) => {
    setSavedSessions(prev => {
      const updated = prev.map(s => s.id === id ? { ...s, is_pinned: !s.is_pinned } : s);
      try { localStorage.setItem(SESSIONS_KEY, JSON.stringify(updated)); } catch {}
      const session = updated.find(s => s.id === id);
      if (session) axiosInstance.patch(`/app-builder/sessions/${id}`, { is_pinned: session.is_pinned }).catch(() => {});
      return updated;
    });
  };

  const archiveSession = (id) => {
    setSavedSessions(prev => {
      const updated = prev.map(s => s.id === id ? { ...s, is_archived: !s.is_archived } : s);
      try { localStorage.setItem(SESSIONS_KEY, JSON.stringify(updated)); } catch {}
      const session = updated.find(s => s.id === id);
      if (session) axiosInstance.patch(`/app-builder/sessions/${id}`, { is_archived: session.is_archived }).catch(() => {});
      return updated;
    });
  };

  const restoreBackendVersion = async (sessionId, versionIndex) => {
    try {
      const res = await axiosInstance.post(`/app-builder/sessions/${sessionId}/restore-version`, {
        version_index: versionIndex,
      });
      const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
      pushUndo(generatedApp);
      setGeneratedApp(prev => ({
        ...prev,
        project: res.data.project,
        html: res.data.html,
        build_id: res.data.build_id,
        full_preview_url: res.data.preview_url ? backendUrl.replace('/api', '') + res.data.preview_url : prev.full_preview_url,
      }));
      setActiveTab('preview');
      toast.success(`Restored: ${res.data.restored_version?.name || `v${versionIndex + 1}`}`);
    } catch {
      toast.error('Failed to restore version');
    }
  };

  // Filtered + sorted session list for display
  const filteredSessions = savedSessions
    .filter(s => {
      if (!showArchived && s.is_archived) return false;
      if (sessionSearch && !s.name?.toLowerCase().includes(sessionSearch.toLowerCase())) return false;
      return true;
    })
    .sort((a, b) => {
      if (sessionSort === 'pinned') {
        if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;
      }
      if (sessionSort === 'oldest') return new Date(a.savedAt) - new Date(b.savedAt);
      if (sessionSort === 'most_edited') return (b.edit_count || 0) - (a.edit_count || 0);
      return new Date(b.savedAt) - new Date(a.savedAt); // newest
    });

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
      const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
      const data = response.data;
      if (data.preview_url) {
        data.full_preview_url = backendUrl.replace('/api', '') + data.preview_url;
      }
      // Use structured project for everything; keep raw html as fallback
      if (data.project) {
        data.html = reconstructHtml(data.project);
      }
      setGeneratedApp(data);
      toast.success('App generated!');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to generate app');
    } finally {
      stopLoadingCycle(setBuildMsg);
      setBuildLoading(false);
    }
  };

  const editApp = async () => {
    if (!editInput.trim() || editLoading || !generatedApp?.html) return;
    const instruction = editInput.trim();
    setEditInput('');
    setEditHistory(prev => [...prev, { role: 'user', content: instruction }]);
    setEditLoading(true);
    let i = 0;
    setEditMsg(EDIT_LOADING_MSGS[0]);
    editLoadingIntervalRef.current = setInterval(() => {
      i = (i + 1) % EDIT_LOADING_MSGS.length;
      setEditMsg(EDIT_LOADING_MSGS[i]);
    }, 2500);
    try {
      // Snapshot current state before overwriting
      pushUndo(generatedApp);
      const res = await axiosInstance.post('/app-builder/edit', {
        project: generatedApp.project || null,
        html: generatedApp.project ? null : generatedApp.html,
        instruction,
      }, { timeout: 300000 });
      const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
      const updated = {
        ...generatedApp,
        project: res.data.project || generatedApp.project,
        html: res.data.html || reconstructHtml(res.data.project),
        build_id: res.data.build_id,
      };
      if (res.data.preview_url) {
        updated.full_preview_url = backendUrl.replace('/api', '') + res.data.preview_url;
      }
      setGeneratedApp(updated);
      const fileChanged = res.data.file_changed;
      const reply = fileChanged
        ? `Done! Edited \`${fileChanged}\`. Preview updated above.`
        : 'Done! Preview updated above.';
      setEditHistory(prev => [...prev, { role: 'assistant', content: reply, file_changed: fileChanged }]);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to apply changes';
      toast.error(msg);
      setEditHistory(prev => [...prev, { role: 'assistant', content: `Error: ${msg}` }]);
    } finally {
      clearInterval(editLoadingIntervalRef.current);
      setEditMsg('');
      setEditLoading(false);
    }
  };

  const handleEditKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      editApp();
    }
  };

  // ── Undo / Redo / Version history ────────────────────────────────────────────
  const pushUndo = (app = generatedApp) => {
    if (!app?.project) return;
    setUndoStack(prev => [...prev.slice(-19), { project: app.project, html: app.html, time: new Date().toISOString() }]);
    setRedoStack([]);  // new action clears redo
  };

  const undo = () => {
    if (!undoStack.length) { toast.error('Nothing to undo'); return; }
    const snap = undoStack[undoStack.length - 1];
    setUndoStack(s => s.slice(0, -1));
    setRedoStack(r => [...r, { project: generatedApp.project, html: generatedApp.html, time: new Date().toISOString() }]);
    setGeneratedApp(g => ({ ...g, project: snap.project, html: snap.html }));
    toast.success('Undone');
  };

  const redo = () => {
    if (!redoStack.length) { toast.error('Nothing to redo'); return; }
    const snap = redoStack[redoStack.length - 1];
    setRedoStack(r => r.slice(0, -1));
    setUndoStack(prev => [...prev, { project: generatedApp.project, html: generatedApp.html, time: new Date().toISOString() }]);
    setGeneratedApp(g => ({ ...g, project: snap.project, html: snap.html }));
    toast.success('Redone');
  };

  const saveVersion = () => {
    if (!generatedApp?.project) return;
    const name = versionName.trim() || `v${versions.length + 1} — ${new Date().toLocaleTimeString()}`;
    const lastEdit = editHistory.filter(m => m.role === 'assistant').slice(-1)[0];
    setVersions(prev => [...prev, {
      name,
      project: generatedApp.project,
      html: generatedApp.html,
      savedAt: new Date().toISOString(),
      file_changed: lastEdit?.file_changed || null,
      summary: editHistory.filter(m => m.role === 'user').slice(-1)[0]?.content?.slice(0, 60) || null,
    }]);
    setVersionName('');
    toast.success(`Saved "${name}"`);
  };

  const restoreVersion = (ver) => {
    pushUndo();
    setGeneratedApp(g => ({ ...g, project: ver.project, html: ver.html }));
    setShowVersions(false);
    setActiveTab('preview');
    toast.success(`Restored "${ver.name}"`);
  };

  // ── Direct file edit (no AI) ─────────────────────────────────────────────────
  const handleDirectEdit = (file, value) => {
    setGeneratedApp(prev => {
      if (!prev?.project) return prev;
      const p = { ...prev.project };
      if (file === 'html') p.index_html = value;
      if (file === 'css')  p.style_css  = value;
      if (file === 'js')   p.script_js  = value;
      return { ...prev, project: p, html: reconstructHtml(p) };
    });
  };

  const openInBrowser = () => {
    if (!generatedApp?.html) return;
    const blob = new Blob([generatedApp.html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  };

  // ── Import ────────────────────────────────────────────────────────────────────
  const handleImportHtml = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const name = file.name.replace(/\.html?$/, '') || 'imported-app';
    try {
      toast.info('Importing HTML...');
      const res = await axiosInstance.post('/app-builder/import-html', { html: text, name }, { timeout: 30000 });
      const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
      const data = res.data;
      if (data.preview_url) data.full_preview_url = backendUrl.replace('/api', '') + data.preview_url;
      setGeneratedApp(data);
      setEditHistory([]);
      setUndoStack([]); setRedoStack([]); setVersions([]);
      setActiveTab('preview');
      setMode('build');
      toast.success(`Imported "${name}"`);
    } catch { toast.error('Import failed'); }
    e.target.value = '';
  };

  const handleImportZip = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    try {
      toast.info('Extracting ZIP...');
      const res = await axiosInstance.post('/app-builder/import-zip', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 30000,
      });
      const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
      const data = res.data;
      if (data.preview_url) data.full_preview_url = backendUrl.replace('/api', '') + data.preview_url;
      setGeneratedApp(data);
      setEditHistory([]);
      setUndoStack([]); setRedoStack([]); setVersions([]);
      setActiveTab('preview');
      setMode('build');
      toast.success(`Imported ZIP: "${data.name}"`);
    } catch { toast.error('ZIP import failed'); }
    e.target.value = '';
  };

  const exportZip = async () => {
    if (!generatedApp?.html) return;
    try {
      toast.info('Building ZIP...');
      const res = await axiosInstance.post('/app-builder/export-zip', {
        project: generatedApp.project || null,
        html: generatedApp.project ? null : generatedApp.html,
        name: generatedApp.name || 'generated-app',
        description: generatedApp.description || '',
      }, { responseType: 'blob', timeout: 60000 });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/zip' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `${generatedApp.name || 'generated-app'}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Project ZIP downloaded!');
    } catch {
      toast.error('Failed to export ZIP');
    }
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

        {/* Templates (build mode only, no active app) */}
        {mode === 'build' && !generatedApp && (
          <div>
            <div className="text-xs text-cyan-400/70 font-mono uppercase mb-2">Quick Templates:</div>
            {['App','Game','Creative','Dashboard'].map(cat => {
              const group = templates.filter(t => t.cat === cat);
              return (
                <div key={cat} className="mb-2">
                  <span className="text-[10px] text-slate-600 font-mono uppercase mr-2">{cat}</span>
                  {group.map((t, i) => (
                    <button
                      key={i}
                      onClick={() => { setDescription(t.desc); }}
                      className="mr-1.5 mb-1 px-2.5 py-1 bg-black/30 border border-cyan-500/20 hover:border-cyan-400/60 text-cyan-200 text-[11px] rounded-sm transition-all font-mono"
                    >
                      {t.name}
                    </button>
                  ))}
                </div>
              );
            })}
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
            <div className="p-5 space-y-4 overflow-y-auto flex-1">

              {/* Saved sessions */}
              {savedSessions.length > 0 && (
                <div className="space-y-2">
                  {/* Header + controls */}
                  <div className="flex items-center gap-2">
                    <FolderOpen className="w-3.5 h-3.5 text-cyan-400/70" />
                    <span className="text-xs font-mono text-cyan-400/70 uppercase tracking-wider flex-1">Saved Builds</span>
                    <button
                      onClick={() => setShowArchived(v => !v)}
                      className={`text-xs font-mono px-2 py-0.5 rounded-sm border transition-all ${showArchived ? 'border-violet-500/60 text-violet-400' : 'border-slate-700 text-slate-500 hover:border-slate-500'}`}
                      title="Show archived"
                    >
                      <Archive className="w-3 h-3" />
                    </button>
                  </div>

                  {/* Search + sort row */}
                  <div className="flex gap-2">
                    <div className="flex-1 flex items-center gap-1.5 bg-black/40 border border-cyan-900/40 rounded-sm px-2">
                      <Search className="w-3 h-3 text-slate-600 flex-shrink-0" />
                      <input
                        value={sessionSearch}
                        onChange={e => setSessionSearch(e.target.value)}
                        placeholder="Search builds..."
                        className="flex-1 bg-transparent text-xs font-mono text-cyan-200 placeholder:text-slate-700 outline-none py-1.5"
                      />
                    </div>
                    <select
                      value={sessionSort}
                      onChange={e => setSessionSort(e.target.value)}
                      className="bg-black/40 border border-cyan-900/40 text-xs font-mono text-cyan-400 rounded-sm px-2 outline-none"
                    >
                      <option value="newest">Newest</option>
                      <option value="oldest">Oldest</option>
                      <option value="most_edited">Most Edited</option>
                      <option value="pinned">Pinned First</option>
                    </select>
                  </div>

                  {/* Session list */}
                  <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
                    {filteredSessions.length === 0 && (
                      <div className="text-xs font-mono text-slate-600 text-center py-3">No builds match</div>
                    )}
                    {filteredSessions.map(session => (
                      <div
                        key={session.id}
                        className={`flex items-center gap-2 p-3 border rounded-sm group transition-all
                          ${session.is_pinned ? 'bg-cyan-950/30 border-cyan-600/40' : 'bg-black/40 border-cyan-900/30'}
                          ${session.is_archived ? 'opacity-50' : ''}
                          hover:border-cyan-500/50`}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            {session.is_pinned && <Pin className="w-3 h-3 text-cyan-500 flex-shrink-0" />}
                            <span className="text-sm font-mono text-cyan-300 truncate">{session.name}</span>
                            {(() => {
                              const badge = getHealthBadge(session);
                              return (
                                <span className={`text-[9px] font-mono border px-1 rounded-sm flex items-center gap-0.5 flex-shrink-0 ${badge.cls}`}>
                                  <badge.Icon className="w-2.5 h-2.5" />{badge.label}
                                </span>
                              );
                            })()}
                          </div>
                          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                            <span className="flex items-center gap-1 text-xs text-slate-600 font-mono">
                              <Clock className="w-3 h-3" />
                              {new Date(session.savedAt).toLocaleDateString(undefined, { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })}
                            </span>
                            {(session.edit_count || 0) > 0 && (
                              <span className="text-xs text-violet-500 font-mono">{session.edit_count} edit{session.edit_count !== 1 ? 's' : ''}</span>
                            )}
                            {session.last_edited_file && (
                              <span className="text-xs text-slate-600 font-mono">{session.last_edited_file}</span>
                            )}
                            {session.versions?.length > 0 && (
                              <span className="text-xs text-amber-600 font-mono">{session.versions.length} versions</span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button
                            onClick={() => resumeSession(session)}
                            className="px-2.5 py-1 bg-cyan-500/20 border border-cyan-500/40 text-cyan-400 text-xs font-mono uppercase rounded-sm hover:bg-cyan-500/30 transition-all"
                          >
                            Open
                          </button>
                          <button
                            onClick={() => pinSession(session.id)}
                            className={`p-1.5 transition-colors ${session.is_pinned ? 'text-cyan-400' : 'text-slate-700 hover:text-cyan-500'}`}
                            title={session.is_pinned ? 'Unpin' : 'Pin'}
                          >
                            <Pin className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => archiveSession(session.id)}
                            className={`p-1.5 transition-colors ${session.is_archived ? 'text-violet-400' : 'text-slate-700 hover:text-violet-500'}`}
                            title={session.is_archived ? 'Unarchive' : 'Archive'}
                          >
                            <Archive className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => deleteSession(session.id)}
                            className="p-1.5 text-slate-700 hover:text-red-400 transition-colors"
                            title="Delete"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="border-t border-cyan-900/30 pt-3 flex items-center gap-3">
                    <span className="text-xs font-mono text-slate-600 uppercase flex-1">Or start a new build:</span>
                    <button onClick={() => importHtmlRef.current?.click()}
                      className="flex items-center gap-1 px-2 py-1 text-slate-500 hover:text-cyan-400 text-[10px] font-mono uppercase border border-slate-700/40 rounded-sm hover:border-cyan-500/40 transition-all">
                      <Upload className="w-3 h-3" /> Import HTML
                    </button>
                    <button onClick={() => importZipRef.current?.click()}
                      className="flex items-center gap-1 px-2 py-1 text-slate-500 hover:text-cyan-400 text-[10px] font-mono uppercase border border-slate-700/40 rounded-sm hover:border-cyan-500/40 transition-all">
                      <Upload className="w-3 h-3" /> Import ZIP
                    </button>
                  </div>
                </div>
              )}

              <textarea
                data-testid="app-description-input"
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Describe your app in detail (or use the Coach to build a spec first)..."
                className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono p-4 outline-none resize-none"
                rows={6}
                disabled={buildLoading}
              />
              {/* Hidden import file inputs */}
              <input ref={importHtmlRef} type="file" accept=".html,.htm" onChange={handleImportHtml} className="hidden" />
              <input ref={importZipRef}  type="file" accept=".zip"       onChange={handleImportZip}  className="hidden" />

              <div className="flex items-center gap-3 flex-wrap">
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
                <div className="flex items-center gap-2 ml-auto">
                  <button onClick={() => importHtmlRef.current?.click()}
                    className="flex items-center gap-1 px-3 py-2 text-slate-500 hover:text-cyan-400 text-xs font-mono uppercase border border-slate-700/40 rounded-sm hover:border-cyan-500/40 transition-all">
                    <Upload className="w-3.5 h-3.5" /> HTML
                  </button>
                  <button onClick={() => importZipRef.current?.click()}
                    className="flex items-center gap-1 px-3 py-2 text-slate-500 hover:text-cyan-400 text-xs font-mono uppercase border border-slate-700/40 rounded-sm hover:border-cyan-500/40 transition-all">
                    <Upload className="w-3.5 h-3.5" /> ZIP
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col overflow-hidden">

              {/* ── Toolbar ── */}
              <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-cyan-500/20 bg-black/50 flex-shrink-0 flex-wrap">
                <CheckCircle className="w-3.5 h-3.5 text-green-400 flex-shrink-0" />
                <span className="text-[11px] font-mono text-green-400 flex-1 truncate min-w-0">{generatedApp.name}</span>

                {/* Undo / Redo */}
                <button onClick={undo} disabled={!undoStack.length}
                  title={`Undo (${undoStack.length})`}
                  className="flex items-center gap-1 px-2 py-1 text-slate-400 hover:text-cyan-400 disabled:opacity-30 disabled:cursor-not-allowed text-[10px] font-mono uppercase transition-colors border border-slate-700/40 rounded-sm hover:border-cyan-500/40">
                  <Undo2 className="w-3 h-3" /> Undo
                </button>
                <button onClick={redo} disabled={!redoStack.length}
                  title={`Redo (${redoStack.length})`}
                  className="flex items-center gap-1 px-2 py-1 text-slate-400 hover:text-cyan-400 disabled:opacity-30 disabled:cursor-not-allowed text-[10px] font-mono uppercase transition-colors border border-slate-700/40 rounded-sm hover:border-cyan-500/40">
                  <Redo2 className="w-3 h-3" /> Redo
                </button>

                {/* Save version */}
                <button onClick={saveVersion}
                  title="Save a named restore point"
                  className="flex items-center gap-1 px-2 py-1 text-yellow-500/80 hover:text-yellow-400 text-[10px] font-mono uppercase transition-colors border border-yellow-700/30 rounded-sm hover:border-yellow-500/50">
                  <BookmarkPlus className="w-3 h-3" /> Save
                </button>

                {/* History */}
                <button onClick={() => setShowVersions(v => !v)}
                  className={`flex items-center gap-1 px-2 py-1 text-[10px] font-mono uppercase transition-colors border rounded-sm ${
                    showVersions ? 'bg-violet-500/20 border-violet-500/50 text-violet-300' : 'text-slate-400 border-slate-700/40 hover:text-violet-400 hover:border-violet-500/40'
                  }`}>
                  <History className="w-3 h-3" /> {versions.length > 0 ? `History (${versions.length})` : 'History'}
                </button>

                <div className="w-px h-4 bg-slate-700/60 mx-0.5" />

                <button onClick={openInBrowser} className="flex items-center gap-1 px-2 py-1 bg-cyan-500/20 border border-cyan-500/40 text-cyan-400 text-[10px] font-mono uppercase rounded-sm hover:bg-cyan-500/30 transition-all">
                  <Eye className="w-3 h-3" /> Open
                </button>
                <button onClick={downloadApp} className="flex items-center gap-1 px-2 py-1 bg-violet-500/20 border border-violet-500/40 text-violet-400 text-[10px] font-mono uppercase rounded-sm hover:bg-violet-500/30 transition-all">
                  <Download className="w-3 h-3" /> .HTML
                </button>
                <button onClick={exportZip} className="flex items-center gap-1 px-2 py-1 bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 text-[10px] font-mono uppercase rounded-sm hover:bg-emerald-500/30 transition-all">
                  <Package className="w-3 h-3" /> ZIP
                </button>
                <button onClick={() => { setGeneratedApp(null); setDescription(''); setEditInput(''); setEditHistory([]); setUndoStack([]); setRedoStack([]); setVersions([]); setActiveTab('preview'); setDiffView(null); }}
                  className="flex items-center gap-1 px-2 py-1 text-slate-500 hover:text-slate-300 text-[10px] font-mono uppercase transition-colors border border-slate-700/30 rounded-sm hover:border-slate-500/50">
                  <RotateCcw className="w-3 h-3" /> New
                </button>
              </div>

              {/* ── Version history panel ── */}
              {showVersions && (
                <div className="border-b border-violet-500/20 bg-black/60 px-4 py-3 flex-shrink-0">
                  <div className="flex items-center gap-2 mb-2">
                    <History className="w-3.5 h-3.5 text-violet-400" />
                    <span className="text-[10px] font-mono text-violet-400 uppercase tracking-wider flex-1">Version History</span>
                    <input
                      value={versionName}
                      onChange={e => setVersionName(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && saveVersion()}
                      placeholder="Version name..."
                      className="bg-black/50 border border-violet-900/50 text-violet-100 placeholder:text-violet-900/50 rounded-sm px-2 py-1 text-[10px] font-mono outline-none focus:border-violet-400 w-36"
                    />
                    <button onClick={saveVersion} className="px-2 py-1 bg-violet-500/20 border border-violet-500/40 text-violet-400 text-[10px] font-mono uppercase rounded-sm hover:bg-violet-500/30">
                      + Save Now
                    </button>
                  </div>
                  {versions.length === 0 ? (
                    <p className="text-[10px] text-slate-600 font-mono">No saved versions yet. Click "+ Save Now" to create a restore point.</p>
                  ) : (
                    <div className="space-y-1 max-h-40 overflow-y-auto">
                      {versions.map((ver, i) => (
                        <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 bg-black/40 border border-violet-900/40 rounded-sm group">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5">
                              <span className="text-[10px] font-mono text-violet-300 truncate">{ver.name}</span>
                              {ver.file_changed && (
                                <span className="text-[9px] font-mono text-slate-500 bg-slate-800 px-1 rounded">{ver.file_changed}</span>
                              )}
                            </div>
                            <div className="flex items-center gap-2 mt-0.5">
                              <span className="text-[9px] text-slate-600 font-mono">
                                {new Date(ver.savedAt).toLocaleString(undefined, { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })}
                              </span>
                              {ver.summary && (
                                <span className="text-[9px] text-slate-500 font-mono truncate max-w-32">{ver.summary}</span>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-1 flex-shrink-0">
                            <button
                              onClick={() => {
                                const prevVer = versions[i - 1] || null;
                                const fileKey = ver.file_changed === 'style.css' ? 'style_css'
                                  : ver.file_changed === 'script.js' ? 'script_js' : 'index_html';
                                setDiffView({
                                  file: ver.file_changed || 'index.html',
                                  fileKey,
                                  verA: prevVer?.project || null,
                                  verB: ver.project,
                                  nameA: prevVer?.name || 'previous',
                                  nameB: ver.name,
                                });
                              }}
                              className="text-[9px] font-mono text-amber-500 hover:text-amber-400 uppercase flex items-center gap-0.5"
                              title="View diff"
                            >
                              Diff
                            </button>
                            <span className="text-slate-700">·</span>
                            <button
                              onClick={() => generatedApp?.build_id
                                ? restoreBackendVersion(generatedApp.build_id, i)
                                : restoreVersion(ver)}
                              className="text-[9px] font-mono text-cyan-400 hover:text-cyan-300 uppercase flex items-center gap-1"
                            >
                              <RefreshCw className="w-2.5 h-2.5" /> Restore
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* ── Diff viewer panel ── */}
              {diffView && (
                <div className="border-b border-amber-500/20 bg-black/70 flex-shrink-0 flex flex-col" style={{ maxHeight: '220px' }}>
                  <div className="flex items-center gap-2 px-4 py-2 border-b border-amber-500/10">
                    <span className="text-[10px] font-mono text-amber-400 uppercase tracking-wider flex-1">
                      Diff — {diffView.file} · {diffView.nameA} → {diffView.nameB}
                    </span>
                    <button onClick={() => setDiffView(null)} className="text-slate-600 hover:text-slate-300"><X className="w-3.5 h-3.5" /></button>
                  </div>
                  <div className="overflow-y-auto text-[10px] font-mono px-3 py-2 space-y-0.5">
                    {computeDiff(diffView.verA?.[diffView.fileKey] || '', diffView.verB?.[diffView.fileKey] || '').map((line, i) => (
                      line.t === 'eq' ? null : (
                        <div key={i} className={`px-1.5 py-0.5 rounded-sm whitespace-pre-wrap break-all ${
                          line.t === 'add' ? 'bg-emerald-950/60 text-emerald-400' : 'bg-red-950/60 text-red-400 line-through'
                        }`}>
                          {line.t === 'add' ? '+ ' : '- '}{line.s}
                        </div>
                      )
                    ))}
                  </div>
                </div>
              )}

              {/* ── File tabs ── */}
              <div className="flex items-center border-b border-cyan-500/20 bg-black/30 flex-shrink-0 overflow-x-auto">
                {[
                  { id: 'preview', label: 'Preview',    icon: <MonitorPlay className="w-3 h-3" /> },
                  { id: 'html',    label: 'index.html', icon: <FileCode className="w-3 h-3" /> },
                  { id: 'css',     label: 'style.css',  icon: <Palette className="w-3 h-3" /> },
                  { id: 'js',      label: 'script.js',  icon: <Code2 className="w-3 h-3" /> },
                  { id: 'readme',  label: 'README.md',  icon: <BookOpen className="w-3 h-3" /> },
                ].map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-1.5 px-3 py-2 text-[11px] font-mono border-r border-cyan-500/10 transition-all flex-shrink-0 ${
                      activeTab === tab.id
                        ? 'bg-cyan-500/10 text-cyan-400 border-b-2 border-b-cyan-400'
                        : 'text-slate-500 hover:text-slate-300 hover:bg-white/5'
                    }`}
                  >
                    {tab.icon}{tab.label}
                  </button>
                ))}
              </div>

              {/* ── Content area (preview OR code editor) ── */}
              <div className="flex-shrink-0 overflow-hidden" style={{ height: '48%' }}>
                {activeTab === 'preview' && (
                  <iframe
                    key={generatedApp.html}
                    srcDoc={generatedApp.html}
                    title="App Preview"
                    className="w-full h-full border-0 bg-white"
                    sandbox="allow-scripts allow-forms allow-modals allow-same-origin"
                  />
                )}
                {activeTab === 'html' && (
                  <textarea
                    value={generatedApp.project?.index_html || ''}
                    onChange={e => handleDirectEdit('html', e.target.value)}
                    onBlur={() => pushUndo()}
                    className="w-full h-full bg-[#0d1117] text-[#e6edf3] font-mono text-xs p-3 outline-none resize-none border-0"
                    spellCheck={false}
                  />
                )}
                {activeTab === 'css' && (
                  <textarea
                    value={generatedApp.project?.style_css || ''}
                    onChange={e => handleDirectEdit('css', e.target.value)}
                    onBlur={() => pushUndo()}
                    className="w-full h-full bg-[#0d1117] text-[#e6edf3] font-mono text-xs p-3 outline-none resize-none border-0"
                    spellCheck={false}
                  />
                )}
                {activeTab === 'js' && (
                  <textarea
                    value={generatedApp.project?.script_js || ''}
                    onChange={e => handleDirectEdit('js', e.target.value)}
                    onBlur={() => pushUndo()}
                    className="w-full h-full bg-[#0d1117] text-[#e6edf3] font-mono text-xs p-3 outline-none resize-none border-0"
                    spellCheck={false}
                  />
                )}
                {activeTab === 'readme' && (
                  <textarea
                    value={generatedApp.project?.readme || ''}
                    onChange={e => setGeneratedApp(prev => ({
                      ...prev,
                      project: { ...prev.project, readme: e.target.value }
                    }))}
                    className="w-full h-full bg-[#0d1117] text-[#e6edf3] font-mono text-xs p-3 outline-none resize-none border-0"
                    spellCheck={false}
                  />
                )}
              </div>

              {/* ── Edit conversation ── */}
              <div className="flex-1 flex flex-col overflow-hidden border-t border-cyan-500/20">
                <div className="px-4 py-1.5 bg-black/40 border-b border-cyan-500/10 flex items-center gap-2 flex-shrink-0">
                  <Pencil className="w-3 h-3 text-cyan-400" />
                  <span className="text-[10px] font-mono text-cyan-400 uppercase tracking-wider flex-1">AI Edit Chat</span>
                  {undoStack.length > 0 && (
                    <span className="text-[9px] text-slate-600 font-mono">{undoStack.length} undo state{undoStack.length !== 1 ? 's' : ''}</span>
                  )}
                </div>

                <div className="flex-1 overflow-y-auto p-3 space-y-2">
                  {editHistory.length === 0 && (
                    <p className="text-[10px] text-slate-600 font-mono text-center py-3">
                      Test in Preview tab, edit files directly above, or chat here to make AI changes.
                    </p>
                  )}
                  {editHistory.map((msg, idx) => (
                    <div key={idx} className={`flex items-start gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      {msg.role === 'assistant' && (
                        <div className="w-5 h-5 rounded bg-gradient-to-br from-cyan-500 to-violet-600 flex items-center justify-center flex-shrink-0">
                          <Wand2 className="w-2.5 h-2.5 text-white" />
                        </div>
                      )}
                      <div className={`max-w-[80%] px-2.5 py-1.5 rounded text-[10px] font-mono ${
                        msg.role === 'user'
                          ? 'bg-cyan-500/20 border border-cyan-500/30 text-cyan-100'
                          : 'bg-black/40 border border-cyan-900/30 text-slate-300'
                      }`}>
                        {msg.content}
                      </div>
                    </div>
                  ))}
                  {editLoading && (
                    <div className="flex items-center gap-2">
                      <div className="w-5 h-5 rounded bg-gradient-to-br from-cyan-500 to-violet-600 flex items-center justify-center flex-shrink-0">
                        <Loader2 className="w-2.5 h-2.5 text-white animate-spin" />
                      </div>
                      <div className="px-2.5 py-1.5 bg-black/40 border border-cyan-900/30 rounded">
                        <span className="text-[10px] font-mono text-cyan-400/80 animate-pulse">{editMsg || 'Working...'}</span>
                      </div>
                    </div>
                  )}
                  <div ref={editEndRef} />
                </div>

                <div className="p-2.5 border-t border-cyan-500/20 bg-black/30 flex gap-2 items-end flex-shrink-0">
                  <textarea
                    value={editInput}
                    onChange={e => setEditInput(e.target.value)}
                    onKeyDown={handleEditKey}
                    placeholder='Ask AI to change or fix something...'
                    className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/40 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono text-[11px] p-2 outline-none resize-none"
                    rows={2}
                    disabled={editLoading}
                  />
                  <button
                    onClick={editApp}
                    disabled={editLoading || !editInput.trim()}
                    className="p-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white rounded-sm hover:from-cyan-400 hover:to-violet-500 disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                  >
                    <Send className="w-3.5 h-3.5" />
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
