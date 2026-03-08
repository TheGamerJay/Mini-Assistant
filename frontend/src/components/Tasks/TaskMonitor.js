import React, { useState, useEffect, useRef, useCallback } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import {
  Activity, CheckCircle, XCircle, Clock, Loader2, MinusCircle,
  RotateCcw, X, Play, ChevronRight, ChevronDown, AlertTriangle,
  Shield, Archive, FileText, Cpu, Zap, RefreshCw, Trash2, Plus,
  Send, CornerDownLeft,
} from 'lucide-react';

// ── Constants ──────────────────────────────────────────────────────────────────

const POLL_INTERVAL_ACTIVE = 2000;   // 2 s when task is running
const POLL_INTERVAL_IDLE   = 10000;  // 10 s when all terminal

const ACTIVE_STATES = new Set([
  'created', 'loading_context', 'planning', 'awaiting_approval',
  'coding', 'reviewing', 'testing', 'fixing', 'deploying', 'documenting',
]);

const TERMINAL_STATES = new Set(['completed', 'failed', 'cancelled']);

const STATE_CONFIG = {
  created:           { color: 'text-slate-400',   bg: 'bg-slate-900/60',   border: 'border-slate-600/40',   dot: 'bg-slate-500'   },
  loading_context:   { color: 'text-sky-400',     bg: 'bg-sky-950/40',     border: 'border-sky-600/40',     dot: 'bg-sky-400'     },
  planning:          { color: 'text-violet-400',  bg: 'bg-violet-950/40',  border: 'border-violet-600/40',  dot: 'bg-violet-400'  },
  awaiting_approval: { color: 'text-amber-400',   bg: 'bg-amber-950/40',   border: 'border-amber-600/40',   dot: 'bg-amber-400'   },
  coding:            { color: 'text-cyan-400',    bg: 'bg-cyan-950/40',    border: 'border-cyan-600/40',    dot: 'bg-cyan-400'    },
  reviewing:         { color: 'text-purple-400',  bg: 'bg-purple-950/40',  border: 'border-purple-600/40',  dot: 'bg-purple-400'  },
  testing:           { color: 'text-yellow-400',  bg: 'bg-yellow-950/40',  border: 'border-yellow-600/40',  dot: 'bg-yellow-400'  },
  fixing:            { color: 'text-orange-400',  bg: 'bg-orange-950/40',  border: 'border-orange-600/40',  dot: 'bg-orange-400'  },
  deploying:         { color: 'text-emerald-400', bg: 'bg-emerald-950/40', border: 'border-emerald-600/40', dot: 'bg-emerald-400' },
  documenting:       { color: 'text-teal-400',    bg: 'bg-teal-950/40',    border: 'border-teal-600/40',    dot: 'bg-teal-400'    },
  completed:         { color: 'text-green-400',   bg: 'bg-green-950/40',   border: 'border-green-600/40',   dot: 'bg-green-400'   },
  failed:            { color: 'text-red-400',     bg: 'bg-red-950/40',     border: 'border-red-600/40',     dot: 'bg-red-400'     },
  cancelled:         { color: 'text-slate-500',   bg: 'bg-slate-900/40',   border: 'border-slate-700/40',   dot: 'bg-slate-600'   },
};

const STEP_STATUS_CONFIG = {
  pending:     { icon: Clock,       color: 'text-slate-500', label: 'Pending'     },
  in_progress: { icon: Loader2,     color: 'text-cyan-400',  label: 'Running',  spin: true },
  done:        { icon: CheckCircle, color: 'text-green-400', label: 'Done'        },
  failed:      { icon: XCircle,     color: 'text-red-400',   label: 'Failed'      },
  skipped:     { icon: MinusCircle, color: 'text-slate-600', label: 'Skipped'     },
};

const TYPE_LABELS = {
  build: 'BUILD', fix: 'FIX', test: 'TEST', review: 'REVIEW',
  deploy: 'DEPLOY', generic: 'TASK',
};

