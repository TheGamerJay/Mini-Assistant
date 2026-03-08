import React, { useState, useRef } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import {
  Brain, Loader2, Send, CheckCircle, XCircle,
  Code, Search, Bug, FlaskConical, Zap, ChevronDown, ChevronUp, Network
} from 'lucide-react';
import { usePersist } from '../../hooks/usePersist';

const BRAINS = [
  { id: 'manager',   label: 'Manager',   icon: Network,      model: 'glm-5:cloud',              color: 'cyan'   },
  { id: 'analysis',  label: 'Analysis',  icon: Search,       model: 'glm-5:cloud',              color: 'violet' },
  { id: 'coder',     label: 'Coder',     icon: Code,         model: 'devstral-2:cloud',         color: 'green'  },
  { id: 'tester',    label: 'Tester',    icon: FlaskConical, model: 'devstral-small-2:cloud',   color: 'yellow' },
  { id: 'debugger',  label: 'Debugger',  icon: Bug,          model: 'qwen3-coder-next:cloud',   color: 'red'    },
  { id: 'fast_chat', label: 'Fast Chat', icon: Zap,          model: 'minimax-m2.1:cloud',       color: 'orange' },
];

const STATUS_BRAIN_MAP = {
  routing:    'manager',
  routed:     'manager',
  responding: 'fast_chat',
  planning:   'analysis',
  planned:    'analysis',
  coding:     'coder',
  coded:      'coder',
  testing:    'tester',
  debugging:  'debugger',
  finalizing: 'manager',
};

const COLOR_CLASSES = {
  cyan:   { active: 'border-cyan-500/70 text-cyan-300 bg-cyan-500/15 shadow-[0_0_12px_rgba(0,243,255,0.3)]',   idle: 'border-slate-700/40 text-slate-600 bg-black/20' },
  violet: { active: 'border-violet-500/70 text-violet-300 bg-violet-500/15 shadow-[0_0_12px_rgba(147,51,234,0.3)]', idle: 'border-slate-700/40 text-slate-600 bg-black/20' },
  green:  { active: 'border-green-500/70 text-green-300 bg-green-500/15 shadow-[0_0_12px_rgba(34,197,94,0.3)]',   idle: 'border-slate-700/40 text-slate-600 bg-black/20' },
  yellow: { active: 'border-yellow-500/70 text-yellow-300 bg-yellow-500/15 shadow-[0_0_12px_rgba(234,179,8,0.3)]', idle: 'border-slate-700/40 text-slate-600 bg-black/20' },
  red:    { active: 'border-red-500/70 text-red-300 bg-red-500/15 shadow-[0_0_12px_rgba(239,68,68,0.3)]',       idle: 'border-slate-700/40 text-slate-600 bg-black/20' },
  orange: { active: 'border-orange-500/70 text-orange-300 bg-orange-500/15 shadow-[0_0_12px_rgba(249,115,22,0.3)]', idle: 'border-slate-700/40 text-slate-600 bg-black/20' },
};

const STATUS_LABEL = {
  routing:    'Manager routing request...',
  routed:     'Route decided',
  responding: 'Fast Chat generating response...',
  planning:   'Analysis Brain planning & researching...',
  planned:    'Plan ready',
  coding:     'Coder Brain writing code...',
  coded:      'Code generated',
  testing:    'Tester Brain validating output...',
  debugging:  'Debug Brain applying fixes...',
  finalizing: 'Manager compiling final response...',
  thinking:   'Processing...',
  done:       'Complete',
  failed:     'Failed',
};

