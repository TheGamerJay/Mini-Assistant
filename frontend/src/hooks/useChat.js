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

  const send = useCallback(async (text, sessionId, history = [], imagesBase64 = null, preferredModel = null, requestId = null) => {
    setLoading(true);
    abortControllerRef.current = new AbortController();

    try {
      const data = await api.chat(text, sessionId, history, imagesBase64, preferredModel, requestId);
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
    { onToken, onDone, onError, vibeMode = false, chatMode = null } = {}
  ) => {
    setLoading(true);
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const res = await api.chatStream(text, sessionId, history, imagesBase64, controller.signal, vibeMode, chatMode);
      if (res.status === 402) throw new Error('out_of_credits');
      if (res.status === 429) {
        let retryAfter = 30;
        try { const d = await res.json(); retryAfter = d.retry_after || retryAfter; } catch {}
        throw new Error(`rate_limit:${retryAfter}`);
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete trailing line

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try {
            const evt = JSON.parse(raw);
            if (evt.done) {
              onDone && onDone(evt.meta || {});
            } else if (evt.t !== undefined) {
              onToken && onToken(evt.t);
            }
          } catch { /* malformed SSE line — ignore */ }
        }
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
