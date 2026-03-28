import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Cpu } from 'lucide-react';

/**
 * IntelligencePanel — shows routing/model info above assistant responses.
 * Props: route_result (object), generation_time_ms (number)
 */
const IntelligencePanel = ({ route_result, generation_time_ms }) => {
  const [open, setOpen] = useState(false);
  if (!route_result) return null;

  const { intent, selected_checkpoint, selected_workflow, confidence, style_family, anime_genre } = route_result;

  // Only show for non-trivial routes
  if (!intent || intent === 'chat') return null;

  const brain = intent === 'image_generation' ? 'dall-e 3'
    : intent === 'image_edit' ? 'ceo + image brain'
    : intent === 'coding' ? 'coder brain'
    : intent === 'image_analysis' ? 'vision brain'
    : 'router brain';

  const confPct = typeof confidence === 'number' ? Math.round(confidence * 100) : null;

  return (
    <div className="mb-2 rounded-lg border border-cyan-500/15 bg-black/30 overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-[11px] font-mono text-cyan-500/70 hover:text-cyan-400 transition-colors"
      >
        <Cpu className="w-3 h-3 flex-shrink-0" />
        <span className="flex-1 text-left">
          {intent.replace('_', ' ')}
          {selected_checkpoint && ` · ${selected_checkpoint}`}
          {confPct !== null && ` · ${confPct}% conf`}
        </span>
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {open && (
        <div className="px-3 pb-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[10px] font-mono border-t border-cyan-500/10 pt-2">
          <span className="text-slate-500">Route</span><span className="text-cyan-400/80">{intent.replace(/_/g,' ')}</span>
          {style_family && <><span className="text-slate-500">Style</span><span className="text-cyan-400/80">{style_family}{anime_genre ? ` / ${anime_genre}` : ''}</span></>}
          {selected_checkpoint && <><span className="text-slate-500">Model</span><span className="text-cyan-400/80 truncate">{selected_checkpoint}</span></>}
          {selected_workflow && <><span className="text-slate-500">Workflow</span><span className="text-cyan-400/80 truncate">{selected_workflow}</span></>}
          {confPct !== null && <><span className="text-slate-500">Confidence</span><span className={`${confPct >= 70 ? 'text-emerald-400' : confPct >= 50 ? 'text-amber-400' : 'text-red-400'}`}>{confPct}%</span></>}
          <span className="text-slate-500">Brain</span><span className="text-cyan-400/80">{brain}</span>
          {generation_time_ms && <><span className="text-slate-500">Time</span><span className="text-slate-400">{(generation_time_ms/1000).toFixed(1)}s</span></>}
        </div>
      )}
    </div>
  );
};

export default IntelligencePanel;
