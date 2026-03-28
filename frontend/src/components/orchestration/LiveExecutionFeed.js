/**
 * LiveExecutionFeed
 *
 * Real-time task execution feed — consumes SSE events from
 * /api/orchestrate/stream/{taskId} and renders a live step-by-step log.
 *
 * Props:
 *   taskId       — string — active task ID to stream
 *   stepCount    — number — total steps (for X/Y progress)
 *   onApproval   — (stepId, stepTitle) => void — called when approval_required fires
 *   onComplete   — (summary) => void
 *   onFailed     — (error) => void
 *   onCancel     — () => void
 */

import React, { useEffect, useRef, useState, useCallback } from 'react';

const EVENT_ICONS = {
  task_started:       '🚀',
  step_started:       '⚙',
  step_completed:     '✔',
  step_failed:        '❌',
  checkpoint_created: '📌',
  approval_required:  '⏸',
  retry_started:      '🔁',
  task_completed:     '🎉',
  task_failed:        '💥',
  task_cancelled:     '🚫',
};

const EVENT_COLOR = {
  task_started:       '#7c3aed',
  step_started:       '#60a5fa',
  step_completed:     '#22c55e',
  step_failed:        '#ef4444',
  checkpoint_created: '#a78bfa',
  approval_required:  '#f59e0b',
  retry_started:      '#f97316',
  task_completed:     '#22c55e',
  task_failed:        '#ef4444',
  task_cancelled:     '#64748b',
};

const TERMINAL = new Set(['task_completed', 'task_failed', 'task_cancelled']);

export default function LiveExecutionFeed({
  taskId,
  stepCount = 5,
  onApproval,
  onComplete,
  onFailed,
  onCancel,
}) {
  const [events, setEvents]       = useState([]);
  const [connected, setConnected] = useState(false);
  const [done, setDone]           = useState(false);
  const [currentStep, setCurrentStep] = useState(null);
  const esRef    = useRef(null);
  const bottomRef = useRef(null);

  const addEvent = useCallback((evt) => {
    setEvents(prev => [...prev.slice(-99), evt]); // keep last 100 events
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, []);

  useEffect(() => {
    if (!taskId) return;

    // SSE connection
    const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
    const es = new EventSource(`${BASE}/api/orchestrate/stream/${taskId}`);
    esRef.current = es;
    setConnected(true);

    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data);
        addEvent(evt);

        if (evt.type === 'step_started') {
          setCurrentStep({ id: evt.step_id, title: evt.title, index: evt.index, total: evt.total });
        }
        if (evt.type === 'step_completed' || evt.type === 'step_failed') {
          setCurrentStep(null);
        }
        if (evt.type === 'approval_required') {
          onApproval?.(evt.step_id, evt.title);
        }
        if (TERMINAL.has(evt.type)) {
          setDone(true);
          setConnected(false);
          es.close();
          if (evt.type === 'task_completed') onComplete?.(evt.summary);
          if (evt.type === 'task_failed')    onFailed?.(evt.error);
          if (evt.type === 'task_cancelled') onCancel?.();
        }
      } catch (_) {}
    };

    es.onerror = () => {
      setConnected(false);
      es.close();
    };

    return () => {
      es.close();
      setConnected(false);
    };
  }, [taskId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!taskId || (!events.length && !connected)) return null;

  const doneCount = events.filter(e => e.type === 'step_completed').length;
  const progress  = stepCount > 0 ? Math.min(1, doneCount / stepCount) : 0;

  return (
    <div style={{
      background:   '#0d0e1a',
      border:       '1px solid rgba(124,58,237,0.2)',
      borderRadius: '12px',
      padding:      '14px 16px',
      fontFamily:   'system-ui, sans-serif',
      marginBottom: '10px',
      maxWidth:     '520px',
    }}>
      {/* Header */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:'10px' }}>
        <div style={{ display:'flex', alignItems:'center', gap:'8px' }}>
          {connected && (
            <span style={{
              display:    'inline-block',
              width:      '7px',
              height:     '7px',
              background: '#22c55e',
              borderRadius:'50%',
              animation:  'lfPulse 1.2s ease-in-out infinite',
            }} />
          )}
          <span style={{ fontSize:'12px', fontWeight:700, color:'#c4b5fd' }}>
            {done ? '✔ Execution Complete' : 'Live Execution'}
          </span>
          {!done && currentStep && (
            <span style={{ fontSize:'11px', color:'#64748b' }}>
              Step {(currentStep.index || 0) + 1}/{currentStep.total || stepCount}
            </span>
          )}
        </div>
        {connected && onCancel && (
          <button
            onClick={() => { esRef.current?.close(); onCancel?.(); }}
            style={{ background:'none', border:'1px solid rgba(239,68,68,0.3)', borderRadius:'6px', color:'#ef4444', fontSize:'11px', padding:'3px 8px', cursor:'pointer' }}
          >
            Cancel
          </button>
        )}
      </div>

      {/* Progress bar */}
      {!done && (
        <div style={{ height:'3px', background:'rgba(255,255,255,0.06)', borderRadius:'2px', marginBottom:'10px', overflow:'hidden' }}>
          <div style={{
            height:     '100%',
            width:      `${Math.round(progress * 100)}%`,
            background: 'linear-gradient(90deg, #7c3aed, #06b6d4)',
            borderRadius:'2px',
            transition: 'width 0.4s ease',
          }} />
        </div>
      )}

      {/* Events log */}
      <div style={{ maxHeight:'220px', overflowY:'auto', display:'flex', flexDirection:'column', gap:'4px' }}>
        {events.map((evt, i) => {
          const icon  = EVENT_ICONS[evt.type] || '•';
          const color = EVENT_COLOR[evt.type] || '#94a3b8';
          const label = _eventLabel(evt);

          return (
            <div key={i} style={{ display:'flex', alignItems:'flex-start', gap:'8px' }}>
              <span style={{ fontSize:'12px', flexShrink:0, marginTop:'1px' }}>{icon}</span>
              <span style={{ fontSize:'11px', color, lineHeight:1.4 }}>{label}</span>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      <style>{`
        @keyframes lfPulse {
          0%,100% { opacity:1; }
          50%      { opacity:0.4; }
        }
      `}</style>
    </div>
  );
}

function _eventLabel(evt) {
  switch (evt.type) {
    case 'task_started':       return `Starting: ${evt.title || 'task'}`;
    case 'step_started':       return `${evt.title}…`;
    case 'step_completed':     return evt.output_summary ? `${evt.title} — ${evt.output_summary}` : `${evt.title} ✓`;
    case 'step_failed':        return `${evt.title} failed${evt.error ? ': ' + evt.error : ''}`;
    case 'checkpoint_created': return `Checkpoint saved: ${evt.label}`;
    case 'approval_required':  return `Waiting for approval: ${evt.title}`;
    case 'retry_started':      return `Retrying (attempt ${evt.attempt})…`;
    case 'task_completed':     return evt.summary || 'Task complete';
    case 'task_failed':        return `Failed: ${evt.error || 'unknown error'}`;
    case 'task_cancelled':     return 'Cancelled';
    default:                   return evt.type;
  }
}
