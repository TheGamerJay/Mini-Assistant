/**
 * ThinkingSequence
 *
 * Shows a staged Jarvis-style analysis animation while the orchestration
 * system is evaluating the user's request.
 *
 * Stages:
 *   1. "Analyzing your request…"
 *   2. "Intent understood"
 *   3. "Building execution plan"
 *   4. "Calculating risk + cost…"
 *   → done (fades out)
 *
 * Each stage maps to real orchestration sub-steps, so timing reflects
 * actual work — not fake delays.
 */

import React, { useEffect, useState, useRef } from 'react';

const STAGES = [
  { id: 0, icon: '🧠', text: 'Analyzing your request…',     doneText: 'Request analyzed' },
  { id: 1, icon: '✔',  text: 'Understanding intent…',       doneText: 'Intent understood' },
  { id: 2, icon: '⚙',  text: 'Building execution plan…',    doneText: 'Plan ready' },
  { id: 3, icon: '📊', text: 'Calculating risk + cost…',    doneText: 'Risk & cost estimated' },
];

// How long each stage shows before advancing (ms)
// These are visual pacing — they fire only while status === 'analyzing'
const STAGE_DURATION = 480;

export default function ThinkingSequence({ status }) {
  const [currentStage, setCurrentStage]     = useState(0);
  const [completedStages, setCompletedStages] = useState([]);
  const [visible, setVisible]               = useState(false);
  const timerRef = useRef(null);

  // Show/hide based on status
  useEffect(() => {
    if (status === 'analyzing') {
      setVisible(true);
      setCurrentStage(0);
      setCompletedStages([]);
    } else if (status === 'done' || status === 'error') {
      // Mark remaining stages complete then fade
      setCompletedStages([0, 1, 2, 3]);
      const t = setTimeout(() => setVisible(false), 800);
      return () => clearTimeout(t);
    }
  }, [status]);

  // Auto-advance stages while analyzing
  useEffect(() => {
    if (status !== 'analyzing') return;
    if (currentStage >= STAGES.length - 1) return;

    timerRef.current = setTimeout(() => {
      setCompletedStages(prev => [...prev, currentStage]);
      setCurrentStage(prev => prev + 1);
    }, STAGE_DURATION);

    return () => clearTimeout(timerRef.current);
  }, [currentStage, status]);

  if (!visible) return null;

  return (
    <div
      style={{
        display:        'flex',
        flexDirection:  'column',
        gap:            '6px',
        padding:        '12px 16px',
        background:     'rgba(15, 16, 32, 0.85)',
        borderRadius:   '12px',
        border:         '1px solid rgba(124, 58, 237, 0.2)',
        backdropFilter: 'blur(8px)',
        marginBottom:   '8px',
        transition:     'opacity 0.4s',
        opacity:        visible ? 1 : 0,
        maxWidth:       '420px',
      }}
    >
      {STAGES.map(stage => {
        const isCompleted = completedStages.includes(stage.id);
        const isCurrent   = currentStage === stage.id && status === 'analyzing';

        return (
          <div
            key={stage.id}
            style={{
              display:    'flex',
              alignItems: 'center',
              gap:        '8px',
              opacity:    (isCompleted || isCurrent) ? 1 : 0.3,
              transition: 'opacity 0.3s',
            }}
          >
            {/* Status dot */}
            <div style={{
              width:        '7px',
              height:       '7px',
              borderRadius: '50%',
              flexShrink:   0,
              background:   isCompleted
                ? '#22c55e'
                : isCurrent
                  ? '#7c3aed'
                  : 'rgba(255,255,255,0.15)',
              boxShadow: isCurrent ? '0 0 6px rgba(124,58,237,0.8)' : 'none',
              transition:   'all 0.3s',
              animation:    isCurrent ? 'orchPulse 1s ease-in-out infinite' : 'none',
            }} />

            {/* Text */}
            <span style={{
              fontSize:   '12px',
              fontFamily: 'system-ui, sans-serif',
              color:      isCompleted ? '#22c55e' : isCurrent ? '#c4b5fd' : '#475569',
              transition: 'color 0.3s',
            }}>
              {isCompleted ? stage.doneText : stage.text}
            </span>

            {/* Spinner for current */}
            {isCurrent && (
              <span style={{
                display:  'inline-block',
                width:    '10px',
                height:   '10px',
                border:   '1.5px solid rgba(124,58,237,0.3)',
                borderTop:'1.5px solid #7c3aed',
                borderRadius: '50%',
                animation:'orchSpin 0.7s linear infinite',
                flexShrink: 0,
              }} />
            )}
          </div>
        );
      })}

      <style>{`
        @keyframes orchPulse {
          0%,100% { opacity:1; transform:scale(1); }
          50%      { opacity:0.6; transform:scale(1.3); }
        }
        @keyframes orchSpin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
