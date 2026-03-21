/**
 * layout/Sidebar.js
 * ChatGPT-style collapsible left sidebar.
 * 260 px expanded · 64 px collapsed (icon-only)
 */

import React, { useState, useCallback, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import {
  ChevronLeft,
  Menu,
  Plus,
  Search,
  Image,
  FolderOpen,
  MessageSquare,
  Wrench,
  Settings,
  ChevronDown,
  ChevronRight,
  Pencil,
  Trash2,
  Check,
  X,
  Pin,
  BookMarked,
  // Tool icons
  Code,
  Terminal,
  Activity,
  Layers,
  Shield,
  GitBranch,
  Play,
  Database,
  Package,
  Rocket,
  Train,
  Bug,
  FlaskConical,
  Brain,
  ListTodo,
  Mic,
  Zap,
  Globe,
  FileSearch,
  Wand2,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------
const TOOLS = [
  { id: 'appbuilder', label: 'Build (Workspace)', icon: Wand2, page: 'chat' },
  { id: 'tasks', label: 'Task Monitor', icon: ListTodo },
  { id: 'agent', label: 'Agent Pipeline', icon: Brain },
  { id: 'codereview', label: 'Code Review', icon: Shield },
  { id: 'coderunner', label: 'Code Runner', icon: Play },
  { id: 'apitester', label: 'API Tester', icon: Zap },
  { id: 'tester', label: 'Tester Agent', icon: FlaskConical },
  { id: 'fixloop', label: 'Fix Loop', icon: Bug },
  { id: 'postgres', label: 'PostgreSQL', icon: Database },
  { id: 'redis', label: 'Redis', icon: Activity },
  { id: 'railway', label: 'Railway', icon: Train },
  { id: 'database', label: 'DB Designer', icon: Layers },
  { id: 'git', label: 'Git & GitHub', icon: GitBranch },
  { id: 'packages', label: 'Packages', icon: Package },
  { id: 'env', label: 'Env Vars', icon: Code },
  { id: 'snippets', label: 'Snippets', icon: BookMarked },
  { id: 'devtools', label: 'Dev Tools', icon: Rocket },
  { id: 'advanced', label: 'Advanced', icon: Settings },
  { id: 'files', label: 'Files', icon: FolderOpen },
  { id: 'terminal', label: 'Terminal', icon: Terminal },
  { id: 'websearch', label: 'Web Search', icon: Globe },
  { id: 'codesearch', label: 'Code Search', icon: FileSearch },
  { id: 'voice', label: 'Voice', icon: Mic },
];

// ---------------------------------------------------------------------------
// SidebarSection
// ---------------------------------------------------------------------------
function SidebarSection({ icon: Icon, label, collapsed, defaultOpen = true, action, children }) {
  const [open, setOpen] = useState(defaultOpen);

  if (collapsed) {
    return (
      <div className="mb-1">
        <button
          className="w-full flex justify-center items-center h-9 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors"
          title={label}
          onClick={() => setOpen((v) => !v)}
        >
          <Icon size={16} />
        </button>
        {open && <div className="px-1">{children}</div>}
      </div>
    );
  }

  return (
    <div className="mb-1">
      <button
        className="w-full flex items-center justify-between px-2 py-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors group"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <Icon size={13} />
          <span className="text-[10px] font-mono uppercase tracking-widest">{label}</span>
        </div>
        <div className="flex items-center gap-1">
          {action && (
            <span
              onClick={(e) => { e.stopPropagation(); action.fn(); }}
              className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-white/10 transition-all"
            >
              {action.icon}
            </span>
          )}
          {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </div>
      </button>
      {open && <div>{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChatRow
// ---------------------------------------------------------------------------
function ChatRow({ chat, active, collapsed, onSelect, onRename, onDelete, onPin }) {
  const [editing, setEditing] = useState(false);
  const [editVal, setEditVal] = useState(chat.title);
  const [hovered, setHovered] = useState(false);

  const commitRename = () => {
    if (editVal.trim()) onRename(chat.id, editVal.trim());
    setEditing(false);
  };

  if (collapsed) {
    return (
      <button
        className={`w-full flex justify-center items-center h-8 rounded-lg mb-0.5 transition-colors
          ${active ? 'bg-cyan-500/10 text-cyan-400' : 'text-slate-500 hover:bg-white/5 hover:text-slate-300'}`}
        onClick={() => onSelect(chat.id)}
        title={chat.title}
      >
        <MessageSquare size={14} />
      </button>
    );
  }

  const relativeTime = chat.updatedAt
    ? new Date(chat.updatedAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    : null;

  return (
    <div
      className={`group relative flex items-center gap-2 px-2 py-1.5 rounded-lg mb-0.5 cursor-pointer transition-colors border-l-2
        ${active
          ? 'bg-cyan-500/10 border-cyan-400 text-slate-100'
          : 'text-slate-400 hover:bg-white/5 hover:text-slate-200 border-transparent'}`}
      onClick={() => !editing && onSelect(chat.id)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {chat.pinned
        ? <Pin size={11} className="flex-shrink-0 text-amber-500/60" />
        : <MessageSquare size={13} className="flex-shrink-0 text-slate-600" />}
      {editing ? (
        <div className="flex items-center gap-1 flex-1 min-w-0" onClick={(e) => e.stopPropagation()}>
          <input
            className="flex-1 min-w-0 bg-transparent text-xs text-slate-200 outline-none border-b border-cyan-500/50"
            value={editVal}
            onChange={(e) => setEditVal(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setEditing(false); }}
            autoFocus
          />
          <button onClick={commitRename} className="text-emerald-400 hover:text-emerald-300"><Check size={11} /></button>
          <button onClick={() => setEditing(false)} className="text-slate-500 hover:text-slate-300"><X size={11} /></button>
        </div>
      ) : (
        <>
          <div className="flex-1 min-w-0">
            <span className="block text-xs truncate">{chat.title}</span>
            {relativeTime && <span className="block text-[10px] text-slate-600 truncate">{relativeTime}</span>}
          </div>
          {hovered && (
            <div className="flex items-center gap-0.5 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
              <button
                className={`p-0.5 rounded hover:bg-white/10 transition-colors ${chat.pinned ? 'text-amber-400' : 'text-slate-500 hover:text-amber-400'}`}
                onClick={() => onPin(chat.id)}
                title={chat.pinned ? 'Unpin' : 'Pin'}
              >
                <Pin size={10} />
              </button>
              <button
                className="p-0.5 rounded hover:bg-white/10 text-slate-500 hover:text-slate-300"
                onClick={() => { setEditVal(chat.title); setEditing(true); }}
              >
                <Pencil size={11} />
              </button>
              <button
                className="p-0.5 rounded hover:bg-red-500/20 text-slate-500 hover:text-red-400"
                onClick={() => onDelete(chat.id)}
              >
                <Trash2 size={11} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProjectRow
// ---------------------------------------------------------------------------
function ProjectRow({ project, chats, activeChatId, collapsed, onSelectChat, onRenameProject, onDeleteProject }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editVal, setEditVal] = useState(project.name);
  const [hovered, setHovered] = useState(false);

  const commitRename = () => {
    if (editVal.trim()) onRenameProject(project.id, editVal.trim());
    setEditing(false);
  };

  if (collapsed) {
    return (
      <button className="w-full flex justify-center items-center h-8 rounded-lg mb-0.5 text-slate-500 hover:bg-white/5 hover:text-slate-300" title={project.name}>
        <FolderOpen size={14} />
      </button>
    );
  }

  return (
    <div className="mb-0.5">
      <div
        className="group flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer hover:bg-white/5 transition-colors"
        onClick={() => setOpen((v) => !v)}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        {open ? <ChevronDown size={11} className="text-slate-500" /> : <ChevronRight size={11} className="text-slate-500" />}
        <FolderOpen size={13} className="text-amber-500/60 flex-shrink-0" />
        {editing ? (
          <div className="flex items-center gap-1 flex-1 min-w-0" onClick={(e) => e.stopPropagation()}>
            <input
              className="flex-1 min-w-0 bg-transparent text-xs text-slate-200 outline-none border-b border-cyan-500/50"
              value={editVal}
              onChange={(e) => setEditVal(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setEditing(false); }}
              autoFocus
            />
            <button onClick={commitRename} className="text-emerald-400"><Check size={11} /></button>
            <button onClick={() => setEditing(false)} className="text-slate-500"><X size={11} /></button>
          </div>
        ) : (
          <>
            <span className="flex-1 min-w-0 text-xs text-slate-400 truncate">
              {project.name}
              {chats.length > 0 && <span className="ml-1 text-slate-600">({chats.length})</span>}
            </span>
            {hovered && (
              <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                <button className="p-0.5 rounded hover:bg-white/10 text-slate-500 hover:text-slate-300" onClick={() => { setEditVal(project.name); setEditing(true); }}><Pencil size={11} /></button>
                <button className="p-0.5 rounded hover:bg-red-500/20 text-slate-500 hover:text-red-400" onClick={() => onDeleteProject(project.id)}><Trash2 size={11} /></button>
              </div>
            )}
          </>
        )}
      </div>
      {open && chats.map((chat) => (
        <div key={chat.id} className="pl-5">
          <div
            className={`flex items-center gap-2 px-2 py-1 rounded-lg mb-0.5 cursor-pointer text-xs transition-colors
              ${activeChatId === chat.id ? 'bg-cyan-500/10 border border-cyan-500/20 text-slate-100' : 'text-slate-500 hover:bg-white/5 hover:text-slate-300'}`}
            onClick={() => onSelectChat(chat.id)}
          >
            <MessageSquare size={11} className="flex-shrink-0" />
            <span className="truncate">{chat.title}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PromptTemplateRow
// ---------------------------------------------------------------------------
function PromptTemplateRow({ template, collapsed, onUse, onDelete }) {
  const [hovered, setHovered] = useState(false);

  if (collapsed) {
    return (
      <button
        className="w-full flex justify-center items-center h-8 rounded-lg mb-0.5 text-slate-500 hover:bg-white/5 hover:text-cyan-400 transition-colors"
        title={template.title}
        onClick={() => onUse(template.text)}
      >
        <BookMarked size={13} />
      </button>
    );
  }

  return (
    <div
      className="group flex items-center gap-2 px-2 py-1.5 rounded-lg mb-0.5 cursor-pointer hover:bg-white/5 transition-colors"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => onUse(template.text)}
    >
      <BookMarked size={11} className="flex-shrink-0 text-violet-400/60" />
      <div className="flex-1 min-w-0">
        <span className="block text-xs text-slate-400 truncate">{template.title}</span>
        <span className="block text-[10px] text-slate-600 truncate">{template.text}</span>
      </div>
      {hovered && (
        <button
          className="p-0.5 rounded hover:bg-red-500/20 text-slate-600 hover:text-red-400 flex-shrink-0"
          onClick={(e) => { e.stopPropagation(); onDelete(template.id); }}
          title="Delete template"
        >
          <Trash2 size={10} />
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------
function Sidebar() {
  const {
    sidebarCollapsed,
    toggleSidebar,
    page,
    setPage,
    newChat,
    chats,
    activeChatId,
    selectChat,
    deleteChat,
    renameChat,
    togglePinChat,
    projects,
    newProject,
    deleteProject,
    renameProject,
    images,
    serverStatus,
    promptTemplates,
    addPromptTemplate,
    deletePromptTemplate,
    firePendingTemplate,
    credits,
    plan,
    isSubscribed,
  } = useApp();

  const [searchQuery, setSearchQuery] = useState('');

  const handleNewProject = useCallback(() => {
    const name = window.prompt('Project name:');
    if (name && name.trim()) newProject(name.trim());
  }, [newProject]);

  const handleAddTemplate = useCallback(() => {
    const title = window.prompt('Template name (e.g. "Write a Bachata song"):');
    if (!title?.trim()) return;
    const text = window.prompt('Template text (the prompt that will fill the input):');
    if (!text?.trim()) return;
    addPromptTemplate(title, text);
  }, [addPromptTemplate]);

  const filteredChats = chats.filter((c) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    if (c.title.toLowerCase().includes(q)) return true;
    return (c.messages || []).some(m => m.content?.toLowerCase().includes(q));
  });

  const pinnedChats = filteredChats.filter((c) => c.pinned)
    .sort((a, b) => b.updatedAt - a.updatedAt);

  const unassignedChats = filteredChats.filter((c) => !c.projectId && !c.pinned)
    .sort((a, b) => b.updatedAt - a.updatedAt);

  const ollamaUp = serverStatus.ollama === true;
  const backendUp = serverStatus.backend === true;
  const isOnline = ollamaUp && backendUp;
  const statusDot = serverStatus.backend === null
    ? 'bg-slate-500 animate-pulse'
    : isOnline ? 'bg-cyan-400' : 'bg-red-400';

  return (
    <div
      className={`flex flex-col bg-[#0a0a0f] border-r border-white/5 transition-all duration-200 ease-in-out flex-shrink-0 ${sidebarCollapsed ? 'w-16' : 'w-[260px]'}`}
      style={{ height: '100vh' }}
    >
      {/* ---- Brand + toggle ---- */}
      <div className={`flex items-center h-14 flex-shrink-0 px-3 border-b border-white/5 ${sidebarCollapsed ? 'flex-col justify-center gap-1' : 'justify-between'}`}>
        {sidebarCollapsed ? (
          <>
            <div className="w-7 h-7 rounded-lg overflow-hidden flex-shrink-0 bg-gradient-to-br from-cyan-400 to-violet-600">
              <img src="/Logo.png" alt="Mini Assistant" className="w-full h-full object-contain" onError={e => { e.target.style.display = 'none'; }} />
            </div>
            <button onClick={toggleSidebar} className="p-1 rounded-lg text-slate-600 hover:text-slate-300 hover:bg-white/5 transition-colors" title="Expand sidebar">
              <Menu size={13} />
            </button>
          </>
        ) : (
          <>
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-7 h-7 rounded-lg overflow-hidden flex-shrink-0 bg-gradient-to-br from-cyan-400 to-violet-600">
                <img src="/Logo.png" alt="Mini Assistant" className="w-full h-full object-contain" onError={e => { e.target.style.display = 'none'; }} />
              </div>
              <span className="text-sm font-semibold text-slate-100 truncate">Mini Assistant</span>
            </div>
            <button onClick={toggleSidebar} className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors flex-shrink-0" title="Collapse sidebar">
              <ChevronLeft size={16} />
            </button>
          </>
        )}
      </div>

      {/* ---- New Chat ---- */}
      <div className={`px-2 pt-3 pb-2 flex-shrink-0 ${sidebarCollapsed ? 'flex justify-center' : ''}`}>
        <button
          onClick={() => { newChat(); setPage('chat'); }}
          className={`flex items-center gap-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/8 hover:border-white/15 text-slate-300 hover:text-white transition-all text-sm font-medium
            ${sidebarCollapsed ? 'p-2' : 'w-full px-3 py-2'}`}
          title="New Chat"
        >
          <Plus size={16} className="flex-shrink-0" />
          {!sidebarCollapsed && <span>New Chat</span>}
        </button>
      </div>

      {/* ---- Search ---- */}
      {!sidebarCollapsed && (
        <div className="px-2 pb-2 flex-shrink-0">
          <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-white/5 border border-white/5">
            <Search size={12} className="text-slate-600 flex-shrink-0" />
            <input
              type="text"
              placeholder="Search chats…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 bg-transparent text-xs text-slate-300 placeholder-slate-600 outline-none"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery('')} className="text-slate-600 hover:text-slate-400">
                <X size={10} />
              </button>
            )}
          </div>
        </div>
      )}

      {/* ---- Scrollable nav ---- */}
      <div className="flex-1 overflow-y-auto px-2 py-1 space-y-1">

        {/* Images */}
        <SidebarSection icon={Image} label="Images" collapsed={sidebarCollapsed} defaultOpen={true}>
          {images.length === 0 ? (
            !sidebarCollapsed && <p className="text-[10px] text-slate-600 px-2 py-2">No images yet</p>
          ) : (
            <div className={`${sidebarCollapsed ? 'flex flex-col gap-1 px-1' : 'grid grid-cols-3 gap-1 px-2 py-1'}`}>
              {images.slice(0, 9).map((img) => (
                <button
                  key={img.id}
                  onClick={() => setPage('images')}
                  title={img.prompt}
                  className="rounded-md overflow-hidden border border-white/10 hover:border-cyan-500/30 transition-colors aspect-square bg-black/40"
                  style={sidebarCollapsed ? { width: 36, height: 36 } : {}}
                >
                  {img.thumb
                    ? <img src={img.thumb} alt={img.prompt} className="w-full h-full object-cover" />
                    : <div className="w-full h-full flex items-center justify-center text-slate-600"><Image size={10} /></div>}
                </button>
              ))}
            </div>
          )}
        </SidebarSection>

        {/* Pinned Chats */}
        {(pinnedChats.length > 0 || !sidebarCollapsed) && (
          <SidebarSection icon={Pin} label="Pinned" collapsed={sidebarCollapsed} defaultOpen={true}>
            {pinnedChats.length === 0 && !sidebarCollapsed && (
              <p className="text-[10px] text-slate-600 px-2 py-1">No pinned chats</p>
            )}
            {pinnedChats.map((chat) => (
              <ChatRow
                key={chat.id}
                chat={chat}
                active={activeChatId === chat.id}
                collapsed={sidebarCollapsed}
                onSelect={selectChat}
                onRename={renameChat}
                onDelete={deleteChat}
                onPin={togglePinChat}
              />
            ))}
          </SidebarSection>
        )}

        {/* Projects */}
        <SidebarSection
          icon={FolderOpen}
          label="Projects"
          collapsed={sidebarCollapsed}
          defaultOpen={true}
          action={{ fn: handleNewProject, icon: <Plus size={11} /> }}
        >
          {projects.length === 0 && !sidebarCollapsed && (
            <p className="text-[10px] text-slate-600 px-2 py-1">No projects yet</p>
          )}
          {projects.map((proj) => {
            const projChats = chats.filter((c) => c.projectId === proj.id).sort((a, b) => b.updatedAt - a.updatedAt);
            return (
              <ProjectRow
                key={proj.id}
                project={proj}
                chats={projChats}
                activeChatId={activeChatId}
                collapsed={sidebarCollapsed}
                onSelectChat={selectChat}
                onRenameProject={renameProject}
                onDeleteProject={deleteProject}
              />
            );
          })}
        </SidebarSection>

        {/* Your Chats */}
        <SidebarSection icon={MessageSquare} label="Your Chats" collapsed={sidebarCollapsed} defaultOpen={true}>
          {unassignedChats.length === 0 && !sidebarCollapsed && (
            <p className="text-[10px] text-slate-600 px-2 py-1">No chats yet</p>
          )}
          {unassignedChats.map((chat) => (
            <ChatRow
              key={chat.id}
              chat={chat}
              active={activeChatId === chat.id}
              collapsed={sidebarCollapsed}
              onSelect={selectChat}
              onRename={renameChat}
              onDelete={deleteChat}
              onPin={togglePinChat}
            />
          ))}
        </SidebarSection>

        {/* Prompt Templates */}
        <SidebarSection
          icon={BookMarked}
          label="Templates"
          collapsed={sidebarCollapsed}
          defaultOpen={false}
          action={{ fn: handleAddTemplate, icon: <Plus size={11} /> }}
        >
          {promptTemplates.length === 0 && !sidebarCollapsed && (
            <p className="text-[10px] text-slate-600 px-2 py-1">No templates — click + to add</p>
          )}
          {promptTemplates.map((t) => (
            <PromptTemplateRow
              key={t.id}
              template={t}
              collapsed={sidebarCollapsed}
              onUse={(text) => { firePendingTemplate(text); setPage('chat'); }}
              onDelete={deletePromptTemplate}
            />
          ))}
        </SidebarSection>

        {/* Tools */}
        <SidebarSection icon={Wrench} label="Tools" collapsed={sidebarCollapsed} defaultOpen={false}>
          {TOOLS.map(({ id, label, icon: Icon, page: customPage }) => {
            const targetPage = customPage || `tool-${id}`;
            const isActive = customPage ? page === customPage : page === `tool-${id}`;
            return (
              <button
                key={id}
                onClick={() => setPage(targetPage)}
                title={label}
                className={`w-full flex items-center gap-2 rounded-lg px-2 py-1.5 mb-0.5 text-xs transition-colors
                  ${isActive
                    ? 'bg-cyan-500/10 border-l-2 border-cyan-400 text-cyan-300 pl-1.5'
                    : 'text-slate-500 hover:bg-white/5 hover:text-slate-300 border-l-2 border-transparent'}
                  ${sidebarCollapsed ? 'justify-center' : ''}`}
              >
                <Icon size={13} className="flex-shrink-0" />
                {!sidebarCollapsed && <span className="truncate">{label}</span>}
              </button>
            );
          })}
        </SidebarSection>
      </div>

      {/* ---- Bottom fixed area ---- */}
      <div className="flex-shrink-0 border-t border-white/5 px-2 py-3 space-y-1">
        {/* Credits badge */}
        {!isSubscribed && credits !== null && (
          <div
            title={sidebarCollapsed ? `${credits} Mini Credits remaining` : undefined}
            className={`flex items-center gap-2 px-2 py-1.5 rounded-lg ${sidebarCollapsed ? 'justify-center' : ''}`}
          >
            <span className="text-[13px] flex-shrink-0">⚡</span>
            {!sidebarCollapsed && (
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-[11px] font-mono text-slate-400">{credits} Mini Credits</span>
                  {credits === 0 && (
                    <span className="text-[10px] text-amber-400 font-medium">Upgrade</span>
                  )}
                </div>
                <div className="h-1 rounded-full bg-white/10 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${credits > 5 ? 'bg-cyan-500' : credits > 2 ? 'bg-amber-500' : 'bg-red-500'}`}
                    style={{ width: `${Math.min(100, (credits / 10) * 100)}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        )}
        {isSubscribed && (
          <div className={`flex items-center gap-2 px-2 py-1.5 rounded-lg ${sidebarCollapsed ? 'justify-center' : ''}`}>
            <span className="text-[13px] flex-shrink-0">✦</span>
            {!sidebarCollapsed && <span className="text-[11px] font-mono text-cyan-400 capitalize">{plan}</span>}
          </div>
        )}

        <div className={`flex items-center gap-2 px-2 py-1.5 rounded-lg ${sidebarCollapsed ? 'justify-center' : ''}`}>
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${statusDot}`} />
          {!sidebarCollapsed && <span className="text-[11px] font-mono text-slate-500">Local AI</span>}
        </div>
        <button
          onClick={() => setPage('settings')}
          title="Settings"
          className={`w-full flex items-center gap-2 rounded-lg px-2 py-1.5 text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors ${sidebarCollapsed ? 'justify-center' : ''}`}
        >
          <Settings size={15} />
          {!sidebarCollapsed && <span className="text-xs">Settings</span>}
        </button>
      </div>
    </div>
  );
}

export default Sidebar;
