/**
 * pages/AuthPage.js
 * Full-screen login / sign-up page shown before entering the workspace.
 * Uses localStorage-based auth via AppContext (register / loginWithCredentials).
 */

import React, { useState, useCallback } from 'react';
import { Eye, EyeOff, Loader2 } from 'lucide-react';
import { useApp } from '../context/AppContext';

// ---------------------------------------------------------------------------
// Password field with show/hide toggle
// ---------------------------------------------------------------------------
function PasswordField({ id, label, value, onChange, placeholder = 'Password', autoComplete }) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-medium text-slate-400">{label}</label>
      <div className="relative">
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          autoComplete={autoComplete}
          // suppress browser native password manager icon
          style={{ WebkitTextSecurity: visible ? 'none' : undefined }}
          className="w-full bg-[#0d0d16] border border-white/10 rounded-xl px-4 py-3 pr-11 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 transition-colors"
        />
        <button
          type="button"
          onClick={() => setVisible(v => !v)}
          tabIndex={-1}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
          title={visible ? 'Hide password' : 'Show password'}
        >
          {visible ? <EyeOff size={15} /> : <Eye size={15} />}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Terms modal
// ---------------------------------------------------------------------------
function TermsModal({ onClose }) {
  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-[#13131f] border border-white/10 rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-y-auto p-8"
        onClick={e => e.stopPropagation()}
      >
        <h2 className="text-xl font-semibold text-white mb-6">Terms of Service & Privacy Policy</h2>
        <div className="space-y-5 text-sm text-slate-400 leading-relaxed">
          <section>
            <h3 className="text-slate-200 font-medium mb-2">1. Acceptance of Terms</h3>
            <p>By creating an account and using Mini Assistant, you agree to these Terms of Service. If you do not agree, do not use the service.</p>
          </section>
          <section>
            <h3 className="text-slate-200 font-medium mb-2">2. Description of Service</h3>
            <p>Mini Assistant is an AI-powered development workspace that provides chat, image generation, code assistance, and project management tools. The service is provided "as is" without warranty of any kind.</p>
          </section>
          <section>
            <h3 className="text-slate-200 font-medium mb-2">3. Acceptable Use</h3>
            <p>You agree NOT to use Mini Assistant to:</p>
            <ul className="list-disc ml-5 mt-2 space-y-1">
              <li>Generate illegal, harmful, abusive, or hateful content</li>
              <li>Violate any applicable laws or regulations</li>
              <li>Attempt to reverse-engineer or exploit the system</li>
              <li>Impersonate others or misrepresent your identity</li>
              <li>Generate content that infringes on intellectual property rights</li>
            </ul>
          </section>
          <section>
            <h3 className="text-slate-200 font-medium mb-2">4. AI-Generated Content</h3>
            <p>AI-generated content (text, images, code) is provided for informational and creative purposes. Mini Assistant makes no guarantees about accuracy, completeness, or fitness for a particular purpose. Always verify AI-generated code and information before use in production environments.</p>
          </section>
          <section>
            <h3 className="text-slate-200 font-medium mb-2">5. Privacy Policy</h3>
            <p>Your account information (name, email, hashed password) is stored locally in your browser's storage. We do not transmit personal information to third parties without your consent. Chat messages are processed by AI models to generate responses. Image generation requests are processed by local AI infrastructure. We do not sell your data.</p>
          </section>
          <section>
            <h3 className="text-slate-200 font-medium mb-2">6. Professional Advice Disclaimer</h3>
            <p>Mini Assistant does not provide legal, medical, financial, or professional advice. Always consult a qualified professional for decisions in those areas. AI responses in those domains are for general informational purposes only.</p>
          </section>
          <section>
            <h3 className="text-slate-200 font-medium mb-2">7. Limitation of Liability</h3>
            <p>Mini Assistant and its operators shall not be liable for any indirect, incidental, special, consequential, or punitive damages arising from your use of the service.</p>
          </section>
          <section>
            <h3 className="text-slate-200 font-medium mb-2">8. Changes to Terms</h3>
            <p>We reserve the right to update these terms at any time. Continued use of the service after changes constitutes acceptance of the new terms.</p>
          </section>
          <section>
            <h3 className="text-slate-200 font-medium mb-2">9. Contact</h3>
            <p>For questions about these terms, contact us at <a href="https://github.com/TheGamerJay/Mini-Assistant/issues" target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:text-cyan-300 underline">GitHub Issues</a>.</p>
          </section>
        </div>
        <button
          onClick={onClose}
          className="mt-6 w-full py-2.5 rounded-xl bg-white/5 border border-white/10 text-slate-400 hover:text-white hover:border-white/20 text-sm transition-colors"
        >
          Close
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Login tab
// ---------------------------------------------------------------------------
function LoginForm({ onSwitchToSignup }) {
  const { loginWithCredentials } = useApp();
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);
  const [showForgot, setShowForgot] = useState(false);
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotSent, setForgotSent]   = useState(false);

  const handleLogin = useCallback(async (e) => {
    e.preventDefault();
    if (!email || !password) { setError('Please fill in all fields.'); return; }
    setError('');
    setLoading(true);
    try {
      await loginWithCredentials(email, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [email, password, loginWithCredentials]);

  const handleForgot = useCallback((e) => {
    e.preventDefault();
    if (!forgotEmail) { setError('Enter your email address.'); return; }
    // No real email backend — just show confirmation UI
    setForgotSent(true);
  }, [forgotEmail]);

  if (showForgot) {
    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-white">Reset Password</h2>
          <p className="text-xs text-slate-500 mt-1">Enter your email and we'll send a reset link.</p>
        </div>
        {forgotSent ? (
          <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/20 px-4 py-3 text-sm text-emerald-400">
            If an account exists for <strong>{forgotEmail}</strong>, a reset link has been sent.
          </div>
        ) : (
          <form onSubmit={handleForgot} className="space-y-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-slate-400">Email</label>
              <input
                type="email"
                value={forgotEmail}
                onChange={e => setForgotEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full bg-[#0d0d16] border border-white/10 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 transition-colors"
              />
            </div>
            <button type="submit"
              className="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-violet-600 text-white text-sm font-medium hover:from-cyan-400 hover:to-violet-500 transition-all shadow-lg">
              Send Reset Link
            </button>
          </form>
        )}
        <button onClick={() => { setShowForgot(false); setForgotSent(false); setForgotEmail(''); }}
          className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
          ← Back to login
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleLogin} className="space-y-4">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="login-email" className="text-xs font-medium text-slate-400">Email</label>
        <input
          id="login-email"
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder="you@example.com"
          autoComplete="email"
          className="w-full bg-[#0d0d16] border border-white/10 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 transition-colors"
        />
      </div>
      <PasswordField
        id="login-password"
        label="Password"
        value={password}
        onChange={e => setPassword(e.target.value)}
        autoComplete="current-password"
      />
      {error && (
        <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>
      )}
      <button
        type="submit"
        disabled={loading}
        className="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-violet-600 text-white text-sm font-medium hover:from-cyan-400 hover:to-violet-500 transition-all shadow-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {loading && <Loader2 size={14} className="animate-spin" />}
        {loading ? 'Signing in…' : 'Sign In'}
      </button>
      <div className="flex items-center justify-between text-xs">
        <button type="button" onClick={() => setShowForgot(true)}
          className="text-slate-500 hover:text-slate-300 transition-colors">
          Forgot password?
        </button>
        <button type="button" onClick={onSwitchToSignup}
          className="text-cyan-400 hover:text-cyan-300 transition-colors font-medium">
          Create account →
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Sign-up tab
// ---------------------------------------------------------------------------
function SignupForm({ onSwitchToLogin }) {
  const { register } = useApp();
  const [name, setName]         = useState('');
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm]   = useState('');
  const [agreed, setAgreed]     = useState(false);
  const [showTerms, setShowTerms] = useState(false);
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);

  const handleSignup = useCallback(async (e) => {
    e.preventDefault();
    if (!name || !email || !password || !confirm) { setError('Please fill in all fields.'); return; }
    if (password.length < 8) { setError('Password must be at least 8 characters.'); return; }
    if (password !== confirm) { setError('Passwords do not match.'); return; }
    if (!agreed) { setError('You must accept the Terms of Service to continue.'); return; }
    setError('');
    setLoading(true);
    try {
      await register(name, email, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [name, email, password, confirm, agreed, register]);

  return (
    <>
      {showTerms && <TermsModal onClose={() => setShowTerms(false)} />}
      <form onSubmit={handleSignup} className="space-y-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="signup-name" className="text-xs font-medium text-slate-400">Full Name</label>
          <input
            id="signup-name"
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Jane Smith"
            autoComplete="name"
            className="w-full bg-[#0d0d16] border border-white/10 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 transition-colors"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="signup-email" className="text-xs font-medium text-slate-400">Email</label>
          <input
            id="signup-email"
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            className="w-full bg-[#0d0d16] border border-white/10 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 transition-colors"
          />
        </div>
        <PasswordField
          id="signup-password"
          label="Password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          placeholder="Min. 8 characters"
          autoComplete="new-password"
        />
        <PasswordField
          id="signup-confirm"
          label="Confirm Password"
          value={confirm}
          onChange={e => setConfirm(e.target.value)}
          placeholder="Repeat your password"
          autoComplete="new-password"
        />

        {/* Terms checkbox */}
        <label className="flex items-start gap-3 cursor-pointer group">
          <div
            onClick={() => setAgreed(v => !v)}
            className={`w-4 h-4 mt-0.5 flex-shrink-0 rounded border flex items-center justify-center transition-colors cursor-pointer
              ${agreed ? 'bg-cyan-500 border-cyan-500' : 'border-white/20 group-hover:border-white/40'}`}
          >
            {agreed && (
              <svg width="10" height="7" viewBox="0 0 10 7" fill="none">
                <path d="M1 3L4 6L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
          </div>
          <span className="text-xs text-slate-400 leading-relaxed">
            I have read and agree to the{' '}
            <button type="button" onClick={() => setShowTerms(true)}
              className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2 transition-colors">
              Terms of Service
            </button>
            {' '}and{' '}
            <button type="button" onClick={() => setShowTerms(true)}
              className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2 transition-colors">
              Privacy Policy
            </button>
            {' '}of Mini Assistant.
          </span>
        </label>

        {error && (
          <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>
        )}
        <button
          type="submit"
          disabled={loading}
          className="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-violet-600 text-white text-sm font-medium hover:from-cyan-400 hover:to-violet-500 transition-all shadow-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {loading && <Loader2 size={14} className="animate-spin" />}
          {loading ? 'Creating account…' : 'Create Account'}
        </button>
        <p className="text-center text-xs text-slate-500">
          Already have an account?{' '}
          <button type="button" onClick={onSwitchToLogin}
            className="text-cyan-400 hover:text-cyan-300 transition-colors font-medium">
            Sign in
          </button>
        </p>
      </form>
    </>
  );
}

// ---------------------------------------------------------------------------
// AuthPage root
// ---------------------------------------------------------------------------
export default function AuthPage() {
  const [tab, setTab] = useState('login'); // 'login' | 'signup'

  return (
    <div className="min-h-screen bg-[#0b0d16] flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background glow */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] rounded-full bg-gradient-radial from-cyan-500/6 via-violet-600/4 to-transparent blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 rounded-2xl overflow-hidden bg-gradient-to-br from-cyan-400 to-violet-600 mb-4 shadow-[0_0_30px_rgba(0,229,255,0.25)]">
            <img src="/Logo.png" alt="Mini Assistant" className="w-full h-full object-contain"
              onError={e => { e.target.style.display = 'none'; }} />
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Mini Assistant</h1>
          <p className="text-sm text-slate-500 mt-1">Your AI-powered development workspace</p>
        </div>

        {/* Card */}
        <div className="bg-[#13131f] border border-white/8 rounded-2xl shadow-2xl overflow-hidden">
          {/* Tab switcher */}
          <div className="flex border-b border-white/[0.06]">
            {['login', 'signup'].map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`flex-1 py-3.5 text-sm font-medium transition-colors
                  ${tab === t
                    ? 'text-white border-b-2 border-cyan-400 bg-white/[0.02]'
                    : 'text-slate-500 hover:text-slate-300'}`}
              >
                {t === 'login' ? 'Sign In' : 'Create Account'}
              </button>
            ))}
          </div>

          {/* Form body */}
          <div className="px-6 py-7">
            {tab === 'login'
              ? <LoginForm onSwitchToSignup={() => setTab('signup')} />
              : <SignupForm onSwitchToLogin={() => setTab('login')} />}
          </div>
        </div>

        <p className="text-center text-[11px] text-slate-700 mt-6">
          Mini Assistant · AI Workspace · v1.0
        </p>
      </div>
    </div>
  );
}
