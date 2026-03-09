/**
 * pages/SettingsModal.js
 * Full-screen modal overlay for app settings.
 * Props: { onClose }
 */

import React, { useEffect } from 'react';
import { X, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { useApp } from '../context/AppContext';
import { useModels } from '../hooks/useModels';
import { api, BACKEND_URL } from '../api/client';
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

function SettingsModal({ onClose }) {
  const { settings, updateSettings, serverStatus, setServerStatus } = useApp();
  const { status: modelsStatus, refresh: refreshModels, loading: modelsLoading } = useModels();

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const handleRefreshStatus = async () => {
    try {
      const [mainData] = await Promise.allSettled([api.mainHealth(), api.imageHealth()]);
      if (mainData.status === 'fulfilled') {
        const d = mainData.value;
        setServerStatus({
          backend: true,
          ollama: d.ollama === 'connected' ? true : false,
        });
      } else {
        setServerStatus({ backend: false, ollama: false });
      }
    } catch {
      setServerStatus({ backend: false, ollama: false });
    }
    try {
      const imgHealth = await api.imageHealth();
      setServerStatus({ comfyui: imgHealth.status === 'ok' ? true : false });
    } catch {
      setServerStatus({ comfyui: false });
    }
    toast.success('Status refreshed');
  };

  const handlePullModels = async () => {
    if (!modelsStatus?.required_status) {
      toast.info('No model list available');
      return;
    }
    const missing = Object.entries(modelsStatus.required_status)
      .filter(([, v]) => !v.available)
      .map(([k]) => k);
    if (missing.length === 0) {
      toast.success('All models already available');
      return;
    }
    try {
      await api.pullModels(missing);
      toast.success(`Pulling ${missing.length} model(s)…`);
      setTimeout(refreshModels, 3000);
    } catch (err) {
      toast.error('Pull failed: ' + (err.message || 'Unknown error'));
    }
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
          <div className="space-y-3">
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Backend URL</label>
              <input
                readOnly
                value={BACKEND_URL}
                className="w-full bg-[#1a1a26] border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-slate-400 outline-none cursor-default"
              />
            </div>

            <div className="flex items-center gap-3 flex-wrap">
              <StatusBadge label="Backend" status={serverStatus.backend} />
              <StatusBadge label="Ollama" status={serverStatus.ollama} />
              <StatusBadge label="ComfyUI" status={serverStatus.comfyui} />
              <button
                onClick={handleRefreshStatus}
                className="ml-auto flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 bg-white/5 hover:bg-white/10 border border-white/10 px-2.5 py-1.5 rounded-lg transition-colors"
              >
                <RefreshCw size={12} /> Refresh
              </button>
            </div>

            <button
              onClick={handlePullModels}
              className="w-full text-xs text-slate-400 hover:text-slate-200 bg-white/5 hover:bg-white/10 border border-white/10 px-3 py-2 rounded-lg transition-colors text-left"
            >
              Pull missing models
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

          {/* --- Models --- */}
          <SectionHeader>Models</SectionHeader>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs text-slate-500">
                {modelsStatus ? 'Model status from server' : 'Loading…'}
              </p>
              <button
                onClick={refreshModels}
                disabled={modelsLoading}
                className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors"
              >
                <RefreshCw size={11} className={modelsLoading ? 'animate-spin' : ''} />
                Refresh
              </button>
            </div>

            {modelsStatus?.required_status ? (
              <div className="rounded-xl border border-white/8 overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-white/8 bg-white/3">
                      <th className="text-left px-3 py-2 text-slate-500 font-normal">Model</th>
                      <th className="text-left px-3 py-2 text-slate-500 font-normal">Role</th>
                      <th className="text-right px-3 py-2 text-slate-500 font-normal">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(modelsStatus.required_status).map(([model, info]) => (
                      <tr key={model} className="border-b border-white/5 last:border-0">
                        <td className="px-3 py-2 font-mono text-slate-300 truncate max-w-[160px]">{model}</td>
                        <td className="px-3 py-2 text-slate-500">{info.role || '—'}</td>
                        <td className="px-3 py-2 text-right">
                          <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border
                            ${info.available
                              ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                              : 'text-red-400 bg-red-500/10 border-red-500/20'}`}>
                            <span className={`w-1 h-1 rounded-full ${info.available ? 'bg-emerald-400' : 'bg-red-400'}`} />
                            {info.available ? 'ready' : 'missing'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-slate-600 italic">No model data available. Check backend connection.</p>
            )}
          </div>

          {/* bottom padding */}
          <div className="h-4" />
        </div>
      </div>
    </div>
  );
}

export default SettingsModal;
