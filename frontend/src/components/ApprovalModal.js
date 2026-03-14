/**
 * components/ApprovalModal.js
 * Modal shown when the assistant requests execution of a dangerous tool.
 * Props:
 *   approval  — { id, tool_name, command, risk_level, reasons[] }
 *   onApprove — (approvalId) => void
 *   onDeny    — (approvalId) => void
 */

import React from 'react';
import { ShieldAlert, ShieldX, Terminal, CheckCircle2, XCircle } from 'lucide-react';

const RISK_STYLES = {
  danger: {
    border: 'border-red-500/30',
    bg:     'bg-red-900/10',
    badge:  'bg-red-500/15 text-red-400 border border-red-500/25',
    icon:   <ShieldAlert size={20} className="text-red-400" />,
  },
  caution: {
    border: 'border-amber-500/30',
    bg:     'bg-amber-900/10',
    badge:  'bg-amber-500/15 text-amber-400 border border-amber-500/25',
    icon:   <ShieldAlert size={20} className="text-amber-400" />,
  },
  blocked: {
    border: 'border-red-600/40',
    bg:     'bg-red-950/20',
    badge:  'bg-red-600/20 text-red-300 border border-red-600/30',
    icon:   <ShieldX size={20} className="text-red-400" />,
  },
};

function ApprovalModal({ approval, onApprove, onDeny }) {
  if (!approval) return null;

  const style = RISK_STYLES[approval.risk_level] || RISK_STYLES.caution;

  return (
    /* Backdrop */
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div
        className={`w-full max-w-lg mx-4 rounded-2xl border ${style.border} ${style.bg}
          bg-[#12121a] shadow-2xl shadow-black/60 p-6 flex flex-col gap-4`}
      >
        {/* Header */}
        <div className="flex items-center gap-3">
          {style.icon}
          <div>
            <h2 className="text-slate-100 font-semibold text-base leading-tight">
              Approval Required
            </h2>
            <p className="text-slate-500 text-xs mt-0.5">
              The assistant wants to run a <span className={`font-mono px-1.5 py-0.5 rounded text-[11px] ${style.badge}`}>
                {approval.risk_level}
              </span> action
            </p>
          </div>
        </div>

        {/* Tool + command */}
        <div className="rounded-xl border border-white/5 bg-white/3 p-4 flex flex-col gap-3">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Terminal size={13} className="text-cyan-400/70" />
            <span className="font-mono text-cyan-300/80">{approval.tool_name}</span>
          </div>
          <code className="block font-mono text-[12px] text-slate-200 bg-black/30 rounded-lg px-3 py-2.5 border border-white/5 break-all whitespace-pre-wrap">
            {approval.command}
          </code>
        </div>

        {/* Reasons */}
        {approval.reasons && approval.reasons.length > 0 && (
          <ul className="flex flex-col gap-1">
            {approval.reasons.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-slate-400">
                <span className="mt-0.5 shrink-0 text-amber-500/70">•</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        )}

        {/* Actions */}
        <div className="flex items-center gap-3 mt-1">
          <button
            onClick={() => onApprove(approval.id)}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl
              bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/25 hover:border-emerald-500/40
              text-emerald-400 hover:text-emerald-300 text-sm font-medium transition-colors"
          >
            <CheckCircle2 size={15} />
            Approve & Run
          </button>
          <button
            onClick={() => onDeny(approval.id)}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl
              bg-red-500/10 hover:bg-red-500/20 border border-red-500/25 hover:border-red-500/40
              text-red-400 hover:text-red-300 text-sm font-medium transition-colors"
          >
            <XCircle size={15} />
            Deny
          </button>
        </div>

        <p className="text-[10px] text-slate-600 text-center">
          Approving will execute this command on the server. Review carefully.
        </p>
      </div>
    </div>
  );
}

export default ApprovalModal;
