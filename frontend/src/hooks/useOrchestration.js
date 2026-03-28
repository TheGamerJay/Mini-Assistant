/**
 * useOrchestration
 *
 * React hook that calls /api/orchestrate/analyze before a message is sent.
 * Returns the analysis result which drives the ThinkingSequence + TaskSummaryCard.
 *
 * Lifecycle:
 *   idle → analyzing → done | error
 *
 * Usage:
 *   const { analyze, analysis, status, reset } = useOrchestration();
 *   await analyze({ message, sessionId, mode, history, hasExistingCode, vibeMode });
 *   // analysis is now populated — render TaskSummaryCard
 */

import { useState, useCallback, useRef } from 'react';
import api from '../api/client';

export const ORCH_STATUS = {
  IDLE:      'idle',
  ANALYZING: 'analyzing',
  DONE:      'done',
  ERROR:     'error',
};

const DEFAULT_ANALYSIS = {
  decision:             'act',
  proceed_immediately:  true,
  intent_type:          'chat',
  normalized_goal:      '',
  mode:                 'chat',
  confidence:           0.85,
  confidence_label:     'High',
  risk_level:           'low',
  risk_score:           0,
  cost_min:             0,
  cost_max:             0,
  cost_label:           'Free',
  confidence_factors:   [],
  confidence_deductions:[],
  risk_factors:         [],
  risk_mitigations:     [],
  clarification_q:      null,
  interpretations:      [],
  requires_checkpoint:  false,
  requires_approval:    false,
  contradiction_found:  false,
  ambiguity_score:      0,
  constraints:          [],
  assumptions:          [],
  recommendation:       null,
  elapsed_ms:           0,
  session_id:           '',
};

export function useOrchestration() {
  const [status,   setStatus]   = useState(ORCH_STATUS.IDLE);
  const [analysis, setAnalysis] = useState(null);
  const [error,    setError]    = useState(null);
  const abortRef = useRef(null);

  const analyze = useCallback(async ({
    message,
    sessionId,
    mode           = 'chat',
    history        = [],
    hasExistingCode = false,
    vibeMode       = false,
  }) => {
    // Cancel any in-flight analysis
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    setStatus(ORCH_STATUS.ANALYZING);
    setAnalysis(null);
    setError(null);

    try {
      const res = await api.post('/api/orchestrate/analyze', {
        message,
        session_id:        sessionId,
        mode,
        history:           history.slice(-20).map(m => ({ role: m.role, content: m.content || '' })),
        has_existing_code: hasExistingCode,
        vibe_mode:         vibeMode,
      }, { signal: abortRef.current.signal });

      const data = res.data || DEFAULT_ANALYSIS;
      setAnalysis(data);
      setStatus(ORCH_STATUS.DONE);
      return data;
    } catch (err) {
      if (err.name === 'CanceledError' || err.name === 'AbortError') {
        return null; // cancelled — don't update state
      }
      console.warn('[useOrchestration] analyze failed — falling back to act:', err);
      // Fail safe: return a minimal ACT result so the user is never blocked
      const fallback = { ...DEFAULT_ANALYSIS, mode, session_id: sessionId, normalized_goal: message };
      setAnalysis(fallback);
      setStatus(ORCH_STATUS.DONE);
      setError(err?.message || 'Analysis unavailable');
      return fallback;
    }
  }, []);

  const reset = useCallback(() => {
    setStatus(ORCH_STATUS.IDLE);
    setAnalysis(null);
    setError(null);
  }, []);

  return { analyze, analysis, status, error, reset };
}
