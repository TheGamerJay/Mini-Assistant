/**
 * checkout.js
 * Complete Stripe checkout + billing portal integration for Mini Assistant AI.
 *
 * Usage:
 *   import { startCheckout, openBillingPortal, PRICE_IDS } from './api/checkout';
 *
 *   // Redirect user to Stripe Checkout:
 *   await startCheckout(PRICE_IDS.pro.monthly);
 *
 *   // Open Stripe Billing Portal (manage/cancel subscription):
 *   await openBillingPortal();
 */

import api from './client';

// ---------------------------------------------------------------------------
// Price ID map — matches the env vars set in Railway
// These are the REACT_APP_ versions of the PRICE_* backend env vars
// ---------------------------------------------------------------------------
export const PRICE_IDS = {
  standard: {
    monthly: process.env.REACT_APP_PRICE_STANDARD_MONTHLY || '',
    yearly:  process.env.REACT_APP_PRICE_STANDARD_YEARLY  || '',
  },
  pro: {
    monthly: process.env.REACT_APP_PRICE_PRO_MONTHLY || '',
    yearly:  process.env.REACT_APP_PRICE_PRO_YEARLY  || '',
  },
  max: {
    monthly: process.env.REACT_APP_PRICE_MAX_MONTHLY || '',
    yearly:  process.env.REACT_APP_PRICE_MAX_YEARLY  || '',
  },
  topup: {
    t10: process.env.REACT_APP_PRICE_TOPUP_10 || '',   // $10 → 100 credits
    t25: process.env.REACT_APP_PRICE_TOPUP_25 || '',   // $25 → 300 credits
    t50: process.env.REACT_APP_PRICE_TOPUP_50 || '',   // $50 → 800 credits
  },
};

// Credit amounts for top-up display
export const TOPUP_CREDITS = {
  [PRICE_IDS.topup.t10]: 100,
  [PRICE_IDS.topup.t25]: 300,
  [PRICE_IDS.topup.t50]: 800,
};

// ---------------------------------------------------------------------------
// startCheckout — redirect to Stripe Checkout
// ---------------------------------------------------------------------------

/**
 * Start a Stripe Checkout session for any price ID.
 * Redirects the current tab to Stripe's hosted checkout page.
 *
 * @param {string} priceId — Stripe price ID (from PRICE_IDS above)
 * @throws {Error}        — if API call fails or priceId is empty
 */
export async function startCheckout(priceId) {
  if (!priceId) {
    throw new Error(
      'Stripe price ID is not configured. ' +
      'Set REACT_APP_PRICE_* env vars and redeploy.'
    );
  }

  const { checkout_url } = await api.stripeCreateCheckout(priceId);

  if (!checkout_url) {
    throw new Error('No checkout URL returned from server.');
  }

  // Redirect the current tab (Stripe Checkout)
  window.location.href = checkout_url;
}

// ---------------------------------------------------------------------------
// openBillingPortal — open Stripe Customer Portal
// ---------------------------------------------------------------------------

/**
 * Open the Stripe Billing Portal in a new tab.
 * Allows users to manage/cancel their subscription, update payment method, etc.
 *
 * @throws {Error} if the API call fails
 */
export async function openBillingPortal() {
  const { portal_url } = await api.stripeOpenPortal();

  if (!portal_url) {
    throw new Error('No portal URL returned from server.');
  }

  window.open(portal_url, '_blank', 'noopener,noreferrer');
}

// ---------------------------------------------------------------------------
// handleCheckoutReturn — call on app mount to detect Stripe redirects
// ---------------------------------------------------------------------------

/**
 * Detect Stripe redirect params (?checkout=success|cancelled, ?portal=return)
 * and clean the URL. Returns the detected state string or null.
 *
 * Call once in your App root useEffect:
 *   const result = handleCheckoutReturn();
 *   if (result === 'success') { refreshUserData(); }
 *
 * @returns {'success' | 'cancelled' | 'portal_return' | null}
 */
export function handleCheckoutReturn() {
  const params   = new URLSearchParams(window.location.search);
  const checkout = params.get('checkout');
  const portal   = params.get('portal');

  if (!checkout && !portal) return null;

  // Clean the URL immediately so refreshing doesn't re-trigger
  window.history.replaceState({}, '', window.location.pathname);

  if (checkout === 'success')   return 'success';
  if (checkout === 'cancelled') return 'cancelled';
  if (portal === 'return')      return 'portal_return';
  return null;
}

// ---------------------------------------------------------------------------
// Convenience: plan → price ID lookup
// ---------------------------------------------------------------------------

/**
 * Get the price ID for a plan + billing period.
 *
 * @param {'standard'|'pro'|'max'} plan
 * @param {'monthly'|'yearly'} period
 * @returns {string} price ID or ''
 */
export function getPriceId(plan, period = 'monthly') {
  return PRICE_IDS[plan]?.[period] || '';
}

/**
 * Check if a given price ID is a top-up (one-time payment).
 *
 * @param {string} priceId
 * @returns {boolean}
 */
export function isTopUp(priceId) {
  return Object.values(PRICE_IDS.topup).includes(priceId);
}

/**
 * Get credit amount for a top-up price ID.
 *
 * @param {string} priceId
 * @returns {number} credit amount or 0
 */
export function getTopUpCredits(priceId) {
  return TOPUP_CREDITS[priceId] || 0;
}
