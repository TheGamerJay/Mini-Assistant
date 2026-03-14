/**
 * api/client.js
 * Clean API layer for Mini Assistant backend endpoints.
 */

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';
export const IMAGE_API = `${BACKEND_URL}/image-api/api`;
const MAIN_API = `${BACKEND_URL}/api`;
const API_KEY = process.env.REACT_APP_API_KEY || '';

export { BACKEND_URL };

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

  const authHeaders = API_KEY ? { 'X-API-Key': API_KEY } : {};

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
  /** Send a chat message with optional conversation history, attached image, and model override */
  chat(message, sessionId, history = [], imageBase64 = null, preferredModel = null) {
    const trimmedHistory = history.slice(-10).map(m => ({ role: m.role, content: m.content }));
    const body = { message, session_id: sessionId, history: trimmedHistory };
    if (imageBase64)     body.image_base64     = imageBase64;
    if (preferredModel)  body.preferred_model  = preferredModel;
    return post(`${IMAGE_API}/chat`, body, 120000);
  },

  /** Open a streaming chat connection. Returns a raw fetch Response (SSE). */
  chatStream(message, sessionId, history = [], imageBase64 = null, signal = null) {
    const trimmedHistory = history.slice(-10).map(m => ({ role: m.role, content: m.content }));
    const body = { message, session_id: sessionId, history: trimmedHistory };
    if (imageBase64) body.image_base64 = imageBase64;
    const authHeaders = API_KEY ? { 'X-API-Key': API_KEY } : {};
    return fetch(`${IMAGE_API}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify(body),
      signal,
    });
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
};

export default api;
