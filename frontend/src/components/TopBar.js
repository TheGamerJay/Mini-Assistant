/**
 * components/TopBar.js
 * Top navigation header — Mini Assistant workspace design.
 */

import React, { useState, useRef, useEffect } from 'react';
import { Settings, CheckCircle2, Github, Code2, User, LogOut, Moon, HelpCircle, ChevronDown } from 'lucide-react';
import { useApp } from '../context/AppContext';

function ProfileMenu({ onClose, setPage }) {
  const menuRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  return (
    <div
      ref={menuRef}
      className="absolute right-0 top-full mt-2 w-56 rounded-xl bg-[#13131f] border border-white/10 shadow-2xl z-50 overflow-hidden"
    >
      {/* User info */}
      <div className="px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-violet-500 to-cyan-500 flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
            M
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-slate-200 truncate">Mini Assistant</p>
            <p className="text-[11px] text-slate-500 truncate">Local AI Workspace</p>
          </div>
        </div>
      </div>

      {/* Menu items */}
      <div className="py-1.5">
        <button
          onClick={() => { setPage('tool-profiles'); onClose(); }}
          className="w-full flex items-center gap-3 px-4 py-2 text-sm text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-colors"
        >
          <User size={14} />
          Project Profiles
        </button>
        <button
          onClick={() => { setPage('settings'); onClose(); }}
          className="w-full flex items-center gap-3 px-4 py-2 text-sm text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-colors"
        >
          <Settings size={14} />
          Settings
        </button>
        <button
          className="w-full flex items-center gap-3 px-4 py-2 text-sm text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-colors"
        >
          <HelpCircle size={14} />
          Help & Docs
        </button>
        <button
          className="w-full flex items-center gap-3 px-4 py-2 text-sm text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-colors"
        >
          <Moon size={14} />
          Theme
        </button>
      </div>

      <div className="border-t border-white/5 py-1.5">
        <button
          className="w-full flex items-center gap-3 px-4 py-2 text-sm text-red-400/70 hover:text-red-400 hover:bg-red-500/5 transition-colors"
        >
          <LogOut size={14} />
          Sign Out
        </button>
      </div>
    </div>
  );
}

function TopBar() {
  const { setPage, serverStatus } = useApp();
  const [profileOpen, setProfileOpen] = useState(false);
  const allOk = serverStatus.backend && serverStatus.ollama;

  return (
    <header className="flex items-center h-14 px-5 border-b border-white/[0.06] bg-[#0b0d16] flex-shrink-0 z-20 gap-3">

      {/* Logo */}
      <div className="flex items-center gap-2.5 mr-4">
        <div className="w-8 h-8 rounded-lg overflow-hidden flex-shrink-0 bg-gradient-to-br from-cyan-400 to-violet-600">
          <img src="/Logo.png" alt="Mini Assistant" className="w-full h-full object-contain"
            onError={e => { e.target.style.display = 'none'; }} />
        </div>
        <span className="text-[15px] font-semibold text-white tracking-tight">Mini Assistant</span>
      </div>

      {/* Slash command pills */}
      <div className="flex items-center gap-1.5">
        <button className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-mono
          bg-emerald-500/10 hover:bg-emerald-500/15 border border-emerald-500/20
          text-emerald-400 hover:text-emerald-300 transition-colors">
          <CheckCircle2 size={11} />
          /context
        </button>
        <button className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-mono
          bg-white/[0.05] hover:bg-white/[0.08] border border-white/[0.08]
          text-slate-400 hover:text-slate-300 transition-colors">
          ? /help
        </button>
        <button
          onClick={() => setPage('settings')}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-mono
            bg-white/[0.05] hover:bg-white/[0.08] border border-white/[0.08]
            text-slate-400 hover:text-slate-300 transition-colors">
          <Settings size={11} />
          Settings
        </button>
      </div>

      {/* Status */}
      {serverStatus.backend !== null && (
        <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-[10px] font-mono border ${allOk
            ? 'bg-emerald-500/8 border-emerald-500/15 text-emerald-400/70'
            : 'bg-red-500/8 border-red-500/15 text-red-400/70'}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${allOk ? 'bg-emerald-400' : 'bg-red-400 animate-pulse'}`} />
          {allOk ? 'online' : 'offline'}
        </span>
      )}

      <div className="flex-1" />

      {/* Right integrations */}
      <div className="flex items-center gap-2">
        <button className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-[12px] font-medium
          bg-violet-500/10 hover:bg-violet-500/15 border border-violet-500/20
          text-violet-300 hover:text-violet-200 transition-colors">
          <Github size={13} />
          Connect GitHub
        </button>
        <button className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-[12px] font-medium
          bg-cyan-500/10 hover:bg-cyan-500/15 border border-cyan-500/20
          text-cyan-300 hover:text-cyan-200 transition-colors">
          <Code2 size={13} />
          Connect VS Code
        </button>

        {/* Profile button */}
        <div className="relative ml-1">
          <button
            onClick={() => setProfileOpen(v => !v)}
            className="flex items-center gap-1 group"
            title="Profile"
          >
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-cyan-500
              flex items-center justify-center text-white text-xs font-bold
              hover:opacity-80 transition-opacity select-none">
              M
            </div>
            <ChevronDown size={11} className={`text-slate-600 group-hover:text-slate-400 transition-all ${profileOpen ? 'rotate-180' : ''}`} />
          </button>

          {profileOpen && (
            <ProfileMenu onClose={() => setProfileOpen(false)} setPage={setPage} />
          )}
        </div>
      </div>
    </header>
  );
}

export default TopBar;