const AgentPipeline = () => {
  const [task, setTask] = usePersist('ma_pipeline_task', '');
  const [running, setRunning] = useState(false);
  const [ctx, setCtx] = useState(null);
  const [showContext, setShowContext] = useState(false);
  const abortRef = useRef(null);

  const activeBrainId = ctx ? STATUS_BRAIN_MAP[ctx.status] : null;
  const isDone = ctx?.status === 'done';
  const isFailed = ctx?.status === 'failed';

  const runPipeline = async () => {
    if (!task.trim() || running) return;
    setRunning(true);
    setCtx(null);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const baseURL = axiosInstance.defaults.baseURL;
      const response = await fetch(`${baseURL}/agent/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        for (const line of text.split('\n')) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.status !== 'thinking') {
                setCtx(data);
              }
            } catch (_) {}
          }
        }
      }
      toast.success('Pipeline complete!');
    } catch (err) {
      if (err.name !== 'AbortError') {
        toast.error('Pipeline failed');
        console.error(err);
      }
    } finally {
      setRunning(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      runPipeline();
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="agent-pipeline">

      {/* ── Header ── */}
      <div className="p-5 border-b border-cyan-500/20 bg-black/40 flex-shrink-0">
        <div className="flex items-center gap-3 mb-4">
          <Brain className="w-7 h-7 text-cyan-400" />
          <div>
            <h2
              className="text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase"
              style={{ fontFamily: 'Rajdhani, sans-serif' }}
            >
              AGENT PIPELINE
            </h2>
            <p className="text-xs text-slate-400 font-mono mt-0.5">MULTI-BRAIN AI EXECUTION SYSTEM</p>
          </div>
        </div>

        {/* Brain indicators */}
        <div className="grid grid-cols-6 gap-2 mb-4">
          {BRAINS.map(brain => {
            const Icon = brain.icon;
            const isActive = activeBrainId === brain.id && running;
            const wasActive = activeBrainId === brain.id && isDone;
            const colors = COLOR_CLASSES[brain.color];
            return (
              <div
                key={brain.id}
                className={`p-2 border rounded-sm text-center transition-all duration-300 ${
                  isActive ? colors.active + ' animate-pulse' :
                  wasActive ? colors.active + ' opacity-60' :
                  colors.idle
                }`}
              >
                <Icon className="w-4 h-4 mx-auto mb-1" />
                <div className="text-xs font-mono uppercase tracking-wider leading-tight">{brain.label}</div>
                <div className="text-xs mt-0.5 opacity-60 font-mono truncate" title={brain.model}>
                  {brain.model.split(':')[0]}
                </div>
              </div>
            );
          })}
        </div>

        {/* Task input */}
        <div className="flex gap-3">
          <textarea
            value={task}
            onChange={e => setTask(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Describe your task... e.g. Build a FastAPI login system with JWT auth and PostgreSQL"
            className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono text-sm p-3 outline-none resize-none"
            rows={2}
            disabled={running}
          />
          <button
            onClick={runPipeline}
            disabled={running || !task.trim()}
            className="px-6 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-sm flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            {running ? 'RUNNING' : 'RUN'}
          </button>
        </div>
      </div>

      {/* ── Content ── */}
      <div className="flex-1 overflow-auto p-5 space-y-4">

        {/* Empty state */}
        {!ctx && !running && (
          <div className="flex items-center justify-center h-full py-20">
            <div className="text-center space-y-3">
              <Brain className="w-16 h-16 mx-auto text-cyan-500/20" />
              <p className="text-slate-500 font-mono text-sm">Enter a task to activate the agent pipeline</p>
              <p className="text-slate-600 font-mono text-xs">
                Simple questions → Fast Chat &nbsp;|&nbsp; Complex tasks → Full Pipeline
              </p>
            </div>
          </div>
        )}

        {/* Status bar */}
        {ctx && (
          <div className={`p-3 border rounded-sm flex items-center gap-3 ${
            isFailed ? 'border-red-500/30 bg-red-500/10' :
            isDone   ? 'border-green-500/30 bg-green-500/10' :
                       'border-cyan-500/20 bg-black/30'
          }`}>
            {isFailed ? <XCircle className="w-5 h-5 text-red-400 flex-shrink-0" /> :
             isDone   ? <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0" /> :
                        <Loader2 className="w-5 h-5 animate-spin text-cyan-400 flex-shrink-0" />}
            <div>
              <span className={`text-sm font-mono uppercase tracking-wider ${
                isFailed ? 'text-red-400' : isDone ? 'text-green-400' : 'text-cyan-400'
              }`}>
                {STATUS_LABEL[ctx.status] || ctx.status}
              </span>
              {isDone && ctx.route && (
                <span className="ml-3 text-xs text-slate-500 font-mono">
                  {ctx.route === 'fast_chat' ? 'FAST CHAT route' : `FULL PIPELINE · ${ctx.debug_attempts} debug round(s)`}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Execution plan */}
        {ctx?.plan?.length > 0 && (
          <div className="p-4 bg-black/40 border border-violet-500/20 rounded-sm">
            <div className="text-xs font-mono text-violet-400 uppercase tracking-wider mb-3">
              EXECUTION PLAN — Analysis Brain
            </div>
            <ol className="space-y-2">
              {ctx.plan.map((step, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-slate-300 font-mono">
                  <span className="text-violet-400 flex-shrink-0 w-5">{i + 1}.</span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
            {ctx.research && (
              <div className="mt-3 pt-3 border-t border-violet-500/10">
                <div className="text-xs font-mono text-violet-400/70 uppercase mb-1">Research Notes</div>
                <p className="text-xs text-slate-400 font-mono">{ctx.research}</p>
              </div>
            )}
          </div>
        )}

        {/* Test result badge */}
        {ctx?.test_results && (
          <div className={`p-3 border rounded-sm flex items-center gap-2 text-sm font-mono ${
            ctx.test_results === 'pass'
              ? 'border-green-500/30 text-green-400 bg-green-500/10'
              : 'border-red-500/30 text-red-400 bg-red-500/10'
          }`}>
            {ctx.test_results === 'pass'
              ? <CheckCircle className="w-4 h-4 flex-shrink-0" />
              : <XCircle className="w-4 h-4 flex-shrink-0" />}
            <span>
              TESTS {ctx.test_results.toUpperCase()}
              {ctx.debug_attempts > 0 && ` — resolved after ${ctx.debug_attempts} debug cycle(s)`}
            </span>
          </div>
        )}

        {/* Final response */}
        {ctx?.final_response && (
          <div className="p-4 bg-black/40 border border-cyan-500/20 rounded-sm">
            <div className="text-xs font-mono text-cyan-400 uppercase tracking-wider mb-3">
              FINAL OUTPUT — Manager Brain
            </div>
            <div className="text-sm text-slate-300 whitespace-pre-wrap font-mono leading-relaxed">
              {ctx.final_response}
            </div>
          </div>
        )}

        {/* Shared context inspector (collapsible) */}
        {ctx && (
          <div className="border border-slate-700/40 rounded-sm overflow-hidden">
            <button
              onClick={() => setShowContext(v => !v)}
              className="w-full p-3 bg-black/20 flex items-center justify-between text-xs font-mono text-slate-500 hover:text-slate-300 uppercase tracking-wider transition-colors"
            >
              <span>SHARED TASK CONTEXT</span>
              {showContext ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
            {showContext && (
              <pre className="p-4 text-xs text-slate-400 font-mono overflow-auto bg-black/30 max-h-80">
                {JSON.stringify(ctx, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default AgentPipeline;
