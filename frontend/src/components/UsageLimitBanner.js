/**
 * UsageLimitBanner.js
 * Soft warning banner — shown when a user's credits are running low.
 * Dismissable per session. Never shown to users with plenty of credits.
 *
 * Thresholds:
 *   < 10% remaining → danger   "You're almost out of credits"
 *   < 25% remaining → warning  "You're approaching your usage limit"
 */

import React, { useState, useEffect } from 'react';
import { AlertTriangle, X, Zap, ArrowRight } from 'lucide-react';
import { useApp } from '../context/AppContext';

const PLAN_LIMITS = { free: 50, standard: 500, pro: 2000, team: 10000, max: 10000 };

// Don't re-show the same severity after dismiss within the same session
const _dismissed = new Set();

export default function UsageLimitBanner() {
  const { credits, plan, isSubscribed, openUpgradeModal, setPurchaseModalOpen, setPage, page } = useApp();
  const [visible, setVisible] = useState(false);
  const [severity, setSeverity] = useState(null); // 'warning' | 'danger'

  useEffect(() => {
    if (credits === null || credits === undefined) return;

    // Don't show on pricing/dashboard pages — user is already looking at billing
    if (page === 'pricing' || page === 'dashboard') { setVisible(false); return; }

    const limit = PLAN_LIMITS[plan] || 50;
    const pct   = Math.max(0, Math.min(100, (credits / limit) * 100));

    if (pct < 10 && !_dismissed.has('danger')) {
      setSeverity('danger');
      setVisible(true);
    } else if (pct < 25 && !_dismissed.has('warning')) {
      setSeverity('warning');
      setVisible(true);
    } else {
      setVisible(false);
    }
  }, [credits, plan, page]);

  const dismiss = () => {
    _dismissed.add(severity);
    setVisible(false);
  };

  const handleAction = () => {
    dismiss();
    if (!isSubscribed) {
      openUpgradeModal('credits');
    } else {
      setPurchaseModalOpen(true);
    }
  };

  if (!visible || !severity) return null;

  const isDanger = severity === 'danger';
  const limit    = PLAN_LIMITS[plan] || 50;
  const pct      = Math.max(0, Math.min(100, ((credits ?? 0) / limit) * 100)).toFixed(0);

  return (
    <div
      className={`flex items-center gap-3 px-4 py-2.5 border-b text-sm transition-all
        ${isDanger
          ? 'bg-red-500/10 border-red-500/20 text-red-300'
          : 'bg-amber-500/10 border-amber-500/20 text-amber-300'
        }`}
    >
      <AlertTriangle
        size={14}
        className={`flex-shrink-0 ${isDanger ? 'text-red-400' : 'text-amber-400'}`}
      />

      <span className="flex-1 text-xs leading-snug">
        {isDanger ? (
          <>
            <strong>Almost out of credits</strong> — you have{' '}
            <span className="font-mono font-bold">{credits ?? 0}</span> credits left ({pct}%).
            {' '}AI features will pause when you hit zero.
          </>
        ) : (
          <>
            <strong>Approaching your usage limit</strong> — you've used{' '}
            <span className="font-mono font-bold">{100 - Number(pct)}%</span> of your {plan} plan credits.
          </>
        )}
      </span>

      <button
        onClick={handleAction}
        className={`flex-shrink-0 flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-bold transition-all
          ${isDanger
            ? 'bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/30'
            : 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30'
          }`}
      >
        <Zap size={11} />
        {isSubscribed ? 'Top Up' : 'Upgrade'}
        <ArrowRight size={11} />
      </button>

      <button
        onClick={dismiss}
        className="flex-shrink-0 p-1 rounded text-current opacity-50 hover:opacity-100 transition-opacity"
        title="Dismiss"
      >
        <X size={13} />
      </button>
    </div>
  );
}
