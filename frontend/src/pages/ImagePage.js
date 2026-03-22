/**
 * pages/ImagePage.js
 * Image generation page — powered by DALL-E 3 via OpenAI API.
 * Left panel: prompt + options. Right panel: results grid.
 */

import React, { useState, useCallback, useRef } from 'react';
import { Image, Loader2, Zap, Sparkles, XCircle, Square, RectangleVertical, RectangleHorizontal } from 'lucide-react';
import { toast } from 'sonner';
import { useApp, makeThumbnail } from '../context/AppContext';
import { api } from '../api/client';
import ImageCard from '../components/ImageCard';

const QUALITY_OPTIONS = [
  { value: 'balanced', label: 'Standard', icon: Zap,      desc: 'Fast & affordable' },
  { value: 'high',     label: 'HD',       icon: Sparkles,  desc: 'Maximum detail' },
];

const SIZE_OPTIONS = [
  { value: '1024x1024',  label: 'Square',    icon: Square,              hint: '1:1' },
  { value: '1024x1792',  label: 'Portrait',  icon: RectangleVertical,   hint: '9:16' },
  { value: '1792x1024',  label: 'Landscape', icon: RectangleHorizontal, hint: '16:9' },
];

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
  const { settings, updateSettings, addImage, imageUsage, incrementImageUsage } = useApp();

  const [prompt, setPrompt]       = useState('');
  const [quality, setQuality]     = useState(settings.quality || 'balanced');
  const [size, setSize]           = useState('1024x1024');
  const [generating, setGenerating] = useState(false);
  const [results, setResults]     = useState([]);
  const sessionIdRef = useRef(crypto.randomUUID());

  const handleGenerate = useCallback(async (overridePrompt) => {
    const activePrompt = (overridePrompt || prompt).trim();
    if (!activePrompt) { toast.warning('Please enter a prompt first.'); return; }
    if (activePrompt.length < 3) { toast.warning('Prompt too short (min 3 characters)'); return; }
    if (generating) return;

    // Image limit gate
    if (imageUsage.used >= imageUsage.limit) {
      toast.error(`Image limit reached (${imageUsage.limit}/${imageUsage.limit}). Upgrade for more.`);
      return;
    }

    sessionIdRef.current = crypto.randomUUID();
    setGenerating(true);
    try {
      // Map size → override_width/height so the backend knows the aspect ratio
      const [w, h] = size.split('x').map(Number);
      const data = await api.generateImage({
        prompt: activePrompt,
        quality,
        session_id: sessionIdRef.current,
        override_width: w,
        override_height: h,
        request_id: crypto.randomUUID(),
      });

      if (data.image_base64) {
        const thumb = await makeThumbnail(data.image_base64);
        await addImage(thumb, activePrompt, data.image_base64);
        incrementImageUsage();
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
  }, [prompt, quality, size, addImage, generating, imageUsage, incrementImageUsage]);

  const handleCancel = useCallback(() => {
    setGenerating(false);
    toast.info('Generation cancelled');
  }, []);

  const handleQualityChange = (q) => {
    setQuality(q);
    updateSettings({ quality: q });
  };

  return (
    <div className="flex h-full overflow-hidden">
      {/* ---- Left panel ---- */}
      <div className="w-80 flex-shrink-0 border-r border-white/5 flex flex-col overflow-y-auto p-6 gap-5">
        <h2 className="text-base font-semibold text-slate-100">Image Generation</h2>
        <p className="text-xs text-slate-500 -mt-3">Powered by DALL·E 3</p>

        {/* Prompt */}
        <div className="space-y-1.5">
          <label className="text-xs text-slate-500 font-mono uppercase tracking-wide">Prompt</label>
          <textarea
            className="w-full min-h-[96px] bg-[#1a1a26] border border-white/10 rounded-xl px-3 py-2.5 text-sm text-slate-200 placeholder-slate-600 outline-none resize-none focus:border-cyan-500/40 transition-colors leading-relaxed"
            placeholder="Describe the image you want to generate…"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleGenerate(); }}
            rows={4}
          />
          <p className="text-[10px] text-slate-600">Ctrl+Enter to generate</p>
        </div>

        {/* Quality selector */}
        <div className="space-y-1.5">
          <label className="text-xs text-slate-500 font-mono uppercase tracking-wide">Quality</label>
          <div className="flex gap-1.5">
            {QUALITY_OPTIONS.map(({ value, label, icon: Icon, desc }) => (
              <button
                key={value}
                onClick={() => handleQualityChange(value)}
                title={desc}
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

        {/* Size selector */}
        <div className="space-y-1.5">
          <label className="text-xs text-slate-500 font-mono uppercase tracking-wide">Size</label>
          <div className="flex gap-1.5">
            {SIZE_OPTIONS.map(({ value, label, icon: Icon, hint }) => (
              <button
                key={value}
                onClick={() => setSize(value)}
                title={hint}
                className={`flex-1 flex flex-col items-center justify-center gap-0.5 py-2 rounded-lg text-[11px] font-medium transition-colors border
                  ${size === value
                    ? 'bg-violet-500/15 border-violet-500/40 text-violet-400'
                    : 'bg-white/5 border-white/10 text-slate-400 hover:text-slate-200 hover:bg-white/8'}`}
              >
                <Icon size={13} />
                <span>{label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Generate / Cancel */}
        <div className="flex gap-2">
          <button
            onClick={() => handleGenerate()}
            disabled={!prompt.trim() || generating}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-gradient-to-br from-cyan-500 to-violet-600 text-white text-sm font-medium hover:from-cyan-400 hover:to-violet-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg hover:shadow-cyan-500/20"
          >
            {generating ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
            {generating ? 'Generating…' : 'Generate Image'}
          </button>
          {generating && (
            <button
              onClick={handleCancel}
              title="Cancel"
              className="px-3 py-2.5 rounded-xl bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 transition-colors"
            >
              <XCircle size={16} />
            </button>
          )}
        </div>

        {/* Cost hint + usage */}
        <p className="text-[10px] text-slate-600 text-center">
          ~$0.13/image · {imageUsage.used}/{imageUsage.limit} used this{imageUsage.resetsOn ? ` month` : ' lifetime'}
        </p>
      </div>

      {/* ---- Right panel ---- */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="flex items-center gap-3 mb-6">
          <h2 className="text-base font-semibold text-slate-100">Results</h2>
          {results.length > 0 && (
            <span className="text-[11px] font-mono text-slate-500 bg-white/5 border border-white/10 px-2 py-0.5 rounded-full">
              {results.length}
            </span>
          )}
        </div>

        {results.length === 0 && !generating ? (
          <div className="flex flex-col items-center justify-center h-64 gap-4 text-slate-600">
            <Image size={40} strokeWidth={1} />
            <p className="text-sm">Your generated images will appear here</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {generating && <SkeletonCard />}
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
                  onRerun={() => { setPrompt(result.prompt); handleGenerate(result.prompt); }}
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
