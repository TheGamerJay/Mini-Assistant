import React from 'react';
import LegalLayout from './LegalLayout';

export default function RefundPage() {
  return (
    <LegalLayout title="Refund Policy" lastUpdated="March 21, 2026">

      <p>
        This Refund Policy governs all purchases made through the Mini Assistant platform ("Service"), including
        credit top-up packages and subscription plans. By completing a purchase, you acknowledge and agree to
        this Policy in its entirety. This Policy is incorporated by reference into our Terms of Service.
      </p>

      <h2>1. General No-Refund Policy</h2>
      <p>
        <strong>All purchases on Mini Assistant are final and non-refundable</strong>, except as expressly stated
        below or as required by applicable law. This includes, without limitation, credit packages that have been
        partially or fully consumed, subscription fees for periods already commenced, and any credits forfeited
        due to account termination for violation of our Terms of Service.
      </p>
      <p>
        Mini Credits have no monetary value, are not redeemable for cash, and are non-transferable. The purchase
        of credits constitutes the purchase of a limited, revocable license to access Service features — not the
        acquisition of any tangible good or currency.
      </p>

      <h2>2. Credit Top-Up Packages</h2>
      <p>
        Credit packages ("top-ups") are one-time purchases. Once a credit package is purchased:
      </p>
      <ul>
        <li>Credits are added to your account immediately upon payment confirmation;</li>
        <li>Credits that have been consumed cannot be refunded under any circumstances;</li>
        <li>Unconsumed credits from a top-up purchase may be eligible for a refund only if requested within <strong>48 hours</strong> of purchase and no more than <strong>10% of the purchased credits have been used</strong>;</li>
        <li>Refund requests outside this window or threshold will be denied.</li>
      </ul>

      <h2>3. Subscription Plans</h2>
      <p>
        Subscription plans are billed on a recurring cycle (monthly or annually, as selected).
      </p>
      <ul>
        <li><strong>New subscriptions:</strong> A refund may be requested within <strong>72 hours</strong> of the initial subscription charge, provided that fewer than <strong>20% of the subscription's included credits have been used</strong>. Approved refunds will cancel the subscription immediately.</li>
        <li><strong>Renewal charges:</strong> Refunds are not available for renewal charges. It is your responsibility to cancel your subscription before the renewal date. Renewal cancellations take effect at the end of the current billing period — access continues until expiry.</li>
        <li><strong>Annual subscriptions:</strong> Annual plans are non-refundable after the 72-hour eligibility window. Unused months in an annual term do not qualify for pro-rated refunds.</li>
        <li><strong>Downgrading or cancelling:</strong> Cancellation or downgrade of a subscription does not trigger a refund of any fees already charged. Access continues until the end of the paid period.</li>
      </ul>

      <h2>4. Refund Abuse &amp; Excessive Refund Requests</h2>
      <p>
        We reserve the right to deny any refund request if we determine, in our sole discretion, that:
      </p>
      <ul>
        <li>The request is part of a pattern of repetitive purchasing and refunding ("refund abuse");</li>
        <li>The Service was used extensively prior to the refund request, regardless of the technical eligibility window;</li>
        <li>The request is associated with a violation of our Terms of Service or Prohibited Uses Policy;</li>
        <li>The account has received more than one refund in any rolling 12-month period;</li>
        <li>We reasonably suspect the request is fraudulent or made in bad faith.</li>
      </ul>
      <p>
        Accounts found to be abusing our refund process may be permanently suspended without further recourse.
      </p>

      <h2>5. Chargebacks &amp; Payment Disputes</h2>
      <p>
        Initiating a chargeback or payment dispute with your bank or card issuer without first contacting us is
        a violation of these Terms. If you initiate a chargeback for charges that were valid and for which the
        Service was delivered as described, we reserve the right to:
      </p>
      <ul>
        <li>Immediately and permanently suspend your account;</li>
        <li>Forfeit all remaining credits and access;</li>
        <li>Submit evidence to dispute the chargeback in full, including transaction records and usage logs;</li>
        <li>Pursue recovery of the disputed amount plus any chargeback fees and associated costs;</li>
        <li>Report the incident to fraud prevention services.</li>
      </ul>
      <p>
        Before initiating any payment dispute, contact our billing team at{' '}
        <strong>billing@miniassistantai.com</strong>. We commit to responding to billing disputes within 3
        business days and resolving legitimate issues in good faith.
      </p>

      <h2>6. Technical Failures &amp; Service Outages</h2>
      <p>
        If credits are deducted from your account as a result of a verified technical failure on our part —
        where the underlying AI service did not complete as expected and no useful output was delivered — you may
        contact support to request a credit restoration. Such requests are evaluated on a case-by-case basis and
        are not guaranteed. Credits lost due to third-party AI provider failures (e.g., Anthropic API outages)
        are handled at our discretion.
      </p>
      <p>
        We do not issue refunds for service degradation, partial outages, dissatisfaction with AI output quality,
        or changes to the Service's features, models, or pricing.
      </p>

      <h2>7. Consumer Protection Compliance</h2>
      <p>
        Nothing in this Refund Policy is intended to limit rights you may have under applicable consumer
        protection laws that cannot be waived by contract. Where such laws require a refund, we will provide
        one in compliance with the minimum legal standard, and no more.
      </p>

      <h2>8. How to Request a Refund</h2>
      <p>
        To request a refund within the eligible windows described above, email{' '}
        <strong>billing@miniassistantai.com</strong> with the subject line "Refund Request" and include:
      </p>
      <ul>
        <li>Your registered account email address;</li>
        <li>The date and amount of the purchase;</li>
        <li>The reason for your request.</li>
      </ul>
      <p>
        Approved refunds are processed within 5–10 business days and are credited to the original payment method.
        We reserve the right to issue account credits instead of cash refunds where appropriate.
      </p>

      <h2>9. Modifications to This Policy</h2>
      <p>
        We reserve the right to modify this Refund Policy at any time. Changes take effect upon posting to the
        Service. For purchases already completed, the Policy in effect at the time of purchase applies.
      </p>

    </LegalLayout>
  );
}
