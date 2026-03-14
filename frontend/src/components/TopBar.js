/**
 * components/TopBar.js
 * Minimal top bar — logo + status + profile dropdown.
 * All nav actions live in the profile menu.
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Settings, Github, Code2, User, LogOut, Moon, Sun,
  HelpCircle, ChevronDown, Terminal, GitBranch,
} from 'lucide-react';
import { useApp } from '../context/AppContext';

// ---------------------------------------------------------------------------
// Profile dropdown
// ---------------------------------------------------------------------------
function ProfileMenu({ onClose, setPage, serverStatus, theme, toggleTheme }) {
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
    if (window.confirm('Clear all local data and reset workspace?')) {
      localStorage.clear();
      sessionStorage.clear();
      window.location.reload();
    }
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
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-violet-500 to-cyan-500 flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
            M
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-slate-200 truncate">Mini Assistant</p>
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
  const { setPage, serverStatus, theme, toggleTheme } = useApp();
  const [profileOpen, setProfileOpen] = useState(false);

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
            M
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
          />
        )}
      </div>
    </header>
  );
}

export default TopBar;
