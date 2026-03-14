/**
 * hooks/useChat.js
 * Custom hook for sending chat messages through the API.
 */

import { useState, useRef, useCallback } from 'react';
import { api } from '../api/client';

/**
 * useChat()
 * Returns { send, cancel, loading }
 * send(text, sessionId, history, imageBase64) → API response data
 * cancel(sessionId) → cancels in-flight request
 */
export function useChat() {
  const [loading, setLoading] = useState(false);
  const abortControllerRef = useRef(null);

  const send = useCallback(async (text, sessionId, history = [], imageBase64 = null, preferredModel = null) => {
    setLoading(true);
    abortControllerRef.current = new AbortController();

    try {
      const data = await api.chat(text, sessionId, history, imageBase64, preferredModel);
      return data;
    } finally {
      setLoading(false);
      abortControllerRef.current = null;
    }
  }, []);

  const cancel = useCallback(async (sessionId) => {
    // Abort in-flight fetch if possible
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    // Also call the backend cancel endpoint
    if (sessionId) {
      try {
        await api.cancelGeneration(sessionId);
      } catch {
        // ignore errors on cancel
      }
    }
    setLoading(false);
  }, []);

  return { send, cancel, loading };
}

export default useChat;
