import React from 'react';
import LegalLayout from './LegalLayout';

export default function RefundPage() {
  return (
    <LegalLayout title="Refund Policy" lastUpdated="March 2026">
      <h2>Overview</h2>
      <p>We want you to be satisfied with Mini Assistant. This policy explains when refunds are available.</p>

      <h2>Subscription Plans</h2>
      <p>If you are unhappy with your subscription within the first <strong>7 days</strong> of your initial purchase, contact us for a full refund. After 7 days, subscriptions are non-refundable for the current billing period. You may cancel at any time — you will retain access until the end of your paid period.</p>

      <h2>Top-Up Credits</h2>
      <p>Top-up credit purchases are <strong>non-refundable</strong> once added to your account. Credits are consumed as you use the Service and cannot be transferred or redeemed for cash.</p>

      <h2>Exceptions</h2>
      <p>We will consider refunds outside the standard policy in the following cases:</p>
      <ul>
        <li>A billing error caused you to be charged incorrectly</li>
        <li>The Service was unavailable for an extended period due to our fault</li>
        <li>A duplicate charge occurred</li>
      </ul>

      <h2>How to Request a Refund</h2>
      <p>Email <strong>support@miniassistantai.com</strong> with your account email, the charge amount, date, and reason. We will respond within 3 business days.</p>

      <h2>Chargebacks</h2>
      <p>If you initiate a chargeback without contacting us first, your account may be suspended pending investigation. We encourage you to contact support first — we are happy to work with you.</p>
    </LegalLayout>
  );
}
