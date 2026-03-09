/**
 * pages/ImagePage.js
 * Dedicated image generation page.
 * Left panel: prompt + options. Right panel: results grid.
 */

import React, { useState, useCallback, useRef } from 'react';
import { Image, Loader2, ChevronDown, ChevronUp, Zap, BarChart2, Sparkles, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { useApp, makeThumbnail } from '../context/AppContext';
import { api } from '../api/client';
import ImageCard from '../components/ImageCard';

const QUALITY_OPTIONS = [
  { value: 'fast', label: 'Fast', icon: Zap },
  { value: 'balanced', label: 'Balanced', icon: BarChart2 },
  { value: 'high', label: 'High', icon: Sparkles },
];

function Toggle({ checked, onChange, label }) {
  return (
    <label className="flex items-center gap-3 cursor-pointer">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-5 w-9 flex-shrink-0 rounded-full border-2 border-transparent transition-colors focus:outline-none
          ${checked ? 'bg-cyan-500' : 'bg-slate-700'}`}
      >
        <span
          className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition-transform
            ${checked ? 'translate-x-4' : 'translate-x-0'}`}
        />
      </button>
      <span className="text-sm text-slate-300">{label}</span>
    </label>
  );
}

function SkeletonCard() {
  return (
    <div className="rounded-xl border border-violet-500/10 bg-black/40 max-w-md overflow-hidden animate-pulse">
      <div className="w-full h-64 bg-slate-800/60" />
      <div className="px-3 py-2 border-t border-white/5 flex gap-2">
        <div className="h-4 w-24 bg-slate-700/60 rounded" />
        <div className="h-4 w-16 bg-slate-700/40 rounded" />
      </div>
    </div>
  );
}

