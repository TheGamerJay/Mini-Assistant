/**
 * hooks/useModels.js
 * Polls /models/status on mount and every 30 seconds.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api/client';

/**
 * useModels()
 * Returns { status, refresh, loading }
 * status: { available_models, required_status } | null
 */
export function useModels() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.modelsStatus();
      setStatus(data);
    } catch {
      // keep previous status on error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    intervalRef.current = setInterval(refresh, 30000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [refresh]);

  return { status, refresh, loading };
}

export default useModels;
