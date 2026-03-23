import React, { useState, useRef, useEffect, useMemo } from 'react';
import { axiosInstance } from '../../App';
import { useApp } from '../../context/AppContext';
import { toast } from 'sonner';
import { trackEvent } from '../../utils/trackEvent';
import {
  reconstructHtmlFromProject,
  getContent as ptGetContent,
  setContent as ptSetContent,
  getExtraFiles as ptGetExtraFiles,
  getAssets as ptGetAssets,
  getFileMeta as ptGetFileMeta,
  setFileMeta as ptSetFileMeta,
  getAllPaths as ptGetAllPaths,
  addNodeToTree as ptAddNodeToTree,
  removeNodeFromTree as ptRemoveNodeFromTree,
  makeFileNode as ptMakeFileNode,
  ensureV2 as ptEnsureV2,
} from '../../utils/projectTree';
import {
  Wand2, Loader2, Download, Eye,
  MessageSquare, Send, ChevronRight, RotateCcw, Sparkles, Pencil, CheckCircle,
  Trash2, FolderOpen, Clock, Package, Undo2, History, MonitorPlay,
  FileCode, Palette, Code2, BookmarkPlus, X, Pin, Archive, Search,
  SortAsc, RefreshCw, Redo2, Upload, BookOpen, AlertTriangle, AlertCircle,
  ShieldCheck, ArchiveRestore, Bug, Zap, Gauge, Terminal, Wrench,
  FilePlus, FolderTree, FileText, Folder,
  Github, Globe, Share2, LogIn, Lock, Unlock, Link, Copy, CheckSquare,
  Columns, Command, Server,
  Activity, StickyNote, Star, AlignLeft, Replace, ChevronDown,
  Shield, ShieldOff, FileSearch, GitCommit, TrendingUp
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

// ── Quick-answer chips for coach questions ─────────────────────────────────────
const QUESTION_CHIPS = {
  who:      ['Just for me', 'Small team', 'Public users', 'Business / clients'],
  style:    ['Dark & minimal', 'Light & clean', 'Colorful & vibrant', 'Neon / cyberpunk', 'Professional'],
  login:    ['No login needed', 'Email & password', 'Google / social login'],
  data:     ['No data storage', 'Browser only', 'Cloud database'],
  features: ['Simple & focused', 'Full-featured', 'Mobile-first', 'Dashboard / charts'],
  pages:    ['Single page', 'Multi-page', 'Full web app with nav'],
};

const detectChips = (text) => {
  if (/(who|target|audience|user|for whom|intended for)/i.test(text)) return QUESTION_CHIPS.who;
  if (/(style|look|feel|design|theme|aesthetic|color|visual|appearance)/i.test(text)) return QUESTION_CHIPS.style;
  if (/(login|sign.?in|auth|account|user account)/i.test(text)) return QUESTION_CHIPS.login;
  if (/(data|stor|sav|persist|database|backend)/i.test(text)) return QUESTION_CHIPS.data;
  if (/(feature|function|capability|must.have|key things)/i.test(text)) return QUESTION_CHIPS.features;
  if (/(page|scope|scale|section|nav|size)/i.test(text)) return QUESTION_CHIPS.pages;
  return [];
};

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
 * Supports both v1 (flat) and v2 (tree) project formats.
 */
const reconstructHtml = (project) => reconstructHtmlFromProject(project);

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

// ---------------------------------------------------------------------------
// LockedCodeView — shown to free-plan users instead of the editable textarea
// ---------------------------------------------------------------------------
function LockedCodeView({ code, onUpgrade }) {
  const lines = (code || '').split('\n');
  const totalLines = lines.length;
  const preview = lines.slice(0, 8).join('\n');
  const lockedCount = Math.max(0, totalLines - 8);

  return (
    <div className="relative h-full bg-[#0d1117] overflow-hidden select-none cursor-default">
      {/* Preview: first 8 lines */}
      <pre className="text-[#e6edf3] font-mono text-xs p-3 whitespace-pre-wrap break-all leading-5 pointer-events-none opacity-60">
        {preview}
      </pre>

      {/* Gradient fade */}
      <div className="absolute inset-x-0 top-0 h-full bg-gradient-to-b from-transparent from-20% via-[#0d1117]/90 to-[#0d1117] pointer-events-none" />

      {/* Lock overlay */}
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 px-6">
        {/* Lock icon + heading */}
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="w-12 h-12 rounded-2xl bg-amber-500/10 border border-amber-500/25 flex items-center justify-center shadow-lg">
            <Lock className="w-5 h-5 text-amber-400" />
          </div>
          <p className="text-sm font-bold text-slate-200">🔒 Source code is locked</p>
          <p className="text-[11px] text-slate-500 max-w-[220px] leading-relaxed text-center">
            Upgrade to access full source code and deployment.
          </p>
          {lockedCount > 0 && (
            <span className="text-[9px] font-mono text-amber-500/70 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full">
              +{lockedCount} lines hidden
            </span>
          )}
        </div>

        {/* CTA */}
        <button
          onClick={onUpgrade}
          className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-violet-600 text-white text-xs font-bold hover:from-cyan-400 hover:to-violet-500 transition-all shadow-lg shadow-violet-900/40"
        >
          <Lock className="w-3 h-3" /> Unlock Full Access
        </button>
        <p className="text-[10px] text-slate-600 text-center max-w-[200px] leading-relaxed">
          Your project is ready to go live.<br />Upgrade to deploy and take ownership.
        </p>
      </div>
    </div>
  );
}

const AppBuilder = () => {
  const { isSubscribed, openUpgradeModal, pendingBuildPrompt, clearPendingBuildPrompt } = useApp();
  const setShowUpgradeModal = (open) => { if (open) openUpgradeModal('code'); };
  // showUpgradeModal is now global — this local alias keeps existing call-sites working
  const showUpgradeModal = false; // modal is rendered globally in App.js
  const [mode, setMode] = useState('coach');   // 'coach' | 'build'

  // Coach state
  const [coachMessages, setCoachMessages] = useState([]);
  const [coachInput, setCoachInput] = useState('');
  const [coachLoading, setCoachLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState('');
  const [spec, setSpec] = useState('');
  const messagesEndRef = useRef(null);
  const loadingIntervalRef = useRef(null);
  const [designPrefs, setDesignPrefs] = useState(() => {
    try { return JSON.parse(localStorage.getItem('design_preferences') || '{}'); } catch { return {}; }
  });

  // Build state
  const [description, setDescription] = useState('');
  const [buildLoading, setBuildLoading] = useState(false);
  const [buildMsg, setBuildMsg] = useState('');
  const [buildStep, setBuildStep] = useState(0);
  const [buildJustCompleted, setBuildJustCompleted] = useState(false);
  const [isResumed, setIsResumed] = useState(false);
  const [autoBuildPending, setAutoBuildPending] = useState(false);
  const [generatedApp, setGeneratedApp] = useState(null);
  const [projectType, setProjectType] = useState('app');
  const [buildMode, setBuildMode] = useState('polished');
  const [projectBrief, setProjectBrief] = useState(null);   // AI brief before build
  const [briefLoading, setBriefLoading] = useState(false);

  // Edit state
  const [editInput, setEditInput] = useState('');
  const [editLoading, setEditLoading] = useState(false);
  const [editMsg, setEditMsg] = useState('');
  const [editHistory, setEditHistory] = useState([]);
  const editLoadingIntervalRef = useRef(null);
  const editEndRef = useRef(null);
  const [pendingChange, setPendingChange] = useState(null); // proposed AI edit awaiting approve/reject

  // Explain panel
  const [explainPanel, setExplainPanel] = useState(null);  // {file, content} | null
  const [explainLoading, setExplainLoading] = useState(false);

  // Session metadata editing
  const [editingSessionId, setEditingSessionId] = useState(null);
  const [editingSessionName, setEditingSessionName] = useState('');
  const [sessionTagInput, setSessionTagInput] = useState('');

  // Phase 2 — Testing & scanning
  const [scanResult, setScanResult] = useState(null);
  const [scanLoading, setScanLoading] = useState(false);
  const [showScanPanel, setShowScanPanel] = useState(false);
  const [consoleErrors, setConsoleErrors] = useState([]);
  const [showConsole, setShowConsole] = useState(false);
  const [autoFixLoading, setAutoFixLoading] = useState(false);

  // Phase 3 — File explorer & asset management
  const [showFileExplorer, setShowFileExplorer] = useState(false);
  const [newFileName, setNewFileName] = useState('');
  const [showNewFileInput, setShowNewFileInput] = useState(false);
  const assetInputRef = useRef(null);

  // Phase 4 — Publish: GitHub + Vercel + session JSON
  const [showGithubModal, setShowGithubModal] = useState(false);
  const [githubToken, setGithubToken] = useState('');
  const [githubRepo, setGithubRepo] = useState('');
  const [githubPrivate, setGithubPrivate] = useState(false);
  const [githubLoading, setGithubLoading] = useState(false);
  const [githubResult, setGithubResult] = useState(null);
  const [showVercelModal, setShowVercelModal] = useState(false);
  const [vercelToken, setVercelToken] = useState('');
  const [vercelLoading, setVercelLoading] = useState(false);
  const [vercelResult, setVercelResult] = useState(null);
  const importSessionJsonRef = useRef(null);

  // Phase 5 — Split view & command palette
  const [splitView, setSplitView] = useState(false);
  const [showCmdPalette, setShowCmdPalette] = useState(false);
  const [cmdQuery, setCmdQuery] = useState('');
  const [cmdIndex, setCmdIndex] = useState(0);

  // Phase 5 — Workspace intelligence
  const [actionLog, setActionLog] = useState([]);
  const [showActionLog, setShowActionLog] = useState(false);
  const [projectNotes, setProjectNotes] = useState('');
  const [showNotes, setShowNotes] = useState(false);
  const [showFindPanel, setShowFindPanel] = useState(false);
  const [findQuery, setFindQuery] = useState('');
  const [replaceQuery, setReplaceQuery] = useState('');
  const [findCaseSensitive, setFindCaseSensitive] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState({});
  const [archLoading, setArchLoading] = useState(false);
  const [archPanel, setArchPanel] = useState(null);
  const [changelogPanel, setChangelogPanel] = useState(null);
  const [changelogLoading, setChangelogLoading] = useState(false);

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

  // Dirty-state tracking (ref to last-saved project snapshot)
  const savedProjectRef = useRef(null);
  const isDirty = (filePath) => {
    if (!savedProjectRef.current || !generatedApp?.project) return false;
    return ptGetContent(savedProjectRef.current, filePath) !== ptGetContent(generatedApp.project, filePath);
  };

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
    'Analyzing request…',
    'Initializing build…',
    'Designing interface…',
    'Generating functionality…',
    'Connecting components…',
    'Build is progressing smoothly.',
    'Applying final adjustments…',
  ];

  const startLoadingCycle = (msgs, setter, stepSetter = null) => {
    let i = 0;
    setter(msgs[0]);
    if (stepSetter) stepSetter(0);
    loadingIntervalRef.current = setInterval(() => {
      i = Math.min(i + 1, msgs.length - 1);
      setter(msgs[i]);
      if (stepSetter) stepSetter(i);
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

  // Onboarding bridge: consume pendingBuildPrompt from context
  useEffect(() => {
    if (!pendingBuildPrompt) return;
    setDescription(pendingBuildPrompt);
    setMode('build');
    setAutoBuildPending(true);
    clearPendingBuildPrompt();
  }, [pendingBuildPrompt]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-trigger build once description is set from onboarding
  useEffect(() => {
    if (!autoBuildPending || !description || buildLoading || generatedApp) return;
    setAutoBuildPending(false);
    generateApp();
  }, [autoBuildPending, description]); // eslint-disable-line react-hooks/exhaustive-deps

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

  // Auto-show diff when pending change arrives
  useEffect(() => {
    if (!pendingChange) return;
    setDiffView({
      file: pendingChange.file_changed || 'index.html',
      verA: generatedApp?.project || null,
      verB: pendingChange.proposed?.project || null,
      nameA: 'current',
      nameB: 'proposed',
    });
  }, [pendingChange]);

  // ── Keyboard shortcuts ────────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e) => {
      const ctrl = e.ctrlKey || e.metaKey;
      // Command palette: Ctrl/Cmd+K (always, even without a project)
      if (ctrl && e.key === 'k') {
        e.preventDefault();
        setShowCmdPalette(v => !v);
        setCmdQuery('');
        setCmdIndex(0);
        return;
      }
      // Escape closes all panels/modals
      if (e.key === 'Escape') {
        setShowCmdPalette(false);
        setShowGithubModal(false);
        setShowVercelModal(false);
        setShowFileExplorer(false);
        return;
      }
      // Command palette arrow/enter navigation
      if (showCmdPalette) {
        if (e.key === 'ArrowDown') { e.preventDefault(); setCmdIndex(i => i + 1); return; }
        if (e.key === 'ArrowUp')   { e.preventDefault(); setCmdIndex(i => Math.max(0, i - 1)); return; }
        return; // don't process other shortcuts while palette is open
      }
      if (!generatedApp) return;
      // Don't intercept when user is typing in textarea/input (except toolbar)
      const tag = document.activeElement?.tagName;
      const inInput = (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT');
      if (ctrl && e.key === 's') { e.preventDefault(); saveVersion(); return; }
      if (ctrl && !e.shiftKey && e.key === 'z') { e.preventDefault(); undo(); return; }
      if (ctrl && (e.key === 'y' || (e.shiftKey && e.key === 'Z'))) { e.preventDefault(); redo(); return; }
      if (ctrl && e.key === '\\') { e.preventDefault(); setSplitView(v => !v); return; }
      if (!inInput && ctrl && e.key === 't') { e.preventDefault(); runScan(); return; }
      if (ctrl && e.key === 'f') { e.preventDefault(); setShowFindPanel(v => !v); setFindQuery(''); return; }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generatedApp, showCmdPalette, undoStack, redoStack]);

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
      project_type: generatedApp.project_type || projectType || 'app',
      project_type_label: generatedApp.project_type_label || null,
      build_mode: generatedApp.build_mode || buildMode || 'polished',
      is_pinned: existing?.is_pinned || false,
      is_archived: existing?.is_archived || false,
      is_favorite: existing?.is_favorite || false,
      edit_count: editHistory.filter(m => m.role === 'user').length,
      last_edited_file: editHistory.filter(m => m.role === 'assistant' && m.file_changed).slice(-1)[0]?.file_changed || null,
      tags: existing?.tags || [],
      notes: existing?.notes || null,
      savedAt: new Date().toISOString(),
    };
    // Persist to Postgres
    axiosInstance.post('/app-builder/sessions', session).catch(() => {});
    // Stamp saved state for dirty tracking
    savedProjectRef.current = generatedApp.project ? { ...generatedApp.project } : null;
    // Also keep localStorage as fallback
    setSavedSessions(prev => {
      const filtered = prev.filter(s => s.id !== session.id);
      const updated = [session, ...filtered].slice(0, 20);
      try { localStorage.setItem(SESSIONS_KEY, JSON.stringify(updated)); } catch {}
      return updated;
    });
  }, [generatedApp, editHistory, versions]);

  const resumeSession = (session) => {
    const project = session.project ? ptEnsureV2(session.project, session.id, session.name) : null;
    const html = project ? reconstructHtml(project) : session.html;
    setGeneratedApp({
      name: session.name,
      description: session.description,
      html,
      project,
      build_id: session.build_id,
      full_preview_url: session.preview_url || session.full_preview_url,
    });
    setEditHistory(session.editHistory || []);
    setVersions(session.versions || []);
    setIsResumed(true);
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

  const sendChip = (chip) => {
    if (QUESTION_CHIPS.style.includes(chip)) {
      const prefs = { ...designPrefs, style: chip };
      setDesignPrefs(prefs);
      try { localStorage.setItem('design_preferences', JSON.stringify(prefs)); } catch {}
    }
    sendCoachMessage(chip);
  };

  const sendCoachMessage = async (textOverride) => {
    const text = (textOverride !== undefined ? textOverride : coachInput).trim();
    if (!text || coachLoading) return;
    const userMsg = { role: 'user', content: text };
    const updatedMsgs = [...coachMessages, userMsg];
    setCoachMessages(updatedMsgs);
    setCoachInput('');
    setCoachLoading(true);
    startLoadingCycle(CHAT_LOADING_MSGS, setLoadingMsg);

    // Check if user typed BUILD
    if (text.toUpperCase() === 'BUILD') {
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
            content: [
              'Please compile everything we discussed into a single detailed app description I can use to build it. Be specific about features, tech stack, and requirements. Output only the description, no extra commentary.',
              designPrefs.style ? `User design preference (from previous sessions): style = "${designPrefs.style}". Incorporate this into the design requirements.` : '',
            ].filter(Boolean).join('\n\n')
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
  const fetchProjectBrief = async () => {
    if (!description.trim() || briefLoading) return;
    setBriefLoading(true);
    try {
      const res = await axiosInstance.post('/app-builder/project-brief', {
        description, project_type: projectType, build_mode: buildMode,
      }, { timeout: 60000 });
      setProjectBrief(res.data.brief);
    } catch { toast.error('Could not generate brief'); }
    finally { setBriefLoading(false); }
  };

  const generateApp = async () => {
    if (!description.trim() || buildLoading) return;
    setBuildLoading(true);
    setBuildJustCompleted(false);
    setProjectBrief(null);
    startLoadingCycle(BUILD_LOADING_MSGS, setBuildMsg, setBuildStep);
    trackEvent('build_started', { description: description.slice(0, 120) });
    try {
      const response = await axiosInstance.post('/app-builder/generate', {
        description, framework: 'react',
        project_type: projectType, build_mode: buildMode,
      }, { timeout: 180000 });
      const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
      const data = response.data;
      if (data.preview_url) data.full_preview_url = backendUrl.replace('/api', '') + data.preview_url;
      if (data.project) data.project = ptEnsureV2(data.project, data.build_id || data.name, data.name);
      if (data.project) data.html = reconstructHtml(data.project);
      data.project_type = data.project_type || projectType;
      data.build_mode   = data.build_mode   || buildMode;
      setGeneratedApp(data);
      setBuildJustCompleted(true);
      setTimeout(() => setBuildJustCompleted(false), 4000);
      trackEvent('build_completed', { project_id: data.build_id || data.name });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to generate app');
    } finally {
      stopLoadingCycle(setBuildMsg);
      setBuildStep(0);
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
      // Collect locked file names to pass to backend (v1 or v2 compatible)
      const lockedFiles = generatedApp.project
        ? ptGetAllPaths(generatedApp.project).filter(p => ptGetFileMeta(generatedApp.project, p)?.locked)
        : [];
      const res = await axiosInstance.post('/app-builder/edit', {
        project: generatedApp.project || null,
        html: generatedApp.project ? null : generatedApp.html,
        instruction,
        locked_files: lockedFiles,
      }, { timeout: 300000 });
      logAction('ai-edit', `AI edit: "${instruction.slice(0, 60)}"`, res.data.file_changed || '');
      const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
      const proposed = {
        ...generatedApp,
        project: res.data.project || generatedApp.project,
        html: res.data.html || reconstructHtml(res.data.project),
        build_id: res.data.build_id,
        full_preview_url: res.data.preview_url
          ? backendUrl.replace('/api', '') + res.data.preview_url
          : generatedApp.full_preview_url,
      };
      // Store as pending — user must approve or reject
      setPendingChange({
        proposed,
        file_changed: res.data.file_changed,
        instruction,
        edit_mode: res.data.edit_mode || 'full_rewrite',
      });
      const chatReply = res.data.chat_reply || `Done! I updated \`${res.data.file_changed || 'your project'}\`. Take a look and let me know what you think.`;
      setEditHistory(prev => [...prev, {
        role: 'assistant',
        content: chatReply,
        file_changed: res.data.file_changed,
        pending: true,
      }]);
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

  const approveChange = () => {
    if (!pendingChange) return;
    // Auto-checkpoint before applying (safe restore point)
    saveVersion('checkpoint', `Before: ${editHistory.filter(m => m.role === 'user').slice(-1)[0]?.content?.slice(0, 40) || 'AI edit'}`);
    pushUndo(generatedApp);
    setGeneratedApp(pendingChange.proposed);
    setEditHistory(prev => prev.map((m, i) =>
      i === prev.length - 1 ? { ...m, content: m.content + '\n\n✓ Applied! Let me know if you want any further tweaks.', pending: false } : m
    ));
    setPendingChange(null);
    logAction('ai-edit', `AI edit applied to ${pendingChange.file_changed || 'project'}`);
    toast.success('Change applied');
  };

  const rejectChange = () => {
    if (!pendingChange) return;
    setEditHistory(prev => prev.map((m, i) =>
      i === prev.length - 1 ? { ...m, content: m.content + '\n\n✗ No problem, change discarded. Want me to try a different approach?', pending: false } : m
    ));
    setPendingChange(null);
    toast.info('Change discarded');
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

  const saveVersion = (eventType = 'manual', overrideName = '') => {
    if (!generatedApp?.project) return;
    const name = overrideName || versionName.trim() || `v${versions.length + 1} — ${new Date().toLocaleTimeString()}`;
    const lastEdit = editHistory.filter(m => m.role === 'assistant').slice(-1)[0];
    const entry = {
      name,
      project: generatedApp.project,
      html: generatedApp.html,
      savedAt: new Date().toISOString(),
      file_changed: lastEdit?.file_changed || null,
      summary: editHistory.filter(m => m.role === 'user').slice(-1)[0]?.content?.slice(0, 60) || null,
      eventType,  // 'manual' | 'ai-edit' | 'restore' | 'import' | 'auto-fix' | 'deploy-ready' | 'checkpoint'
    };
    setVersions(prev => [...prev, entry]);
    setVersionName('');
    if (eventType === 'manual') toast.success(`Saved "${name}"`);
    logAction('save', `Version saved: ${name}`, eventType);
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
      const pathMap = { html: 'index.html', css: 'style.css', js: 'script.js', readme: 'README.md' };
      const path = pathMap[file] || file;
      const p = ptSetContent(prev.project, path, value);
      return { ...prev, project: p, html: reconstructHtml(p) };
    });
  };

  const openInBrowser = () => {
    if (!generatedApp?.html) return;
    const blob = new Blob([generatedApp.html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  };

  // ── Explain file ─────────────────────────────────────────────────────────────
  const explainFile = async (file, content) => {
    if (!content?.trim()) { toast.error('File is empty'); return; }
    setExplainLoading(true);
    setExplainPanel({ file, content: 'Loading explanation...' });
    try {
      const res = await axiosInstance.post('/app-builder/explain', {
        file, content, project_name: generatedApp?.name || '',
      }, { timeout: 60000 });
      setExplainPanel({ file, content: res.data.explanation });
    } catch { setExplainPanel({ file, content: 'Explanation failed. Try again.' }); }
    finally { setExplainLoading(false); }
  };

  // ── Generate README ───────────────────────────────────────────────────────────
  const generateReadme = async () => {
    if (!generatedApp?.project) return;
    toast.info('Generating README...');
    try {
      const res = await axiosInstance.post('/app-builder/generate-readme', {
        project: generatedApp.project,
        name: generatedApp.name,
        description: generatedApp.description || '',
      }, { timeout: 60000 });
      setGeneratedApp(prev => ({
        ...prev,
        project: ptSetContent(prev.project, 'README.md', res.data.readme),
      }));
      setActiveTab('readme');
      toast.success('README generated!');
    } catch { toast.error('README generation failed'); }
  };

  // ── Clone session ─────────────────────────────────────────────────────────────
  const cloneSession = async (id) => {
    try {
      const res = await axiosInstance.post(`/app-builder/sessions/${id}/clone`);
      toast.success(`Cloned as "${res.data.name}"`);
      // Refresh sessions from backend
      const list = await axiosInstance.get('/app-builder/sessions');
      if (Array.isArray(list.data)) setSavedSessions(list.data);
    } catch { toast.error('Clone failed'); }
  };

  // ── Session rename inline ─────────────────────────────────────────────────────
  const commitRename = (id) => {
    if (!editingSessionName.trim()) { setEditingSessionId(null); return; }
    axiosInstance.patch(`/app-builder/sessions/${id}`, { name: editingSessionName.trim() }).catch(() => {});
    setSavedSessions(prev => prev.map(s => s.id === id ? { ...s, name: editingSessionName.trim() } : s));
    setEditingSessionId(null);
  };

  // ── Session tag management ────────────────────────────────────────────────────
  const addTag = (id, tag) => {
    if (!tag.trim()) return;
    setSavedSessions(prev => {
      const updated = prev.map(s => {
        if (s.id !== id) return s;
        const tags = [...new Set([...(s.tags || []), tag.trim()])];
        axiosInstance.patch(`/app-builder/sessions/${id}`, { tags }).catch(() => {});
        return { ...s, tags };
      });
      try { localStorage.setItem(SESSIONS_KEY, JSON.stringify(updated)); } catch {}
      return updated;
    });
    setSessionTagInput('');
  };

  const removeTag = (id, tag) => {
    setSavedSessions(prev => {
      const updated = prev.map(s => {
        if (s.id !== id) return s;
        const tags = (s.tags || []).filter(t => t !== tag);
        axiosInstance.patch(`/app-builder/sessions/${id}`, { tags }).catch(() => {});
        return { ...s, tags };
      });
      try { localStorage.setItem(SESSIONS_KEY, JSON.stringify(updated)); } catch {}
      return updated;
    });
  };

  // ── Phase 2: Console error capture ───────────────────────────────────────────
  useEffect(() => {
    const handler = (e) => {
      if (e.data?.type === 'console') {
        setConsoleErrors(prev => [...prev.slice(-99), {
          level: e.data.level,
          msg: e.data.msg,
          time: new Date().toLocaleTimeString(),
        }]);
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, []);

  // Inject console capture into iframe srcDoc
  const injectConsoleCapture = (html) => {
    if (!html) return html;
    const script = `<script>(function(){var t=console;['log','warn','error'].forEach(function(l){var o=t[l].bind(t);t[l]=function(){o.apply(t,arguments);try{window.parent.postMessage({type:'console',level:l,msg:Array.from(arguments).map(function(a){return typeof a==='object'?JSON.stringify(a):String(a)}).join(' ')}, '*')}catch(e){}};});window.onerror=function(m,s,l){window.parent.postMessage({type:'console',level:'error',msg:m+' ('+s+':'+l+')'},'*')};window.addEventListener('unhandledrejection',function(e){window.parent.postMessage({type:'console',level:'error',msg:'Unhandled Promise: '+e.reason},'*')});})();<\/script>`;
    if (html.includes('<head>')) return html.replace('<head>', '<head>' + script);
    return script + html;
  };

  // ── Phase 2: Static scan ──────────────────────────────────────────────────────
  const runScan = async () => {
    if (!generatedApp?.project || scanLoading) return;
    setScanLoading(true);
    setShowScanPanel(true);
    try {
      const res = await axiosInstance.post('/app-builder/scan', {
        project: generatedApp.project,
        project_type: generatedApp.project_type || projectType || 'app',
      }, { timeout: 15000 });
      setScanResult(res.data);
      const { counts } = res.data;
      const total = Object.values(counts).reduce((a, b) => a + b, 0);
      if (total === 0) toast.success(`Clean scan — score ${res.data.score}/100`);
      else toast.warning(`${total} finding(s) — score ${res.data.score}/100`);
    } catch { toast.error('Scan failed'); }
    finally { setScanLoading(false); }
  };

  // ── Phase 2: Auto-fix ─────────────────────────────────────────────────────────
  const runAutoFix = async (errors) => {
    if (!generatedApp?.build_id || autoFixLoading) return;
    setAutoFixLoading(true);
    try {
      const res = await axiosInstance.post(
        `/app-builder/sessions/${generatedApp.build_id}/auto-fix`,
        { errors: errors.slice(0, 5), max_attempts: 3 },
        { timeout: 180000 }
      );
      if (res.data.ok) {
        pushUndo(generatedApp);
        const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
        setGeneratedApp(prev => ({
          ...prev,
          project: res.data.project,
          html: res.data.html,
          build_id: res.data.build_id,
          full_preview_url: res.data.preview_url
            ? backendUrl.replace('/api', '') + res.data.preview_url
            : prev.full_preview_url,
        }));
        toast.success(`Auto-fixed ${res.data.applied.length} issue(s)`);
        saveVersion('auto-fix', `Auto-fix: ${res.data.applied.length} issue(s)`);
        logAction('auto-fix', `Auto-fix applied ${res.data.applied.length} fix(es)`);
        setTimeout(runScan, 500);
      } else {
        toast.error(res.data.message || 'Auto-fix could not apply changes');
      }
    } catch { toast.error('Auto-fix failed'); }
    finally { setAutoFixLoading(false); }
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

  const handleSaveProject = () => {
    if (!isSubscribed) { openUpgradeModal('save'); return; }
    // Auto-save already runs via useEffect; just confirm to the user
    toast.success('Project saved.');
  };

  const [shareLoading, setShareLoading] = useState(false);
  const handleShare = async () => {
    if (!generatedApp?.html || shareLoading) return;
    setShareLoading(true);
    try {
      const res = await axiosInstance.post('/share', {
        content_type: 'app',
        content: generatedApp.html,
        title: generatedApp.name || 'My App',
      });
      const url = res.data.url || `${window.location.origin}/s/${res.data.id}`;
      navigator.clipboard.writeText(url).then(() => toast.success('Share link copied!'));
    } catch {
      toast.error('Failed to generate share link');
    } finally {
      setShareLoading(false);
    }
  };

  const exportZip = async () => {
    if (!isSubscribed) { openUpgradeModal('export'); return; }
    if (!generatedApp?.html) return;
    try {
      toast.info('Building ZIP...');
      const res = await axiosInstance.post('/app-builder/export-zip', {
        project: generatedApp.project || null,
        html: generatedApp.project ? null : generatedApp.html,
        name: generatedApp.name || 'generated-app',
        description: generatedApp.description || '',
        assets: ptGetAssets(generatedApp.project),
        extra_files: ptGetExtraFiles(generatedApp.project),
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
    if (!isSubscribed) { openUpgradeModal('export'); return; }
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

  // ── Phase 3: Asset & file management ─────────────────────────────────────────
  const uploadAsset = (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    files.forEach(file => {
      const reader = new FileReader();
      reader.onload = (ev) => {
        const dataUrl = ev.target.result;
        setGeneratedApp(prev => {
          // Remove existing asset with same name, then add new node at root
          const assetPath = `assets/${file.name}`;
          const withoutOld = ptRemoveNodeFromTree(prev.project, assetPath);
          const newNode = ptMakeFileNode(file.name, assetPath, '', {
            dataUrl,
            mime: file.type,
            source: 'imported',
          });
          return { ...prev, project: ptAddNodeToTree(withoutOld, newNode, null) };
        });
        toast.success(`Asset uploaded: ${file.name}`);
      };
      reader.readAsDataURL(file);
    });
    e.target.value = '';
  };

  const createExtraFile = () => {
    const name = newFileName.trim();
    if (!name) return;
    if (!name.match(/\.(js|css|json|txt|md|html?)$/i)) {
      toast.error('Use a valid extension: .js .css .json .txt .md .html');
      return;
    }
    setGeneratedApp(prev => {
      if (ptGetExtraFiles(prev.project).find(f => f.name === name)) { toast.error('File already exists'); return prev; }
      const newNode = ptMakeFileNode(name, name, '');
      return { ...prev, project: ptAddNodeToTree(prev.project, newNode, null) };
    });
    setActiveTab(`extra:${name}`);
    setNewFileName('');
    setShowNewFileInput(false);
  };

  const deleteExtraFile = (name) => {
    setGeneratedApp(prev => ({
      ...prev,
      project: ptRemoveNodeFromTree(prev.project, name),
    }));
    if (activeTab === `extra:${name}`) setActiveTab('preview');
  };

  const deleteAsset = (name) => {
    setGeneratedApp(prev => ({
      ...prev,
      project: ptRemoveNodeFromTree(prev.project, `assets/${name}`),
    }));
    toast.success(`Removed asset: ${name}`);
  };

  // ── Phase 4: Publish handlers ─────────────────────────────────────────────────
  const exportSessionJson = () => {
    if (!isSubscribed) { openUpgradeModal('export'); return; }
    if (!generatedApp) return;
    const payload = { ...generatedApp, versions, editHistory, exportedAt: new Date().toISOString() };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${generatedApp.name || 'session'}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Session exported as JSON');
  };

  const importSessionJson = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target.result);
        if (!data.project && !data.html) { toast.error('Not a valid session JSON'); return; }
        if (data.project) data.project = ptEnsureV2(data.project, data.build_id || data.name, data.name);
        setGeneratedApp(data);
        if (data.versions) setVersions(data.versions);
        if (data.editHistory) setEditHistory(data.editHistory);
        setUndoStack([]); setRedoStack([]);
        setActiveTab('preview');
        setMode('build');
        toast.success(`Imported session: "${data.name || 'unnamed'}"`);
      } catch { toast.error('Invalid JSON file'); }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const pushToGithub = async () => {
    if (!isSubscribed) { openUpgradeModal('github'); return; }
    if (!githubToken.trim() || !githubRepo.trim()) { toast.error('Enter token and repo name'); return; }
    setGithubLoading(true); setGithubResult(null);
    try {
      const res = await axiosInstance.post('/app-builder/github-push', {
        token: githubToken,
        repo_name: githubRepo,
        project: generatedApp.project,
        name: generatedApp.name || 'generated-app',
        description: generatedApp.description || '',
        private: githubPrivate,
        assets: ptGetAssets(generatedApp.project),
        extra_files: ptGetExtraFiles(generatedApp.project),
      });
      setGithubResult(res.data);
      toast.success('Pushed to GitHub!');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'GitHub push failed');
    } finally { setGithubLoading(false); }
  };

  const deployToVercel = async () => {
    if (!isSubscribed) { openUpgradeModal('deploy'); return; }
    if (!vercelToken.trim()) { toast.error('Enter your Vercel token'); return; }
    setVercelLoading(true); setVercelResult(null);
    try {
      const res = await axiosInstance.post('/app-builder/deploy-vercel', {
        token: vercelToken,
        project: generatedApp.project,
        name: generatedApp.name || 'generated-app',
        assets: ptGetAssets(generatedApp.project),
        extra_files: ptGetExtraFiles(generatedApp.project),
      });
      setVercelResult(res.data);
      toast.success('Deployed to Vercel!');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Vercel deploy failed');
    } finally { setVercelLoading(false); }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text).then(() => toast.success('Copied!'));
  };

  // ── Phase 5: Workspace intelligence handlers ──────────────────────────────────

  // Action log
  const logAction = (type, msg, detail = '') => {
    setActionLog(prev => [...prev.slice(-99), {
      id: Date.now(), time: new Date().toLocaleTimeString(), type, msg, detail
    }]);
  };

  // File metadata helpers (v1 and v2 compatible via projectTree utilities)
  const getFileMeta = (fileName) => ptGetFileMeta(generatedApp?.project, fileName) || {};
  const updateFileMeta = (fileName, patch) => {
    setGeneratedApp(prev => ({
      ...prev,
      project: ptSetFileMeta(prev.project, fileName, patch),
    }));
  };

  // Map tab id → display file name (for lock checks)
  const tabToFileName = (tab) => {
    if (tab === 'html') return 'index.html';
    if (tab === 'css')  return 'style.css';
    if (tab === 'js')   return 'script.js';
    if (tab === 'readme') return 'README.md';
    if (tab.startsWith('extra:')) return tab.slice(6);
    return tab;
  };
  const tabToKey = (tab) => {
    if (tab === 'html') return 'index_html';
    if (tab === 'css')  return 'style_css';
    if (tab === 'js')   return 'script_js';
    if (tab === 'readme') return 'readme';
    return tab; // extra files use name as key
  };
  const isLocked = (tab) => !!getFileMeta(tabToFileName(tab)).locked;

  const toggleLock = (tab) => {
    const key = tabToFileName(tab);
    const cur = !!getFileMeta(key).locked;
    updateFileMeta(key, { locked: !cur });
    toast.info(!cur ? `🔒 ${key} locked` : `🔓 ${key} unlocked`);
  };

  // Format file
  const formatFile = async (tab) => {
    if (!generatedApp?.project) return;
    const langMap = { html: 'html', css: 'css', js: 'js', readme: 'markdown' };
    const lang = langMap[tab] || 'html';
    const filePath = tabToFileName(tab);
    const content = ptGetContent(generatedApp.project, filePath);
    if (!content.trim()) return;
    try {
      toast.info('Formatting...');
      const res = await axiosInstance.post('/app-builder/format', { content, language: lang });
      const formatted = res.data.formatted;
      setGeneratedApp(prev => ({
        ...prev,
        project: ptSetContent(prev.project, filePath, formatted),
      }));
      logAction('format', `Formatted ${filePath}`);
      toast.success('Formatted!');
    } catch { toast.error('Format failed'); }
  };

  // Duplicate extra file
  const duplicateExtraFile = (name) => {
    const ef = ptGetExtraFiles(generatedApp?.project).find(f => f.name === name);
    if (!ef) return;
    const ext = name.includes('.') ? name.slice(name.lastIndexOf('.')) : '';
    const base = name.slice(0, name.length - ext.length);
    const newName = `${base}-copy${ext}`;
    const newNode = ptMakeFileNode(newName, newName, ef.content || '');
    setGeneratedApp(prev => ({
      ...prev,
      project: ptAddNodeToTree(prev.project, newNode),
    }));
    toast.success(`Duplicated as ${newName}`);
  };

  // Toggle folder expand/collapse in explorer
  const toggleFolder = (folder) => setExpandedFolders(prev => ({ ...prev, [folder]: !prev[folder] }));

  // Find in current file
  const getActiveContent = () => {
    if (!generatedApp?.project) return '';
    const pathMap = { html: 'index.html', css: 'style.css', js: 'script.js', readme: 'README.md' };
    if (pathMap[activeTab]) return ptGetContent(generatedApp.project, pathMap[activeTab]);
    if (activeTab.startsWith('extra:')) return ptGetContent(generatedApp.project, activeTab.slice(6));
    return '';
  };

  const findCount = useMemo(() => {
    if (!findQuery.trim() || !generatedApp) return 0;
    const content = getActiveContent();
    const q = findCaseSensitive ? findQuery : findQuery.toLowerCase();
    const c = findCaseSensitive ? content : content.toLowerCase();
    let count = 0, idx = 0;
    while ((idx = c.indexOf(q, idx)) !== -1) { count++; idx += q.length; }
    return count;
  }, [findQuery, findCaseSensitive, activeTab, generatedApp]);

  const replaceInFile = (all = false) => {
    if (!findQuery.trim()) return;
    const content = getActiveContent();
    const flags = findCaseSensitive ? 'g' : 'gi';
    const escaped = findQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const replaced = all
      ? content.replace(new RegExp(escaped, flags), replaceQuery)
      : content.replace(new RegExp(escaped, findCaseSensitive ? '' : 'i'), replaceQuery);
    const count = (content.match(new RegExp(escaped, flags)) || []).length;
    const pathMap = { html: 'index.html', css: 'style.css', js: 'script.js', readme: 'README.md' };
    const filePath = pathMap[activeTab] || (activeTab.startsWith('extra:') ? activeTab.slice(6) : null);
    if (filePath) {
      setGeneratedApp(prev => ({ ...prev, project: ptSetContent(prev.project, filePath, replaced) }));
    }
    toast.success(all ? `Replaced ${count} occurrence(s)` : 'Replaced first occurrence');
  };

  // Explain diff (calls backend with before/after content from diffView)
  const explainDiff = async () => {
    if (!diffView) return;
    try {
      toast.info('Analyzing diff...');
      const before = ptGetContent(diffView.verA, diffView.file) || '';
      const after  = ptGetContent(diffView.verB, diffView.file) || '';
      const res = await axiosInstance.post('/app-builder/explain-diff', {
        file_name: diffView.file, before, after
      });
      toast.success('Explanation ready');
      setExplainPanel({ file: `Diff: ${diffView.file}`, content: res.data.explanation });
    } catch { toast.error('Explain diff failed'); }
  };

  // Explain architecture
  const explainArchitecture = async () => {
    if (!generatedApp?.project) return;
    setArchLoading(true); setArchPanel(null);
    try {
      const res = await axiosInstance.post('/app-builder/explain-architecture', {
        project: generatedApp.project, name: generatedApp.name
      });
      setArchPanel(res.data.overview);
      logAction('explain', 'Architecture explained');
    } catch { toast.error('Architecture explain failed'); }
    finally { setArchLoading(false); }
  };

  // Generate changelog
  const generateChangelog = async () => {
    if (!versions.length) { toast.error('No versions saved yet'); return; }
    setChangelogLoading(true); setChangelogPanel(null);
    try {
      const res = await axiosInstance.post('/app-builder/generate-changelog', {
        versions, project_name: generatedApp?.name || 'project'
      });
      setChangelogPanel(res.data.changelog);
      logAction('changelog', 'Changelog generated');
    } catch { toast.error('Changelog generation failed'); }
    finally { setChangelogLoading(false); }
  };

  // Compute project readiness score (0-100)
  const computeReadiness = () => {
    if (!generatedApp) return null;
    let score = scanResult ? (scanResult.score ?? 80) : 80;
    const consoleErrs = consoleErrors.filter(e => e.level === 'error').length;
    score = Math.max(0, score - consoleErrs * 5);
    if (!ptGetContent(generatedApp.project, 'README.md')?.trim()) score = Math.max(0, score - 8);
    if (!ptGetContent(generatedApp.project, 'style.css')?.trim()) score = Math.max(0, score - 5);
    return Math.min(100, Math.round(score));
  };
  const readinessScore = computeReadiness();
  const readinessColor = readinessScore === null ? 'text-slate-500'
    : readinessScore >= 80 ? 'text-emerald-400'
    : readinessScore >= 60 ? 'text-amber-400'
    : 'text-red-400';

  // ── Phase 5: Command palette ──────────────────────────────────────────────────
  const ALL_COMMANDS = useMemo(() => [
    { label: 'Save Version',          shortcut: '⌃S',   icon: BookmarkPlus,  action: () => saveVersion(),             group: 'Edit' },
    { label: 'Undo',                  shortcut: '⌃Z',   icon: Undo2,         action: () => undo(),                    group: 'Edit' },
    { label: 'Redo',                  shortcut: '⌃Y',   icon: Redo2,         action: () => redo(),                    group: 'Edit' },
    { label: 'Toggle Split View',     shortcut: '⌃\\',  icon: Columns,       action: () => setSplitView(v => !v),     group: 'View' },
    { label: 'Toggle File Explorer',  shortcut: '',     icon: FolderTree,    action: () => setShowFileExplorer(v => !v), group: 'View' },
    { label: 'Toggle Console',        shortcut: '',     icon: Terminal,      action: () => setShowConsole(v => !v),   group: 'View' },
    { label: 'Toggle Version History',shortcut: '',     icon: History,       action: () => setShowVersions(v => !v),  group: 'View' },
    { label: 'Run Scan / Test',       shortcut: '⌃T',  icon: Bug,           action: () => runScan(),                 group: 'Tools' },
    { label: 'Generate README',       shortcut: '',     icon: BookOpen,      action: () => generateReadme(),          group: 'Tools' },
    { label: 'Generate Project Brief',shortcut: '',     icon: Sparkles,      action: () => fetchProjectBrief(),       group: 'Tools' },
    { label: 'Export HTML',           shortcut: '',     icon: Download,      action: () => downloadApp(),             group: 'Export' },
    { label: 'Export ZIP',            shortcut: '',     icon: Package,       action: () => exportZip(),               group: 'Export' },
    { label: 'Export Session JSON',   shortcut: '',     icon: Download,      action: () => exportSessionJson(),       group: 'Export' },
    { label: 'Open in Browser',       shortcut: '',     icon: Eye,           action: () => openInBrowser(),           group: 'Export' },
    { label: 'Push to GitHub',        shortcut: '',     icon: Github,        action: () => { setShowGithubModal(true); setGithubResult(null); }, group: 'Publish' },
    { label: 'Deploy to Vercel',      shortcut: '',     icon: Globe,         action: () => { setShowVercelModal(true); setVercelResult(null); }, group: 'Publish' },
    { label: 'New Project',           shortcut: '',     icon: RotateCcw,     action: () => { setGeneratedApp(null); setDescription(''); setEditInput(''); setEditHistory([]); setUndoStack([]); setRedoStack([]); setVersions([]); setActiveTab('preview'); setDiffView(null); setShowFileExplorer(false); setScanResult(null); setConsoleErrors([]); }, group: 'Project' },
  ], []); // eslint-disable-line react-hooks/exhaustive-deps

  const filteredCmds = useMemo(() => {
    if (!cmdQuery.trim()) return ALL_COMMANDS;
    const q = cmdQuery.toLowerCase();
    return ALL_COMMANDS.filter(c => c.label.toLowerCase().includes(q) || c.group.toLowerCase().includes(q));
  }, [cmdQuery, ALL_COMMANDS]);

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <>
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

          {/* Quick-answer chips */}
          {!coachLoading && coachMessages.length > 0 && (() => {
            const last = coachMessages[coachMessages.length - 1];
            if (last.role !== 'assistant') return null;
            const chips = detectChips(last.content);
            if (!chips.length) return null;
            return (
              <div className="px-4 pb-2 pt-1 flex flex-wrap gap-1.5 border-t border-cyan-900/20 bg-black/20">
                {chips.map((chip, i) => (
                  <button
                    key={i}
                    onClick={() => sendChip(chip)}
                    className="px-3 py-1 bg-cyan-500/10 border border-cyan-500/25 hover:border-cyan-400/70 hover:bg-cyan-500/20 text-cyan-300 text-[11px] font-mono rounded-sm transition-all"
                  >
                    {chip}
                  </button>
                ))}
              </div>
            );
          })()}

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
                            {session.is_favorite && <span className="text-amber-400 text-xs">★</span>}
                            {editingSessionId === session.id ? (
                              <input
                                autoFocus
                                value={editingSessionName}
                                onChange={e => setEditingSessionName(e.target.value)}
                                onBlur={() => commitRename(session.id)}
                                onKeyDown={e => { if (e.key === 'Enter') commitRename(session.id); if (e.key === 'Escape') setEditingSessionId(null); }}
                                className="flex-1 bg-black/60 border border-cyan-500/50 text-cyan-200 text-sm font-mono px-1 py-0 rounded-sm outline-none"
                              />
                            ) : (
                              <span
                                className="text-sm font-mono text-cyan-300 truncate cursor-pointer hover:text-cyan-200"
                                onDoubleClick={() => { setEditingSessionId(session.id); setEditingSessionName(session.name); }}
                                title="Double-click to rename"
                              >{session.name}</span>
                            )}
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
                            {session.build_mode && session.build_mode !== 'polished' && (
                              <span className="text-[9px] font-mono text-slate-600 bg-slate-800 px-1 rounded">{session.build_mode}</span>
                            )}
                          </div>
                          {/* Tags */}
                          {(session.tags || []).length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1">
                              {session.tags.map(tag => (
                                <span key={tag} className="text-[9px] font-mono bg-cyan-950/50 border border-cyan-800/40 text-cyan-500 px-1 py-0.5 rounded-sm flex items-center gap-0.5">
                                  {tag}
                                  <button onClick={() => removeTag(session.id, tag)} className="text-slate-600 hover:text-red-400 ml-0.5"><X className="w-2 h-2" /></button>
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button
                            onClick={() => resumeSession(session)}
                            className="px-2.5 py-1 bg-cyan-500/20 border border-cyan-500/40 text-cyan-400 text-xs font-mono uppercase rounded-sm hover:bg-cyan-500/30 transition-all"
                          >
                            Open
                          </button>
                          <button
                            onClick={() => { setSavedSessions(prev => prev.map(s => s.id === session.id ? { ...s, is_favorite: !s.is_favorite } : s)); axiosInstance.patch(`/app-builder/sessions/${session.id}`, { is_favorite: !session.is_favorite }).catch(() => {}); }}
                            className={`p-1.5 transition-colors ${session.is_favorite ? 'text-amber-400' : 'text-slate-700 hover:text-amber-500'}`}
                            title="Favorite"
                          >★</button>
                          <button onClick={() => cloneSession(session.id)} className="p-1.5 text-slate-700 hover:text-cyan-400 transition-colors" title="Clone"><RefreshCw className="w-3.5 h-3.5" /></button>
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
                    <button onClick={() => importSessionJsonRef.current?.click()}
                      className="flex items-center gap-1 px-2 py-1 text-slate-500 hover:text-violet-400 text-[10px] font-mono uppercase border border-slate-700/40 rounded-sm hover:border-violet-500/40 transition-all">
                      <Download className="w-3 h-3" /> Import JSON
                    </button>
                  </div>
                </div>
              )}

              {/* Project type + build mode selectors */}
              <div className="flex gap-3 flex-wrap">
                <div className="flex flex-col gap-1 flex-1 min-w-32">
                  <label className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">Project Type</label>
                  <select value={projectType} onChange={e => setProjectType(e.target.value)}
                    className="bg-black/50 border border-cyan-900/50 text-cyan-300 font-mono text-xs rounded-sm px-2 py-1.5 outline-none focus:border-cyan-500">
                    <option value="app">App / Tool</option>
                    <option value="game">Game</option>
                    <option value="dashboard">Dashboard</option>
                    <option value="landing">Landing Page</option>
                    <option value="creative">Creative / Art</option>
                    <option value="tool">Utility</option>
                    <option value="fullstack">Full-stack (+ server.js)</option>
                  </select>
                </div>
                <div className="flex flex-col gap-1 flex-1 min-w-32">
                  <label className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">Build Mode</label>
                  <select value={buildMode} onChange={e => setBuildMode(e.target.value)}
                    className="bg-black/50 border border-cyan-900/50 text-cyan-300 font-mono text-xs rounded-sm px-2 py-1.5 outline-none focus:border-cyan-500">
                    <option value="quick">Quick Prototype</option>
                    <option value="polished">Polished Demo</option>
                    <option value="production">Production Starter</option>
                    <option value="game_jam">Game Jam Mode</option>
                    <option value="mobile">Mobile-First</option>
                  </select>
                </div>
                <div className="flex items-end">
                  <button onClick={fetchProjectBrief} disabled={!description.trim() || briefLoading}
                    className="px-3 py-1.5 border border-violet-500/40 text-violet-400 text-[10px] font-mono uppercase rounded-sm hover:bg-violet-500/10 disabled:opacity-40 flex items-center gap-1">
                    {briefLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
                    Brief
                  </button>
                </div>
              </div>

              {/* AI Project Brief panel */}
              {projectBrief && (
                <div className="bg-black/50 border border-violet-500/20 rounded-sm p-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-3.5 h-3.5 text-violet-400" />
                    <span className="text-[10px] font-mono text-violet-400 uppercase tracking-wider flex-1">AI Project Brief</span>
                    <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${
                      projectBrief.complexity === 'high' ? 'text-red-400 border-red-800' :
                      projectBrief.complexity === 'medium' ? 'text-amber-400 border-amber-800' :
                      'text-emerald-400 border-emerald-800'}`}>{projectBrief.complexity} complexity</span>
                    <button onClick={() => setProjectBrief(null)} className="text-slate-600 hover:text-slate-400"><X className="w-3 h-3" /></button>
                  </div>
                  <p className="text-xs font-mono text-cyan-200">{projectBrief.one_liner}</p>
                  {projectBrief.must_haves?.length > 0 && (
                    <div>
                      <div className="text-[9px] font-mono text-slate-500 uppercase mb-1">Must-haves</div>
                      <div className="flex flex-wrap gap-1">
                        {projectBrief.must_haves.map((f, i) => <span key={i} className="text-[9px] font-mono bg-cyan-950/50 border border-cyan-800/30 text-cyan-400 px-1.5 py-0.5 rounded-sm">{f}</span>)}
                      </div>
                    </div>
                  )}
                  {projectBrief.risks?.length > 0 && (
                    <div>
                      <div className="text-[9px] font-mono text-slate-500 uppercase mb-1">Risks</div>
                      <div className="flex flex-wrap gap-1">
                        {projectBrief.risks.map((r, i) => <span key={i} className="text-[9px] font-mono bg-red-950/30 border border-red-800/30 text-red-400 px-1.5 py-0.5 rounded-sm">{r}</span>)}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ── Live build progress panel ── */}
              {buildLoading ? (
                <div className="flex-1 flex flex-col items-center justify-center py-10 px-6 gap-6">
                  {/* Header */}
                  <div className="flex flex-col items-center gap-1.5 text-center">
                    <div className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />
                      <span className="text-[10px] font-mono text-cyan-500 uppercase tracking-widest">Building your application</span>
                    </div>
                    <p className="text-base font-bold text-white mt-1">{buildMsg || 'Initializing…'}</p>
                  </div>

                  {/* Step list */}
                  <div className="w-full max-w-sm space-y-1.5">
                    {BUILD_LOADING_MSGS.map((msg, i) => (
                      <div key={i} className={`flex items-center gap-3 px-3 py-2 rounded-lg border transition-all duration-500 ${
                        i < buildStep  ? 'bg-emerald-500/8 border-emerald-500/20' :
                        i === buildStep ? 'bg-cyan-500/10 border-cyan-500/30' :
                        'border-transparent opacity-25'
                      }`}>
                        {i < buildStep
                          ? <CheckCircle className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                          : i === buildStep
                            ? <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin flex-shrink-0" />
                            : <div className="w-3.5 h-3.5 rounded-full border border-slate-700 flex-shrink-0" />
                        }
                        <span className={`text-xs font-mono ${
                          i < buildStep  ? 'text-emerald-400' :
                          i === buildStep ? 'text-cyan-300' :
                          'text-slate-600'
                        }`}>{msg}</span>
                      </div>
                    ))}
                  </div>

                  {/* Progress bar */}
                  <div className="w-full max-w-sm h-0.5 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-cyan-500 to-violet-600 rounded-full transition-all duration-1000"
                      style={{ width: `${Math.min(((buildStep + 1) / BUILD_LOADING_MSGS.length) * 100, 95)}%` }}
                    />
                  </div>

                  {/* Helper text */}
                  <p className="text-[10px] text-slate-600 text-center max-w-xs leading-relaxed">
                    The preview updates in real time.{' '}
                    You can interact with the application as it builds.
                  </p>
                </div>
              ) : (
              <>
              <textarea
                data-testid="app-description-input"
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Describe your app in detail (or use the Coach to build a spec first)..."
                className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono p-4 outline-none resize-none"
                rows={5}
              />
              {/* Hidden import file inputs */}
              <input ref={importHtmlRef} type="file" accept=".html,.htm" onChange={handleImportHtml} className="hidden" />
              <input ref={importZipRef}  type="file" accept=".zip"       onChange={handleImportZip}  className="hidden" />
              <input ref={assetInputRef} type="file" accept="image/*,.svg,.ico,.woff,.woff2,.ttf,.otf" multiple onChange={uploadAsset} className="hidden" />
              <input ref={importSessionJsonRef} type="file" accept=".json" onChange={importSessionJson} className="hidden" />

              <div className="flex items-center gap-3 flex-wrap">
                <button
                  data-testid="generate-app-btn"
                  onClick={generateApp}
                  disabled={!description.trim()}
                  className="px-8 py-3 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 hover:shadow-[0_0_20px_rgba(0,243,255,0.4)] uppercase tracking-wider rounded-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  <Wand2 className="w-5 h-5" />GENERATE APP
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
              </>
              )}
            </div>
          ) : (
            <div className="flex-1 flex flex-col overflow-hidden">

              {/* ── Toolbar Row 1: Identity + Edit tools ── */}
              <div className="flex items-center gap-2 px-4 py-2 border-b border-cyan-500/10 bg-black/60 flex-shrink-0">
                <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />
                <span className="text-xs font-mono text-green-300 flex-1 truncate min-w-0 mr-1">{generatedApp.name}</span>

                {readinessScore !== null && (
                  <span title="Project readiness score"
                    className={`text-[10px] font-mono px-2 py-0.5 border rounded-sm ${readinessColor} border-current/40 flex items-center gap-1 flex-shrink-0`}>
                    <TrendingUp className="w-2.5 h-2.5" />{readinessScore}%
                  </span>
                )}

                <div className="w-px h-5 bg-slate-700/60 mx-1" />

                {/* Undo / Redo / Save */}
                <button onClick={undo} disabled={!undoStack.length} title={`Undo (${undoStack.length})`}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-slate-400 hover:text-cyan-400 disabled:opacity-25 text-xs font-mono uppercase transition-colors border border-slate-700/40 rounded-sm hover:border-cyan-500/40 disabled:cursor-not-allowed">
                  <Undo2 className="w-3.5 h-3.5" /> UNDO
                </button>
                <button onClick={redo} disabled={!redoStack.length} title={`Redo (${redoStack.length})`}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-slate-400 hover:text-cyan-400 disabled:opacity-25 text-xs font-mono uppercase transition-colors border border-slate-700/40 rounded-sm hover:border-cyan-500/40 disabled:cursor-not-allowed">
                  <Redo2 className="w-3.5 h-3.5" /> REDO
                </button>
                <button onClick={saveVersion} title="Save restore point"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-yellow-400/80 hover:text-yellow-300 text-xs font-mono uppercase transition-colors border border-yellow-700/40 rounded-sm hover:border-yellow-500/50 hover:bg-yellow-500/5">
                  <BookmarkPlus className="w-3.5 h-3.5" /> SAVE
                </button>
                <button onClick={() => setShowVersions(v => !v)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono uppercase transition-colors border rounded-sm ${
                    showVersions ? 'bg-violet-500/20 border-violet-500/50 text-violet-300' : 'text-slate-400 border-slate-700/40 hover:text-violet-400 hover:border-violet-500/40'}`}>
                  <History className="w-3.5 h-3.5" /> HISTORY{versions.length > 0 ? ` (${versions.length})` : ''}
                </button>

                <div className="w-px h-5 bg-slate-700/60 mx-1" />

                {/* Test / Console / Split / ⌃K */}
                <button onClick={runScan} disabled={scanLoading || !generatedApp?.project}
                  title="Static code scan"
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono uppercase transition-colors border rounded-sm disabled:opacity-30 ${
                    showScanPanel
                      ? (scanResult?.counts && Object.values(scanResult.counts).some(v => v > 0)
                          ? 'bg-amber-500/20 border-amber-500/50 text-amber-300'
                          : 'bg-emerald-500/20 border-emerald-500/50 text-emerald-300')
                      : 'text-slate-400 border-slate-700/40 hover:text-amber-400 hover:border-amber-500/40'}`}>
                  {scanLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Bug className="w-3.5 h-3.5" />}
                  {scanResult ? `SCORE ${scanResult.score}` : 'TEST'}
                </button>
                <button onClick={() => setShowConsole(v => !v)} title="Console errors"
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono uppercase transition-colors border rounded-sm ${
                    consoleErrors.some(e => e.level === 'error')
                      ? 'bg-red-500/20 border-red-500/50 text-red-300'
                      : showConsole ? 'bg-slate-700/40 border-slate-500 text-slate-300'
                      : 'text-slate-500 border-slate-700/30 hover:text-slate-300 hover:border-slate-500'}`}>
                  <Terminal className="w-3.5 h-3.5" />
                  {consoleErrors.length > 0 ? consoleErrors.length : 'CONSOLE'}
                </button>
                <button onClick={() => setSplitView(v => !v)} title="Split view (⌃\)"
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono uppercase transition-colors border rounded-sm ${
                    splitView ? 'bg-sky-500/20 border-sky-500/50 text-sky-300' : 'text-slate-500 border-slate-700/30 hover:text-sky-400 hover:border-sky-500/40'}`}>
                  <Columns className="w-3.5 h-3.5" /> SPLIT
                </button>
                <button onClick={() => { setShowCmdPalette(true); setCmdQuery(''); setCmdIndex(0); }} title="Command palette"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono uppercase transition-colors border rounded-sm text-slate-500 border-slate-700/30 hover:text-cyan-400 hover:border-cyan-500/40">
                  <Command className="w-3.5 h-3.5" /> ⌃K
                </button>
              </div>

              {/* ── Toolbar Row 2: Panels + Export + Deploy ── */}
              <div className="flex items-center gap-2 px-4 py-2 border-b border-cyan-500/20 bg-black/40 flex-shrink-0">
                {/* Panels group */}
                <span className="text-[9px] font-mono text-slate-600 uppercase tracking-widest mr-1">PANELS</span>
                <button onClick={() => setShowFileExplorer(v => !v)} title="File explorer"
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono uppercase transition-colors border rounded-sm ${
                    showFileExplorer ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-300' : 'text-slate-500 border-slate-700/30 hover:text-indigo-400 hover:border-indigo-500/40'}`}>
                  <FolderTree className="w-3.5 h-3.5" /> FILES
                  {(() => { const n = ptGetExtraFiles(generatedApp?.project).length + ptGetAssets(generatedApp?.project).length; return n > 0 ? ` (${n})` : ''; })()}
                </button>
                <button onClick={() => setShowActionLog(v => !v)} title="Action log"
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono uppercase transition-colors border rounded-sm ${
                    showActionLog ? 'bg-slate-700/40 border-slate-500 text-slate-300' : 'text-slate-500 border-slate-700/30 hover:text-slate-300 hover:border-slate-500'}`}>
                  <Activity className="w-3.5 h-3.5" /> {actionLog.length > 0 ? `LOG (${actionLog.length})` : 'LOG'}
                </button>
                <button onClick={() => setShowNotes(v => !v)} title="Project notes"
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono uppercase transition-colors border rounded-sm ${
                    showNotes ? 'bg-yellow-500/20 border-yellow-500/50 text-yellow-300' : 'text-slate-500 border-slate-700/30 hover:text-yellow-400 hover:border-yellow-500/40'}`}>
                  <StickyNote className="w-3.5 h-3.5" /> NOTES
                </button>
                <button onClick={explainArchitecture} disabled={archLoading} title="AI architecture explain"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono uppercase transition-colors border rounded-sm text-slate-500 border-slate-700/30 hover:text-violet-400 hover:border-violet-500/40 disabled:opacity-30">
                  {archLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <GitCommit className="w-3.5 h-3.5" />} ARCH
                </button>

                <div className="w-px h-5 bg-slate-700/60 mx-2" />

                {/* Export group */}
                <span className="text-[9px] font-mono text-slate-600 uppercase tracking-widest mr-1">EXPORT</span>
                <button onClick={openInBrowser}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-500/15 border border-cyan-500/40 text-cyan-400 text-xs font-mono uppercase rounded-sm hover:bg-cyan-500/25 transition-all">
                  <Eye className="w-3.5 h-3.5" /> OPEN
                </button>
                <button onClick={downloadApp}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-500/15 border border-violet-500/40 text-violet-400 text-xs font-mono uppercase rounded-sm hover:bg-violet-500/25 transition-all">
                  <Download className="w-3.5 h-3.5" /> .HTML
                </button>
                <button onClick={exportZip}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-500/15 border border-emerald-500/40 text-emerald-400 text-xs font-mono uppercase rounded-sm hover:bg-emerald-500/25 transition-all">
                  <Package className="w-3.5 h-3.5" /> ZIP
                </button>
                <button onClick={exportSessionJson} title="Export session as importable JSON"
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700/30 border border-slate-600/40 text-slate-400 text-xs font-mono uppercase rounded-sm hover:bg-slate-600/30 transition-all">
                  <Download className="w-3.5 h-3.5" /> JSON
                </button>
                <button onClick={handleShare} disabled={shareLoading} title="Share a public live preview link"
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-pink-500/15 border border-pink-500/40 text-pink-400 text-xs font-mono uppercase rounded-sm hover:bg-pink-500/25 transition-all disabled:opacity-50">
                  {shareLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Share2 className="w-3.5 h-3.5" />} SHARE
                </button>

                <div className="w-px h-5 bg-slate-700/60 mx-2" />

                {/* Deploy group */}
                <span className="text-[9px] font-mono text-slate-600 uppercase tracking-widest mr-1">DEPLOY</span>
                <button onClick={() => { setShowGithubModal(true); setGithubResult(null); }} title="Push to GitHub"
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800/70 border border-gray-600/50 text-gray-300 text-xs font-mono uppercase rounded-sm hover:bg-gray-700/70 hover:text-white transition-all">
                  <Github className="w-3.5 h-3.5" /> GITHUB
                </button>
                <button onClick={() => { setShowVercelModal(true); setVercelResult(null); }} title="Deploy to Vercel"
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-black/70 border border-white/25 text-white text-xs font-mono uppercase rounded-sm hover:bg-white/10 transition-all">
                  <Globe className="w-3.5 h-3.5" /> VERCEL
                </button>

                <div className="w-px h-5 bg-slate-700/60 mx-2" />

                {/* Save group */}
                <button onClick={handleSaveProject} title={isSubscribed ? 'Save project' : 'Upgrade to save your project'}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono uppercase rounded-sm transition-all border ${
                    isSubscribed
                      ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/20'
                      : 'bg-white/5 border-white/10 text-slate-400 hover:bg-white/10 hover:text-slate-300'
                  }`}>
                  <BookmarkPlus className="w-3.5 h-3.5" /> SAVE
                  {!isSubscribed && <Lock className="w-2.5 h-2.5 opacity-50" />}
                </button>

                <div className="flex-1" />

                <button onClick={() => { setGeneratedApp(null); setDescription(''); setEditInput(''); setEditHistory([]); setUndoStack([]); setRedoStack([]); setVersions([]); setActiveTab('preview'); setDiffView(null); setShowFileExplorer(false); setScanResult(null); setConsoleErrors([]); }}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-slate-500 hover:text-slate-300 text-xs font-mono uppercase transition-colors border border-slate-700/30 rounded-sm hover:border-slate-500/50">
                  <RotateCcw className="w-3.5 h-3.5" /> NEW
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
                    <button onClick={() => saveVersion('manual')} className="px-2 py-1 bg-violet-500/20 border border-violet-500/40 text-violet-400 text-[10px] font-mono uppercase rounded-sm hover:bg-violet-500/30">
                      + Save Now
                    </button>
                    <button onClick={generateChangelog} disabled={changelogLoading || !versions.length}
                      className="px-2 py-1 text-slate-400 hover:text-violet-300 text-[10px] font-mono uppercase disabled:opacity-30 flex items-center gap-1">
                      {changelogLoading ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : <AlignLeft className="w-2.5 h-2.5" />} Changelog
                    </button>
                  </div>
                  {changelogPanel && (
                    <div className="mb-2 px-3 py-2 bg-black/50 border border-violet-900/30 rounded-sm text-[9px] font-mono text-slate-300 whitespace-pre-wrap max-h-32 overflow-y-auto">
                      {changelogPanel}
                    </div>
                  )}
                  {versions.length === 0 ? (
                    <p className="text-[10px] text-slate-600 font-mono">No saved versions yet. Click "+ Save Now" to create a restore point.</p>
                  ) : (
                    <div className="space-y-1 max-h-40 overflow-y-auto">
                      {versions.map((ver, i) => {
                        const etColors = { manual:'text-violet-400', 'ai-edit':'text-cyan-400', restore:'text-amber-400', import:'text-blue-400', 'auto-fix':'text-emerald-400', checkpoint:'text-slate-500', 'deploy-ready':'text-green-400' };
                        const etColor = etColors[ver.eventType] || 'text-slate-600';
                        return (
                        <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 bg-black/40 border border-violet-900/40 rounded-sm group">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5">
                              <span className="text-[10px] font-mono text-violet-300 truncate">{ver.name}</span>
                              {ver.eventType && <span className={`text-[8px] font-mono uppercase ${etColor}`}>{ver.eventType}</span>}
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
                                setDiffView({
                                  file: ver.file_changed || 'index.html',
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
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* ── Action log panel ── */}
              {showActionLog && (
                <div className="border-b border-slate-700/40 bg-black/60 flex-shrink-0" style={{ maxHeight: '180px' }}>
                  <div className="flex items-center gap-2 px-4 py-2 border-b border-slate-700/20 sticky top-0 bg-black/80">
                    <Activity className="w-3 h-3 text-slate-400" />
                    <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider flex-1">Action Log</span>
                    <button onClick={() => setActionLog([])} className="text-[9px] font-mono text-slate-600 hover:text-slate-400 uppercase">Clear</button>
                    <button onClick={() => setShowActionLog(false)} className="text-slate-600 hover:text-slate-400 ml-2"><X className="w-3 h-3" /></button>
                  </div>
                  <div className="overflow-y-auto px-3 py-2 space-y-0.5 font-mono text-[9px]">
                    {actionLog.length === 0 && <span className="text-slate-700">No actions logged yet.</span>}
                    {[...actionLog].reverse().map(entry => {
                      const typeColors = { generate:'text-cyan-400', 'ai-edit':'text-violet-400', scan:'text-amber-400', 'auto-fix':'text-emerald-400', save:'text-violet-300', format:'text-blue-400', explain:'text-pink-400', changelog:'text-indigo-400', restore:'text-orange-400', deploy:'text-green-400' };
                      return (
                        <div key={entry.id} className="flex items-center gap-2">
                          <span className="text-slate-700 flex-shrink-0">{entry.time}</span>
                          <span className={`flex-shrink-0 uppercase ${typeColors[entry.type] || 'text-slate-500'}`}>[{entry.type}]</span>
                          <span className="text-slate-400 truncate">{entry.msg}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* ── Notes panel ── */}
              {showNotes && (
                <div className="border-b border-yellow-500/20 bg-black/60 flex-shrink-0" style={{ maxHeight: '160px' }}>
                  <div className="flex items-center gap-2 px-4 py-2 border-b border-yellow-500/10">
                    <StickyNote className="w-3 h-3 text-yellow-400" />
                    <span className="text-[10px] font-mono text-yellow-400 uppercase tracking-wider flex-1">Project Notes</span>
                    <button onClick={() => setShowNotes(false)} className="text-slate-600 hover:text-slate-400"><X className="w-3 h-3" /></button>
                  </div>
                  <textarea
                    value={projectNotes}
                    onChange={e => setProjectNotes(e.target.value)}
                    placeholder="Notes, ideas, TODOs for this project..."
                    className="w-full bg-transparent text-yellow-100 placeholder:text-yellow-900/50 font-mono text-[10px] p-3 outline-none resize-none border-0"
                    style={{ minHeight: '100px' }}
                  />
                </div>
              )}

              {/* ── Architecture panel ── */}
              {archPanel && (
                <div className="border-b border-violet-500/20 bg-black/60 flex-shrink-0" style={{ maxHeight: '200px' }}>
                  <div className="flex items-center gap-2 px-4 py-2 border-b border-violet-500/10">
                    <GitCommit className="w-3 h-3 text-violet-400" />
                    <span className="text-[10px] font-mono text-violet-400 uppercase tracking-wider flex-1">Architecture Overview</span>
                    <button onClick={() => setArchPanel(null)} className="text-slate-600 hover:text-slate-400"><X className="w-3 h-3" /></button>
                  </div>
                  <p className="px-4 py-3 text-[10px] font-mono text-slate-300 whitespace-pre-wrap overflow-y-auto" style={{ maxHeight: '156px' }}>{archPanel}</p>
                </div>
              )}

              {/* ── Scan results panel ── */}
              {showScanPanel && (
                <div className="border-b border-amber-500/20 bg-black/70 flex-shrink-0 flex flex-col" style={{ maxHeight: '240px' }}>
                  <div className="flex items-center gap-2 px-4 py-2 border-b border-amber-500/10 flex-shrink-0">
                    <Bug className="w-3.5 h-3.5 text-amber-400" />
                    <span className="text-[10px] font-mono text-amber-400 uppercase tracking-wider flex-1">
                      Static Scan {scanResult ? `— Score ${scanResult.score}/100` : ''}
                    </span>
                    {scanResult && (
                      <div className="flex gap-2 mr-2">
                        {scanResult.counts.critical > 0    && <span className="text-[9px] font-mono text-red-400">{scanResult.counts.critical} critical</span>}
                        {scanResult.counts.warning > 0     && <span className="text-[9px] font-mono text-amber-400">{scanResult.counts.warning} warning</span>}
                        {scanResult.counts.performance > 0 && <span className="text-[9px] font-mono text-blue-400">{scanResult.counts.performance} perf</span>}
                        {scanResult.counts.cosmetic > 0    && <span className="text-[9px] font-mono text-slate-500">{scanResult.counts.cosmetic} cosmetic</span>}
                      </div>
                    )}
                    {scanResult?.findings?.filter(f => ['critical','warning'].includes(f.severity)).length > 0 && (
                      <button
                        onClick={() => runAutoFix(scanResult.findings.filter(f => ['critical','warning'].includes(f.severity)))}
                        disabled={autoFixLoading}
                        className="flex items-center gap-1 px-2 py-0.5 bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 text-[9px] font-mono uppercase rounded-sm hover:bg-emerald-500/30 disabled:opacity-50"
                      >
                        {autoFixLoading ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : <Wrench className="w-2.5 h-2.5" />}
                        Auto-Fix
                      </button>
                    )}
                    <button onClick={() => setShowScanPanel(false)} className="text-slate-600 hover:text-slate-400"><X className="w-3 h-3" /></button>
                  </div>
                  <div className="overflow-y-auto px-3 py-2 space-y-1">
                    {scanLoading && <p className="text-[10px] font-mono text-slate-500 animate-pulse">Scanning project files...</p>}
                    {!scanLoading && scanResult?.findings?.length === 0 && (
                      <p className="text-[10px] font-mono text-emerald-400">No issues found. Project looks clean!</p>
                    )}
                    {!scanLoading && scanResult?.findings?.map((f, i) => {
                      const colors = {
                        critical:    'text-red-400 border-red-900/50 bg-red-950/30',
                        warning:     'text-amber-400 border-amber-900/50 bg-amber-950/20',
                        performance: 'text-blue-400 border-blue-900/50 bg-blue-950/20',
                        cosmetic:    'text-slate-500 border-slate-700/50 bg-slate-900/20',
                      };
                      const icons = {
                        critical: <AlertCircle className="w-3 h-3 flex-shrink-0" />,
                        warning:  <AlertTriangle className="w-3 h-3 flex-shrink-0" />,
                        performance: <Gauge className="w-3 h-3 flex-shrink-0" />,
                        cosmetic: <Zap className="w-3 h-3 flex-shrink-0" />,
                      };
                      return (
                        <div key={i} className={`flex items-start gap-2 px-2 py-1.5 rounded-sm border text-[10px] font-mono ${colors[f.severity] || colors.cosmetic}`}>
                          {icons[f.severity] || icons.cosmetic}
                          <span className="flex-1">{f.message}</span>
                          <span className="text-[9px] opacity-60 flex-shrink-0">{f.file}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* ── Console panel ── */}
              {showConsole && (
                <div className="border-b border-slate-700/40 bg-black/80 flex-shrink-0 flex flex-col" style={{ maxHeight: '180px' }}>
                  <div className="flex items-center gap-2 px-4 py-1.5 border-b border-slate-700/30 flex-shrink-0">
                    <Terminal className="w-3 h-3 text-slate-400" />
                    <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider flex-1">Console</span>
                    <button onClick={() => setConsoleErrors([])} className="text-[9px] font-mono text-slate-600 hover:text-slate-400 uppercase">Clear</button>
                    <button onClick={() => setShowConsole(false)} className="text-slate-600 hover:text-slate-400 ml-2"><X className="w-3 h-3" /></button>
                  </div>
                  <div className="overflow-y-auto px-3 py-1.5 space-y-0.5 font-mono text-[10px]">
                    {consoleErrors.length === 0 && <span className="text-slate-600">No console output captured yet. Use the OPEN button to view the app and start capturing errors.</span>}
                    {consoleErrors.map((e, i) => (
                      <div key={i} className={`flex gap-2 ${e.level === 'error' ? 'text-red-400' : e.level === 'warn' ? 'text-amber-400' : 'text-slate-400'}`}>
                        <span className="text-slate-600 flex-shrink-0">{e.time}</span>
                        <span className="opacity-60 flex-shrink-0">[{e.level}]</span>
                        <span className="break-all">{e.msg}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ── File Explorer panel ── */}
              {showFileExplorer && (
                <div className="border-b border-indigo-500/20 bg-black/60 flex-shrink-0" style={{ maxHeight: '260px', overflowY: 'auto' }}>
                  <div className="flex items-center gap-2 px-4 py-2 border-b border-indigo-500/10 sticky top-0 bg-black/80">
                    <FolderTree className="w-3.5 h-3.5 text-indigo-400" />
                    <span className="text-[10px] font-mono text-indigo-400 uppercase tracking-wider flex-1">File Explorer</span>
                    <button onClick={() => assetInputRef.current?.click()}
                      className="flex items-center gap-1 px-2 py-0.5 text-[9px] font-mono uppercase text-cyan-400 border border-cyan-700/40 rounded-sm hover:bg-cyan-500/10 transition-colors">
                      <Upload className="w-2.5 h-2.5" /> Upload Asset
                    </button>
                    <button onClick={() => setShowNewFileInput(v => !v)}
                      className="flex items-center gap-1 px-2 py-0.5 text-[9px] font-mono uppercase text-indigo-400 border border-indigo-700/40 rounded-sm hover:bg-indigo-500/10 transition-colors">
                      <FilePlus className="w-2.5 h-2.5" /> New File
                    </button>
                    <button onClick={() => setShowFileExplorer(false)} className="text-slate-600 hover:text-slate-300 ml-1">
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {showNewFileInput && (
                    <div className="flex items-center gap-2 px-4 py-2 bg-indigo-950/30 border-b border-indigo-500/10">
                      <input
                        value={newFileName}
                        onChange={e => setNewFileName(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && createExtraFile()}
                        placeholder="filename.js or filename.css..."
                        className="flex-1 bg-black/50 border border-indigo-700/50 text-indigo-100 placeholder:text-indigo-900/60 rounded-sm px-2 py-1 text-[10px] font-mono outline-none focus:border-indigo-400"
                        autoFocus
                      />
                      <button onClick={createExtraFile}
                        className="px-2 py-1 bg-indigo-500/20 border border-indigo-500/40 text-indigo-400 text-[9px] font-mono uppercase rounded-sm hover:bg-indigo-500/30">
                        Create
                      </button>
                      <button onClick={() => { setShowNewFileInput(false); setNewFileName(''); }}
                        className="px-2 py-1 text-slate-500 hover:text-slate-300 text-[9px] font-mono uppercase">
                        Cancel
                      </button>
                    </div>
                  )}

                  <div className="px-2 py-2 space-y-0.5">
                    {/* Core files */}
                    <div className="px-2 py-0.5 text-[9px] font-mono text-slate-600 uppercase tracking-wider">Core Files</div>
                    {[
                      { id: 'html',   label: 'index.html', icon: <FileCode className="w-3 h-3 text-orange-400" /> },
                      { id: 'css',    label: 'style.css',  icon: <Palette className="w-3 h-3 text-blue-400" /> },
                      { id: 'js',     label: 'script.js',  icon: <Code2 className="w-3 h-3 text-yellow-400" /> },
                      { id: 'readme', label: 'README.md',  icon: <BookOpen className="w-3 h-3 text-green-400" /> },
                    ].map(f => (
                      <button key={f.id} onClick={() => { setActiveTab(f.id); setShowFileExplorer(false); }}
                        className={`w-full flex items-center gap-2 px-3 py-1 rounded-sm text-[10px] font-mono text-left transition-colors ${
                          activeTab === f.id ? 'bg-indigo-500/15 text-indigo-300' : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'
                        }`}>
                        {f.icon} {f.label}
                      </button>
                    ))}

                    {/* Extra custom files */}
                    {ptGetExtraFiles(generatedApp?.project).length > 0 && (
                      <>
                        <div className="px-2 py-0.5 mt-2 text-[9px] font-mono text-slate-600 uppercase tracking-wider">Custom Files</div>
                        {ptGetExtraFiles(generatedApp.project).map(ef => (
                          <div key={ef.name} className={`flex items-center gap-1 px-3 py-1 rounded-sm transition-colors ${
                            activeTab === `extra:${ef.name}` ? 'bg-indigo-500/15' : 'hover:bg-white/5'
                          }`}>
                            <button onClick={() => { setActiveTab(`extra:${ef.name}`); setShowFileExplorer(false); }}
                              className="flex items-center gap-2 flex-1 text-[10px] font-mono text-slate-400 hover:text-slate-200 text-left">
                              <FileText className="w-3 h-3 text-indigo-400 flex-shrink-0" />
                              {ef.name}
                            </button>
                            <button onClick={() => deleteExtraFile(ef.name)}
                              className="text-slate-700 hover:text-red-400 transition-colors flex-shrink-0">
                              <Trash2 className="w-2.5 h-2.5" />
                            </button>
                          </div>
                        ))}
                      </>
                    )}

                    {/* Assets */}
                    {ptGetAssets(generatedApp?.project).length > 0 && (
                      <>
                        <div className="px-2 py-0.5 mt-2 text-[9px] font-mono text-slate-600 uppercase tracking-wider flex items-center gap-1">
                          <Folder className="w-2.5 h-2.5" /> assets/
                        </div>
                        {ptGetAssets(generatedApp.project).map(asset => (
                          <div key={asset.name} className="flex items-center gap-1 px-3 py-1 rounded-sm hover:bg-white/5 group">
                            <span className="flex items-center gap-2 flex-1 text-[10px] font-mono text-slate-500">
                              {asset.type?.startsWith('image/') ? '🖼' : '📄'} {asset.name}
                              <span className="text-[8px] text-slate-700 ml-auto">
                                {asset.type?.split('/')[1]?.toUpperCase() || 'FILE'}
                              </span>
                            </span>
                            <button onClick={() => deleteAsset(asset.name)}
                              className="text-slate-700 hover:text-red-400 transition-colors flex-shrink-0 opacity-0 group-hover:opacity-100">
                              <Trash2 className="w-2.5 h-2.5" />
                            </button>
                          </div>
                        ))}
                      </>
                    )}

                    {ptGetExtraFiles(generatedApp?.project).length === 0 && ptGetAssets(generatedApp?.project).length === 0 && (
                      <p className="px-3 py-3 text-[9px] font-mono text-slate-700 text-center">
                        No custom files or assets yet. Upload an image or create a new file.
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* ── Diff viewer panel ── */}
              {diffView && (
                <div className="border-b border-amber-500/20 bg-black/70 flex-shrink-0 flex flex-col" style={{ maxHeight: '220px' }}>
                  <div className="flex items-center gap-2 px-4 py-2 border-b border-amber-500/10">
                    <span className="text-[10px] font-mono text-amber-400 uppercase tracking-wider flex-1">
                      Diff — {diffView.file} · {diffView.nameA} → {diffView.nameB}
                    </span>
                    <button
                      onClick={() => explainDiff()}
                      className="flex items-center gap-1 px-2 py-0.5 text-violet-400 text-[9px] font-mono uppercase border border-violet-700/40 rounded-sm hover:bg-violet-500/10">
                      <FileSearch className="w-2.5 h-2.5" /> Explain Diff
                    </button>
                    <button onClick={() => setDiffView(null)} className="text-slate-600 hover:text-slate-300 ml-1"><X className="w-3.5 h-3.5" /></button>
                  </div>
                  <div className="overflow-y-auto text-[10px] font-mono px-3 py-2 space-y-0.5">
                    {computeDiff(ptGetContent(diffView.verA, diffView.file) || '', ptGetContent(diffView.verB, diffView.file) || '').map((line, i) => (
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

              {/* ── Find/Replace panel ── */}
              {showFindPanel && (
                <div className="flex-shrink-0 border-b border-cyan-500/20 bg-black/40 px-3 py-2 space-y-1.5">
                  <div className="flex items-center gap-2">
                    <Search className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0" />
                    <input
                      value={findQuery}
                      onChange={e => setFindQuery(e.target.value)}
                      placeholder="Find…"
                      className="flex-1 bg-slate-800/60 text-slate-200 text-[11px] font-mono px-2 py-1 rounded border border-slate-600/40 focus:outline-none focus:border-cyan-500/60"
                    />
                    <input
                      value={replaceQuery}
                      onChange={e => setReplaceQuery(e.target.value)}
                      placeholder="Replace…"
                      className="flex-1 bg-slate-800/60 text-slate-200 text-[11px] font-mono px-2 py-1 rounded border border-slate-600/40 focus:outline-none focus:border-cyan-500/60"
                    />
                    <label className="flex items-center gap-1 text-[10px] text-slate-400 cursor-pointer select-none">
                      <input type="checkbox" checked={findCaseSensitive} onChange={e => setFindCaseSensitive(e.target.checked)} className="accent-cyan-500" />
                      Aa
                    </label>
                    <button
                      onClick={replaceInFile}
                      disabled={!findQuery}
                      className="px-2 py-1 text-[10px] rounded bg-cyan-600/20 text-cyan-300 hover:bg-cyan-600/40 disabled:opacity-40 disabled:cursor-not-allowed"
                    >Replace All</button>
                    <span className="text-[10px] text-slate-500 min-w-[3rem] text-right">{findQuery ? `${findCount} match${findCount !== 1 ? 'es' : ''}` : ''}</span>
                    <button onClick={() => setShowFindPanel(false)} className="text-slate-500 hover:text-slate-300"><X className="w-3.5 h-3.5" /></button>
                  </div>
                </div>
              )}

              {/* ── File tabs ── */}
              <div className="flex items-center border-b border-cyan-500/20 bg-black/30 flex-shrink-0 overflow-x-auto">
                {[
                  { id: 'preview', label: 'Preview',    icon: <MonitorPlay className="w-3 h-3" />, dirty: false },
                  { id: 'html',    label: 'index.html', icon: <FileCode className="w-3 h-3" />,    dirty: isDirty('index.html'), file: 'index.html' },
                  { id: 'css',     label: 'style.css',  icon: <Palette className="w-3 h-3" />,     dirty: isDirty('style.css'),  file: 'style.css' },
                  { id: 'js',      label: 'script.js',  icon: <Code2 className="w-3 h-3" />,       dirty: isDirty('script.js'),  file: 'script.js' },
                  { id: 'readme',  label: 'README.md',  icon: <BookOpen className="w-3 h-3" />,    dirty: false,                 file: null },
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
                    {tab.file && isLocked(tab.file) && <Shield className="w-2.5 h-2.5 text-amber-400 flex-shrink-0" title="Locked" />}
                    {tab.dirty && <span className="w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" title="Unsaved changes" />}
                  </button>
                ))}
                {/* Extra file tabs */}
                {ptGetExtraFiles(generatedApp?.project).map(ef => (
                  <button
                    key={`extra:${ef.name}`}
                    onClick={() => setActiveTab(`extra:${ef.name}`)}
                    className={`flex items-center gap-1.5 px-3 py-2 text-[11px] font-mono border-r border-cyan-500/10 transition-all flex-shrink-0 group ${
                      activeTab === `extra:${ef.name}`
                        ? 'bg-indigo-500/10 text-indigo-300 border-b-2 border-b-indigo-400'
                        : 'text-slate-500 hover:text-slate-300 hover:bg-white/5'
                    }`}
                  >
                    <FileText className="w-3 h-3" />{ef.name}
                    {isLocked(ef.name) && <Shield className="w-2.5 h-2.5 text-amber-400 flex-shrink-0" title="Locked" />}
                    <span
                      onClick={e => { e.stopPropagation(); deleteExtraFile(ef.name); }}
                      className="opacity-0 group-hover:opacity-100 ml-1 hover:text-red-400 transition-opacity cursor-pointer"
                    ><X className="w-2.5 h-2.5" /></span>
                  </button>
                ))}
                {/* Explain panel toggle */}
                {explainPanel && (
                  <button onClick={() => setExplainPanel(null)}
                    className="ml-auto flex items-center gap-1 px-2 py-1.5 text-[10px] font-mono text-cyan-500 hover:text-cyan-300 flex-shrink-0">
                    <X className="w-3 h-3" /> Close Explain
                  </button>
                )}
              </div>

              {/* ── Explain panel ── */}
              {explainPanel && (
                <div className="border-b border-cyan-500/20 bg-black/60 px-4 py-3 flex-shrink-0 max-h-40 overflow-y-auto">
                  <div className="flex items-center gap-2 mb-1.5">
                    <Wand2 className="w-3 h-3 text-cyan-400" />
                    <span className="text-[10px] font-mono text-cyan-400 uppercase tracking-wider">{explainPanel.file} — Explanation</span>
                    {explainLoading && <Loader2 className="w-3 h-3 text-cyan-400 animate-spin" />}
                  </div>
                  <p className="text-[10px] font-mono text-slate-300 whitespace-pre-wrap">{explainPanel.content}</p>
                </div>
              )}

              {/* ── Content area (preview OR code editor, or split view) ── */}
              <div className={`flex-shrink-0 overflow-hidden flex ${splitView ? 'flex-row' : 'flex-col'}`} style={{ height: splitView ? '62%' : '48%' }}>

                {/* Preview pane: always visible in split mode; also in normal mode when activeTab=preview */}
                {(splitView || activeTab === 'preview') && (
                  <div className={`relative ${splitView ? 'w-1/2 border-r border-cyan-500/20 flex-shrink-0 h-full' : 'h-full'}`}>
                    <iframe
                      key={generatedApp.html}
                      srcDoc={injectConsoleCapture(generatedApp.html)}
                      title="App Preview"
                      className="w-full h-full border-0 bg-white"
                      sandbox="allow-scripts allow-forms allow-modals allow-same-origin"
                    />
                    {/* Return experience banner — shown when resuming an existing session */}
                    {isResumed && !buildJustCompleted && (
                      <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2.5 bg-[#0d0d16]/95 border border-cyan-500/30 rounded-xl px-4 py-2.5 shadow-2xl backdrop-blur-sm pointer-events-none"
                        style={{ animation: 'fadeInDown 0.3s ease-out' }}>
                        <CheckCircle className="w-4 h-4 text-cyan-400 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-bold text-cyan-300 leading-none">Your project is ready.</p>
                          <p className="text-[10px] text-cyan-700 mt-0.5 leading-none">Continue building or deploy when you're ready.</p>
                        </div>
                        <button
                          onClick={() => { setIsResumed(false); if (!isSubscribed) { openUpgradeModal('deploy'); } else { setShowVercelModal(true); setVercelResult(null); } }}
                          title={!isSubscribed ? 'Deployment requires an active plan' : 'Deploy to Vercel'}
                          className="pointer-events-auto flex-shrink-0 flex items-center gap-1 px-2.5 py-1 bg-violet-500/20 border border-violet-500/40 text-violet-300 text-[10px] font-mono uppercase rounded-sm hover:bg-violet-500/30 transition-colors">
                          <Globe className="w-3 h-3" /> Deploy
                        </button>
                        <button onClick={() => setIsResumed(false)}
                          className="pointer-events-auto flex-shrink-0 p-1 text-slate-600 hover:text-slate-300 transition-colors rounded">
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}

                    {/* Build complete notification */}
                    {buildJustCompleted && (
                      <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2.5 bg-emerald-950/95 border border-emerald-500/40 rounded-xl px-4 py-2.5 shadow-2xl backdrop-blur-sm pointer-events-none"
                        style={{ animation: 'fadeInDown 0.3s ease-out' }}>
                        <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                        <div>
                          <p className="text-xs font-bold text-emerald-300 leading-none">Build complete.</p>
                          <p className="text-[10px] text-emerald-600 mt-0.5 leading-none">Your application is ready. You can now interact with the preview.</p>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Code editor pane: right half in split, full pane in normal (non-preview) */}
                {(splitView || activeTab !== 'preview') && (
                <div className={splitView ? 'flex-1 flex flex-col overflow-hidden h-full' : 'h-full'}>
                {/* In split mode show html by default; otherwise show whichever tab is active */}
                {(activeTab === 'html' || (splitView && activeTab === 'preview')) && (
                  <div className="h-full flex flex-col">
                    <div className="flex items-center gap-2 px-2 py-1 bg-black/40 border-b border-cyan-500/10 flex-shrink-0">
                      <button onClick={() => explainFile('index.html', ptGetContent(generatedApp.project, 'index.html'))}
                        className="flex items-center gap-1 px-2 py-0.5 text-cyan-500 text-[9px] font-mono uppercase border border-cyan-700/40 rounded-sm hover:bg-cyan-500/10">
                        <Wand2 className="w-2.5 h-2.5" /> Explain
                      </button>
                      <button onClick={() => formatFile('html')}
                        className="flex items-center gap-1 px-2 py-0.5 text-emerald-400 text-[9px] font-mono uppercase border border-emerald-700/40 rounded-sm hover:bg-emerald-500/10">
                        <AlignLeft className="w-2.5 h-2.5" /> Format
                      </button>
                      <button onClick={() => toggleLock('index.html')}
                        className={`flex items-center gap-1 px-2 py-0.5 text-[9px] font-mono uppercase border rounded-sm transition-colors ${isLocked('index.html') ? 'text-amber-400 border-amber-700/40 hover:bg-amber-500/10' : 'text-slate-500 border-slate-700/40 hover:bg-slate-500/10'}`}>
                        {isLocked('index.html') ? <Shield className="w-2.5 h-2.5" /> : <ShieldOff className="w-2.5 h-2.5" />}
                        {isLocked('index.html') ? 'Locked' : 'Lock'}
                      </button>
                      {isDirty('index.html') && <span className="text-[9px] font-mono text-amber-400">● Unsaved</span>}
                    </div>
                    {isSubscribed
                      ? <textarea
                          value={ptGetContent(generatedApp.project, 'index.html')}
                          onChange={e => handleDirectEdit('html', e.target.value)}
                          onBlur={() => pushUndo()}
                          className="flex-1 bg-[#0d1117] text-[#e6edf3] font-mono text-xs p-3 outline-none resize-none border-0"
                          spellCheck={false}
                        />
                      : <LockedCodeView code={ptGetContent(generatedApp.project, 'index.html')} onUpgrade={() => setShowUpgradeModal(true)} />
                    }
                  </div>
                )}
                {activeTab === 'css' && (
                  <div className="h-full flex flex-col">
                    <div className="flex items-center gap-2 px-2 py-1 bg-black/40 border-b border-cyan-500/10 flex-shrink-0">
                      <button onClick={() => explainFile('style.css', ptGetContent(generatedApp.project, 'style.css'))}
                        className="flex items-center gap-1 px-2 py-0.5 text-cyan-500 text-[9px] font-mono uppercase border border-cyan-700/40 rounded-sm hover:bg-cyan-500/10">
                        <Wand2 className="w-2.5 h-2.5" /> Explain
                      </button>
                      <button onClick={() => formatFile('css')}
                        className="flex items-center gap-1 px-2 py-0.5 text-emerald-400 text-[9px] font-mono uppercase border border-emerald-700/40 rounded-sm hover:bg-emerald-500/10">
                        <AlignLeft className="w-2.5 h-2.5" /> Format
                      </button>
                      <button onClick={() => toggleLock('style.css')}
                        className={`flex items-center gap-1 px-2 py-0.5 text-[9px] font-mono uppercase border rounded-sm transition-colors ${isLocked('style.css') ? 'text-amber-400 border-amber-700/40 hover:bg-amber-500/10' : 'text-slate-500 border-slate-700/40 hover:bg-slate-500/10'}`}>
                        {isLocked('style.css') ? <Shield className="w-2.5 h-2.5" /> : <ShieldOff className="w-2.5 h-2.5" />}
                        {isLocked('style.css') ? 'Locked' : 'Lock'}
                      </button>
                      {isDirty('style.css') && <span className="text-[9px] font-mono text-amber-400">● Unsaved</span>}
                    </div>
                    {isSubscribed
                      ? <textarea
                          value={ptGetContent(generatedApp.project, 'style.css')}
                          onChange={e => handleDirectEdit('css', e.target.value)}
                          onBlur={() => pushUndo()}
                          className="flex-1 bg-[#0d1117] text-[#e6edf3] font-mono text-xs p-3 outline-none resize-none border-0"
                          spellCheck={false}
                        />
                      : <LockedCodeView code={ptGetContent(generatedApp.project, 'style.css')} onUpgrade={() => setShowUpgradeModal(true)} />
                    }
                  </div>
                )}
                {activeTab === 'js' && (
                  <div className="h-full flex flex-col">
                    <div className="flex items-center gap-2 px-2 py-1 bg-black/40 border-b border-cyan-500/10 flex-shrink-0">
                      <button onClick={() => explainFile('script.js', ptGetContent(generatedApp.project, 'script.js'))}
                        className="flex items-center gap-1 px-2 py-0.5 text-cyan-500 text-[9px] font-mono uppercase border border-cyan-700/40 rounded-sm hover:bg-cyan-500/10">
                        <Wand2 className="w-2.5 h-2.5" /> Explain
                      </button>
                      <button onClick={() => formatFile('js')}
                        className="flex items-center gap-1 px-2 py-0.5 text-emerald-400 text-[9px] font-mono uppercase border border-emerald-700/40 rounded-sm hover:bg-emerald-500/10">
                        <AlignLeft className="w-2.5 h-2.5" /> Format
                      </button>
                      <button onClick={() => toggleLock('script.js')}
                        className={`flex items-center gap-1 px-2 py-0.5 text-[9px] font-mono uppercase border rounded-sm transition-colors ${isLocked('script.js') ? 'text-amber-400 border-amber-700/40 hover:bg-amber-500/10' : 'text-slate-500 border-slate-700/40 hover:bg-slate-500/10'}`}>
                        {isLocked('script.js') ? <Shield className="w-2.5 h-2.5" /> : <ShieldOff className="w-2.5 h-2.5" />}
                        {isLocked('script.js') ? 'Locked' : 'Lock'}
                      </button>
                      {isDirty('script.js') && <span className="text-[9px] font-mono text-amber-400">● Unsaved</span>}
                    </div>
                    {isSubscribed
                      ? <textarea
                          value={ptGetContent(generatedApp.project, 'script.js')}
                          onChange={e => handleDirectEdit('js', e.target.value)}
                          onBlur={() => pushUndo()}
                          className="flex-1 bg-[#0d1117] text-[#e6edf3] font-mono text-xs p-3 outline-none resize-none border-0"
                          spellCheck={false}
                        />
                      : <LockedCodeView code={ptGetContent(generatedApp.project, 'script.js')} onUpgrade={() => setShowUpgradeModal(true)} />
                    }
                  </div>
                )}
                {activeTab === 'readme' && (
                  <div className="h-full flex flex-col">
                    <div className="flex items-center gap-2 px-2 py-1 bg-black/40 border-b border-cyan-500/10 flex-shrink-0">
                      <button onClick={generateReadme}
                        className="flex items-center gap-1 px-2 py-0.5 text-violet-400 text-[9px] font-mono uppercase border border-violet-700/40 rounded-sm hover:bg-violet-500/10">
                        <Sparkles className="w-2.5 h-2.5" /> AI Generate
                      </button>
                      <button onClick={() => explainFile('README.md', ptGetContent(generatedApp.project, 'README.md'))}
                        className="flex items-center gap-1 px-2 py-0.5 text-cyan-500 text-[9px] font-mono uppercase border border-cyan-700/40 rounded-sm hover:bg-cyan-500/10">
                        <Wand2 className="w-2.5 h-2.5" /> Explain
                      </button>
                    </div>
                    <textarea
                      value={ptGetContent(generatedApp.project, 'README.md')}
                      onChange={e => handleDirectEdit('readme', e.target.value)}
                      className="flex-1 bg-[#0d1117] text-[#e6edf3] font-mono text-xs p-3 outline-none resize-none border-0"
                      spellCheck={false}
                    />
                  </div>
                )}
                {/* Extra custom file tabs */}
                {activeTab.startsWith('extra:') && (() => {
                  const efName = activeTab.slice(6);
                  const efContent = ptGetContent(generatedApp?.project, efName);
                  if (efContent === '' && !ptGetExtraFiles(generatedApp?.project).find(f => f.name === efName)) return null;
                  return (
                    <div className="h-full flex flex-col">
                      <div className="flex items-center gap-2 px-2 py-1 bg-black/40 border-b border-indigo-500/10 flex-shrink-0">
                        <FileText className="w-3 h-3 text-indigo-400" />
                        <span className="text-[9px] font-mono text-indigo-400 flex-1">{efName}</span>
                        <button onClick={() => duplicateExtraFile(efName)}
                          className="flex items-center gap-1 px-2 py-0.5 text-indigo-400 text-[9px] font-mono uppercase border border-indigo-700/40 rounded-sm hover:bg-indigo-500/10">
                          <Copy className="w-2.5 h-2.5" /> Dupe
                        </button>
                        <button onClick={() => toggleLock(efName)}
                          className={`flex items-center gap-1 px-2 py-0.5 text-[9px] font-mono uppercase border rounded-sm transition-colors ${isLocked(efName) ? 'text-amber-400 border-amber-700/40 hover:bg-amber-500/10' : 'text-slate-500 border-slate-700/40 hover:bg-slate-500/10'}`}>
                          {isLocked(efName) ? <Shield className="w-2.5 h-2.5" /> : <ShieldOff className="w-2.5 h-2.5" />}
                          {isLocked(efName) ? 'Locked' : 'Lock'}
                        </button>
                        <button onClick={() => deleteExtraFile(efName)}
                          className="flex items-center gap-1 px-2 py-0.5 text-red-500 text-[9px] font-mono uppercase border border-red-700/40 rounded-sm hover:bg-red-500/10">
                          <Trash2 className="w-2.5 h-2.5" /> Delete
                        </button>
                      </div>
                      {isSubscribed
                        ? <textarea
                            value={efContent}
                            onChange={e => setGeneratedApp(prev => ({
                              ...prev,
                              project: ptSetContent(prev.project, efName, e.target.value),
                            }))}
                            onBlur={() => pushUndo()}
                            className="flex-1 bg-[#0d1117] text-[#e6edf3] font-mono text-xs p-3 outline-none resize-none border-0"
                            spellCheck={false}
                            placeholder={`// ${efName}\n`}
                          />
                        : <LockedCodeView code={efContent} onUpgrade={() => setShowUpgradeModal(true)} />
                      }
                    </div>
                  );
                })()}
                </div>
                )}
              </div>

              {/* ── Edit conversation ── */}
              <div className="flex-1 flex flex-col overflow-hidden border-t border-cyan-500/20">
                <div className="px-4 py-2 bg-black/50 border-b border-cyan-500/10 flex items-center gap-2 flex-shrink-0">
                  <div className="w-5 h-5 rounded bg-gradient-to-br from-cyan-500 to-violet-600 flex items-center justify-center flex-shrink-0">
                    <Wand2 className="w-3 h-3 text-white" />
                  </div>
                  <div className="flex-1">
                    <span className="text-xs font-semibold text-cyan-300">AI Editor</span>
                    <span className="text-[9px] text-slate-500 font-mono ml-2">Chat to make changes — I'll explain everything</span>
                  </div>
                  {undoStack.length > 0 && (
                    <span className="text-[9px] text-slate-600 font-mono">{undoStack.length} undo{undoStack.length !== 1 ? 's' : ''}</span>
                  )}
                </div>

                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                  {editHistory.length === 0 && (
                    <div className="flex items-start gap-2.5 mt-1">
                      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-cyan-500 to-violet-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                        <Wand2 className="w-3.5 h-3.5 text-white" />
                      </div>
                      <div className="bg-black/50 border border-cyan-900/30 rounded-lg rounded-tl-sm px-3.5 py-2.5 max-w-[85%]">
                        <p className="text-xs text-slate-300 leading-relaxed">
                          Hey! Your app is ready. Tell me what you'd like to change — I'll update the code, explain what I did, and let you approve or reject before anything is applied.
                        </p>
                        <p className="text-[10px] text-slate-500 mt-1.5 font-mono">Try: "make the buttons bigger", "fix the navigation", "add a dark mode toggle"</p>
                      </div>
                    </div>
                  )}
                  {editHistory.map((msg, idx) => (
                    <div key={idx} className={`flex items-start gap-2.5 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      {msg.role === 'assistant' && (
                        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-cyan-500 to-violet-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                          <Wand2 className="w-3.5 h-3.5 text-white" />
                        </div>
                      )}
                      <div className={`max-w-[82%] px-3.5 py-2.5 rounded-lg text-xs leading-relaxed ${
                        msg.role === 'user'
                          ? 'bg-cyan-500/20 border border-cyan-500/30 text-cyan-100 rounded-tr-sm'
                          : msg.pending
                          ? 'bg-amber-950/40 border border-amber-500/30 text-amber-100 rounded-tl-sm'
                          : 'bg-black/50 border border-cyan-900/30 text-slate-300 rounded-tl-sm'
                      }`}>
                        <span className="whitespace-pre-wrap">{msg.content}</span>
                        {msg.file_changed && msg.pending && (
                          <span className="inline-block mt-1 text-[9px] font-mono bg-black/40 px-1.5 py-0.5 rounded text-cyan-500 border border-cyan-900/40">
                            {msg.file_changed}
                          </span>
                        )}
                        {msg.pending && idx === editHistory.length - 1 && pendingChange && (
                          <div className="flex gap-2 mt-3">
                            <button onClick={approveChange}
                              className="px-3 py-1.5 bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-[10px] font-mono uppercase rounded-sm hover:bg-emerald-500/30 flex items-center gap-1">
                              ✓ Apply it
                            </button>
                            <button onClick={rejectChange}
                              className="px-3 py-1.5 bg-red-500/10 border border-red-500/30 text-red-400 text-[10px] font-mono uppercase rounded-sm hover:bg-red-500/20">
                              ✗ Discard
                            </button>
                          </div>
                        )}
                      </div>
                      {msg.role === 'user' && (
                        <div className="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center flex-shrink-0 mt-0.5 text-[10px] font-bold text-slate-300">
                          U
                        </div>
                      )}
                    </div>
                  ))}
                  {editLoading && (
                    <div className="flex items-start gap-2.5">
                      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-cyan-500 to-violet-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                        <Loader2 className="w-3.5 h-3.5 text-white animate-spin" />
                      </div>
                      <div className="px-3.5 py-2.5 bg-black/50 border border-cyan-900/30 rounded-lg rounded-tl-sm">
                        <span className="text-xs text-cyan-400/80 animate-pulse">{editMsg || 'Working on it...'}</span>
                      </div>
                    </div>
                  )}
                  <div ref={editEndRef} />
                </div>

                <div className="p-3 border-t border-cyan-500/20 bg-black/40 flex gap-2 items-end flex-shrink-0">
                  <textarea
                    value={editInput}
                    onChange={e => setEditInput(e.target.value)}
                    onKeyDown={handleEditKey}
                    placeholder='Tell me what to change... (Shift+Enter for new line)'
                    className="flex-1 bg-black/60 border border-cyan-900/50 text-cyan-100 placeholder:text-slate-600 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/30 rounded-lg font-mono text-xs p-3 outline-none resize-none"
                    rows={2}
                    disabled={editLoading}
                  />
                  <button
                    onClick={editApp}
                    disabled={editLoading || !editInput.trim()}
                    className="p-3 bg-gradient-to-r from-cyan-500 to-violet-600 text-white rounded-lg hover:from-cyan-400 hover:to-violet-500 disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0 transition-all"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </div>
              </div>

            </div>
          )}
        </div>
      )}
    </div>

    {/* ── Command Palette ── */}
    {showCmdPalette && (
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-start justify-center pt-[12vh]" onClick={() => setShowCmdPalette(false)}>
        <div className="bg-[#0d1117] border border-cyan-500/30 rounded-lg shadow-2xl w-full max-w-xl overflow-hidden" onClick={e => e.stopPropagation()}>
          {/* Search input */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-cyan-500/20">
            <Command className="w-4 h-4 text-cyan-500 flex-shrink-0" />
            <input
              autoFocus
              value={cmdQuery}
              onChange={e => { setCmdQuery(e.target.value); setCmdIndex(0); }}
              onKeyDown={e => {
                if (e.key === 'ArrowDown') { e.preventDefault(); setCmdIndex(i => Math.min(i + 1, filteredCmds.length - 1)); }
                if (e.key === 'ArrowUp')   { e.preventDefault(); setCmdIndex(i => Math.max(0, i - 1)); }
                if (e.key === 'Enter' && filteredCmds[cmdIndex]) {
                  filteredCmds[cmdIndex].action();
                  setShowCmdPalette(false);
                }
              }}
              placeholder="Search commands..."
              className="flex-1 bg-transparent text-cyan-100 placeholder:text-slate-600 outline-none font-mono text-sm"
            />
            <span className="text-[9px] font-mono text-slate-700 flex-shrink-0">ESC to close</span>
          </div>
          {/* Results */}
          <div className="max-h-80 overflow-y-auto py-1">
            {filteredCmds.length === 0 && (
              <p className="px-4 py-3 text-[11px] font-mono text-slate-600">No commands found</p>
            )}
            {filteredCmds.map((cmd, i) => {
              const Icon = cmd.icon;
              return (
                <button
                  key={cmd.label}
                  onClick={() => { cmd.action(); setShowCmdPalette(false); }}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                    i === cmdIndex ? 'bg-cyan-500/15 text-cyan-300' : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'
                  }`}
                  onMouseEnter={() => setCmdIndex(i)}
                >
                  <Icon className="w-3.5 h-3.5 flex-shrink-0 opacity-70" />
                  <span className="flex-1 font-mono text-[11px]">{cmd.label}</span>
                  {cmd.shortcut && (
                    <span className="text-[9px] font-mono text-slate-600 bg-black/40 px-1.5 py-0.5 rounded border border-slate-700/50">
                      {cmd.shortcut}
                    </span>
                  )}
                  <span className="text-[9px] font-mono text-slate-700">{cmd.group}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    )}

    {/* ── GitHub Push Modal ── */}
    {/* Upgrade modal is now rendered globally in App.js via openUpgradeModal() */}

    {showGithubModal && (
      <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setShowGithubModal(false)}>
        <div className="bg-[#0d1117] border border-gray-700/60 rounded-lg p-6 w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
          <div className="flex items-center gap-3 mb-5">
            <Github className="w-6 h-6 text-white" />
            <h3 className="text-lg font-bold text-white">Push to GitHub</h3>
            <button onClick={() => setShowGithubModal(false)} className="ml-auto text-gray-600 hover:text-gray-300"><X className="w-5 h-5" /></button>
          </div>

          <div className="space-y-3">
            <div>
              <label className="text-[10px] font-mono text-gray-400 uppercase mb-1 block">GitHub Personal Access Token</label>
              <input
                type="password"
                value={githubToken}
                onChange={e => setGithubToken(e.target.value)}
                placeholder="ghp_..."
                className="w-full bg-black/50 border border-gray-700 text-gray-100 placeholder:text-gray-700 rounded px-3 py-2 text-sm font-mono outline-none focus:border-gray-500"
              />
              <p className="text-[9px] text-gray-600 mt-1 font-mono">Needs repo scope. <a href="https://github.com/settings/tokens/new" target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">Create token →</a></p>
            </div>
            <div>
              <label className="text-[10px] font-mono text-gray-400 uppercase mb-1 block">Repository Name</label>
              <input
                value={githubRepo}
                onChange={e => setGithubRepo(e.target.value)}
                placeholder={generatedApp?.name?.toLowerCase().replace(/\s+/g, '-') || 'my-app'}
                className="w-full bg-black/50 border border-gray-700 text-gray-100 placeholder:text-gray-700 rounded px-3 py-2 text-sm font-mono outline-none focus:border-gray-500"
              />
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={githubPrivate} onChange={e => setGithubPrivate(e.target.checked)} className="accent-gray-400" />
              <span className="text-[10px] font-mono text-gray-400">Private repository</span>
            </label>

            {githubResult && (
              <div className="p-3 bg-green-950/40 border border-green-800/50 rounded space-y-1.5">
                <p className="text-[10px] font-mono text-green-400 font-semibold">✓ Pushed successfully!</p>
                <div className="flex items-center gap-2">
                  <span className="text-[9px] font-mono text-gray-500 flex-1 truncate">{githubResult.repo_url}</span>
                  <button onClick={() => copyToClipboard(githubResult.repo_url)} className="text-gray-500 hover:text-gray-300"><Copy className="w-3 h-3" /></button>
                  <a href={githubResult.repo_url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300"><Link className="w-3 h-3" /></a>
                </div>
                <p className="text-[9px] font-mono text-gray-600">Enable GitHub Pages → Settings → Pages to get a live URL.</p>
              </div>
            )}

            <button onClick={pushToGithub} disabled={githubLoading || !githubToken || !githubRepo}
              className="w-full py-2.5 bg-gray-800 hover:bg-gray-700 border border-gray-600 text-white font-semibold rounded text-sm uppercase tracking-wide flex items-center justify-center gap-2 disabled:opacity-40 transition-colors">
              {githubLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Github className="w-4 h-4" />}
              {githubLoading ? 'Pushing...' : githubResult ? 'Push Again' : 'Push to GitHub'}
            </button>
          </div>
        </div>
      </div>
    )}

    {/* ── Vercel Deploy Modal ── */}
    {showVercelModal && (
      <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setShowVercelModal(false)}>
        <div className="bg-[#0d1117] border border-white/10 rounded-lg p-6 w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
          <div className="flex items-center gap-3 mb-5">
            <Globe className="w-6 h-6 text-white" />
            <h3 className="text-lg font-bold text-white">Deploy to Vercel</h3>
            <button onClick={() => setShowVercelModal(false)} className="ml-auto text-gray-600 hover:text-gray-300"><X className="w-5 h-5" /></button>
          </div>

          <div className="space-y-3">
            <div>
              <label className="text-[10px] font-mono text-gray-400 uppercase mb-1 block">Vercel Token</label>
              <input
                type="password"
                value={vercelToken}
                onChange={e => setVercelToken(e.target.value)}
                placeholder="your Vercel API token..."
                className="w-full bg-black/50 border border-white/10 text-gray-100 placeholder:text-gray-700 rounded px-3 py-2 text-sm font-mono outline-none focus:border-white/30"
              />
              <p className="text-[9px] text-gray-600 mt-1 font-mono">
                Get yours at <a href="https://vercel.com/account/tokens" target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">vercel.com/account/tokens →</a>
              </p>
            </div>

            {vercelResult && (
              <div className="p-3 bg-green-950/40 border border-green-800/50 rounded space-y-1.5">
                <p className="text-[10px] font-mono text-green-400 font-semibold">
                  ✓ Deployed! Status: {vercelResult.status}
                </p>
                <div className="flex items-center gap-2">
                  <span className="text-[9px] font-mono text-gray-400 flex-1 truncate">{vercelResult.deploy_url}</span>
                  <button onClick={() => copyToClipboard(vercelResult.deploy_url)} className="text-gray-500 hover:text-gray-300"><Copy className="w-3 h-3" /></button>
                  <a href={vercelResult.deploy_url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300"><Link className="w-3 h-3" /></a>
                </div>
                <p className="text-[9px] text-gray-600 font-mono">May take ~30s to be live if status is BUILDING.</p>
              </div>
            )}

            <button onClick={deployToVercel} disabled={vercelLoading || !vercelToken}
              className="w-full py-2.5 bg-white hover:bg-gray-100 text-black font-semibold rounded text-sm uppercase tracking-wide flex items-center justify-center gap-2 disabled:opacity-40 transition-colors">
              {vercelLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Globe className="w-4 h-4" />}
              {vercelLoading ? 'Deploying...' : vercelResult ? 'Redeploy' : 'Deploy to Vercel'}
            </button>
          </div>
        </div>
      </div>
    )}
    </>
  );
};

export default AppBuilder;
