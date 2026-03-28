/**
 * ExportRecordModal
 *
 * Shown before any creation record export.
 * User must check the acknowledgment box before Export is enabled.
 * Optionally fills in creator name, project description, and notes.
 *
 * Props:
 *   projectTitle  — string (pre-filled)
 *   onExport      — ({ creatorName, description, notes }) => void
 *   onCancel      — () => void
 */

import React, { useState } from 'react';

export default function ExportRecordModal({ projectTitle = '', onExport, onCancel }) {
  const [isChecked,        setIsChecked]        = useState(false);
  const [creatorName,      setCreatorName]      = useState('');
  const [description,      setDescription]      = useState('');
  const [notes,            setNotes]            = useState('');

  function handleExport() {
    if (!isChecked) return;
    onExport?.({
      creatorName:  creatorName.trim() || null,
      description:  description.trim() || null,
      notes:        notes.trim()       || null,
    });
  }

  return (
    /* Overlay */
    <div
      style={{
        position:       'fixed',
        inset:          0,
        zIndex:         9000,
        background:     'rgba(0,0,0,0.65)',
        backdropFilter: 'blur(4px)',
        display:        'flex',
        alignItems:     'center',
        justifyContent: 'center',
        padding:        '16px',
      }}
      onClick={onCancel}
    >
      {/* Modal box */}
      <div
        style={{
          width:        '100%',
          maxWidth:     '460px',
          background:   '#0f1020',
          border:       '1px solid rgba(255,255,255,0.08)',
          borderRadius: '16px',
          overflow:     'hidden',
          boxShadow:    '0 24px 64px rgba(0,0,0,0.6)',
          fontFamily:   'system-ui, -apple-system, sans-serif',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Top accent bar */}
        <div style={{ height: '3px', background: 'linear-gradient(90deg, #7c3aed, #06b6d4)' }} />

        <div style={{ padding: '24px 24px 20px' }}>
          {/* Title */}
          <h2 style={{ margin: '0 0 6px', fontSize: '16px', fontWeight: 700, color: '#f1f5f9' }}>
            Export Creation Record
          </h2>
          {projectTitle && (
            <p style={{ margin: '0 0 16px', fontSize: '11px', color: '#475569' }}>
              {projectTitle}
            </p>
          )}

          {/* Message */}
          <p style={{ margin: '0 0 16px', fontSize: '13px', color: '#94a3b8', lineHeight: 1.6 }}>
            This report provides a documented timeline and history of your project, which may help
            support authorship claims.
          </p>
          <p style={{ margin: '0 0 20px', fontSize: '13px', color: '#94a3b8', lineHeight: 1.6 }}>
            It is not a substitute for formal copyright registration or legal advice, and does not
            guarantee ownership protection.
          </p>

          {/* Divider */}
          <div style={{ height: '1px', background: 'rgba(255,255,255,0.06)', marginBottom: '20px' }} />

          {/* Optional fields */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '20px' }}>
            <label style={labelStyle}>
              Creator Name <Opt />
              <input
                type="text"
                value={creatorName}
                onChange={e => setCreatorName(e.target.value)}
                placeholder="Your name or alias"
                style={inputStyle}
              />
            </label>

            <label style={labelStyle}>
              Project Description <Opt />
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Brief description of the project"
                rows={2}
                style={{ ...inputStyle, resize: 'vertical', minHeight: '56px' }}
              />
            </label>

            <label style={labelStyle}>
              Notes <Opt />
              <textarea
                value={notes}
                onChange={e => setNotes(e.target.value)}
                placeholder="Any additional notes"
                rows={2}
                style={{ ...inputStyle, resize: 'vertical', minHeight: '56px' }}
              />
            </label>
          </div>

          {/* Required checkbox */}
          <label style={{
            display:    'flex',
            alignItems: 'flex-start',
            gap:        '10px',
            cursor:     'pointer',
            marginBottom: '20px',
          }}>
            <input
              type="checkbox"
              checked={isChecked}
              onChange={e => setIsChecked(e.target.checked)}
              style={{ marginTop: '2px', accentColor: '#7c3aed', width: '15px', height: '15px', flexShrink: 0, cursor: 'pointer' }}
            />
            <span style={{ fontSize: '13px', color: isChecked ? '#c4b5fd' : '#94a3b8', lineHeight: 1.5, transition: 'color 0.2s' }}>
              I understand this is a documentation tool and not legal protection
            </span>
          </label>

          {/* Actions */}
          <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
            <button onClick={onCancel} style={cancelBtnStyle}>
              Cancel
            </button>
            <button
              onClick={handleExport}
              disabled={!isChecked}
              style={{
                ...exportBtnStyle,
                opacity:    isChecked ? 1 : 0.38,
                cursor:     isChecked ? 'pointer' : 'not-allowed',
              }}
            >
              Export Record
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Opt() {
  return (
    <span style={{ fontWeight: 400, fontSize: '10px', color: '#475569', marginLeft: '4px' }}>
      (optional)
    </span>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const labelStyle = {
  display:       'flex',
  flexDirection: 'column',
  gap:           '5px',
  fontSize:      '12px',
  fontWeight:    600,
  color:         '#64748b',
};

const inputStyle = {
  background:   'rgba(255,255,255,0.04)',
  border:       '1px solid rgba(255,255,255,0.08)',
  borderRadius: '8px',
  padding:      '8px 10px',
  fontSize:     '13px',
  color:        '#e2e8f0',
  outline:      'none',
  fontFamily:   'system-ui, sans-serif',
  width:        '100%',
  boxSizing:    'border-box',
};

const cancelBtnStyle = {
  background:   'rgba(255,255,255,0.05)',
  border:       '1px solid rgba(255,255,255,0.08)',
  borderRadius: '8px',
  padding:      '9px 18px',
  fontSize:     '13px',
  fontWeight:   600,
  color:        '#64748b',
  cursor:       'pointer',
  fontFamily:   'system-ui, sans-serif',
};

const exportBtnStyle = {
  background:   'linear-gradient(135deg, #7c3aed, #06b6d4)',
  border:       'none',
  borderRadius: '8px',
  padding:      '9px 20px',
  fontSize:     '13px',
  fontWeight:   700,
  color:        '#fff',
  fontFamily:   'system-ui, sans-serif',
  transition:   'opacity 0.2s',
};
