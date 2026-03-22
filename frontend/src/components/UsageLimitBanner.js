/**
 * UsageLimitBanner.js
 * Shows a one-time toast when credits are running low.
 *
 * Rules:
 *  - Auto-dismisses after 8 s (no permanent banner)
 *  - Dismissal stored in localStorage — survives page refresh
 *  - Re-shows only if credits have dropped further since last dismiss
 *  - Three tiers: warning (<25%), danger (<10%), critical (≤1 credit)
 */

import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { useApp } from '../context/AppContext';

const PLAN_LIMITS = { free: 50, standard: 500, pro: 2000, team: 10000, max: 10000 };
const STORAGE_KEY = 'ma_usage_banner';

function getStore() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); } catch { return {}; }
}

/** Returns true if we should show the toast for this severity + credit count. */
function shouldShow(severity, credits) {
  const store = getStore();
  if (!(severity in store)) return true;
  // Re-show only if credits have dropped by more than 1 since last dismiss
  return credits < store[severity] - 1;
}

function markDismissed(severity, credits) {
  try {
    const store = getStore();
    store[severity] = credits;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {}
}

export default function UsageLimitBanner() {
  const { credits, plan, page, isSubscribed, openUpgradeModal, setPurchaseModalOpen } = useApp();
  // Track which (severity, credits) combos we've already toasted this session
  const shownRef = useRef(new Set());

  useEffect(() => {
    if (credits === null || credits === undefined) return;
    // Skip on billing-focused pages — user is already aware
    if (page === 'pricing' || page === 'dashboard') return;

    const limit = PLAN_LIMITS[plan] || 50;
    const pct   = (credits / limit) * 100;

    let severity = null;
    if      (credits <= 1) severity = 'critical';
    else if (pct < 10)     severity = 'danger';
    else if (pct < 25)     severity = 'warning';

    if (!severity)                        return;
    if (!shouldShow(severity, credits))   return;

    // Prevent duplicate toasts within the same JS session
    const sessionKey = `${severity}-${credits}`;
    if (shownRef.current.has(sessionKey)) return;
    shownRef.current.add(sessionKey);

    const messages = {
      critical: `1 credit left — AI will pause after your next action.`,
      danger:   `Almost out — ${credits} credit${credits !== 1 ? 's' : ''} remaining.`,
      warning:  `Low on credits — ${credits} of ${limit} remaining.`,
    };

    const dismiss = () => markDismissed(severity, credits);
    const toastFn = severity === 'warning' ? toast.warning : toast.error;

    toastFn(messages[severity], {
      id:          'usage-banner',   // deduplicates if already on screen
      duration:    8000,
      action: {
        label:   isSubscribed ? 'Top Up' : 'Upgrade',
        onClick: () => {
          dismiss();
          isSubscribed ? setPurchaseModalOpen(true) : openUpgradeModal('credits');
        },
      },
      onDismiss:   dismiss,
      onAutoClose: dismiss,
    });
  }, [credits, plan, page, isSubscribed, openUpgradeModal, setPurchaseModalOpen]);

  return null;
}
