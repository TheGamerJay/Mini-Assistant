/**
 * pages/AuthPage.js
 * Full-screen login / sign-up page shown before entering the workspace.
 * Uses localStorage-based auth via AppContext (register / loginWithCredentials).
 */

import React, { useState, useCallback } from 'react';
import { Loader2 } from 'lucide-react';
import { useGoogleLogin } from '@react-oauth/google';
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
          className="absolute right-3 top-1/2 -translate-y-1/2 text-base leading-none hover:opacity-70 transition-opacity"
          title={visible ? 'Hide password' : 'Show password'}
        >
          {visible ? '🙈' : '👁️'}
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
// Google sign-in button (shared by Login + Signup)
// ---------------------------------------------------------------------------
function GoogleButton() {
  const { loginWithGoogle } = useApp();
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState('');

  const handleSuccess = useCallback(async (tokenResponse) => {
    setLoading(true);
    setError('');
    try {
      // implicit flow gives access_token; backend verifies via Google userinfo endpoint
      const token = tokenResponse.access_token || tokenResponse.credential;
      await loginWithGoogle(token);
    } catch (err) {
      setError(err.message || 'Google sign-in failed.');
    } finally {
      setLoading(false);
    }
  }, [loginWithGoogle]);

  const googleLogin = useGoogleLogin({
    onSuccess: handleSuccess,
    onError: () => setError('Google sign-in was cancelled or failed.'),
    flow: 'implicit',
  });

  return (
    <div>
      <button
        type="button"
        onClick={() => googleLogin()}
        disabled={loading}
        className="w-full flex items-center justify-center gap-3 py-2.5 px-4 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-sm text-slate-200 font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? (
          <Loader2 size={15} className="animate-spin text-slate-400" />
        ) : (
          <svg width="17" height="17" viewBox="0 0 48 48" fill="none">
            <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.08 17.74 9.5 24 9.5z"/>
            <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
            <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
            <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.97 2.36-8.16 2.36-6.26 0-11.57-3.59-13.46-8.83l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
          </svg>
        )}
        {loading ? 'Signing in…' : 'Continue with Google'}
      </button>
      {error && (
        <p className="mt-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>
      )}
    </div>
  );
}

