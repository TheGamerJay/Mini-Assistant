/**
 * TaskSummaryCard
 *
 * Shown after ThinkingSequence completes when decision !== 'act'.
 * Displays:
 *   - Normalized goal
 *   - Confidence / Risk / Cost estimates
 *   - Risk factors + mitigations
 *   - Constraints / assumptions
 *   - Clarification question (if decision === 'ask')
 *   - Actions: Proceed | Modify | Auto-Split
 *
 * Props:
 *   analysis      — AnalysisResult from orchestrator
 *   onProceed     — () => void  — user confirmed, run the task
 *   onModify      — () => void  — user wants to adjust the request
 *   onSplit       — () => void  — user wants auto-split into smaller steps
 *   onClarify     — (choice) => void  — user chose an interpretation
 *   onDismiss     — () => void  — close without action
 */

import React, { useState } from 'react';

// Risk level → color
const RISK_COLOR = {
  low:    '#22c55e',
  medium: '#f59e0b',
  high:   '#ef4444',
};

const RISK_LABEL = {
  low:    'Low Risk',
  medium: 'Medium Risk',
  high:   'High Risk',
};

// Confidence label → color
const CONF_COLOR = {
  'Very High': '#22c55e',
  'High':      '#6ee7b7',
  'Medium':    '#f59e0b',
  'Low':       '#f97316',
  'Very Low':  '#ef4444',
};