function ImagePage() {
  const { settings, updateSettings, addImage } = useApp();

  const [prompt, setPrompt] = useState('');
  const [quality, setQuality] = useState(settings.quality || 'balanced');
  const [dryRun, setDryRun] = useState(settings.dryRun || false);
  const [checkpoint, setCheckpoint] = useState('');
  const [seed, setSeed] = useState('');
  const [generating, setGenerating] = useState(false);
  const [results, setResults] = useState([]);
  const [routePreview, setRoutePreview] = useState(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [routeLoading, setRouteLoading] = useState(false);
  const sessionIdRef = useRef(crypto.randomUUID());

  const handleRoutePreview = useCallback(async () => {
    if (!prompt.trim()) return;
    setRouteLoading(true);
    try {
      const data = await api.routePrompt(prompt.trim());
      setRoutePreview(data);
    } catch (err) {
      toast.error('Route preview failed: ' + (err.message || 'Unknown error'));
    } finally {
      setRouteLoading(false);
    }
  }, [prompt]);

  const handleGenerate = useCallback(async (overridePrompt) => {
    const activePrompt = (overridePrompt || prompt).trim();
    if (!activePrompt) {
      toast.warning('Please enter a prompt first.');
      return;
    }
    if (activePrompt.length < 3) {
      toast.warning('Message too short (min 3 characters)');
      return;
    }
    if (generating) return;

    sessionIdRef.current = crypto.randomUUID();
    setGenerating(true);
    try {
      const params = {
        prompt: activePrompt,
        quality,
        dry_run: dryRun,
        session_id: sessionIdRef.current,
      };
      if (checkpoint.trim()) params.override_checkpoint = checkpoint.trim();
      if (seed.trim()) params.override_seed = seed.trim();

      const data = await api.generateImage(params);

      if (data.image_base64 && !dryRun) {
        const thumb = await makeThumbnail(data.image_base64);
        await addImage(thumb, activePrompt, data.image_base64);
      }

      setResults((prev) => [{ ...data, prompt: activePrompt, _id: crypto.randomUUID() }, ...prev]);
    } catch (err) {
      if (err.name !== 'AbortError') {
        toast.error('Generation failed: ' + (err.message || 'Unknown error'));
        setResults((prev) => [{
          _id: crypto.randomUUID(),
          _error: true,
          errorMessage: err.message || 'Unknown error',
          prompt: activePrompt,
        }, ...prev]);
      }
    } finally {
      setGenerating(false);
    }
  }, [prompt, quality, dryRun, checkpoint, seed, addImage, generating]);

  const handleCancel = useCallback(async () => {
    try {
      await api.cancelGeneration(sessionIdRef.current);
    } catch {}
    setGenerating(false);
    toast.info('Generation cancelled');
  }, []);

  const handleQualityChange = (q) => {
    setQuality(q);
    updateSettings({ quality: q });
  };

  const handleDryRunChange = (v) => {
    setDryRun(v);
    updateSettings({ dryRun: v });
  };

  return (
    <div className="flex h-full overflow-hidden">
      {/* ---- Left panel ---- */}
      <div className="w-80 flex-shrink-0 border-r border-white/5 flex flex-col overflow-y-auto p-6 gap-5">
        <h2 className="text-base font-semibold text-slate-100">Image Generation</h2>

        {/* Prompt */}
        <div className="space-y-1.5">
          <label className="text-xs text-slate-500 font-mono uppercase tracking-wide">Prompt</label>
          <textarea
            className="w-full min-h-[96px] bg-[#1a1a26] border border-white/10 rounded-xl px-3 py-2.5 text-sm text-slate-200 placeholder-slate-600 outline-none resize-none focus:border-cyan-500/40 transition-colors leading-relaxed"
            placeholder="Describe the image you want to generate…"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={4}
          />
        </div>

        {/* Quality selector */}
        <div className="space-y-1.5">
          <label className="text-xs text-slate-500 font-mono uppercase tracking-wide">Quality</label>
          <div className="flex gap-1.5">
            {QUALITY_OPTIONS.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                onClick={() => handleQualityChange(value)}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium transition-colors border
                  ${quality === value
                    ? 'bg-cyan-500/15 border-cyan-500/40 text-cyan-400'
                    : 'bg-white/5 border-white/10 text-slate-400 hover:text-slate-200 hover:bg-white/8'}`}
              >
                <Icon size={12} />
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Advanced toggle */}
        <button
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
          onClick={() => setShowAdvanced((v) => !v)}
        >
          {showAdvanced ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          Advanced options
        </button>

        {showAdvanced && (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-xs text-slate-500 font-mono">Checkpoint override</label>
              <input
                type="text"
                className="w-full bg-[#1a1a26] border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 outline-none focus:border-cyan-500/40 transition-colors"
                placeholder="e.g. dreamshaper_8.safetensors"
                value={checkpoint}
                onChange={(e) => setCheckpoint(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-slate-500 font-mono">Seed</label>
              <input
                type="text"
                className="w-full bg-[#1a1a26] border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 outline-none focus:border-cyan-500/40 transition-colors"
                placeholder="Random if blank"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
              />
            </div>
          </div>
        )}

        {/* Dry run toggle */}
        <Toggle checked={dryRun} onChange={handleDryRunChange} label="Dry run (plan only)" />

        {/* Route preview button */}
        <button
          onClick={handleRoutePreview}
          disabled={!prompt.trim() || routeLoading}
          className="w-full flex items-center justify-center gap-2 py-2 rounded-lg border border-white/10 text-xs text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {routeLoading ? <Loader2 size={13} className="animate-spin" /> : null}
          Preview Route
        </button>

        {/* Route preview card */}
        {routePreview && (
          <div className="p-3 rounded-lg bg-white/5 border border-white/10 space-y-1.5">
            <p className="text-[10px] font-mono uppercase text-slate-500 tracking-wide">Route result</p>
            {routePreview.intent && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-violet-400/80 bg-violet-500/10 border border-violet-500/20 px-1.5 py-0.5 rounded">{routePreview.intent}</span>
              </div>
            )}
            {routePreview.checkpoint && (
              <p className="text-[11px] font-mono text-cyan-400/70 truncate">{routePreview.checkpoint}</p>
            )}
            {routePreview.workflow && (
              <p className="text-[11px] font-mono text-slate-500 truncate">{routePreview.workflow}</p>
            )}
            {routePreview.confidence != null && (
              <p className="text-[11px] font-mono text-slate-400">
                Confidence: {Math.round(routePreview.confidence * 100)}%
              </p>
            )}
          </div>
        )}

        {/* Generate / Cancel buttons */}
        <div className="flex gap-2">
          <button
            onClick={() => handleGenerate()}
            disabled={!prompt.trim() || generating}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-gradient-to-br from-cyan-500 to-violet-600 text-white text-sm font-medium hover:from-cyan-400 hover:to-violet-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg hover:shadow-cyan-500/20"
          >
            {generating ? <Loader2 size={15} className="animate-spin" /> : null}
            {dryRun ? 'Preview Plan' : 'Generate Image'}
          </button>
          {generating && (
            <button
              onClick={handleCancel}
              title="Cancel generation"
              className="px-3 py-2.5 rounded-xl bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 transition-colors"
            >
              <XCircle size={16} />
            </button>
          )}
        </div>
      </div>

      {/* ---- Right panel ---- */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <h2 className="text-base font-semibold text-slate-100">Results</h2>
          {results.length > 0 && (
            <span className="text-[11px] font-mono text-slate-500 bg-white/5 border border-white/10 px-2 py-0.5 rounded-full">
              {results.length}
            </span>
          )}
        </div>

        {/* Empty state */}
        {results.length === 0 && !generating ? (
          <div className="flex flex-col items-center justify-center h-64 gap-4 text-slate-600">
            <Image size={40} strokeWidth={1} />
            <p className="text-sm">Your generated images will appear here</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {/* Skeleton for in-progress generation */}
            {generating && <SkeletonCard />}
            {/* Results (latest first — already prepended) */}
            {results.map((result) => {
              if (result._error) {
                return (
                  <div key={result._id} className="rounded-xl border border-red-500/20 bg-red-900/10 p-4 space-y-3">
                    <p className="text-xs text-red-400 font-mono">{result.errorMessage}</p>
                    <button
                      onClick={() => handleGenerate(result.prompt)}
                      className="flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 px-2.5 py-1.5 rounded-lg transition-colors"
                    >
                      Retry
                    </button>
                  </div>
                );
              }
              return (
                <ImageCard
                  key={result._id}
                  image_base64={result.image_base64}
                  prompt={result.prompt}
                  route_result={result.route_result}
                  generation_time_ms={result.generation_time_ms}
                  retry_used={result.retry_used}
                  plan={result.plan}
                  dry_run={result.dry_run || dryRun}
                  onRerun={() => {
                    setPrompt(result.prompt);
                    handleGenerate(result.prompt);
                  }}
                />
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export default ImagePage;
