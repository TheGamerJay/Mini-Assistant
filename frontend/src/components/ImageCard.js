/**
 * components/ImageCard.js
 * Renders a generated image result or a dry-run plan.
 * Props: { image_base64, prompt, route_result, generation_time_ms, retry_used, plan, dry_run, onGenerate, onRerun }
 */

import React, { useState } from 'react';
import { Download, ChevronDown, ChevronUp, Copy, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

function copyToClipboard(text, label) {
  navigator.clipboard.writeText(text).then(
    () => toast.success(`${label} copied`),
    () => toast.error('Copy failed')
  );
}

function ImageCard({ image_base64, prompt, route_result, generation_time_ms, retry_used, plan, dry_run, onGenerate, onRerun }) {
  const [showFullPositive, setShowFullPositive] = useState(false);
  const [showFullNegative, setShowFullNegative] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

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
          <span className="text-[10px] font-mono text-amber-300 bg-amber-500/20 border border-amber-500/30 px-1.5 py-0.5 rounded font-bold">
            DRY RUN
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
            <div className="flex items-center justify-between mb-1">
              <p className="text-[10px] font-mono text-amber-600/60">Positive prompt</p>
              <button
                onClick={() => copyToClipboard(positive, 'Positive prompt')}
                className="p-0.5 rounded text-amber-600/40 hover:text-amber-400 transition-colors"
                title="Copy positive prompt"
              >
                <Copy size={10} />
              </button>
            </div>
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
            <div className="flex items-center justify-between mb-1">
              <p className="text-[10px] font-mono text-amber-600/60">Negative prompt</p>
              <button
                onClick={() => copyToClipboard(negative, 'Negative prompt')}
                className="p-0.5 rounded text-amber-600/40 hover:text-amber-400 transition-colors"
                title="Copy negative prompt"
              >
                <Copy size={10} />
              </button>
            </div>
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

        {/* Generate for real */}
        {onGenerate && (
          <div className="px-4 py-3 border-t border-amber-500/10">
            <button
              onClick={onGenerate}
              className="w-full py-2 rounded-lg bg-gradient-to-br from-amber-500/20 to-amber-600/20 hover:from-amber-500/30 hover:to-amber-600/30 border border-amber-500/30 text-amber-300 text-xs font-medium transition-all"
            >
              Generate for real
            </button>
          </div>
        )}
      </div>
    );
  }

  // Normal image result
  const checkpoint = route_result?.checkpoint || route_result?.checkpoint_file || null;
  const workflow = route_result?.workflow || null;
  const checkpointDisplay = checkpoint ? checkpoint.slice(0, 20) + (checkpoint.length > 20 ? '…' : '') : null;

  return (
    <div className="rounded-xl overflow-hidden border border-violet-500/20 bg-black/40 max-w-md">
      {image_base64 && (
        <img
          src={`data:image/png;base64,${image_base64}`}
          alt={prompt || 'Generated image'}
          className="w-full object-contain"
        />
      )}
      {/* Compact metadata footer */}
      <div className="flex items-center gap-2 px-3 py-2 border-t border-white/5 flex-wrap">
        {checkpointDisplay && (
          <span className="text-[10px] font-mono text-violet-400/70 bg-violet-500/10 px-1.5 py-0.5 rounded border border-violet-500/20" title={checkpoint}>
            {checkpointDisplay}
          </span>
        )}
        {timeS && (
          <span className="text-[10px] font-mono text-slate-500">{timeS}s</span>
        )}
        {retry_used && (
          <span className="text-[10px] font-mono text-amber-400/70 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
            retried
          </span>
        )}
        <div className="flex-1" />

        {/* Details toggle */}
        <button
          onClick={() => setShowDetails((v) => !v)}
          className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/10 transition-colors"
          title="Toggle details"
        >
          {showDetails ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>

        {/* Re-run button */}
        {onRerun && (
          <button
            onClick={onRerun}
            className="p-1.5 rounded-lg text-slate-500 hover:text-cyan-400 hover:bg-cyan-500/10 transition-colors"
            title="Re-run with same settings"
          >
            <RefreshCw size={14} />
          </button>
        )}

        {/* Download (always visible) */}
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

      {/* Expandable details */}
      {showDetails && (
        <div className="px-3 py-3 border-t border-white/5 space-y-1.5 bg-black/20">
          {checkpoint && (
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-slate-600">Checkpoint</span>
              <span className="text-[10px] font-mono text-slate-400 truncate max-w-[200px]">{checkpoint}</span>
            </div>
          )}
          {workflow && (
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-slate-600">Workflow</span>
              <span className="text-[10px] font-mono text-slate-400 truncate max-w-[200px]">{workflow}</span>
            </div>
          )}
          {route_result?.seed !== undefined && (
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-slate-600">Seed</span>
              <span className="text-[10px] font-mono text-slate-400">{route_result.seed ?? 'random'}</span>
            </div>
          )}
          {route_result?.steps && (
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-slate-600">Steps</span>
              <span className="text-[10px] font-mono text-slate-400">{route_result.steps}</span>
            </div>
          )}
          {route_result?.cfg !== undefined && (
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-slate-600">CFG</span>
              <span className="text-[10px] font-mono text-slate-400">{route_result.cfg}</span>
            </div>
          )}
          {timeS && (
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-slate-600">Time</span>
              <span className="text-[10px] font-mono text-slate-400">{timeS}s</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ImageCard;