export default function TaskSummaryCard({
  analysis,
  onProceed,
  onModify,
  onSplit,
  onClarify,
  onDismiss,
}) {
  const [selectedInterp, setSelectedInterp] = useState(null);

  if (!analysis) return null;

  const {
    decision,
    normalized_goal,
    confidence_label,
    confidence,
    risk_level,
    risk_score,
    cost_min,
    cost_max,
    cost_label,
    confidence_factors,
    confidence_deductions,
    risk_factors,
    risk_mitigations,
    clarification_q,
    interpretations,
    requires_approval,
    constraints,
    assumptions,
    recommendation,
  } = analysis;

  const isAsk   = decision === 'ask';
  const isHigh  = risk_level === 'high';
  const showCard = decision === 'act_show' || isAsk || requires_approval || isHigh;

  if (!showCard) return null;

  const riskColor = RISK_COLOR[risk_level] || '#94a3b8';
  const confColor = CONF_COLOR[confidence_label] || '#94a3b8';

  function handleProceed() {
    if (isAsk && interpretations.length > 0 && selectedInterp === null) return;
    onProceed?.();
  }

  function handleClarify(interp) {
    setSelectedInterp(interp);
    onClarify?.(interp);
  }

  return (
    <div style={{
      background:     'linear-gradient(135deg, #0f1020 0%, #13141f 100%)',
      border:         `1px solid ${isHigh ? 'rgba(239,68,68,0.35)' : 'rgba(124,58,237,0.25)'}`,
      borderRadius:   '14px',
      padding:        '16px 18px',
      marginBottom:   '10px',
      fontFamily:     'system-ui, -apple-system, sans-serif',
      boxShadow:      `0 0 20px ${isHigh ? 'rgba(239,68,68,0.08)' : 'rgba(124,58,237,0.08)'}`,
      maxWidth:       '520px',
      position:       'relative',
    }}>
      {/* Top gradient bar */}
      <div style={{
        position:   'absolute',
        top:        0,
        left:       0,
        right:      0,
        height:     '2px',
        borderRadius: '14px 14px 0 0',
        background: isHigh
          ? 'linear-gradient(90deg, #ef4444, #f97316)'
          : 'linear-gradient(90deg, #7c3aed, #06b6d4)',
      }} />

      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:'12px' }}>
        <div>
          <div style={{ fontSize:'10px', fontWeight:700, letterSpacing:'0.1em', color:'#475569', textTransform:'uppercase', marginBottom:'3px' }}>
            {isAsk ? '❓ Clarification Needed' : isHigh ? '⚠️ High Risk Action' : '📋 Execution Plan'}
          </div>
          {normalized_goal && (
            <div style={{ fontSize:'13px', color:'#e2e8f0', lineHeight:1.4, maxWidth:'380px' }}>
              {normalized_goal}
            </div>
          )}
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            style={{ background:'none', border:'none', color:'#475569', cursor:'pointer', padding:'2px 4px', fontSize:'16px', lineHeight:1 }}
          >×</button>
        )}
      </div>

      {/* Clarification block */}
      {isAsk && clarification_q && (
        <div style={{
          background:   'rgba(124,58,237,0.08)',
          border:       '1px solid rgba(124,58,237,0.2)',
          borderRadius: '8px',
          padding:      '10px 12px',
          marginBottom: '12px',
          fontSize:     '13px',
          color:        '#c4b5fd',
          lineHeight:   1.5,
        }}>
          {clarification_q}
        </div>
      )}

      {/* Interpretations */}
      {isAsk && interpretations.length > 0 && (
        <div style={{ marginBottom:'12px', display:'flex', flexDirection:'column', gap:'6px' }}>
          {interpretations.map((interp, i) => (
            <button
              key={i}
              onClick={() => handleClarify(interp)}
              style={{
                background:   selectedInterp === interp ? 'rgba(124,58,237,0.25)' : 'rgba(255,255,255,0.04)',
                border:       `1px solid ${selectedInterp === interp ? 'rgba(124,58,237,0.6)' : 'rgba(255,255,255,0.08)'}`,
                borderRadius: '8px',
                padding:      '8px 12px',
                color:        selectedInterp === interp ? '#c4b5fd' : '#94a3b8',
                fontSize:     '12px',
                textAlign:    'left',
                cursor:       'pointer',
                transition:   'all 0.2s',
              }}
            >
              <span style={{ color:'#7c3aed', marginRight:'6px', fontWeight:700 }}>{i + 1}.</span>
              {interp}
            </button>
          ))}
        </div>
      )}

      {/* Metrics row */}
      <div style={{ display:'flex', gap:'8px', marginBottom:'12px', flexWrap:'wrap' }}>
        {/* Confidence */}
        <div style={metricStyle}>
          <div style={{ fontSize:'9px', color:'#475569', textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:'2px' }}>Confidence</div>
          <div style={{ fontSize:'14px', fontWeight:700, color: confColor }}>
            {Math.round(confidence * 100)}%
          </div>
          <div style={{ fontSize:'10px', color: confColor }}>{confidence_label}</div>
        </div>

        {/* Risk */}
        <div style={metricStyle}>
          <div style={{ fontSize:'9px', color:'#475569', textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:'2px' }}>Risk</div>
          <div style={{ fontSize:'14px', fontWeight:700, color: riskColor }}>
            {risk_score}/10
          </div>
          <div style={{ fontSize:'10px', color: riskColor }}>{RISK_LABEL[risk_level]}</div>
        </div>

        {/* Cost */}
        <div style={metricStyle}>
          <div style={{ fontSize:'9px', color:'#475569', textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:'2px' }}>Cost</div>
          <div style={{ fontSize:'14px', fontWeight:700, color:'#e2e8f0' }}>
            {cost_min === 0 && cost_max === 0 ? 'Free' : `${cost_min}–${cost_max}`}
          </div>
          <div style={{ fontSize:'10px', color:'#94a3b8' }}>{cost_label} {cost_max > 0 ? 'credits' : ''}</div>
        </div>
      </div>

      {/* Risk factors */}
      {risk_factors.length > 0 && (
        <Detail label="Risk Factors" items={risk_factors} color={riskColor} />
      )}

      {/* Mitigations */}
      {risk_mitigations.length > 0 && (
        <Detail label="Safeguards" items={risk_mitigations} color='#22c55e' />
      )}

      {/* Constraints */}
      {constraints.length > 0 && (
        <Detail label="Constraints" items={constraints} color='#60a5fa' />
      )}

      {/* Recommendation */}
      {recommendation && (
        <div style={{
          background:   'rgba(245,158,11,0.08)',
          border:       '1px solid rgba(245,158,11,0.2)',
          borderRadius: '6px',
          padding:      '7px 10px',
          fontSize:     '11px',
          color:        '#fbbf24',
          marginBottom: '12px',
          lineHeight:   1.4,
        }}>
          💡 {recommendation}
        </div>
      )}

      {/* Actions */}
      <div style={{ display:'flex', gap:'8px', flexWrap:'wrap' }}>
        {/* Proceed */}
        <button
          onClick={handleProceed}
          disabled={isAsk && interpretations.length > 0 && selectedInterp === null}
          style={{
            ...btnBase,
            background: isHigh
              ? 'rgba(239,68,68,0.15)'
              : 'linear-gradient(135deg, rgba(124,58,237,0.8), rgba(6,182,212,0.6))',
            border:  isHigh ? '1px solid rgba(239,68,68,0.4)' : '1px solid rgba(124,58,237,0.5)',
            color:   '#fff',
            opacity: (isAsk && interpretations.length > 0 && selectedInterp === null) ? 0.4 : 1,
          }}
        >
          {isAsk ? '✓ Confirm & Proceed' : isHigh ? '⚠️ Proceed Anyway' : '▶ Proceed'}
        </button>

        {/* Modify */}
        {onModify && (
          <button onClick={onModify} style={{ ...btnBase, ...btnGhost }}>
            ✏ Modify
          </button>
        )}

        {/* Auto-Split */}
        {onSplit && (
          <button onClick={onSplit} style={{ ...btnBase, ...btnGhost }}>
            ⚡ Auto-Split
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Detail({ label, items, color }) {
  return (
    <div style={{ marginBottom:'10px' }}>
      <div style={{ fontSize:'10px', fontWeight:700, color:'#475569', textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:'5px' }}>
        {label}
      </div>
      <div style={{ display:'flex', flexDirection:'column', gap:'3px' }}>
        {items.map((item, i) => (
          <div key={i} style={{ display:'flex', alignItems:'flex-start', gap:'6px', fontSize:'11px', color:'#94a3b8', lineHeight:1.4 }}>
            <span style={{ color, flexShrink:0, marginTop:'1px' }}>•</span>
            {item}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const metricStyle = {
  background:   'rgba(255,255,255,0.04)',
  border:       '1px solid rgba(255,255,255,0.06)',
  borderRadius: '8px',
  padding:      '8px 12px',
  minWidth:     '80px',
  textAlign:    'center',
};

const btnBase = {
  border:       'none',
  borderRadius: '8px',
  padding:      '8px 14px',
  fontSize:     '12px',
  fontWeight:   600,
  cursor:       'pointer',
  transition:   'all 0.2s',
  fontFamily:   'system-ui, sans-serif',
};

const btnGhost = {
  background: 'rgba(255,255,255,0.05)',
  border:     '1px solid rgba(255,255,255,0.1)',
  color:      '#94a3b8',
};
