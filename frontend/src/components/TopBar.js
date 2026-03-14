/**
 * components/TopBar.js
 * Minimal top bar — logo + status + profile dropdown.
 * All nav actions live in the profile menu.
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Settings, Github, User, LogOut, Moon, Sun,
  HelpCircle, ChevronDown, Terminal, GitBranch, RefreshCw,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { api } from '../api/client';

// ---------------------------------------------------------------------------
// Status dot
// ---------------------------------------------------------------------------
function StatusDot({ label, ok }) {
  const color = ok === null || ok === undefined
    ? 'bg-slate-600'
    : ok ? 'bg-emerald-400' : 'bg-red-400 animate-pulse';
  return (
    <div className="flex items-center gap-1">
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${color}`} />
      <span className="text-[10px] font-mono text-slate-500">{label}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Profile dropdown
// ---------------------------------------------------------------------------
function ProfileMenu({ onClose, setPage, serverStatus, theme, toggleTheme, user, logout }) {
  const menuRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  const allOk = serverStatus.backend && serverStatus.ollama;

  const go = (page) => { setPage(page); onClose(); };

  const handleSignOut = () => {
    onClose();
    logout();
  };

  const handleTheme = () => {
    toggleTheme();
    onClose();
  };

  const handleHelp = () => {
    window.open('https://github.com/TheGamerJay/Mini-Assistant', '_blank', 'noopener');
    onClose();
  };

  const handleGitHub = () => {
    window.open('https://github.com', '_blank', 'noopener');
    onClose();
  };

  const handleVSCode = () => {
    window.open('vscode://file/', '_blank', 'noopener');
    onClose();
  };

  return (
    <div
      ref={menuRef}
      className="absolute right-0 top-full mt-2 w-60 rounded-xl bg-[#13131f] border border-white/10 shadow-2xl z-50 overflow-hidden"
    >
      {/* User info + status */}
      <div className="px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-violet-500 to-cyan-500 flex items-center justify-center text-white text-sm font-bold flex-shrink-0 select-none">
            {user?.name ? user.name[0].toUpperCase() : 'U'}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-slate-200 truncate">{user?.name || 'Mini Assistant'}</p>
            <p className="text-[10px] text-slate-600 font-mono truncate">{user?.email || ''}</p>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${allOk ? 'bg-emerald-400' : 'bg-red-400 animate-pulse'}`} />
              <span className="text-[10px] font-mono text-slate-500">{allOk ? 'All systems online' : 'Backend offline'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <div className="py-1.5 border-b border-white/5">
        <MenuItem icon={User} label="Project Profiles" onClick={() => go('tool-profiles')} />
        <MenuItem icon={Settings} label="Settings" onClick={() => go('settings')} />
        <MenuItem icon={Terminal} label="/context — Scan project" onClick={() => go('chat')} hint="slash" />
        <MenuItem icon={HelpCircle} label="/help — All commands" onClick={() => { go('chat'); }} hint="slash" />
      </div>

      {/* Integrations */}
      <div className="py-1.5 border-b border-white/5">
        <p className="px-4 py-1 text-[10px] font-mono uppercase tracking-widest text-slate-600">Integrations</p>
        <MenuItem icon={Github} label="Connect GitHub" onClick={handleGitHub} />
        <MenuItem icon={GitBranch} label="Connect VS Code" onClick={handleVSCode} />
      </div>

      {/* Preferences + sign out */}
      <div className="py-1.5">
        <button
          onClick={handleTheme}
          className="w-full flex items-center justify-between px-4 py-2 text-sm text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-colors"
        >
          <span className="flex items-center gap-3">
            {theme === 'dark' ? <Moon size={14} /> : <Sun size={14} />}
            Theme
          </span>
          <span className="text-[10px] font-mono text-slate-600 bg-white/5 px-2 py-0.5 rounded">
            {theme === 'dark' ? 'Dark' : 'Light'}
          </span>
        </button>
        <MenuItem icon={HelpCircle} label="Help & Docs" onClick={handleHelp} />
      </div>

      <div className="border-t border-white/5 py-1.5">
        <button
          onClick={handleSignOut}
          className="w-full flex items-center gap-3 px-4 py-2 text-sm text-red-400/70 hover:text-red-400 hover:bg-red-500/5 transition-colors"
        >
          <LogOut size={14} />
          Clear & Reset Workspace
        </button>
      </div>
    </div>
  );
}

function MenuItem({ icon: Icon, label, onClick, hint }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-4 py-2 text-sm text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-colors"
    >
      <Icon size={14} className="flex-shrink-0" />
      <span className="flex-1 text-left truncate">{label}</span>
      {hint === 'slash' && (
        <span className="text-[9px] font-mono text-cyan-600 bg-cyan-500/10 px-1.5 py-0.5 rounded">cmd</span>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// TopBar
// ---------------------------------------------------------------------------
function TopBar() {
  const { setPage, serverStatus, setServerStatus, theme, toggleTheme, user, logout } = useApp();
  const [profileOpen, setProfileOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = useCallback(async () => {
    if (refreshing) return;
    setRefreshing(true);
    setServerStatus({ backend: null, ollama: null, comfyui: null });
    try {
      const data = await api.mainHealth();
      setServerStatus({
        backend: true,
        ollama: data.ollama === 'connected',
        comfyui: data.comfyui === 'connected',
      });
    } catch {
      setServerStatus({ backend: false, ollama: false, comfyui: false });
    } finally {
      setRefreshing(false);
    }
  }, [refreshing, setServerStatus]);

  return (
    <header className="flex items-center h-14 px-5 border-b border-white/[0.06] bg-[#0b0d16] flex-shrink-0 z-20">

      {/* Logo */}
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg overflow-hidden flex-shrink-0 bg-gradient-to-br from-cyan-400 to-violet-600">
          <img
            src="/Logo.png"
            alt="Mini Assistant"
            className="w-full h-full object-contain"
            onError={e => { e.target.style.display = 'none'; }}
          />
        </div>
        <span className="text-[15px] font-semibold text-white tracking-tight">Mini Assistant</span>
      </div>

      {/* Status indicators */}
      <div className="flex items-center gap-3 ml-5 pl-5 border-l border-white/[0.06]">
        <StatusDot label="Backend" ok={serverStatus.backend} />
        <StatusDot label="Mini" ok={serverStatus.ollama} />
        <StatusDot label="ComfyUI" ok={serverStatus.comfyui} />
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          title="Refresh status"
          className="ml-1 p-1 rounded text-slate-600 hover:text-slate-400 transition-colors disabled:opacity-40"
        >
          <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="flex-1" />

      {/* Profile button */}
      <div className="relative">
        <button
          onClick={() => setProfileOpen(v => !v)}
          className="flex items-center gap-1.5 group pl-2"
          title="Profile & settings"
        >
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-cyan-500
            flex items-center justify-center text-white text-xs font-bold
            group-hover:opacity-80 transition-opacity select-none">
            {user?.name ? user.name[0].toUpperCase() : 'U'}
          </div>
          <ChevronDown
            size={12}
            className={`text-slate-600 group-hover:text-slate-400 transition-transform ${profileOpen ? 'rotate-180' : ''}`}
          />
        </button>

        {profileOpen && (
          <ProfileMenu
            onClose={() => setProfileOpen(false)}
            setPage={setPage}
            serverStatus={serverStatus}
            theme={theme}
            toggleTheme={toggleTheme}
            user={user}
            logout={logout}
          />
        )}
      </div>
    </header>
  );
}

export default TopBar;