const TYPE_COLORS = {
  build:   'text-cyan-400 border-cyan-700/40 bg-cyan-950/30',
  fix:     'text-orange-400 border-orange-700/40 bg-orange-950/30',
  test:    'text-yellow-400 border-yellow-700/40 bg-yellow-950/30',
  review:  'text-purple-400 border-purple-700/40 bg-purple-950/30',
  deploy:  'text-emerald-400 border-emerald-700/40 bg-emerald-950/30',
  generic: 'text-slate-400 border-slate-700/40 bg-slate-900/30',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmt = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

const fmtRelative = (iso) => {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  return `${Math.round(diff / 3600)}h ago`;
};

const StateTag = ({ state, compact }) => {
  const cfg = STATE_CONFIG[state] || STATE_CONFIG.created;
  const isActive = ACTIVE_STATES.has(state);
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm border text-[10px] font-mono uppercase tracking-wider ${cfg.color} ${cfg.border} ${cfg.bg}`}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${cfg.dot} ${isActive ? 'animate-pulse' : ''}`} />
      {compact ? state.replace('_', ' ') : state.replace(/_/g, ' ')}
    </span>
  );
};

const StepIcon = ({ status }) => {
  const cfg = STEP_STATUS_CONFIG[status] || STEP_STATUS_CONFIG.pending;
  const Icon = cfg.icon;
  return <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${cfg.color} ${cfg.spin ? 'animate-spin' : ''}`} />;
};

// ── Sub-components ────────────────────────────────────────────────────────────

const StepList = ({ steps }) => {
  const [expanded, setExpanded] = useState({});
  if (!steps?.length) return <p className="text-[10px] text-slate-600 font-mono py-2">No steps yet.</p>;

  return (
    <div className="space-y-1">
      {steps.map((step, i) => {
        const isOpen = expanded[step.step_id];
        const hasDetail = step.output || step.error || step.swarm_task_ids?.length;
        return (
          <div key={step.step_id || i} className="border border-white/5 rounded-sm overflow-hidden">
            <button
              onClick={() => hasDetail && setExpanded(p => ({ ...p, [step.step_id]: !p[step.step_id] }))}
              className={`w-full flex items-center gap-2 px-3 py-2 text-left ${hasDetail ? 'cursor-pointer hover:bg-white/5' : 'cursor-default'}`}
            >
              <StepIcon status={step.status} />
              <span className="text-[11px] font-mono text-slate-300 flex-1">{step.name}</span>
              <span className="text-[9px] font-mono text-slate-600">{step.agent_name}</span>
              <StateTag state={step.state} compact />
              <span className={`text-[9px] font-mono ${STEP_STATUS_CONFIG[step.status]?.color || 'text-slate-600'}`}>
                {STEP_STATUS_CONFIG[step.status]?.label}
              </span>
              {step.started_at && (
                <span className="text-[9px] font-mono text-slate-700">{fmt(step.started_at)}</span>
              )}
              {hasDetail && (
                isOpen ? <ChevronDown className="w-3 h-3 text-slate-600" /> : <ChevronRight className="w-3 h-3 text-slate-600" />
              )}
            </button>
            {isOpen && (
              <div className="px-3 pb-2 space-y-1.5 bg-black/30">
                {step.output && (
                  <div>
                    <p className="text-[9px] font-mono text-slate-600 uppercase mb-0.5">Output</p>
                    <pre className="text-[9px] font-mono text-slate-400 whitespace-pre-wrap break-all max-h-24 overflow-y-auto">{step.output}</pre>
                  </div>
                )}
                {step.error && (
                  <div>
                    <p className="text-[9px] font-mono text-red-500 uppercase mb-0.5">Error</p>
                    <pre className="text-[9px] font-mono text-red-400 whitespace-pre-wrap break-all max-h-16 overflow-y-auto">{step.error}</pre>
                  </div>
                )}
                {step.swarm_task_ids?.length > 0 && (
                  <p className="text-[9px] font-mono text-slate-700">
                    Swarm tasks: {step.swarm_task_ids.join(', ')}
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

const StateTimeline = ({ history }) => {
  if (!history?.length) return null;
  return (
    <div className="space-y-0">
      {history.map((t, i) => (
        <div key={i} className="flex items-start gap-2 py-1">
          <div className="flex flex-col items-center gap-0">
            <div className="w-1.5 h-1.5 rounded-full bg-cyan-500/60 mt-1 flex-shrink-0" />
            {i < history.length - 1 && <div className="w-px flex-1 bg-cyan-500/10 mt-0.5" style={{ height: 16 }} />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[9px] font-mono text-slate-600">{t.from} →</span>
              <StateTag state={t.to} compact />
              <span className="text-[9px] font-mono text-slate-700 ml-auto">{fmt(t.timestamp)}</span>
            </div>
            {t.reason && (
              <p className="text-[9px] font-mono text-slate-700 truncate">{t.reason}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

const CheckpointList = ({ checkpoints, taskId, onRollback, disabled }) => {
  if (!checkpoints?.length) return <p className="text-[10px] text-slate-600 font-mono">No checkpoints yet.</p>;
  return (
    <div className="space-y-1">
      {checkpoints.map((cp, i) => (
        <div key={i} className="flex items-center gap-2 px-2 py-1.5 bg-black/30 rounded-sm border border-white/5">
          <Archive className="w-3 h-3 text-violet-400 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-mono text-violet-300">{cp.name}</p>
            <p className="text-[9px] font-mono text-slate-600">{cp.state} · {fmt(cp.timestamp)}</p>
          </div>
          <button
            onClick={() => onRollback(taskId, cp.name)}
            disabled={disabled}
            className="flex items-center gap-1 px-2 py-0.5 text-[9px] font-mono text-violet-400 border border-violet-700/40 rounded-sm hover:bg-violet-500/10 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <CornerDownLeft className="w-2.5 h-2.5" /> Rollback
          </button>
        </div>
      ))}
    </div>
  );
};

const PreservedOutputs = ({ outputs }) => {
  if (!outputs || !Object.keys(outputs).length) return null;
  return (
    <div className="space-y-1">
      {Object.entries(outputs).map(([k, v]) => (
        <div key={k} className="px-2 py-1 bg-black/30 rounded-sm border border-white/5">
          <p className="text-[9px] font-mono text-slate-600 uppercase mb-0.5">{k.replace(/_/g, ' ')}</p>
          <pre className="text-[9px] font-mono text-slate-400 whitespace-pre-wrap break-all max-h-12 overflow-y-auto">
            {typeof v === 'string' ? v : JSON.stringify(v, null, 2)}
          </pre>
        </div>
      ))}
    </div>
  );
};

// ── Task Detail Panel ─────────────────────────────────────────────────────────

const TaskDetail = ({ task, onResume, onCancel, onRollback, onDelete, actionLoading }) => {
  const [activeSection, setActiveSection] = useState('steps');
  if (!task) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-slate-600 font-mono text-sm">Select a task to view details</p>
      </div>
    );
  }

  const isActive    = ACTIVE_STATES.has(task.current_state);
  const isResumable = task.current_state === 'failed';
  const isCancellable = isActive;
  const isDone      = TERMINAL_STATES.has(task.current_state);
  const sections    = ['steps', 'timeline', 'checkpoints', 'outputs'];

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Task header */}
      <div className="px-4 py-3 border-b border-cyan-500/10 bg-black/40 flex-shrink-0">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-[10px] font-mono uppercase border px-1.5 py-0.5 rounded-sm ${TYPE_COLORS[task.task_type] || TYPE_COLORS.generic}`}>
                {TYPE_LABELS[task.task_type] || task.task_type}
              </span>
              <StateTag state={task.current_state} />
              {task.retry_count > 0 && (
                <span className="text-[9px] font-mono text-amber-500 border border-amber-700/40 px-1.5 py-0.5 rounded-sm bg-amber-950/30">
                  {task.retry_count}/{task.max_retries} retries
                </span>
              )}
            </div>
            <p className="text-[11px] font-mono text-slate-300 leading-relaxed line-clamp-3">{task.goal}</p>
            <div className="flex items-center gap-3 mt-1">
              <span className="text-[9px] font-mono text-slate-700">{task.task_id.slice(0, 8)}</span>
              <span className="text-[9px] font-mono text-slate-700">Created {fmtRelative(task.created_at)}</span>
              {task.assigned_agents?.length > 0 && (
                <span className="text-[9px] font-mono text-slate-700">
                  Agents: {task.assigned_agents.join(', ')}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 mt-2">
          {isResumable && (
            <button
              onClick={() => onResume(task.task_id)}
              disabled={actionLoading}
              className="flex items-center gap-1.5 px-3 py-1 text-[10px] font-mono uppercase text-emerald-400 border border-emerald-700/40 rounded-sm hover:bg-emerald-500/10 disabled:opacity-40"
            >
              {actionLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
              Resume
            </button>
          )}
          {isCancellable && (
            <button
              onClick={() => onCancel(task.task_id)}
              disabled={actionLoading}
              className="flex items-center gap-1.5 px-3 py-1 text-[10px] font-mono uppercase text-amber-400 border border-amber-700/40 rounded-sm hover:bg-amber-500/10 disabled:opacity-40"
            >
              <X className="w-3 h-3" /> Cancel
            </button>
          )}
          {isDone && (
            <button
              onClick={() => onDelete(task.task_id)}
              disabled={actionLoading}
              className="flex items-center gap-1.5 px-3 py-1 text-[10px] font-mono uppercase text-red-500 border border-red-700/40 rounded-sm hover:bg-red-500/10 disabled:opacity-40"
            >
              <Trash2 className="w-3 h-3" /> Delete
            </button>
          )}
        </div>
      </div>

      {/* Failure summary */}
      {(task.failure_summary || task.failure_reason) && (
        <div className="mx-4 mt-3 flex-shrink-0 px-3 py-2 bg-red-950/40 border border-red-800/40 rounded-sm">
          <div className="flex items-center gap-1.5 mb-1">
            <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
            <span className="text-[10px] font-mono text-red-400 uppercase">Failure Summary</span>
          </div>
          <p className="text-[10px] font-mono text-red-300 leading-relaxed">
            {task.failure_summary || task.failure_reason}
          </p>
          {task.preserved_outputs?.last_checkpoint && (
            <p className="text-[9px] font-mono text-red-500 mt-1">
              Last checkpoint: {task.preserved_outputs.last_checkpoint}
            </p>
          )}
        </div>
      )}

      {/* Result */}
      {task.current_state === 'completed' && task.result && (
        <div className="mx-4 mt-3 flex-shrink-0 px-3 py-2 bg-green-950/40 border border-green-800/40 rounded-sm">
          <div className="flex items-center gap-1.5 mb-1">
            <CheckCircle className="w-3.5 h-3.5 text-green-400" />
            <span className="text-[10px] font-mono text-green-400 uppercase">Result</span>
          </div>
          <pre className="text-[10px] font-mono text-green-300 whitespace-pre-wrap break-all max-h-24 overflow-y-auto">{task.result}</pre>
        </div>
      )}

      {/* Section tabs */}
      <div className="flex items-center border-b border-cyan-500/10 bg-black/20 flex-shrink-0 px-4 mt-3">
        {sections.map(s => (
          <button
            key={s}
            onClick={() => setActiveSection(s)}
            className={`px-3 py-1.5 text-[10px] font-mono uppercase border-b-2 transition-colors ${
              activeSection === s
                ? 'border-cyan-400 text-cyan-400'
                : 'border-transparent text-slate-600 hover:text-slate-400'
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Section content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {activeSection === 'steps' && (
          <StepList steps={task.steps} />
        )}
        {activeSection === 'timeline' && (
          <StateTimeline history={task.state_history} />
        )}
        {activeSection === 'checkpoints' && (
          <CheckpointList
            checkpoints={task.checkpoints}
            taskId={task.task_id}
            onRollback={onRollback}
            disabled={actionLoading || isActive}
          />
        )}
        {activeSection === 'outputs' && (
          <PreservedOutputs outputs={task.preserved_outputs} />
        )}
      </div>
    </div>
  );
};

// ── Task List ─────────────────────────────────────────────────────────────────

const TaskListItem = ({ task, selected, onClick }) => {
  const cfg     = STATE_CONFIG[task.current_state] || STATE_CONFIG.created;
  const isActive = ACTIVE_STATES.has(task.current_state);
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2.5 border-b border-white/5 transition-colors ${
        selected ? 'bg-cyan-500/10' : 'hover:bg-white/5'
      }`}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${cfg.dot} ${isActive ? 'animate-pulse' : ''}`} />
        <span className={`text-[9px] font-mono uppercase ${TYPE_COLORS[task.task_type]?.split(' ')[0] || 'text-slate-500'}`}>
          {TYPE_LABELS[task.task_type] || task.task_type}
        </span>
        <StateTag state={task.current_state} compact />
        <span className="text-[9px] font-mono text-slate-700 ml-auto">{fmtRelative(task.created_at)}</span>
      </div>
      <p className="text-[10px] font-mono text-slate-400 truncate">{task.goal}</p>
      <p className="text-[9px] font-mono text-slate-700">{task.task_id?.slice(0, 8)}</p>
    </button>
  );
};

// ── New Task Form ─────────────────────────────────────────────────────────────

const NewTaskForm = ({ onCreate, loading }) => {
  const [goal, setGoal] = useState('');

  const submit = () => {
    if (!goal.trim() || loading) return;
    onCreate(goal.trim());
    setGoal('');
  };

  return (
    <div className="p-3 border-b border-cyan-500/10 bg-black/40 flex-shrink-0">
      <div className="flex gap-2">
        <textarea
          value={goal}
          onChange={e => setGoal(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
          placeholder="Describe your task... (build / fix / test / review / deploy)"
          rows={2}
          className="flex-1 bg-black/50 border border-cyan-900/40 text-cyan-100 placeholder:text-slate-700 rounded-sm font-mono text-[11px] p-2 outline-none resize-none focus:border-cyan-500/60"
          disabled={loading}
        />
        <button
          onClick={submit}
          disabled={!goal.trim() || loading}
          className="px-3 bg-gradient-to-r from-cyan-500 to-violet-600 text-white rounded-sm hover:from-cyan-400 hover:to-violet-500 disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );
};

// ── Main TaskMonitor Component ─────────────────────────────────────────────────

const TaskMonitor = () => {
  const [tasks,          setTasks]          = useState([]);   // summary list
  const [selectedId,     setSelectedId]     = useState(null);
  const [selectedTask,   setSelectedTask]   = useState(null);
  const [filter,         setFilter]         = useState('all');
  const [actionLoading,  setActionLoading]  = useState(false);
  const [creating,       setCreating]       = useState(false);
  const pollRef = useRef(null);

  // ── Polling ──────────────────────────────────────────────────────────────────

  const hasActiveTasks = tasks.some(t => ACTIVE_STATES.has(t.current_state));

  const fetchList = useCallback(async () => {
    try {
      const res = await axiosInstance.get('/tasks', { params: { limit: 100 } });
      setTasks(res.data || []);
    } catch (_) {}
  }, []);

  const fetchSelected = useCallback(async (id) => {
    if (!id) return;
    try {
      const res = await axiosInstance.get(`/tasks/${id}`);
      setSelectedTask(res.data);
    } catch (_) {}
  }, []);

  const poll = useCallback(async () => {
    await fetchList();
    if (selectedId) await fetchSelected(selectedId);
  }, [fetchList, fetchSelected, selectedId]);

  useEffect(() => {
    poll();
    const interval = hasActiveTasks ? POLL_INTERVAL_ACTIVE : POLL_INTERVAL_IDLE;
    pollRef.current = setInterval(poll, interval);
    return () => clearInterval(pollRef.current);
  }, [poll, hasActiveTasks]);

  // Refresh immediately when a task is selected
  const selectTask = async (id) => {
    setSelectedId(id);
    try {
      const res = await axiosInstance.get(`/tasks/${id}`);
      setSelectedTask(res.data);
    } catch (_) {}
  };

  // ── Actions ──────────────────────────────────────────────────────────────────

  const handleCreate = async (goal) => {
    setCreating(true);
    try {
      const res = await axiosInstance.post('/tasks', { goal });
      setTasks(prev => [res.data, ...prev]);
      setSelectedId(res.data.task_id);
      setSelectedTask(res.data);
      toast.success('Task created and running');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to create task');
    } finally {
      setCreating(false);
    }
  };

  const handleResume = async (taskId) => {
    setActionLoading(true);
    try {
      const res = await axiosInstance.post(`/tasks/${taskId}/resume`);
      setSelectedTask(res.data);
      toast.success('Task resumed');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Resume failed');
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async (taskId) => {
    setActionLoading(true);
    try {
      const res = await axiosInstance.post(`/tasks/${taskId}/cancel`);
      setSelectedTask(res.data);
      fetchList();
      toast.success('Task cancelled');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Cancel failed');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRollback = async (taskId, checkpointName) => {
    setActionLoading(true);
    try {
      const res = await axiosInstance.post(`/tasks/${taskId}/rollback/${checkpointName}`);
      setSelectedTask(res.data);
      toast.success(`Rolled back to '${checkpointName}' — click Resume to re-run`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Rollback failed');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async (taskId) => {
    setActionLoading(true);
    try {
      await axiosInstance.delete(`/tasks/${taskId}`);
      setTasks(prev => prev.filter(t => t.task_id !== taskId));
      if (selectedId === taskId) { setSelectedId(null); setSelectedTask(null); }
      toast.success('Task deleted');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Delete failed');
    } finally {
      setActionLoading(false);
    }
  };

  // ── Filter ────────────────────────────────────────────────────────────────────

  const filtered = tasks.filter(t => {
    if (filter === 'active')    return ACTIVE_STATES.has(t.current_state);
    if (filter === 'completed') return t.current_state === 'completed';
    if (filter === 'failed')    return t.current_state === 'failed';
    return true;
  });

  const activeCnt    = tasks.filter(t => ACTIVE_STATES.has(t.current_state)).length;
  const failedCnt    = tasks.filter(t => t.current_state === 'failed').length;
  const completedCnt = tasks.filter(t => t.current_state === 'completed').length;

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50">
      {/* Header */}
      <div className="p-5 border-b border-cyan-500/20 bg-black/40 flex-shrink-0">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <Cpu className="w-6 h-6 text-cyan-400" />
            <div>
              <h2 className="text-xl font-bold text-cyan-400 uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
                TASK MONITOR
              </h2>
              <p className="text-[10px] font-mono text-slate-600 uppercase tracking-widest">ORCHESTRATOR STATE MACHINE</p>
            </div>
          </div>
          <button
            onClick={fetchList}
            className="p-2 text-slate-500 hover:text-cyan-400 transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
        {/* Summary badges */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-cyan-400 border border-cyan-700/40 px-2 py-0.5 rounded-sm bg-cyan-950/30">
            {activeCnt} active
          </span>
          <span className="text-[10px] font-mono text-green-400 border border-green-700/40 px-2 py-0.5 rounded-sm bg-green-950/30">
            {completedCnt} done
          </span>
          {failedCnt > 0 && (
            <span className="text-[10px] font-mono text-red-400 border border-red-700/40 px-2 py-0.5 rounded-sm bg-red-950/30">
              {failedCnt} failed
            </span>
          )}
          <span className="text-[10px] font-mono text-slate-700 ml-auto">
            {tasks.length} total · polling {hasActiveTasks ? '2s' : '10s'}
          </span>
        </div>
      </div>

      {/* Body: split list + detail */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: task list */}
        <div className="w-72 flex-shrink-0 flex flex-col border-r border-cyan-500/10 overflow-hidden">
          {/* New task form */}
          <NewTaskForm onCreate={handleCreate} loading={creating} />

          {/* Filter tabs */}
          <div className="flex border-b border-cyan-500/10 flex-shrink-0">
            {[['all', 'All'], ['active', 'Active'], ['completed', '✓ Done'], ['failed', '✗ Failed']].map(([v, l]) => (
              <button
                key={v}
                onClick={() => setFilter(v)}
                className={`flex-1 py-1.5 text-[9px] font-mono uppercase transition-colors ${
                  filter === v ? 'text-cyan-400 border-b border-cyan-400' : 'text-slate-600 hover:text-slate-400'
                }`}
              >
                {l}
              </button>
            ))}
          </div>

          {/* List */}
          <div className="flex-1 overflow-y-auto">
            {filtered.length === 0 && (
              <p className="text-[10px] font-mono text-slate-700 text-center py-6">No tasks</p>
            )}
            {filtered.map(t => (
              <TaskListItem
                key={t.task_id}
                task={t}
                selected={selectedId === t.task_id}
                onClick={() => selectTask(t.task_id)}
              />
            ))}
          </div>
        </div>

        {/* Right: task detail */}
        <TaskDetail
          task={selectedTask}
          onResume={handleResume}
          onCancel={handleCancel}
          onRollback={handleRollback}
          onDelete={handleDelete}
          actionLoading={actionLoading}
        />
      </div>
    </div>
  );
};

export default TaskMonitor;
