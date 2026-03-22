/**
 * VerifyEmailBanner.js
 * Shown to users who haven't verified their email yet.
 * Sits just below the TopBar and blocks usage with a soft gate.
 */

import React, { useState, useCallback } from 'react';
import { Mail, RefreshCw, CheckCircle } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '../api/client';
import { useApp } from '../context/AppContext';

export default function VerifyEmailBanner() {
  const { user } = useApp();
  const [resending, setResending] = useState(false);
  const [sent, setSent] = useState(false);

  const handleResend = useCallback(async () => {
    if (resending || sent) return;
    setResending(true);
    try {
      await api.authResendVerification();
      setSent(true);
      toast.success(`Verification email sent to ${user?.email}`);
    } catch (err) {
      toast.error(err?.message || 'Could not send email. Try again shortly.');
    } finally {
      setResending(false);
    }
  }, [resending, sent, user?.email]);

  if (!user || user.email_verified !== false) return null;

  return (
    <div className="flex-shrink-0 bg-amber-500/10 border-b border-amber-500/20 px-4 py-2.5 flex items-center gap-3">
      <Mail size={14} className="text-amber-400 flex-shrink-0" />
      <p className="flex-1 text-xs text-amber-300 leading-snug">
        <span className="font-semibold">Please verify your email</span> — we sent a link to{' '}
        <span className="font-mono">{user.email}</span>. You need to verify to start using credits.
      </p>
      <button
        onClick={handleResend}
        disabled={resending || sent}
        className="flex-shrink-0 flex items-center gap-1 px-3 py-1 rounded-lg text-[11px] font-semibold transition-all
          bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30 disabled:opacity-60"
      >
        {sent
          ? <><CheckCircle size={11} /> Sent!</>
          : resending
            ? <><RefreshCw size={11} className="animate-spin" /> Sending…</>
            : <><RefreshCw size={11} /> Resend</>
        }
      </button>
    </div>
  );
}
