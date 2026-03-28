/**
 * api/client.js
 * Clean API layer for Mini Assistant backend endpoints.
 */

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';
export const IMAGE_API = `${BACKEND_URL}/image-api/api`;
const MAIN_API = `${BACKEND_URL}/api`;
const API_KEY = process.env.REACT_APP_API_KEY || '';

export { BACKEND_URL };

// ---------------------------------------------------------------------------
// JWT token management
// ---------------------------------------------------------------------------
export function getToken() { return localStorage.getItem('ma_token'); }
export function setToken(t) { localStorage.setItem('ma_token', t); }
export function clearToken() { localStorage.removeItem('ma_token'); }

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function request(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const _token = getToken();
  const authHeaders = {
    ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
    ...(_token ? { 'Authorization': `Bearer ${_token}` } : {}),
  };

  // If caller passed headers: {} (empty), skip Content-Type so browser sets it (multipart)
  const callerHeaders = options.headers;
  const baseHeaders = callerHeaders && Object.keys(callerHeaders).length === 0
    ? { ...authHeaders }
    : { 'Content-Type': 'application/json', ...authHeaders, ...callerHeaders };

  try {
    const res = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: baseHeaders,
    });

    clearTimeout(timer);

    let data;
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      data = await res.json();
    } else {
      data = await res.text();
    }

    if (!res.ok) {
      // Auto-logout on 401 — token expired or account deleted
      if (res.status === 401) {
        clearToken();
        window.dispatchEvent(new CustomEvent('ma:unauthorized'));
      }
      throw new ApiError(
        (data && data.detail) || (data && data.message) || `HTTP ${res.status}`,
        res.status,
        data
      );
    }

    return data;
  } catch (err) {
    clearTimeout(timer);
    if (err.name === 'AbortError') {
      throw new ApiError('Request timed out', 408, null);
    }
    throw err;
  }
}

function post(url, body, timeoutMs) {
  return request(url, { method: 'POST', body: JSON.stringify(body) }, timeoutMs);
}

function get(url, timeoutMs) {
  return request(url, { method: 'GET' }, timeoutMs);
}

function del(url, timeoutMs) {
  return request(url, { method: 'DELETE' }, timeoutMs);
}

