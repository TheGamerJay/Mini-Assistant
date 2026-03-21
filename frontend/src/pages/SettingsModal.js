/**
 * pages/SettingsModal.js
 * Full-screen modal overlay for app settings.
 * Props: { onClose }
 */

import React, { useEffect } from 'react';
import { X, RefreshCw, FileText, Shield, RotateCcw, AlertOctagon, Copyright, Mail, ChevronRight } from 'lucide-react';
import { toast } from 'sonner';
import { useApp } from '../context/AppContext';
import { api } from '../api/client';
import StatusBadge from '../components/StatusBadge';

const QUALITY_OPTIONS = ['fast', 'balanced', 'high'];

function Toggle({ checked, onChange, label, description }) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-white/5 last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-slate-200">{label}</p>
        {description && <p className="text-xs text-slate-500 mt-0.5">{description}</p>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-5 w-9 flex-shrink-0 rounded-full border-2 border-transparent transition-colors focus:outline-none mt-0.5
          ${checked ? 'bg-cyan-500' : 'bg-slate-700'}`}
      >
        <span
          className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition-transform
            ${checked ? 'translate-x-4' : 'translate-x-0'}`}
        />
      </button>
    </div>
  );
}

function SectionHeader({ children }) {
  return (
    <h3 className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-3 mt-6 first:mt-0">
      {children}
    </h3>
  );
}

const LEGAL_LINKS = [
  { page: 'legal-terms',      icon: FileText,      label: 'Terms of Service' },
  { page: 'legal-privacy',    icon: Shield,        label: 'Privacy Policy' },
  { page: 'legal-refund',     icon: RotateCcw,     label: 'Refund Policy' },
  { page: 'legal-prohibited', icon: AlertOctagon,  label: 'Prohibited Content' },
  { page: 'legal-dmca',       icon: Copyright,     label: 'DMCA & Copyright' },
  { page: 'legal-contact',    icon: Mail,          label: 'Contact Us' },
];

function SettingsModal({ onClose }) {
  const { settings, updateSettings, serverStatus, setServerStatus, setPage } = useApp();

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const handleRefreshStatus = async () => {
    try {
      const data = await api.mainHealth();
      setServerStatus({
        backend: true,
        openai: data.openai === 'connected',
      });
    } catch {
      setServerStatus({ backend: false, openai: false });
    }
    toast.success('Status refreshed');
  };

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-[#111118] border border-white/10 rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/8 flex-shrink-0">
          <h2 className="text-base font-semibold text-slate-100">Settings</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4 flex-1">

          {/* --- Connection --- */}
          <SectionHeader>Connection</SectionHeader>
          <div className="flex items-center gap-3 flex-wrap">
            <StatusBadge label="Backend" status={serverStatus.backend} />
            <StatusBadge label="Claude API" status={serverStatus.openai} />
            <button
              onClick={handleRefreshStatus}
              className="ml-auto flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 bg-white/5 hover:bg-white/10 border border-white/10 px-2.5 py-1.5 rounded-lg transition-colors"
            >
              <RefreshCw size={12} /> Refresh
            </button>
          </div>

          {/* --- Chat preferences --- */}
          <SectionHeader>Chat preferences</SectionHeader>
          <div className="bg-white/3 rounded-xl border border-white/5 px-4">
            <Toggle
              checked={settings.showRouteInfo}
              onChange={(v) => updateSettings({ showRouteInfo: v })}
              label="Show route / model info in chat"
              description="Display intent, checkpoint, confidence and timing below assistant messages."
            />
            <Toggle
              checked={settings.autoReview}
              onChange={(v) => updateSettings({ autoReview: v })}
              label="Auto-review generated images"
              description="Automatically analyse generated images and show a brief description."
            />
          </div>

          {/* --- Image generation --- */}
          <SectionHeader>Image generation</SectionHeader>
          <div className="bg-white/3 rounded-xl border border-white/5 px-4">
            <Toggle
              checked={settings.dryRun}
              onChange={(v) => updateSettings({ dryRun: v })}
              label="Dry run mode"
              description="Preview the generation plan without actually producing an image."
            />
            <div className="py-3">
              <p className="text-sm text-slate-200 mb-2">Default quality</p>
              <div className="flex gap-1.5">
                {QUALITY_OPTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => updateSettings({ quality: q })}
                    className={`flex-1 capitalize py-1.5 rounded-lg text-xs font-medium transition-colors border
                      ${settings.quality === q
                        ? 'bg-cyan-500/15 border-cyan-500/40 text-cyan-400'
                        : 'bg-white/5 border-white/10 text-slate-400 hover:text-slate-200 hover:bg-white/8'}`}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* --- Legal --- */}
          <SectionHeader>Legal</SectionHeader>
          <div className="rounded-xl border border-white/5 overflow-hidden">
            {LEGAL_LINKS.map(({ page, icon: Icon, label }, i) => (
              <button
                key={page}
                onClick={() => { setPage(page); onClose(); }}
                className={`flex items-center gap-3 w-full px-4 py-3 text-left hover:bg-white/5 transition-colors
                  ${i < LEGAL_LINKS.length - 1 ? 'border-b border-white/5' : ''}`}
              >
                <Icon size={14} className="text-slate-500 flex-shrink-0" />
                <span className="flex-1 text-sm text-slate-300">{label}</span>
                <ChevronRight size={13} className="text-slate-600" />
              </button>
            ))}
          </div>

          {/* bottom padding */}
          <div className="h-4" />
        </div>
      </div>
    </div>
  );
}

export default SettingsModal;
