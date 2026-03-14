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

  try {
    const res = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders,
        ...(options.headers || {}),
      },
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
  /** Send a chat message with optional conversation history */
  chat(message, sessionId, history = []) {
    // Only send last 10 turns to keep payload small
    const trimmedHistory = history.slice(-10).map(m => ({ role: m.role, content: m.content }));
    return post(`${IMAGE_API}/chat`, { message, session_id: sessionId, history: trimmedHistory }, 120000);
  },

  /** Generate an image */
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
};

export default api;
