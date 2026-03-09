/**
 * components/ImageCard.js
 * Renders a generated image result or a dry-run plan.
 * Props: { image_base64, prompt, route_result, generation_time_ms, retry_used, plan, dry_run }
 */

import React, { useState } from 'react';
import { Download, ChevronDown, ChevronUp } from 'lucide-react';

function ImageCard({ image_base64, prompt, route_result, generation_time_ms, retry_used, plan, dry_run }) {
  const [showFullPositive, setShowFullPositive] = useState(false);
  const [showFullNegative, setShowFullNegative] = useState(false);

  const handleDownload = () => {
    if (!image_base64) return;
    const link = document.createElement('a');
    link.href = `data:image/png;base64,${image_base64}`;
    link.download = `mini-assistant-${Date.now()}.png`;
    link.click();
  };

  const timeS = generation_time_ms ? (generation_time_ms / 1000).toFixed(1) : null;

  // Dry-run plan view
  if (dry_run && plan) {
    const positive = plan.positive_prompt || '';
    const negative = plan.negative_prompt || '';
    return (
      <div className="rounded-xl border border-amber-500/20 bg-amber-900/10 overflow-hidden max-w-md">
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-amber-500/10">
          <span className="text-[10px] font-mono uppercase tracking-widest text-amber-400/80 bg-amber-500/10 px-2 py-0.5 rounded">
            Generation Plan
          </span>
          <span className="text-[10px] font-mono text-amber-600 bg-amber-900/30 border border-amber-500/20 px-1.5 py-0.5 rounded">
            dry run
          </span>
        </div>

        {/* Plan details grid */}
        <div className="px-4 py-3 grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-mono">
          {plan.checkpoint_file && (
            <>
              <span className="text-amber-600/60">Checkpoint</span>
              <span className="text-amber-300/80 truncate">{plan.checkpoint_file}</span>
            </>
          )}
          {plan.workflow && (
            <>
              <span className="text-amber-600/60">Workflow</span>
              <span className="text-amber-300/80 truncate">{plan.workflow}</span>
            </>
          )}
          {(plan.width || plan.height) && (
            <>
              <span className="text-amber-600/60">Size</span>
              <span className="text-amber-300/80">{plan.width ?? '?'}×{plan.height ?? '?'}</span>
            </>
          )}
          {plan.steps && (
            <>
              <span className="text-amber-600/60">Steps</span>
              <span className="text-amber-300/80">{plan.steps}</span>
            </>
          )}
          {plan.cfg !== undefined && (
            <>
              <span className="text-amber-600/60">CFG</span>
              <span className="text-amber-300/80">{plan.cfg}</span>
            </>
          )}
          {plan.seed !== undefined && (
            <>
              <span className="text-amber-600/60">Seed</span>
              <span className="text-amber-300/80">{plan.seed}</span>
            </>
          )}
        </div>

        {/* Positive prompt */}
        {positive && (
          <div className="px-4 py-2 border-t border-amber-500/10">
            <p className="text-[10px] font-mono text-amber-600/60 mb-1">Positive prompt</p>
            <p className="text-[11px] text-amber-300/70 leading-relaxed">
              {showFullPositive ? positive : positive.slice(0, 140)}
              {positive.length > 140 && (
                <button
                  onClick={() => setShowFullPositive((v) => !v)}
                  className="ml-1 text-amber-500/60 hover:text-amber-400 inline-flex items-center gap-0.5"
                >
                  {showFullPositive ? <><ChevronUp size={10} /> less</> : <><ChevronDown size={10} /> more</>}
                </button>
              )}
            </p>
          </div>
        )}

        {/* Negative prompt */}
        {negative && (
          <div className="px-4 py-2 border-t border-amber-500/10">
            <p className="text-[10px] font-mono text-amber-600/60 mb-1">Negative prompt</p>
            <p className="text-[11px] text-amber-300/50 leading-relaxed">
              {showFullNegative ? negative : negative.slice(0, 100)}
              {negative.length > 100 && (
                <button
                  onClick={() => setShowFullNegative((v) => !v)}
                  className="ml-1 text-amber-500/60 hover:text-amber-400 inline-flex items-center gap-0.5"
                >
                  {showFullNegative ? <><ChevronUp size={10} /> less</> : <><ChevronDown size={10} /> more</>}
                </button>
              )}
            </p>
          </div>
        )}

        {/* Overrides */}
        {plan.overrides_applied && plan.overrides_applied.length > 0 && (
          <div className="px-4 py-2 border-t border-amber-500/10">
            <p className="text-[10px] font-mono text-amber-600/60 mb-1">Overrides applied</p>
            <div className="flex flex-wrap gap-1">
              {plan.overrides_applied.map((o, i) => (
                <span key={i} className="text-[10px] font-mono text-amber-400/70 bg-amber-900/20 border border-amber-500/20 px-1.5 py-0.5 rounded">
                  {o}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  // Normal image result
  const checkpoint = route_result?.checkpoint || route_result?.checkpoint_file || null;
  const workflow = route_result?.workflow || null;

  return (
    <div className="rounded-xl overflow-hidden border border-violet-500/20 bg-black/40 max-w-md">
      {image_base64 && (
        <img
          src={`data:image/png;base64,${image_base64}`}
          alt={prompt || 'Generated image'}
          className="w-full object-contain"
        />
      )}
      {/* Footer */}
      <div className="flex items-center gap-2 px-3 py-2 border-t border-white/5 flex-wrap">
        {checkpoint && (
          <span className="text-[10px] font-mono text-violet-400/70 bg-violet-500/10 px-1.5 py-0.5 rounded border border-violet-500/20 truncate max-w-[140px]">
            {checkpoint}
          </span>
        )}
        {workflow && (
          <span className="text-[10px] font-mono text-slate-500 truncate max-w-[100px]">{workflow}</span>
        )}
        {retry_used && (
          <span className="text-[10px] font-mono text-amber-400/70 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
            retried
          </span>
        )}
        {timeS && (
          <span className="text-[10px] font-mono text-slate-500">{timeS}s</span>
        )}
        <div className="flex-1" />
        {image_base64 && (
          <button
            onClick={handleDownload}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/10 transition-colors"
            title="Download image"
          >
            <Download size={14} />
          </button>
        )}
      </div>
    </div>
  );
}

export default ImageCard;
