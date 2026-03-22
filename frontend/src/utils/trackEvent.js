/**
 * trackEvent — lightweight client-side event tracker.
 * Fires-and-forgets to /api/events. Never blocks the UI.
 *
 * Usage:
 *   trackEvent('build_started', { project_id: '...' });
 */

const BASE_URL = process.env.REACT_APP_BACKEND_URL || '/api';

export function trackEvent(eventName, metadata = {}) {
  try {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token') || null;
    fetch(`${BASE_URL}/events`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: token } : {}),
      },
      body: JSON.stringify({ event: eventName, metadata }),
    }).catch(() => {}); // never reject
  } catch {
    // silently ignore
  }
}
