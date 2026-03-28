/**
 * AIDataUsageSetting
 *
 * Radio-style toggle between two AI data usage modes:
 *   • Private Mode (default) — only session metadata collected
 *   • Improve the System    — structured summaries shared (no raw content)
 *
 * Reads/writes from /api/settings  (PATCH { ai_data_usage_mode: '...' })
 */

import React, { useEffect, useState } from 'react';
import { ShieldCheck, Sparkles, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { IMAGE_API } from '../../api/client';

// Settings endpoints live on the image system server, accessed via IMAGE_API proxy
const SETTINGS_URL = `${IMAGE_API.replace(/\/api$/, '')}/api/settings`;

const MODES = [
  {
    id: 'private',
    label: 'Private Mode',
    icon: ShieldCheck,
    iconColor: 'text-emerald-400',
    borderActive: 'border-emerald-500/50',
    bgActive: 'bg-emerald-500/8',
    description: 'Only essential session metadata is stored. No prompts, outputs, or usage patterns are shared.',
    collects: [
      'Session ID (hashed, one-way)',
      'Mode used (chat / builder / image)',
      'Turn count per session',
      'Timestamps',
    ],
  },
  {
    id: 'improve_system',
    label: 'Help improve Mini Assistant',
    icon: Sparkles,
    iconColor: 'text-violet-400',
    borderActive: 'border-violet-500/50',
    bgActive: 'bg-violet-500/8',
    description: 'Structured summaries help improve routing, confidence, and failure recovery. No raw prompts or outputs are stored.',
    collects: [
      'Intent type & ambiguity score',
      'Confidence and risk labels',
      'Step counts & credit usage',
      'Success / failure class (no content)',
      'Verification pass/fail',
    ],
    notCollected: [
      'Your prompts or messages',
      'Generated code or images',
      'Personal identifiers',
    ],
  },
];

export default function AIDataUsageSetting() {
  const [mode, setMode]       = useState(null);   // null = loading
  const [saving, setSaving]   = useState(false);

  // Load current setting on mount
  useEffect(() => {
    fetch(SETTINGS_URL)
      .then((r) => r.json())
      .then((d) => setMode(d.ai_data_usage_mode || 'private'))
      .catch(() => setMode('private'));
  }, []);

  const handleSelect = async (newMode) => {
    if (newMode === mode || saving) return;
    setSaving(true);
    try {
      const res = await fetch(SETTINGS_URL, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ai_data_usage_mode: newMode }),
      });
      if (!res.ok) throw new Error('Save failed');
      const data = await res.json();
      setMode(data.ai_data_usage_mode);
      toast.success(
        newMode === 'improve_system'
          ? 'Thank you! Structured summaries will be shared.'
          : 'Private mode enabled. Only metadata is collected.'
      );
    } catch {
      toast.error('Could not save setting — please try again.');
    } finally {
      setSaving(false);
    }
  };

  if (mode === null) {
    return (
      <div className="flex items-center gap-2 py-3 text-slate-500 text-xs">
        <Loader2 size={13} className="animate-spin" /> Loading…
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {MODES.map((m) => {
        const Icon    = m.icon;
        const active  = mode === m.id;
        return (
          <button
            key={m.id}
            onClick={() => handleSelect(m.id)}
            disabled={saving}
            className={`w-full text-left rounded-xl border px-4 py-3.5 transition-colors
              ${active
                ? `${m.bgActive} ${m.borderActive}`
                : 'bg-white/3 border-white/5 hover:bg-white/5 hover:border-white/10'}`}
          >
            {/* Row: icon + label + radio dot */}
            <div className="flex items-center gap-2.5 mb-1.5">
              <Icon size={14} className={active ? m.iconColor : 'text-slate-500'} />
              <span className={`text-sm font-medium flex-1 ${active ? 'text-slate-100' : 'text-slate-300'}`}>
                {m.label}
              </span>
              {/* Radio dot */}
              <span className={`h-4 w-4 rounded-full border-2 flex items-center justify-center flex-shrink-0
                ${active ? `${m.borderActive} ${m.bgActive}` : 'border-slate-600'}`}>
                {active && <span className={`h-2 w-2 rounded-full ${active ? m.iconColor.replace('text-', 'bg-') : ''}`} />}
              </span>
            </div>

            {/* Description */}
            <p className="text-[11px] text-slate-500 leading-relaxed pl-[22px]">
              {m.description}
            </p>

            {/* What's collected */}
            {active && (
              <div className="mt-2.5 pl-[22px] space-y-1">
                <p className="text-[10px] font-mono uppercase tracking-wider text-slate-600 mb-1">
                  Collected
                </p>
                {m.collects.map((item) => (
                  <div key={item} className="flex items-start gap-1.5 text-[11px] text-slate-500">
                    <span className="text-emerald-500 mt-px flex-shrink-0">✓</span> {item}
                  </div>
                ))}
                {m.notCollected && (
                  <>
                    <p className="text-[10px] font-mono uppercase tracking-wider text-slate-600 mt-2 mb-1">
                      Never collected
                    </p>
                    {m.notCollected.map((item) => (
                      <div key={item} className="flex items-start gap-1.5 text-[11px] text-slate-500">
                        <span className="text-red-500 mt-px flex-shrink-0">✕</span> {item}
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}
          </button>
        );
      })}

      <p className="text-[10px] text-slate-600 pt-1 leading-relaxed">
        You can change this setting at any time. Data collected under "Help improve" is retained for 30 days then automatically purged.
      </p>
    </div>
  );
}
