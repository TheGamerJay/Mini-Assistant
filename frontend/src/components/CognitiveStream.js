/**
 * CognitiveStream.js
 *
 * Shows the Mini Assistant's internal pipeline stages in real time while a
 * request is processing. Since the backend exposes a single REST endpoint
 * (no streaming), stages are driven by:
 *   1. Realistic timing estimates per stage
 *   2. Keyword-based intent detection on the prompt (same heuristic the router uses)
 *   3. Real data injection when the API response arrives
 *
 * Props:
 *   active     {boolean}  true while the request is in flight
 *   prompt     {string}   user's input — used for client-side intent heuristic
 *   response   {object}   the resolved API response (null while loading)
 *   onDone     {function} called 2.5s after the final stage completes
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ChevronDown, ChevronUp, CheckCircle2, XCircle, Loader2, Brain, Cpu, Wand2, Eye, Code2, MessageSquare } from 'lucide-react';

// ── Stage definitions ──────────────────────────────────────────────────────

const STAGE_ICONS = {
  router:   Brain,
  prompt:   Wand2,
  comfyui:  Cpu,
  vision:   Eye,
  coder:    Code2,
  llm:      MessageSquare,
};

const PIPELINE = {
  image_generation: [
    { id: 'router',  icon: 'router',  label: 'Router Brain',     desc: 'Analyzing intent & style…',         estimatedMs: 2000 },
    { id: 'prompt',  icon: 'prompt',  label: 'Prompt Builder',   desc: 'Crafting positive & negative prompts…', estimatedMs: 1200 },
    { id: 'comfyui', icon: 'comfyui', label: 'ComfyUI Pipeline', desc: 'Building workflow & running inference…', estimatedMs: 90000 },
    { id: 'vision',  icon: 'vision',  label: 'Vision Brain',     desc: 'Reviewing output quality…',         estimatedMs: 6000 },
  ],
  image_edit: [
    { id: 'router',  icon: 'router',  label: 'Router Brain',     desc: 'Detecting edit intent…',            estimatedMs: 2000 },
    { id: 'prompt',  icon: 'prompt',  label: 'Prompt Builder',   desc: 'Building inpaint prompt…',          estimatedMs: 1000 },
    { id: 'comfyui', icon: 'comfyui', label: 'ComfyUI Pipeline', desc: 'Running inpaint workflow…',         estimatedMs: 60000 },
    { id: 'vision',  icon: 'vision',  label: 'Vision Brain',     desc: 'Reviewing edit result…',            estimatedMs: 5000 },
  ],
  coding: [
    { id: 'router', icon: 'router', label: 'Router Brain', desc: 'Detecting coding intent…',      estimatedMs: 1500 },
    { id: 'coder',  icon: 'coder',  label: 'Coder Brain',  desc: 'Running qwen2.5-coder:14b…',   estimatedMs: 20000 },
  ],
  image_analysis: [
    { id: 'router', icon: 'router', label: 'Router Brain',  desc: 'Detecting analysis intent…', estimatedMs: 1500 },
    { id: 'vision', icon: 'vision', label: 'Vision Brain',  desc: 'Analyzing image content…',   estimatedMs: 10000 },
  ],
  chat: [
    { id: 'router', icon: 'router', label: 'Router Brain',    desc: 'Routing your message…',       estimatedMs: 1500 },
    { id: 'llm',    icon: 'llm',    label: 'Language Model',  desc: 'Generating response…',        estimatedMs: 15000 },
  ],
  planning: [
    { id: 'router', icon: 'router', label: 'Router Brain',    desc: 'Understanding your goal…',    estimatedMs: 1500 },
    { id: 'llm',    icon: 'llm',    label: 'Language Model',  desc: 'Drafting plan…',              estimatedMs: 20000 },
  ],
};

const DEFAULT_PIPELINE = PIPELINE.chat;

// Client-side heuristic — mirrors the router brain keywords
function guessIntent(prompt) {
  const t = prompt.toLowerCase();
  if (/\b(flux|ultra realistic|8k|hyperrealistic)\b/.test(t))  return 'image_generation';
  if (/\b(draw|generate|paint|illustrate|sketch|create an? (image|picture|art|portrait|scene|landscape|character))\b/.test(t)) return 'image_generation';
  if (/\b(anime|manga|waifu|shonen|seinen|shojo|realistic photo|dslr|bokeh|fantasy dragon|rpg|wizard|castle)\b/.test(t)) return 'image_generation';
  if (/\b(edit|modify|inpaint|change the (color|background|hair)|fix this image)\b/.test(t)) return 'image_edit';
  if (/\b(write code|python|javascript|typescript|debug|function|algorithm|script|class|api|sql)\b/.test(t)) return 'coding';
  if (/\b(describe|analyze|what is in|identify|what does this image)\b/.test(t)) return 'image_analysis';
  return 'chat';
}

// ── Stage status helpers ───────────────────────────────────────────────────

const STATUS = { WAITING: 'waiting', ACTIVE: 'active', DONE: 'done', ERROR: 'error' };

function initStages(pipeline) {
  return pipeline.map((s, i) => ({
    ...s,
    status: i === 0 ? STATUS.ACTIVE : STATUS.WAITING,
    result: null,
    progress: null, // 0-100 for comfyui stage
  }));
}

// ── CognitiveStream component ──────────────────────────────────────────────

export default function CognitiveStream({ active, prompt, response, onDone }) {
  const [stages, setStages] = useState([]);
  const [collapsed, setCollapsed] = useState(false);
  const [visible, setVisible] = useState(false);
  const [comfyuiProgress, setComfyuiProgress] = useState(0);

  const intentRef      = useRef('chat');
  const timerRefs      = useRef([]);
  const progressRef    = useRef(null);
  const doneCalledRef  = useRef(false);
  const startTimeRef   = useRef(null);

  // Clear all timers on unmount / reset
  const clearTimers = useCallback(() => {
    timerRefs.current.forEach(clearTimeout);
    timerRefs.current = [];
    if (progressRef.current) clearInterval(progressRef.current);
    progressRef.current = null;
  }, []);

  // Called when the API response arrives — inject real data into stages
  const finalizeStages = useCallback((res) => {
    const rr = res?.route_result || {};
    const isImage = !!res?.image_base64;
    const qualityScore = res?.review?.quality_score;
    const timeTaken = res?.generation_time_ms;
    const checkpoint = rr.selected_checkpoint;
    const workflow   = rr.selected_workflow;
    const intent     = rr.intent || intentRef.current;
    const confidence = rr.confidence;

    setStages(prev => prev.map(s => {
      if (s.status === STATUS.ERROR) return s; // don't overwrite errors
      let result = null;
      if (s.id === 'router') {
        result = [
          `Route: ${(intent || 'chat').replace(/_/g,' ')}`,
          confidence != null ? `Confidence: ${Math.round(confidence * 100)}%` : null,
          rr.style_family ? `Style: ${rr.style_family}${rr.anime_genre ? ' / '+rr.anime_genre : ''}` : null,
        ].filter(Boolean).join('  ·  ');
      }
      if (s.id === 'prompt') {
        result = checkpoint ? `Model: ${checkpoint}` : 'Prompts built';
      }
      if (s.id === 'comfyui') {
        result = [
          workflow ? `Workflow: ${workflow}` : null,
          timeTaken ? `Time: ${(timeTaken/1000).toFixed(1)}s` : null,
          res?.retry_used ? 'Retry used' : null,
        ].filter(Boolean).join('  ·  ');
      }
      if (s.id === 'vision') {
        result = qualityScore != null
          ? `Quality score: ${(qualityScore * 100).toFixed(0)}%`
          : (isImage ? 'Review complete' : null);
      }
      if (s.id === 'coder') {
        result = timeTaken ? `Generated in ${(timeTaken/1000).toFixed(1)}s` : 'Code generated';
      }
      if (s.id === 'llm') {
        result = timeTaken ? `Responded in ${(timeTaken/1000).toFixed(1)}s` : 'Response ready';
      }
      return { ...s, status: STATUS.DONE, progress: null, result };
    }));
  }, []);

  // Drive stage progression with timers
  const runPipeline = useCallback((pipeline) => {
    clearTimers();
    doneCalledRef.current = false;
    startTimeRef.current = Date.now();

    const newStages = initStages(pipeline);
    setStages(newStages);
    setVisible(true);
    setCollapsed(false);
    setComfyuiProgress(0);

    let cursor = 0; // which stage is currently active
    let elapsed = 0;

    pipeline.forEach((stage, i) => {
      if (i === 0) return; // first stage starts immediately

      // Advance to stage i after all previous stages' estimated time
      elapsed += pipeline[i - 1].estimatedMs;
      const delay = elapsed;

      const t = setTimeout(() => {
        setStages(prev => prev.map((s, idx) => {
          if (idx === i - 1) return { ...s, status: STATUS.DONE };
          if (idx === i)     return { ...s, status: STATUS.ACTIVE };
          return s;
        }));
        cursor = i;

        // Fake progress bar for comfyui stage
        if (stage.id === 'comfyui') {
          setComfyuiProgress(0);
          let prog = 0;
          const estimatedMs = stage.estimatedMs;
          const tick = 500;
          const increment = (tick / estimatedMs) * 100 * 0.92; // cap at 92% until real done
          progressRef.current = setInterval(() => {
            prog = Math.min(prog + increment + Math.random() * 0.5, 92);
            setComfyuiProgress(Math.round(prog));
          }, tick);
        }
      }, delay);

      timerRefs.current.push(t);
    });
  }, [clearTimers]);

  // Start pipeline when active turns true
  useEffect(() => {
    if (active && prompt) {
      const intent = guessIntent(prompt);
      intentRef.current = intent;
      const pipeline = PIPELINE[intent] || DEFAULT_PIPELINE;
      runPipeline(pipeline);
    }
  }, [active, prompt]); // eslint-disable-line react-hooks/exhaustive-deps

  // Inject real data + complete when response arrives
  useEffect(() => {
    if (response && stages.length > 0 && !doneCalledRef.current) {
      clearTimers();
      setComfyuiProgress(100);

      // Brief delay so progress bar "hits 100" visually
      setTimeout(() => {
        finalizeStages(response);

        // Auto-collapse + call onDone after 2.5s
        setTimeout(() => {
          setCollapsed(true);
          setTimeout(() => {
            if (!doneCalledRef.current) {
              doneCalledRef.current = true;
              onDone?.();
              setVisible(false);
            }
          }, 600);
        }, 2500);
      }, 300);
    }
  }, [response]); // eslint-disable-line react-hooks/exhaustive-deps

  // Hide when no longer active AND no response yet (cancelled)
  useEffect(() => {
    if (!active && !response && stages.length > 0) {
      clearTimers();
      setStages(prev => prev.map(s =>
        s.status === STATUS.ACTIVE ? { ...s, status: STATUS.ERROR, result: 'Cancelled' } : s
      ));
      setTimeout(() => {
        setVisible(false);
        setStages([]);
      }, 1500);
    }
  }, [active]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => clearTimers(), [clearTimers]);

  if (!visible || stages.length === 0) return null;

  return (
    <div className="mb-3 rounded-xl border border-cyan-500/15 bg-[#0e0e17] overflow-hidden transition-all duration-300">
      {/* Header */}
      <button
        onClick={() => setCollapsed(v => !v)}
        className="w-full flex items-center gap-2.5 px-4 py-2.5 hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-1.5 flex-1 text-left">
          <Loader2 className={`w-3.5 h-3.5 text-cyan-500 ${stages.some(s => s.status === STATUS.ACTIVE) ? 'animate-spin' : 'opacity-0'}`} />
          <span className="text-[11px] font-mono font-semibold text-cyan-500/80 uppercase tracking-widest">
            Cognitive Stream
          </span>
          <span className="text-[10px] font-mono text-slate-600 ml-1">
            {stages.filter(s => s.status === STATUS.DONE).length}/{stages.length} stages
          </span>
        </div>
        {collapsed
          ? <ChevronDown className="w-3.5 h-3.5 text-slate-600" />
          : <ChevronUp   className="w-3.5 h-3.5 text-slate-600" />
        }
      </button>

      {/* Stage list */}
      {!collapsed && (
        <div className="px-4 pb-3 space-y-0">
          {stages.map((stage, idx) => {
            const Icon = STAGE_ICONS[stage.icon] || Brain;
            const isActive = stage.status === STATUS.ACTIVE;
            const isDone   = stage.status === STATUS.DONE;
            const isError  = stage.status === STATUS.ERROR;
            const isWait   = stage.status === STATUS.WAITING;

            return (
              <div key={stage.id} className="relative">
                {/* Connector line */}
                {idx < stages.length - 1 && (
                  <div className={`absolute left-[19px] top-8 w-px h-4 transition-colors duration-500 ${
                    isDone ? 'bg-cyan-500/40' : 'bg-white/5'
                  }`} />
                )}

                <div className={`flex items-start gap-3 py-2 rounded-lg px-2 transition-all duration-300 ${
                  isActive ? 'bg-cyan-500/5' : ''
                }`}>
                  {/* Status icon */}
                  <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5 transition-all duration-300 ${
                    isDone  ? 'bg-cyan-500/15 text-cyan-400' :
                    isActive ? 'bg-cyan-500/20 text-cyan-300' :
                    isError  ? 'bg-red-500/15 text-red-400'  :
                    'bg-white/5 text-slate-600'
                  }`}>
                    {isDone  && <CheckCircle2 className="w-3.5 h-3.5" />}
                    {isError  && <XCircle     className="w-3.5 h-3.5" />}
                    {isActive && <Loader2     className="w-3.5 h-3.5 animate-spin" />}
                    {isWait   && <Icon        className="w-3 h-3 opacity-30" />}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-[12px] font-semibold transition-colors duration-300 ${
                        isDone  ? 'text-cyan-400/90'  :
                        isActive ? 'text-cyan-300'    :
                        isError  ? 'text-red-400'     :
                        'text-slate-600'
                      }`}>
                        {stage.label}
                      </span>
                      {isDone && (
                        <span className="text-[10px] font-mono text-emerald-500/70 uppercase tracking-wider">done</span>
                      )}
                      {isActive && (
                        <span className="text-[10px] font-mono text-cyan-500/60 animate-pulse uppercase tracking-wider">running</span>
                      )}
                    </div>

                    {/* Description or result */}
                    <p className={`text-[11px] font-mono mt-0.5 transition-all duration-300 ${
                      isDone   ? 'text-slate-400'   :
                      isActive ? 'text-slate-400'   :
                      'text-slate-600'
                    }`}>
                      {isDone && stage.result ? stage.result : stage.desc}
                    </p>

                    {/* ComfyUI progress bar */}
                    {stage.id === 'comfyui' && isActive && (
                      <div className="mt-2 flex items-center gap-2">
                        <div className="flex-1 h-1 rounded-full bg-white/5 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-violet-500 transition-all duration-500"
                            style={{ width: `${comfyuiProgress}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-mono text-slate-500 w-8 text-right">
                          {comfyuiProgress}%
                        </span>
                      </div>
                    )}
                    {stage.id === 'comfyui' && isDone && (
                      <div className="mt-1.5 h-1 rounded-full bg-cyan-500/20 overflow-hidden">
                        <div className="h-full w-full rounded-full bg-gradient-to-r from-cyan-500 to-violet-500" />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
