/**
 * usePersist – lightweight localStorage persistence hook.
 *
 * Usage:
 *   const [value, setValue] = usePersist('ma_key', defaultValue);
 *
 * Behaves exactly like useState but reads from / writes to localStorage.
 * JSON-serialisable values only.
 */
import { useState, useEffect, useRef } from 'react';

export function usePersist(key, defaultValue) {
  const [state, setState] = useState(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw === null) return defaultValue;
      return JSON.parse(raw);
    } catch {
      return defaultValue;
    }
  });

  const first = useRef(true);

  useEffect(() => {
    // Skip the initial render to avoid overwriting valid stored data
    // with a stale render cycle value
    if (first.current) { first.current = false; return; }
    try {
      localStorage.setItem(key, JSON.stringify(state));
    } catch {
      // storage full or private-browsing restriction – silently ignore
    }
  }, [key, state]);

  return [state, setState];
}
