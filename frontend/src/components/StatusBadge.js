/**
 * components/StatusBadge.js
 * Small pill badge showing server/service status.
 * Props: { label: string, status: true | false | null, title?: string }
 */

import React from 'react';

function StatusBadge({ label, status, title }) {
  let dotColor = 'bg-slate-500';
  let textColor = 'text-slate-500';
  let borderColor = 'border-slate-700/50';
  let pulse = false;
  let statusLabel = 'checking…';

  if (status === true) {
    dotColor = 'bg-emerald-400';
    textColor = 'text-emerald-400';
    borderColor = 'border-emerald-500/20';
    statusLabel = 'online';
  } else if (status === false) {
    dotColor = 'bg-red-400';
    textColor = 'text-red-400';
    borderColor = 'border-red-500/20';
    statusLabel = 'offline';
  } else {
    pulse = true;
  }

  const tooltipTitle = title || `${label}: ${statusLabel}`;

  return (
    <span
      title={tooltipTitle}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-mono ${textColor} ${borderColor} bg-black/20`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotColor} ${pulse ? 'animate-pulse' : ''}`}
      />
      {label}
    </span>
  );
}

export default StatusBadge;
