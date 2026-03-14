/**
 * pages/ProfilePage.js
 * Full-screen profile management page.
 * Sections: avatar upload, display name, change password, terms, delete account.
 */

import React, { useState, useRef } from 'react';
import {
  Camera, Check, AlertTriangle, Lock, User, Trash2,
  ChevronLeft, Eye, EyeOff, FileText, LogOut,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// TermsModal (inline)
// ---------------------------------------------------------------------------
function TermsModal({ onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-lg max-h-[80vh] flex flex-col rounded-2xl bg-[#0f0f1a] border border-white/10 shadow-2xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/8">
          <h2 className="text-base font-semibold text-slate-100">Terms & Privacy Policy</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors text-lg leading-none">✕</button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5 text-sm text-slate-400 space-y-4 leading-relaxed">
          <section><h3 className="text-slate-200 font-semibold mb-1">1. Local-Only Storage</h3>
            <p>All your data (chats, images, settings, account credentials) is stored exclusively in your browser's localStorage. No data is sent to any third-party server.</p></section>
          <section><h3 className="text-slate-200 font-semibold mb-1">2. Authentication</h3>
            <p>Passwords are hashed with SHA-256 before storage. Mini Assistant never stores plaintext passwords. Resetting a forgotten password requires deleting and re-creating your account.</p></section>
          <section><h3 className="text-slate-200 font-semibold mb-1">3. AI Outputs</h3>
            <p>Mini Assistant uses local AI models. Outputs may be inaccurate, incomplete, or inappropriate. Always review AI-generated code, text, and images before use in production.</p></section>
          <section><h3 className="text-slate-200 font-semibold mb-1">4. Image Generation</h3>
            <p>Generated images are stored locally and are subject to the policies of the underlying model (ComfyUI / Stable Diffusion). Do not generate illegal or harmful content.</p></section>
          <section><h3 className="text-slate-200 font-semibold mb-1">5. No Warranties</h3>
            <p>This software is provided "as is" without warranty of any kind. Use at your own risk.</p></section>
          <section><h3 className="text-slate-200 font-semibold mb-1">6. Account Deletion</h3>
            <p>Deleting your account permanently erases all associated data from your browser. This action is irreversible.</p></section>
          <section><h3 className="text-slate-200 font-semibold mb-1">7. Open Source</h3>
            <p>Mini Assistant is open source. Report issues or contribute at <a href="https://github.com/TheGamerJay/Mini-Assistant" target="_blank" rel="noopener noreferrer" className="text-cyan-400 underline">github.com/TheGamerJay/Mini-Assistant</a>.</p></section>
        </div>
        <div className="px-6 py-4 border-t border-white/8">
          <button onClick={onClose} className="w-full py-2 rounded-xl bg-white/8 hover:bg-white/12 text-slate-300 text-sm font-medium transition-colors">Close</button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DeleteConfirmModal
// ---------------------------------------------------------------------------
function DeleteConfirmModal({ onConfirm, onClose }) {
  const [confirm, setConfirm] = useState('');
  const match = confirm.trim().toLowerCase() === 'delete my account';
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-2xl bg-[#0f0f1a] border border-red-500/20 shadow-2xl p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-red-500/10 flex items-center justify-center flex-shrink-0">
            <AlertTriangle size={18} className="text-red-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-red-400">Delete Account</h3>
            <p className="text-xs text-slate-500 mt-0.5">This cannot be undone.</p>
          </div>
        </div>
        <p className="text-xs text-slate-400 mb-4 leading-relaxed">
          All your chats, images, projects, and settings will be permanently erased. Type <span className="text-slate-200 font-mono">delete my account</span> to confirm.
        </p>
        <input
          type="text"
          value={confirm}
          onChange={e => setConfirm(e.target.value)}
          placeholder="delete my account"
          className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-slate-200 placeholder-slate-600 outline-none focus:border-red-500/40 mb-4"
        />
        <div className="flex gap-2">
          <button onClick={onClose} className="flex-1 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 text-sm transition-colors">Cancel</button>
          <button
            onClick={onConfirm}
            disabled={!match}
            className="flex-1 py-2 rounded-xl bg-red-500/20 hover:bg-red-500/30 text-red-400 text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >Delete Forever</button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section card wrapper
// ---------------------------------------------------------------------------
function Card({ children, className = '' }) {
  return (
    <div className={`bg-[#0f0f1a] border border-white/8 rounded-2xl p-6 ${className}`}>
      {children}
    </div>
  );
}

function SectionTitle({ children }) {
  return <h2 className="text-xs font-mono uppercase tracking-widest text-slate-500 mb-4">{children}</h2>;
}

function SaveBtn({ loading, label = 'Save Changes' }) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/20 text-cyan-300 text-sm font-medium transition-colors disabled:opacity-50"
    >
      {loading ? <span className="w-3 h-3 border border-cyan-400/40 border-t-cyan-400 rounded-full animate-spin" /> : <Check size={13} />}
      {label}
    </button>
  );
}

function PwdField({ label, value, onChange, placeholder }) {
  const [show, setShow] = useState(false);
  return (
    <div>
      <label className="block text-xs text-slate-500 mb-1">{label}</label>
      <div className="relative">
        <input
          type={show ? 'text' : 'password'}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          className="w-full px-3 py-2.5 pr-10 rounded-xl bg-white/5 border border-white/10 text-sm text-slate-200 placeholder-slate-600 outline-none focus:border-cyan-500/40 transition-colors"
        />
        <button
          type="button"
          onClick={() => setShow(v => !v)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors text-base leading-none select-none"
        >
          {show ? '🙈' : '👁️'}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProfilePage
// ---------------------------------------------------------------------------
function ProfilePage() {
  const {
    user, avatar, updateAvatar, removeAvatar,
    updateDisplayName, changePassword, deleteAccount,
    logout, setPage, getPrevPage,
  } = useApp();

  const fileRef = useRef(null);

  // Display name
  const [name, setName] = useState(user?.name || '');
  const [nameSaving, setNameSaving] = useState(false);

  // Password
  const [curPwd, setCurPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [conPwd, setConPwd] = useState('');
  const [pwdSaving, setPwdSaving] = useState(false);

  // Modals
  const [showTerms, setShowTerms] = useState(false);
  const [showDelete, setShowDelete] = useState(false);

  const initial = user?.name ? user.name[0].toUpperCase() : 'U';

  // Avatar upload
  const handleAvatarClick = () => fileRef.current?.click();
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { toast.error('Image must be under 2 MB'); return; }
    const reader = new FileReader();
    reader.onload = (ev) => {
      updateAvatar(ev.target.result);
      toast.success('Avatar updated');
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  // Save display name
  const handleSaveName = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setNameSaving(true);
    try {
      updateDisplayName(name.trim());
      toast.success('Display name updated');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setNameSaving(false);
    }
  };

  // Change password
  const handleChangePwd = async (e) => {
    e.preventDefault();
    if (newPwd.length < 6) { toast.error('New password must be at least 6 characters'); return; }
    if (newPwd !== conPwd) { toast.error('Passwords do not match'); return; }
    setPwdSaving(true);
    try {
      await changePassword(curPwd, newPwd);
      toast.success('Password changed successfully');
      setCurPwd(''); setNewPwd(''); setConPwd('');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setPwdSaving(false);
    }
  };

  const handleDeleteConfirm = () => {
    deleteAccount();
  };

  const handleBack = () => {
    const prev = getPrevPage();
    setPage(prev || 'chat');
  };

  return (
    <div className="h-full overflow-y-auto bg-[#0d0d12]">
      <div className="max-w-2xl mx-auto px-6 py-8">

        {/* Back */}
        <button
          onClick={handleBack}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors mb-6"
        >
          <ChevronLeft size={14} />
          Back
        </button>

        <h1 className="text-xl font-semibold text-slate-100 mb-6">My Profile</h1>

        {/* ── Avatar + Identity ── */}
        <Card className="mb-4">
          <div className="flex items-center gap-5">
            {/* Avatar */}
            <div className="relative flex-shrink-0 group cursor-pointer" onClick={handleAvatarClick}>
              <div className="w-20 h-20 rounded-full overflow-hidden bg-gradient-to-br from-violet-500 to-cyan-500 flex items-center justify-center text-white text-2xl font-bold select-none ring-2 ring-white/10 group-hover:ring-cyan-500/40 transition-all">
                {avatar
                  ? <img src={avatar} alt="Avatar" className="w-full h-full object-cover" />
                  : initial}
              </div>
              <div className="absolute inset-0 rounded-full bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <Camera size={18} className="text-white" />
              </div>
            </div>
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleFileChange} />

            {/* Identity */}
            <div className="flex-1 min-w-0">
              <p className="text-base font-semibold text-slate-100 truncate">{user?.name}</p>
              <p className="text-xs text-slate-500 font-mono truncate mt-0.5">{user?.email}</p>
              <div className="flex gap-2 mt-3">
                <button
                  onClick={handleAvatarClick}
                  className="text-xs px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-slate-200 border border-white/8 transition-colors"
                >
                  Upload photo
                </button>
                {avatar && (
                  <button
                    onClick={() => { removeAvatar(); toast.success('Avatar removed'); }}
                    className="text-xs px-3 py-1.5 rounded-lg bg-white/5 hover:bg-red-500/10 text-slate-500 hover:text-red-400 border border-white/8 transition-colors"
                  >
                    Remove
                  </button>
                )}
              </div>
            </div>
          </div>
        </Card>

        {/* ── Display Name ── */}
        <Card className="mb-4">
          <SectionTitle>Display Name</SectionTitle>
          <form onSubmit={handleSaveName} className="flex gap-3 items-end">
            <div className="flex-1">
              <label className="block text-xs text-slate-500 mb-1">Name</label>
              <div className="relative">
                <User size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-600" />
                <input
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="Your display name"
                  maxLength={40}
                  className="w-full pl-8 pr-3 py-2.5 rounded-xl bg-white/5 border border-white/10 text-sm text-slate-200 placeholder-slate-600 outline-none focus:border-cyan-500/40 transition-colors"
                />
              </div>
            </div>
            <SaveBtn loading={nameSaving} />
          </form>
        </Card>

        {/* ── Change Password ── */}
        <Card className="mb-4">
          <SectionTitle>Change Password</SectionTitle>
          <form onSubmit={handleChangePwd} className="space-y-3">
            <PwdField label="Current password" value={curPwd} onChange={e => setCurPwd(e.target.value)} placeholder="••••••••" />
            <PwdField label="New password" value={newPwd} onChange={e => setNewPwd(e.target.value)} placeholder="Min. 6 characters" />
            <PwdField label="Confirm new password" value={conPwd} onChange={e => setConPwd(e.target.value)} placeholder="Repeat new password" />
            <div className="pt-1">
              <SaveBtn loading={pwdSaving} label="Update Password" />
            </div>
          </form>
        </Card>

        {/* ── Legal ── */}
        <Card className="mb-4">
          <SectionTitle>Legal</SectionTitle>
          <button
            onClick={() => setShowTerms(true)}
            className="flex items-center gap-3 w-full px-4 py-3 rounded-xl bg-white/4 hover:bg-white/8 border border-white/8 transition-colors text-left"
          >
            <FileText size={16} className="text-slate-500 flex-shrink-0" />
            <span className="text-sm text-slate-300">Terms & Privacy Policy</span>
          </button>
        </Card>

        {/* ── Sign Out ── */}
        <Card className="mb-4">
          <SectionTitle>Session</SectionTitle>
          <button
            onClick={logout}
            className="flex items-center gap-3 w-full px-4 py-3 rounded-xl bg-white/4 hover:bg-white/8 border border-white/8 transition-colors text-left"
          >
            <LogOut size={16} className="text-slate-500 flex-shrink-0" />
            <span className="text-sm text-slate-300">Sign out</span>
          </button>
        </Card>

        {/* ── Danger Zone ── */}
        <Card className="border-red-500/15">
          <SectionTitle>Danger Zone</SectionTitle>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-slate-300">Delete account</p>
              <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
                Permanently erase your account and all associated data. This cannot be undone.
              </p>
            </div>
            <button
              onClick={() => setShowDelete(true)}
              className="flex-shrink-0 flex items-center gap-2 px-4 py-2 rounded-xl bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 text-red-400 text-sm font-medium transition-colors"
            >
              <Trash2 size={13} />
              Delete
            </button>
          </div>
        </Card>

      </div>

      {showTerms && <TermsModal onClose={() => setShowTerms(false)} />}
      {showDelete && (
        <DeleteConfirmModal
          onConfirm={handleDeleteConfirm}
          onClose={() => setShowDelete(false)}
        />
      )}
    </div>
  );
}

export default ProfilePage;