export const api = {
  /** Send a chat message with optional conversation history, attached images, and model override */
  chat(message, sessionId, history = [], imagesBase64 = null, preferredModel = null, requestId = null) {
    const trimmedHistory = history.slice(-10).map(m => ({ role: m.role, content: m.content }));
    const body = { message, session_id: sessionId, history: trimmedHistory };
    const imgs = Array.isArray(imagesBase64) ? imagesBase64.filter(Boolean) : (imagesBase64 ? [imagesBase64] : []);
    if (imgs.length === 1) body.image_base64 = imgs[0];
    else if (imgs.length > 1) body.images_base64 = imgs;
    if (preferredModel) body.preferred_model = preferredModel;
    if (requestId)      body.request_id      = requestId;
    return post(`${IMAGE_API}/chat`, body, 120000);
  },

  /** Open a streaming chat connection. Returns a raw fetch Response (SSE). */
  chatStream(message, sessionId, history = [], imagesBase64 = null, signal = null, vibeMode = false, chatMode = null) {
    const trimmedHistory = history.slice(-10).map(m => ({ role: m.role, content: m.content }));
    const body = { message, session_id: sessionId, history: trimmedHistory };
    const imgs = Array.isArray(imagesBase64) ? imagesBase64.filter(Boolean) : (imagesBase64 ? [imagesBase64] : []);
    if (imgs.length === 1) body.image_base64 = imgs[0];
    else if (imgs.length > 1) body.images_base64 = imgs;
    if (vibeMode) body.vibe_mode = true;
    if (chatMode) body.chat_mode = chatMode;
    const _streamToken = getToken();
    const authHeaders = {
      ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
      ...(_streamToken ? { 'Authorization': `Bearer ${_streamToken}` } : {}),
    };
    return fetch(`${IMAGE_API}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify(body),
      signal,
    });
  },

  /** One autonomous bug-fix pass. Returns raw fetch Response (SSE). */
  autofixStream(html, errors, domReport, iteration, sessionId, signal) {
    const _token = getToken();
    const authHeaders = {
      ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
      ...(_token ? { 'Authorization': `Bearer ${_token}` } : {}),
    };
    return fetch(`${IMAGE_API}/autofix/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify({ html, errors, dom_report: domReport || null, iteration, session_id: sessionId }),
      signal,
    });
  },

  /** Summarize a list of messages into bullet points for context compaction */
  summarizeMessages(messages) {
    const msgs = messages
      .filter(m => (m.role === 'user' || m.role === 'assistant') && m.content)
      .map(m => ({ role: m.role, content: m.content }));
    return post(`${IMAGE_API}/chat/summarize`, { messages: msgs }, 60000);
  },

  /** Run the same message through two models in parallel; returns {reply_a, model_a, reply_b, model_b} */
  chatCompare(message, sessionId, history = []) {
    const trimmedHistory = history.slice(-10).map(m => ({ role: m.role, content: m.content }));
    return post(`${IMAGE_API}/chat/compare`, { message, session_id: sessionId, history: trimmedHistory }, 180000);
  },

  /**
   * Try to call Ollama directly on localhost:11434 for image analysis.
   * Only works when the user's machine runs Ollama locally (e.g. developer).
   * Returns the reply string on success, throws on failure/timeout.
   * Timeout is 25s — fast enough to still fall back to backend if it fails.
   */
  async tryLocalOllamaChat(message, imageBase64, model = 'gemma3:4b') {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 25000);
    try {
      const res = await fetch('http://localhost:11434/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model,
          messages: [{ role: 'user', content: message, images: [imageBase64] }],
          stream: false,
        }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`Ollama local: HTTP ${res.status}`);
      const data = await res.json();
      const reply = data.message?.content;
      if (!reply) throw new Error('Empty reply from local Ollama');
      return reply;
    } finally {
      clearTimeout(timer);
    }
  },

  /** Get session memory facts */
  getMemory(sessionId) {
    return get(`${MAIN_API}/memory/${sessionId}`, 10000);
  },

  /** Manually store a memory fact */
  storeFact(sessionId, key, value, confidence = 0.9) {
    return post(`${MAIN_API}/memory/${sessionId}/fact`, { key, value, confidence }, 10000);
  },

  /** Clear all session memory */
  clearMemory(sessionId) {
    return del(`${MAIN_API}/memory/${sessionId}`, 10000);
  },

  /** Transcribe audio via Whisper STT */
  transcribeAudio(audioBlob) {
    const formData = new FormData();
    formData.append('file', audioBlob, 'recording.wav');
    return request(`${MAIN_API}/voice/stt`, {
      method: 'POST',
      body: formData,
      headers: {},
    }, 30000);
  },

  /** Extract text from a PDF or plain-text file */
  extractTextFromFile(file) {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return request(`${MAIN_API}/extract-text`, {
      method: 'POST',
      body: formData,
      headers: {},
    }, 60000);
  },

  /**
   * Generate an image — Phase 7: smart ComfyUI routing.
   * params may include: prompt, quality, session_id,
   *   reference_image_base64, mask_image_base64,
   *   pose_image_base64, style_image_base64,
   *   init_image_base64, denoise_strength,
   *   dry_run, override_checkpoint, override_workflow,
   *   override_width, override_height, override_steps,
   *   override_cfg, override_seed
   */
  generateImage(params) {
    return post(`${IMAGE_API}/image/generate`, params, 360000);
  },

  /** Route a prompt to determine intent */
  routePrompt(prompt) {
    return post(`${IMAGE_API}/image/route`, { prompt }, 30000);
  },

  /** Analyze an image */
  analyzeImage(image_base64, question) {
    return post(`${IMAGE_API}/image/analyze`, { image_base64, question }, 60000);
  },

  /** Get models status */
  modelsStatus() {
    return get(`${IMAGE_API}/models/status`, 10000);
  },

  /** Pull models */
  pullModels(models) {
    return post(`${IMAGE_API}/models/pull`, { models }, 120000);
  },

  /** Cancel an ongoing generation */
  cancelGeneration(sessionId) {
    return del(`${IMAGE_API}/image/generate/${sessionId}`, 10000);
  },

  /** Image API health check */
  imageHealth() {
    return get(`${IMAGE_API}/health`, 10000);
  },

  /** Main backend health check */
  mainHealth() {
    return get(`${MAIN_API}/health`, 10000);
  },

  // ── Phase 8: Tool & Security Layer ──────────────────────────────────────

  /** List registered tools (optionally filter by category) */
  listTools(category) {
    const url = category
      ? `${MAIN_API}/tools?category=${encodeURIComponent(category)}`
      : `${MAIN_API}/tools`;
    return get(url, 10000);
  },

  /** Execute a tool immediately (auto_approve=true skips the approval queue) */
  executeTool(toolName, command, sessionId = 'default', cwd = null, autoApprove = false) {
    return post(`${MAIN_API}/tools/execute`, {
      tool_name: toolName,
      command,
      session_id: sessionId,
      cwd,
      auto_approve: autoApprove,
    }, 60000);
  },

  /** Dry-run security evaluation without executing */
  evaluateTool(toolName, command, sessionId = 'default') {
    return post(`${MAIN_API}/tools/evaluate`, {
      tool_name: toolName,
      command,
      session_id: sessionId,
    }, 10000);
  },

  /** List pending tool approvals for a session */
  listApprovals(sessionId) {
    const url = sessionId
      ? `${MAIN_API}/tools/approvals?session_id=${encodeURIComponent(sessionId)}`
      : `${MAIN_API}/tools/approvals`;
    return get(url, 10000);
  },

  /** Approve and execute a pending tool call */
  approveTool(approvalId, cwd = null) {
    const url = cwd
      ? `${MAIN_API}/tools/approve/${approvalId}?cwd=${encodeURIComponent(cwd)}`
      : `${MAIN_API}/tools/approve/${approvalId}`;
    return post(url, {}, 60000);
  },

  /** Deny a pending tool call */
  denyTool(approvalId) {
    return post(`${MAIN_API}/tools/deny/${approvalId}`, {}, 10000);
  },

  // ── Auth endpoints ──────────────────────────────────────────────────────────

  /** Register a new account. Returns { token, user }. */
  authRegister(name, email, password, securityQuestion, securityAnswer, referralCode) {
    return post(`${MAIN_API}/auth/register`, {
      name,
      email,
      password,
      security_question: securityQuestion || null,
      security_answer: securityAnswer || null,
      referral_code: referralCode || null,
    }, 15000);
  },

  /** Get current user's referral code and stats. */
  authReferral() {
    return get(`${MAIN_API}/auth/referral`, 10000);
  },

  /** Login with credentials. Returns { token, user }. */
  authLogin(email, password) {
    return post(`${MAIN_API}/auth/login`, { email, password }, 15000);
  },

  /** Sign in / sign up via Google OAuth. credential = Google ID token. Returns { token, user }. */
  authGoogle(credential) {
    return post(`${MAIN_API}/auth/google`, { credential }, 15000);
  },

  /** Get current user profile (requires Bearer token). */
  authMe() {
    return get(`${MAIN_API}/auth/me`, 10000);
  },

  /** Verify email using token from verification link. */
  authVerifyEmail(token) {
    return request(`${MAIN_API}/auth/verify-email`, {
      method: 'POST',
      body: JSON.stringify({ token }),
    }, 10000);
  },

  /** Resend the verification email to the authenticated user. */
  authResendVerification() {
    return request(`${MAIN_API}/auth/resend-verification`, {
      method: 'POST',
      body: JSON.stringify({}),
    }, 10000);
  },

  /** Get current credit balance and plan. */
  authCredits() {
    return get(`${MAIN_API}/auth/credits`, 10000);
  },

  /** Get personal usage dashboard stats + recent activity. */
  authDashboard() {
    return get(`${MAIN_API}/auth/dashboard`, 15000);
  },

  /** Update display name. */
  authUpdateProfile(name) {
    return request(`${MAIN_API}/auth/profile`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }, 10000);
  },

  /** Update avatar (base64 dataUrl or null to remove). */
  authUpdateAvatar(avatar) {
    return request(`${MAIN_API}/auth/avatar`, {
      method: 'PATCH',
      body: JSON.stringify({ avatar }),
    }, 15000);
  },

  /** Change password. */
  authChangePassword(currentPassword, newPassword) {
    return post(`${MAIN_API}/auth/change-password`, {
      current_password: currentPassword,
      new_password: newPassword,
    }, 15000);
  },

  /** Delete account. */
  authDeleteAccount() {
    return del(`${MAIN_API}/auth/account`, 15000);
  },

  /** Get security question for a given email (no auth required). */
  authSecurityQuestion(email) {
    return get(`${MAIN_API}/auth/security-question?email=${encodeURIComponent(email)}`, 10000);
  },

  /** Reset password using security answer. */
  authResetPassword(email, answer, newPassword) {
    return post(`${MAIN_API}/auth/reset-password`, {
      email,
      answer,
      new_password: newPassword,
    }, 15000);
  },

  // ── Admin endpoints (/api/admin/*) ─────────────────────────────────────────

  /** List all users — admin only */
  adminGetUsers() { return get(`${MAIN_API}/admin/users`, 15000); },

  /** Get platform-wide stats — admin only */
  adminGetStats() { return get(`${MAIN_API}/admin/stats`, 15000); },

  /** Change a user's role — admin only */
  adminSetRole(userId, role) {
    return request(`${MAIN_API}/admin/users/${userId}/role`, { method: 'PATCH', body: JSON.stringify({ role }) }, 10000);
  },

  /** Delete a user and all their data — admin only */
  adminDeleteUser(userId) { return del(`${MAIN_API}/admin/users/${userId}`, 10000); },

  /** Set a user's credit balance — admin only */
  adminSetCredits(userId, credits) {
    return request(`${MAIN_API}/admin/users/${userId}/credits`, { method: 'PATCH', body: JSON.stringify({ credits }) }, 10000);
  },

  /** Set a user's bonus image allowance on top of their plan limit — admin only */
  adminSetImages(userId, images) {
    return request(`${MAIN_API}/admin/users/${userId}/images`, { method: 'PATCH', body: JSON.stringify({ images }) }, 10000);
  },

  /** Get recent activity logs — admin only */
  adminGetActivity(limit = 100) { return get(`${MAIN_API}/admin/activity?limit=${limit}`, 15000); },

  /** Unified revenue + cost + usage analytics — admin only */
  adminGetAnalytics() { return get(`${MAIN_API}/admin/analytics`, 20000); },

  /** Credit pricing optimizer analysis — admin only */
  adminGetPricingOptimizer() { return get(`${MAIN_API}/admin/pricing-optimizer`, 15000); },

  /** Set a user's plan — admin only */
  adminSetPlan(userId, plan) {
    return request(`${MAIN_API}/admin/users/${userId}/plan`, { method: 'PATCH', body: JSON.stringify({ plan }) }, 10000);
  },

  /** Get users flagged for potential abuse — admin only */
  adminGetAbuseFlags(actioned = false) {
    return get(`${MAIN_API}/admin/abuse-flags?actioned=${actioned}`, 10000);
  },

  /** Mark a user's abuse flags as reviewed — admin only */
  adminActionAbuseFlag(userId, note = '') {
    return request(`${MAIN_API}/admin/abuse-flags/${userId}`, { method: 'PATCH', body: JSON.stringify({ note }) }, 10000);
  },

  /** Get system-level alerts (margin drops, cost spikes) — admin only */
  adminGetSystemAlerts(limit = 50) {
    return get(`${MAIN_API}/admin/system-alerts?limit=${limit}`, 10000);
  },

  // ── Stripe billing endpoints ─────────────────────────────────────────────────

  /** Create a Stripe Checkout session (subscription or top-up). Returns { checkout_url, session_id }. */
  stripeCreateCheckout(priceId) {
    return post(`${MAIN_API}/stripe/create-checkout-session`, { price_id: priceId }, 15000);
  },

  /** Open Stripe Billing Portal. Returns { portal_url }. */
  stripeOpenPortal() {
    return post(`${MAIN_API}/stripe/billing-portal`, {}, 10000);
  },

  /** Create a public share link. Returns { id, url, created_at }. */
  createShare(contentType, content, title = '', prompt = '') {
    return post(`${MAIN_API}/share`, { content_type: contentType, content, title, prompt }, 15000);
  },

  /** Delete own share. */
  deleteShare(shareId) {
    return request(`${MAIN_API}/share/${shareId}`, { method: 'DELETE' }, 10000);
  },

  /** Get full credit breakdown for a user. */
  stripeGetCredits(userId) {
    return get(`${MAIN_API}/stripe/credits/${userId}`, 10000);
  },

  // ── DB sync endpoints ───────────────────────────────────────────────────────

  /** Fetch all chats for the current user from MongoDB. */
  dbGetChats() {
    return get(`${MAIN_API}/db/chats`, 15000);
  },

  /** Replace all chats for the current user in MongoDB. */
  dbSaveChats(chats) {
    return post(`${MAIN_API}/db/chats`, { chats }, 20000);
  },

  /** Fetch all projects for the current user from MongoDB. */
  dbGetProjects() {
    return get(`${MAIN_API}/db/projects`, 15000);
  },

  /** Replace all projects for the current user in MongoDB. */
  dbSaveProjects(projects) {
    return post(`${MAIN_API}/db/projects`, { projects }, 20000);
  },

  /** Fetch user settings from MongoDB. */
  dbGetSettings() {
    return get(`${MAIN_API}/db/settings`, 10000);
  },

  /** Replace user settings in MongoDB. */
  dbSaveSettings(settings) {
    return post(`${MAIN_API}/db/settings`, { settings }, 10000);
  },

  /** Fetch prompt templates from MongoDB. */
  dbGetTemplates() {
    return get(`${MAIN_API}/db/templates`, 10000);
  },

  /** Replace prompt templates in MongoDB. */
  dbSaveTemplates(templates) {
    return post(`${MAIN_API}/db/templates`, { templates }, 10000);
  },

  // ── Document text extraction ─────────────────────────────────────────────

  /** Upload a file (PDF, TXT, MD, CSV) and extract its text. */
  extractTextFromFile(file) {
    const form = new FormData();
    form.append('file', file);
    return request(`${IMAGE_API}/extract-text`, { method: 'POST', body: form }, 30000);
  },

  // ── Code execution ──────────────────────────────────────────────────────

  /** Execute Python code on the server. Returns { output, error, exit_code }. */
  executeCode(code, language = 'python') {
    return post(`${IMAGE_API}/execute`, { code, language }, 15000);
  },

  // ── Follow-up suggestions ───────────────────────────────────────────────

  /** Get 3 follow-up suggestions for the last exchange. */
  getSuggestions(message, reply) {
    return post(`${IMAGE_API}/chat/suggestions`, { message, reply }, 20000);
  },

  // ── Tasks ───────────────────────────────────────────────────────────────

  /** Fetch all tasks for the current user. */
  getTasks() { return get(`${MAIN_API}/tasks`, 10000); },

  /** Add a new task. */
  addTask(text) { return post(`${MAIN_API}/tasks`, { text }, 10000); },

  /** Update a task (toggle done, edit text). */
  updateTask(id, updates) {
    return request(`${MAIN_API}/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(updates) }, 10000);
  },

  /** Delete a task. */
  deleteTask(id) { return request(`${MAIN_API}/tasks/${id}`, { method: 'DELETE' }, 10000); },

  // ── Ad Mode endpoints ──────────────────────────────────────────────────────

  /** Check if user has Ad Mode access. Returns { has_ad_mode }. */
  adModeStatus() { return get(`${MAIN_API}/ad-mode/status`, 10000); },

  /** Create Stripe checkout for Ad Mode add-on. Returns { checkout_url }. */
  adModeCheckout(billingPeriod = 'monthly') {
    return post(`${MAIN_API}/checkout/ad-mode`, { billing_period: billingPeriod }, 15000);
  },

  /** Generate a brand profile with Claude. Returns { profile }. */
  adModeProfileGenerate(data) { return post(`${MAIN_API}/ad-mode/profile/generate`, data, 90000); },

  /** Get stored brand profile. Returns { profile }. */
  adModeGetProfile() { return get(`${MAIN_API}/ad-mode/profile`, 10000); },

  /** Update brand profile fields. Returns { profile }. */
  adModeUpdateProfile(data) {
    return request(`${MAIN_API}/ad-mode/profile`, { method: 'PUT', body: JSON.stringify(data) }, 15000);
  },

  /** Create a campaign. Returns { campaign }. */
  adModeCreateCampaign(data) { return post(`${MAIN_API}/ad-mode/campaigns`, data, 10000); },

  /** List all campaigns. Returns { campaigns }. */
  adModeGetCampaigns() { return get(`${MAIN_API}/ad-mode/campaigns`, 10000); },

  /** Get one campaign with its ad sets. Returns { campaign, ad_sets }. */
  adModeGetCampaign(id) { return get(`${MAIN_API}/ad-mode/campaigns/${id}`, 10000); },

  /** Generate full ad set (Claude copy + DALL-E images). Returns { ad_sets, count }. */
  adModeGenerate(data) { return post(`${MAIN_API}/ad-mode/generate`, data, 180000); },

  /** Regenerate copy only for an ad set. Returns updated fields. */
  adModeRegenerateCopy(adSetId, campaignId) {
    return post(`${MAIN_API}/ad-mode/regenerate-copy`, { ad_set_id: adSetId, campaign_id: campaignId }, 60000);
  },

  /** Regenerate image for an ad set. Returns { image_base64 }. */
  adModeRegenerateImage(adSetId, imagePrompt) {
    return post(`${MAIN_API}/ad-mode/regenerate-image`, { ad_set_id: adSetId, image_prompt: imagePrompt }, 60000);
  },

  /** Download asset data (base64 image). Returns { image_base64, headline }. */
  adModeDownloadAsset(adSetId) { return get(`${MAIN_API}/ad-mode/assets/${adSetId}/download`, 15000); },
};

export default api;
