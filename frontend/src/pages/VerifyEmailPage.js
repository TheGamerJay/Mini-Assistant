/**
 * VerifyEmailPage.js
 * Rendered at /verify-email?token=... — no auth required.
 * Calls backend, shows result, then redirects into the app.
 */

import React, { useEffect, useState } from 'react';
import { CheckCircle, XCircle, Loader2, Zap } from 'lucide-react';
import { api, setToken } from '../api/client';

const APP_URL = process.env.REACT_APP_FRONTEND_URL || 'https://www.miniassistantai.com';

export default function VerifyEmailPage({ token }) {
  const [status, setStatus] = useState('loading'); // loading | success | error
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!token) { setStatus('error'); setMessage('No verification token found in the link.'); return; }
    api.authVerifyEmail(token)
      .then(data => {
        // Store the fresh token so the user is logged in
        if (data.token) setToken(data.token);
        setStatus('success');
        setMessage(data.message || 'Email verified!');
        // Redirect into the app after 2.5s
        setTimeout(() => {
          window.location.href = APP_URL;
        }, 2500);
      })
      .catch(err => {
        setStatus('error');
        setMessage(err?.message || 'Verification failed. The link may have expired.');
      });
  }, [token]);

  return (
    <div className="min-h-screen bg-[#0b0b12] flex flex-col items-center justify-center px-4">
      <a href={APP_URL} className="mb-8 flex items-center gap-2">
        <img src="/Logo.png" alt="Mini Assistant AI" className="w-8 h-8 object-contain" />
        <span className="text-sm font-semibold text-slate-300">Mini Assistant AI</span>
      </a>

      <div className="w-full max-w-sm bg-[#111118] border border-white/10 rounded-2xl p-8 text-center">
        {status === 'loading' && (
          <>
            <Loader2 size={36} className="text-violet-400 animate-spin mx-auto mb-4" />
            <h2 className="text-lg font-bold text-white mb-1">Verifying your email…</h2>
            <p className="text-sm text-slate-500">Just a moment.</p>
          </>
        )}

        {status === 'success' && (
          <>
            <CheckCircle size={36} className="text-emerald-400 mx-auto mb-4" />
            <h2 className="text-lg font-bold text-white mb-1">Email verified!</h2>
            <p className="text-sm text-slate-400 mb-4">{message}</p>
            <div className="flex items-center justify-center gap-1.5 text-xs text-cyan-400 font-medium">
              <Zap size={12} /> Credits added to your account
            </div>
            <p className="text-xs text-slate-600 mt-3">Redirecting you to the app…</p>
          </>
        )}

        {status === 'error' && (
          <>
            <XCircle size={36} className="text-red-400 mx-auto mb-4" />
            <h2 className="text-lg font-bold text-white mb-1">Verification failed</h2>
            <p className="text-sm text-slate-400 mb-5">{message}</p>
            <a
              href={APP_URL}
              className="inline-block px-5 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-bold transition-colors"
            >
              Go to Mini Assistant
            </a>
          </>
        )}
      </div>
    </div>
  );
}
