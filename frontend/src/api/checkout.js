/**
 * checkout.js
 * Stripe subscription checkout integration (BYOK model — no top-ups).
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
  if (!_prices) _prices = { monthly: null, yearly: null };
}

// Pre-fetch immediately so prices are ready before user interaction
const _ready = _fetchPrices();

// ---------------------------------------------------------------------------
// getPriceId — async (waits for prices to load)
// ---------------------------------------------------------------------------
export async function getPriceId(period = 'monthly') {
  await _ready;
  return _prices?.[period] || '';
}

// ---------------------------------------------------------------------------
// PRICE_IDS — lazy proxy
// ---------------------------------------------------------------------------
export const PRICE_IDS = {
  get monthly() { return _prices?.monthly || ''; },
  get yearly()  { return _prices?.yearly  || ''; },
};

// ---------------------------------------------------------------------------
// startCheckout — redirect to Stripe Checkout
// ---------------------------------------------------------------------------
export async function startCheckout(priceId) {
  if (!priceId) {
    throw new Error(
      'Stripe price ID is not configured. ' +
      'Set PRICE_MONTHLY / PRICE_YEARLY env vars in Railway and redeploy.'
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
