/**
 * hooks/useChat.js
 * Custom hook for sending chat messages through the API.
 */

import { useState, useRef, useCallback } from 'react';
import { api } from '../api/client';

/**
 * useChat()
 * Returns { send, sendStream, cancel, loading }
 *
 * send(text, sessionId, history, imageBase64) → API response data (non-streaming)
 * sendStream(text, sessionId, history, imageBase64, { onToken, onDone, onError }) → streaming
 * cancel(sessionId) → cancels in-flight request
 */
export function useChat() {
  const [loading, setLoading] = useState(false);
  const abortControllerRef = useRef(null);

  const send = useCallback(async (text, sessionId, history = [], imagesBase64 = null, preferredModel = null, requestId = null, chatMode = null, userTier = null) => {
    setLoading(true);
    abortControllerRef.current = new AbortController();

    try {
      const data = await api.chat(text, sessionId, history, imagesBase64, preferredModel, requestId, chatMode, userTier);
      return data;
    } finally {
      setLoading(false);
      abortControllerRef.current = null;
    }
  }, []);

  /**
   * Stream tokens for a general-chat message.
   * Calls onToken(text) for each chunk, onDone(meta) when complete.
   * If the backend signals image_redirect, calls onDone with {type:'image_redirect'}.
   */
  const sendStream = useCallback(async (
    text,
    sessionId,
    history = [],
    imagesBase64 = null,
    { onToken, onDone, onError, vibeMode = false, chatMode = null, userTier = null } = {}
  ) => {
    setLoading(true);
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const res = await api.chatStream(text, sessionId, history, imagesBase64, controller.signal, vibeMode, chatMode, userTier);
      if (res.status === 402) {
        let reason = 'not_subscribed';
        try { const d = await res.json(); reason = d.reason || reason; } catch {}
        throw new Error(reason);
      }
      if (res.status === 403) {
        let reason = 'no_api_key';
        try { const d = await res.json(); reason = d.detail || d.reason || reason; } catch {}
        throw new Error(reason);
      }
      if (res.status === 429) {
        let retryAfter = 30;
        try { const d = await res.json(); retryAfter = d.retry_after || retryAfter; } catch {}
        throw new Error(`rate_limit:${retryAfter}`);
      }
      if (!res.ok) {
        // Treat all other non-200s as a soft error, not a raw HTTP code
        let detail = '';
        try { const d = await res.json(); detail = d.detail || d.message || ''; } catch {}
        throw new Error(detail || 'server_error');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let receivedDone = false;

      const processLines = (lines) => {
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try {
            const evt = JSON.parse(raw);
            if (evt.done) {
              receivedDone = true;
              onDone && onDone(evt.meta || {});
            } else if (evt.t !== undefined) {
              onToken && onToken(evt.t);
            }
          } catch { /* malformed SSE line — ignore */ }
        }
      };

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            // Flush any remaining bytes in the decoder and buffer
            const tail = decoder.decode(undefined, { stream: false });
            if (tail) buffer += tail;
            if (buffer.trim()) processLines(buffer.split('\n'));
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop(); // keep incomplete trailing line
          processLines(lines);
        }
      } finally {
        reader.cancel().catch(() => {});
      }

      // Stream closed without a done event (e.g. backend crashed mid-response).
      if (!receivedDone) {
        onDone && onDone({});
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        onError && onError(err);
      }
    } finally {
      setLoading(false);
      abortControllerRef.current = null;
    }
  }, []);

  const cancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setLoading(false);
  }, []);

  return { send, sendStream, cancel, loading };
}

export default useChat;
