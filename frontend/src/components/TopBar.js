/**
 * components/TopBar.js
 * Minimal top bar — logo + status + profile dropdown.
 * All nav actions live in the profile menu.
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Settings, User, LogOut, Moon, Sun,
  HelpCircle, ChevronDown, RefreshCw, ShieldCheck, BarChart2, Menu,
  KeyRound, CreditCard, CheckCircle2, AlertCircle,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { api } from '../api/client';
import AvatarMedia from './AvatarMedia';


// ---------------------------------------------------------------------------
// StatusChip — shows subscription + API key state
// ---------------------------------------------------------------------------
function StatusChip() {
  const { isSubscribed: _isSubscribed, isAdmin, apiKeyVerified, setPage } = useApp();
  const isSubscribed = _isSubscribed || isAdmin;

  if (!isSubscribed) {
    return (
      <button
        onClick={() => setPage('pricing')}
        title="Subscribe to unlock AI execution"
        className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] hover:border-violet-500/40 transition-all group"
      >
        <AlertCircle className="w-3 h-3 text-amber-400 flex-shrink-0" />
        <span className="text-[11px] text-slate-400 group-hover:text-violet-300 transition-colors">Subscribe</span>
      </button>
    );
  }

  if (!apiKeyVerified) {
    return (
      <button
        onClick={() => setPage('settings')}
        title="Add your API key to start"
        className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] hover:border-amber-500/40 transition-all group"
      >
        <KeyRound className="w-3 h-3 text-amber-400 flex-shrink-0" />
        <span className="text-[11px] text-slate-400 group-hover:text-amber-300 transition-colors">Add API Key</span>
      </button>
    );
  }

  return (
    <div
      title="Subscribed & API key verified — ready to execute"
      className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/[0.04] border border-white/[0.06]"
    >
      <CheckCircle2 className="w-3 h-3 text-emerald-400 flex-shrink-0" />
      <span className="text-[11px] text-emerald-400">Active</span>
    </div>
  );
}

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
function ProfileMenu({ onClose, setPage, serverStatus, theme, toggleTheme, user, logout, avatar, isSubscribed, openUpgradeModal }) {
  const menuRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  const allOk = serverStatus.backend && serverStatus.openai;

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

  return (
    <div
      ref={menuRef}
      className="absolute right-0 top-full mt-2 w-[min(240px,calc(100vw-1rem))] rounded-xl bg-[#13131f] border border-white/10 shadow-2xl z-50 overflow-hidden"
    >
      {/* User info + status */}
      <div className="px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-cyan-500 flex items-center justify-center text-white text-sm font-bold flex-shrink-0 select-none overflow-hidden">
            {avatar
              ? <AvatarMedia src={avatar} className="w-full h-full object-cover" fallback={<span>{user?.name ? user.name[0].toUpperCase() : 'U'}</span>} />
              : (user?.name ? user.name[0].toUpperCase() : 'U')}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-slate-200 truncate">{user?.name || 'Mini Assistant'}</p>
            <p className="text-[10px] text-slate-600 font-mono truncate">{user?.email || ''}</p>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${serverStatus.backend ? 'bg-emerald-400' : 'bg-red-400 animate-pulse'}`} />
              <span className="text-[10px] font-mono text-slate-500">{serverStatus.backend ? 'All systems online' : 'Backend offline'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <div className="py-1.5 border-b border-white/5">
        <MenuItem icon={BarChart2} label="My Dashboard" onClick={() => go('dashboard')} />
        <MenuItem icon={User} label="My Profile" onClick={() => go('profile')} />
        <MenuItem icon={Settings} label="Settings" onClick={() => go('settings')} />
        <MenuItem icon={CreditCard} label="Plans & Pricing" onClick={() => go('pricing')} />
        {user?.role === 'admin' && (
          <MenuItem icon={ShieldCheck} label="Admin Dashboard" onClick={() => go('admin')} />
        )}
      </div>

      {/* Upgrade nudge — only for free users */}
      {!isSubscribed && (
        <div className="mx-3 my-2 px-3 py-2.5 rounded-xl bg-gradient-to-r from-violet-500/10 to-cyan-500/10 border border-violet-500/20">
          <p className="text-[10px] font-bold text-violet-300 mb-0.5">Free Plan</p>
          <p className="text-[10px] text-slate-500 mb-2">Unlock code, export &amp; deploy</p>
          <button
            onClick={() => { setPage('pricing'); onClose(); }}
            className="w-full py-1.5 rounded-lg bg-gradient-to-r from-violet-600 to-cyan-600 text-white text-[10px] font-bold hover:opacity-90 transition-all"
          >
            Upgrade Now →
          </button>
        </div>
      )}

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
          Sign out
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
  const { setPage, serverStatus, setServerStatus, theme, toggleTheme, user, logout, avatar, setMobileSidebarOpen, isSubscribed: _isSubscribed2, isAdmin: _isAdmin2, openUpgradeModal } = useApp(); // openUpgradeModal kept for ProfileMenu
  const isSubscribed = _isSubscribed2 || _isAdmin2;
  const [profileOpen, setProfileOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = useCallback(async () => {
    if (refreshing) return;
    setRefreshing(true);
    setServerStatus({ backend: null, openai: null });
    try {
      const data = await api.mainHealth();
      setServerStatus({
        backend: true,
        openai: data.openai === 'connected',
      });
    } catch {
      setServerStatus({ backend: false, openai: false });
    } finally {
      setRefreshing(false);
    }
  }, [refreshing, setServerStatus]);

  return (
    <header className="flex items-center h-14 px-3 md:px-5 border-b border-white/[0.06] bg-[#0b0d16] flex-shrink-0 z-20">

      {/* Hamburger — mobile only */}
      <button
        className="md:hidden p-2 mr-1 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors flex-shrink-0"
        onClick={() => setMobileSidebarOpen(true)}
        title="Open menu"
      >
        <Menu size={18} />
      </button>

      {/* Logo */}
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg overflow-hidden flex-shrink-0 bg-gradient-to-br from-cyan-400 to-violet-600">
          <img
            src="/Logo.png"
            alt="Mini Assistant"
            className="w-full h-full object-contain"
            onError={e => { e.target.style.display = 'none'; }}
          />
        </div>
        <span className="hidden sm:block text-[15px] font-semibold text-white tracking-tight">Mini Assistant</span>
      </div>

      {/* Status indicators — hidden on small screens */}
      <div className="hidden sm:flex items-center gap-3 ml-4 pl-4 border-l border-white/[0.06]">
        <StatusDot label="Backend" ok={serverStatus.backend} />
        <StatusDot label="Claude" ok={serverStatus.openai} />
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

      {/* Subscription status chip */}
      <div className="mr-3">
        <StatusChip />
      </div>

      {/* Profile button */}
      <div className="relative">
        <button
          onClick={() => setProfileOpen(v => !v)}
          className="flex items-center gap-1.5 group pl-2"
          title="Profile & settings"
        >
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-cyan-500
            flex items-center justify-center text-white text-xs font-bold
            group-hover:opacity-80 transition-opacity select-none overflow-hidden">
            {avatar
              ? <AvatarMedia src={avatar} className="w-full h-full object-cover" fallback={<span>{user?.name ? user.name[0].toUpperCase() : 'U'}</span>} />
              : (user?.name ? user.name[0].toUpperCase() : 'U')}
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
            avatar={avatar}
            isSubscribed={isSubscribed}
            openUpgradeModal={openUpgradeModal}
          />
        )}
      </div>
    </header>
  );
}

export default TopBar;
