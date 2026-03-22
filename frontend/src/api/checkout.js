/**
 * checkout.js
 * Complete Stripe checkout + billing portal integration for Mini Assistant AI.
 *
 * Price IDs are fetched from the backend (/api/stripe/prices) so no
 * REACT_APP_PRICE_* env vars are needed — the backend reads PRICE_* directly.
 */

import api from './client';

// ---------------------------------------------------------------------------
// Price cache — populated on module load
// ---------------------------------------------------------------------------

let _prices = null;

async function _fetchPrices() {
  try {
    const BASE = process.env.REACT_APP_API_URL || '';
    const res = await fetch(`${BASE}/api/stripe/prices`);
    if (res.ok) _prices = await res.json();
  } catch (e) {
    console.warn('Could not fetch Stripe prices:', e);
  }
  if (!_prices) _prices = { standard: {}, pro: {}, max: {}, topup: {} };
}

// Pre-fetch immediately so prices are ready before user interaction
const _ready = _fetchPrices();

// ---------------------------------------------------------------------------
// Sync accessor (uses cache — returns '' if prices not loaded yet)
// ---------------------------------------------------------------------------
function _get(plan, period) {
  return _prices?.[plan]?.[period] || '';
}

// ---------------------------------------------------------------------------
// getPriceId — async (waits for prices to load)
// ---------------------------------------------------------------------------
export async function getPriceId(plan, period = 'monthly') {
  await _ready;
  return _get(plan, period);
}

// ---------------------------------------------------------------------------
// PRICE_IDS — lazy proxy so module-level references resolve after load
// PricingPage uses this at module scope; values will be '' until _ready,
// but by the time a user clicks, prices are loaded.
// ---------------------------------------------------------------------------
export const PRICE_IDS = {
  get standard() { return { monthly: _get('standard', 'monthly'), yearly: _get('standard', 'yearly') }; },
  get pro()      { return { monthly: _get('pro', 'monthly'),      yearly: _get('pro', 'yearly')      }; },
  get max()      { return { monthly: _get('max', 'monthly'),      yearly: _get('max', 'yearly')       }; },
  get topup()    { return { t10: _get('topup', 't10'), t25: _get('topup', 't25'), t50: _get('topup', 't50') }; },
};

// ---------------------------------------------------------------------------
// startCheckout — redirect to Stripe Checkout
// ---------------------------------------------------------------------------
export async function startCheckout(priceId) {
  if (!priceId) {
    throw new Error(
      'Stripe price ID is not configured. ' +
      'Set PRICE_* env vars in Railway and redeploy.'
    );
  }

  const { checkout_url } = await api.stripeCreateCheckout(priceId);

  if (!checkout_url) {
    throw new Error('No checkout URL returned from server.');
  }

  window.location.href = checkout_url;
}

// ---------------------------------------------------------------------------
// openBillingPortal — open Stripe Customer Portal
// ---------------------------------------------------------------------------
export async function openBillingPortal() {
  const { portal_url } = await api.stripeOpenPortal();

  if (!portal_url) {
    throw new Error('No portal URL returned from server.');
  }

  window.open(portal_url, '_blank', 'noopener,noreferrer');
}

// ---------------------------------------------------------------------------
// handleCheckoutReturn — detect Stripe redirect params on app mount
// ---------------------------------------------------------------------------
export function handleCheckoutReturn() {
  const params   = new URLSearchParams(window.location.search);
  const checkout = params.get('checkout');
  const portal   = params.get('portal');

  if (!checkout && !portal) return null;

  window.history.replaceState({}, '', window.location.pathname);

  if (checkout === 'success')   return 'success';
  if (checkout === 'cancelled') return 'cancelled';
  if (portal === 'return')      return 'portal_return';
  return null;
}

// ---------------------------------------------------------------------------
// isTopUp / getTopUpCredits
// ---------------------------------------------------------------------------
export function isTopUp(priceId) {
  return Object.values(_prices?.topup || {}).includes(priceId);
}

export function getTopUpCredits(priceId) {
  const t = _prices?.topup || {};
  const map = { [t.t10]: 100, [t.t25]: 300, [t.t50]: 800 };
  return map[priceId] || 0;
}