// Divider between Google and email/password forms
function OrDivider() {
  return (
    <div className="flex items-center gap-3 my-1">
      <div className="flex-1 h-px bg-white/8" />
      <span className="text-[11px] text-slate-600 font-medium">or</span>
      <div className="flex-1 h-px bg-white/8" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Login tab
// ---------------------------------------------------------------------------
function LoginForm({ onSwitchToSignup }) {
  const { loginWithCredentials, getUserSecurityQuestion, resetPasswordWithSecurityAnswer } = useApp();
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);
  // forgot flow: null → 'email' → 'answer' → 'done'
  const [forgotStep, setForgotStep] = useState(null);
  const [forgotEmail, setForgotEmail] = useState('');
  const [securityQuestion, setSecurityQuestion] = useState('');
  const [forgotAnswer, setForgotAnswer] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNew, setConfirmNew] = useState('');

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

  const handleForgotEmail = useCallback(async (e) => {
    e.preventDefault();
    setError('');
    if (!forgotEmail) { setError('Enter your email address.'); return; }
    setLoading(true);
    try {
      const q = await getUserSecurityQuestion(forgotEmail);
      if (!q) { setError('No account found with this email, or no security question was set.'); return; }
      setSecurityQuestion(q);
      setForgotStep('answer');
    } catch {
      setError('No account found with this email, or no security question was set.');
    } finally {
      setLoading(false);
    }
  }, [forgotEmail, getUserSecurityQuestion]);

  const handleForgotReset = useCallback(async (e) => {
    e.preventDefault();
    setError('');
    if (!forgotAnswer) { setError('Please answer the security question.'); return; }
    if (!newPassword || newPassword.length < 8) { setError('New password must be at least 8 characters.'); return; }
    if (newPassword !== confirmNew) { setError('Passwords do not match.'); return; }
    setLoading(true);
    try {
      await resetPasswordWithSecurityAnswer(forgotEmail, forgotAnswer, newPassword);
      setForgotStep('done');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [forgotAnswer, newPassword, confirmNew, forgotEmail, resetPasswordWithSecurityAnswer]);

  const resetForgot = () => {
    setForgotStep(null); setForgotEmail(''); setSecurityQuestion('');
    setForgotAnswer(''); setNewPassword(''); setConfirmNew(''); setError('');
  };

  if (forgotStep) {
    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-white">Reset Password</h2>
          <p className="text-xs text-slate-500 mt-1">Answer your security question to set a new password.</p>
        </div>
        {error && <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>}

        {forgotStep === 'done' ? (
          <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/20 px-4 py-3 text-sm text-emerald-400">
            Password reset successfully! You can now sign in with your new password.
          </div>
        ) : forgotStep === 'email' ? (
          <form onSubmit={handleForgotEmail} className="space-y-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-slate-400">Email</label>
              <input type="email" value={forgotEmail} onChange={e => setForgotEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full bg-[#0d0d16] border border-white/10 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 transition-colors" />
            </div>
            <button type="submit" disabled={loading} className="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-violet-600 text-white text-sm font-medium hover:from-cyan-400 hover:to-violet-500 transition-all shadow-lg disabled:opacity-50 flex items-center justify-center gap-2">
              {loading && <Loader2 size={14} className="animate-spin" />}
              {loading ? 'Looking up…' : 'Continue'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleForgotReset} className="space-y-4">
            <div className="rounded-xl bg-cyan-500/5 border border-cyan-500/20 px-4 py-3">
              <p className="text-[11px] text-slate-500 mb-1">Security question</p>
              <p className="text-sm text-slate-200">{securityQuestion}</p>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-slate-400">Your Answer</label>
              <input type="text" value={forgotAnswer} onChange={e => setForgotAnswer(e.target.value)}
                placeholder="Answer (case-insensitive)"
                className="w-full bg-[#0d0d16] border border-white/10 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 transition-colors" />
            </div>
            <PasswordField id="new-pwd" label="New Password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Min. 8 characters" autoComplete="new-password" />
            <PasswordField id="confirm-new-pwd" label="Confirm New Password" value={confirmNew} onChange={e => setConfirmNew(e.target.value)} placeholder="Repeat new password" autoComplete="new-password" />
            <button type="submit" disabled={loading}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-violet-600 text-white text-sm font-medium hover:from-cyan-400 hover:to-violet-500 transition-all shadow-lg disabled:opacity-50 flex items-center justify-center gap-2">
              {loading && <Loader2 size={14} className="animate-spin" />}
              {loading ? 'Resetting…' : 'Reset Password'}
            </button>
          </form>
        )}
        <button onClick={resetForgot} className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
          ← Back to login
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <GoogleButton />
      <OrDivider />
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
        <button type="button" onClick={() => setForgotStep('email')}
          className="text-slate-500 hover:text-slate-300 transition-colors">
          Forgot password?
        </button>
        <button type="button" onClick={onSwitchToSignup}
          className="text-cyan-400 hover:text-cyan-300 transition-colors font-medium">
          Create account →
        </button>
      </div>
    </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sign-up tab
// ---------------------------------------------------------------------------
const SECURITY_QUESTIONS = [
  "What was the name of your first pet?",
  "What city were you born in?",
  "What is your mother's maiden name?",
  "What was the name of your elementary school?",
  "What was the make of your first car?",
  "What is your oldest sibling's middle name?",
  "What street did you grow up on?",
];

function SignupForm({ onSwitchToLogin }) {
  const { register } = useApp();
  const [name, setName]         = useState('');
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm]   = useState('');
  const [securityQuestion, setSecurityQuestion] = useState(SECURITY_QUESTIONS[0]);
  const [securityAnswer, setSecurityAnswer]     = useState('');
  const [agreed, setAgreed]     = useState(false);
  const [showTerms, setShowTerms] = useState(false);
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);

  const handleSignup = useCallback(async (e) => {
    e.preventDefault();
    if (!name || !email || !password || !confirm) { setError('Please fill in all fields.'); return; }
    if (password.length < 8) { setError('Password must be at least 8 characters.'); return; }
    if (password !== confirm) { setError('Passwords do not match.'); return; }
    if (!securityAnswer.trim()) { setError('Please provide an answer to your security question.'); return; }
    if (!agreed) { setError('You must accept the Terms of Service to continue.'); return; }
    setError('');
    setLoading(true);
    try {
      await register(name, email, password, securityQuestion, securityAnswer);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [name, email, password, confirm, securityQuestion, securityAnswer, agreed, register]);

  return (
    <>
      {showTerms && <TermsModal onClose={() => setShowTerms(false)} />}
      <div className="space-y-4">
        <GoogleButton />
        <OrDivider />
      </div>
      <form onSubmit={handleSignup} className="space-y-4 mt-0">
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

        {/* Security question for password recovery */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-slate-400">Security Question <span className="text-slate-600">(for password recovery)</span></label>
          <select
            value={securityQuestion}
            onChange={e => setSecurityQuestion(e.target.value)}
            className="w-full bg-[#0d0d16] border border-white/10 rounded-xl px-4 py-3 text-sm text-slate-200 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 transition-colors"
          >
            {SECURITY_QUESTIONS.map(q => <option key={q} value={q}>{q}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-slate-400">Your Answer</label>
          <input
            type="text"
            value={securityAnswer}
            onChange={e => setSecurityAnswer(e.target.value)}
            placeholder="Your answer (case-insensitive)"
            className="w-full bg-[#0d0d16] border border-white/10 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 transition-colors"
          />
        </div>

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
                {t === 'login' ? 'Sign In' : 'Sign Up'}
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
