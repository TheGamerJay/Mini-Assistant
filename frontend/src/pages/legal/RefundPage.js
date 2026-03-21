import React from 'react';
import LegalLayout from './LegalLayout';

export default function RefundPage() {
  return (
    <LegalLayout title="Refund Policy" lastUpdated="March 21, 2026">

      <p>
        This Refund Policy governs all purchases made through the Mini Assistant AI platform ("Service"),
        including Credit top-up packages and subscription plans. By completing any purchase, you
        acknowledge that you have read and agree to this Policy in its entirety. This Policy is
        incorporated by reference into our Terms of Service. In the event of conflict, our Terms of
        Service prevail.
      </p>

      <h2>1. General No-Refund Policy</h2>
      <p>
        <strong>All purchases on Mini Assistant AI are final and non-refundable</strong>, except as
        expressly and narrowly stated in this Policy or as strictly required by applicable law that
        cannot be contractually waived. This general rule applies without exception to:
      </p>
      <ul>
        <li>Credits that have been partially or fully consumed;</li>
        <li>Subscription fees for billing periods that have already commenced, regardless of actual usage during that period;</li>
        <li>Credits forfeited due to account termination for any reason, including voluntary closure or termination by us for policy violations;</li>
        <li>Purchases made in connection with promotional offers, discounts, or limited-time pricing;</li>
        <li>Credits lost or consumed as a result of your failure to secure your account credentials.</li>
      </ul>
      <p>
        Mini Credits have no monetary value, are not property, and are not redeemable for cash or any
        equivalent under any circumstances. A purchase of Credits constitutes the purchase of a limited,
        revocable license to access Service features — not the acquisition of any tangible good or
        currency of any kind.
      </p>

      <h2>2. Credit Top-Up Packages — Narrow Refund Eligibility</h2>
      <p>
        Credit packages purchased as one-time top-ups may be eligible for a refund only if <strong>all
        three</strong> of the following conditions are simultaneously met:
      </p>
      <ul>
        <li>The refund request is submitted within <strong>48 hours</strong> of the original purchase timestamp;</li>
        <li>No more than <strong>5% of the purchased Credits</strong> have been consumed; <strong>and</strong></li>
        <li>The absolute number of Credits consumed does not exceed <strong>10 Credits</strong>, regardless of the package size purchased.</li>
      </ul>
      <p>
        The dual threshold (percentage and absolute limit) closes the exploit of purchasing large packages
        and requesting refunds after consuming a technically small percentage but a large absolute number
        of Credits. Both conditions must be satisfied. Refund requests failing any single condition will
        be denied without exception.
      </p>

      <h2>3. Subscription Plans — Narrow Refund Eligibility</h2>
      <p>
        Subscription plans are billed on a recurring cycle as selected at checkout.
      </p>
      <ul>
        <li>
          <strong>New subscriptions only:</strong> A refund of the initial subscription charge may be
          requested within <strong>72 hours</strong> of the first payment, provided that: (a) no more
          than <strong>10% of the subscription's included Credits</strong> have been consumed; and
          (b) no more than <strong>20 Credits absolute</strong> have been consumed. Both thresholds apply.
          Approved refunds cancel the subscription immediately.
        </li>
        <li>
          <strong>Renewal charges:</strong> No refunds are available for any automatic renewal charge.
          It is your sole responsibility to cancel your subscription before the renewal date. Failure to
          cancel does not constitute grounds for a refund, regardless of whether you used the Service
          during the renewed period.
        </li>
        <li>
          <strong>Annual plans:</strong> Annual subscriptions are strictly non-refundable beyond the
          72-hour initial eligibility window described above. Unused months remaining in an annual term
          do not qualify for pro-rata or partial refunds of any kind.
        </li>
        <li>
          <strong>Mid-cycle cancellation or downgrade:</strong> Cancelling or downgrading your subscription
          does not trigger any refund of fees already charged. Access continues until the end of the paid
          billing period.
        </li>
      </ul>

      <h2>4. Absolute Disqualifiers — Refunds Will Not Be Issued</h2>
      <p>
        Notwithstanding any other provision of this Policy, a refund will not be issued under any
        circumstances where:
      </p>
      <ul>
        <li>The account has received any refund from Mini Assistant AI within the preceding 12-month rolling period;</li>
        <li>We determine, in our sole discretion, that the refund request is part of a pattern of repetitive purchase-and-refund activity ("refund cycling");</li>
        <li>The account has violated, or is suspected of violating, our Terms of Service or Prohibited Uses Policy;</li>
        <li>The request is submitted by or on behalf of an account that has been previously terminated or suspended by us;</li>
        <li>We reasonably determine the request to be made in bad faith, to be fraudulent, or to be an attempt to exploit this Policy;</li>
        <li>The Credit consumption cannot be independently verified due to data corruption or other technical circumstances beyond our control.</li>
      </ul>
      <p>
        Accounts determined to be abusing this Policy will be permanently suspended without further
        recourse, and any pending refund eligibility will be immediately voided.
      </p>

      <h2>5. Chargeback &amp; Payment Dispute Policy</h2>
      <p>
        <strong>Initiating a chargeback without first contacting us is a material breach of our Terms of
        Service.</strong> Before filing any payment dispute with your bank or card issuer, you must email{' '}
        <strong>billing@miniassistantai.com</strong> and allow us at least five (5) business days to
        investigate and respond.
      </p>
      <p>
        If you initiate a chargeback, reversal, or dispute for a charge that was valid and for which the
        Service was delivered as described — or for Credits that were consumed — we will:
      </p>
      <ul>
        <li>Immediately and permanently terminate your account without notice;</li>
        <li>Forfeit all remaining Credits and access without right of appeal or reinstatement;</li>
        <li>Submit full transaction records, usage logs, and account history as evidence to dispute and reverse the chargeback;</li>
        <li>Pursue recovery of the full disputed amount plus all associated chargeback fees, bank processing fees, and our administrative costs;</li>
        <li>Report the incident to Stripe and fraud prevention services, which may affect your ability to use payment systems across other platforms;</li>
        <li>Permanently ban the associated email address, payment method, device fingerprint, and IP address from the Service.</li>
      </ul>
      <p>
        Accounts subject to open chargebacks are ineligible for any refund under this Policy until the
        chargeback is resolved and withdrawn. A resolved or withdrawn chargeback does not automatically
        reinstate refund eligibility.
      </p>
      <p>
        Initiating a chargeback does not release you from your obligation to pay amounts legitimately
        owed. We reserve the right to pursue all available legal remedies to collect outstanding debts.
      </p>

      <h2>6. Re-Registration After Refund</h2>
      <p>
        Receiving a refund and then re-registering to obtain additional Credits or free-tier access is
        prohibited. We may track email addresses, payment methods, IP addresses, and device fingerprints
        associated with prior refund recipients. Accounts identified as engaging in refund-then-re-register
        activity will be immediately terminated, and all Credits will be forfeited. Such conduct may be
        treated as fraud.
      </p>

      <h2>7. Technical Failures</h2>
      <p>
        If Credits are deducted from your account due to a verified technical failure on our part —
        specifically where the AI service failed to initiate and no useful output was delivered — you
        may contact support to request a Credit restoration. Such requests are evaluated case-by-case,
        are not guaranteed, and are issued as Credit adjustments rather than monetary refunds. Credits
        consumed due to third-party AI provider failures (e.g., Anthropic or OpenAI API outages) are
        handled at our sole discretion. We do not issue monetary refunds for service degradation,
        partial outages, AI output quality dissatisfaction, or feature changes.
      </p>

      <h2>8. Consumer Protection Law Compliance</h2>
      <p>
        Nothing in this Policy is intended to exclude rights you may have under mandatory consumer
        protection laws that cannot be contractually waived. Where such laws require a minimum refund
        right, we will honor that minimum to the extent legally required and no further. This Policy
        operates to the maximum extent permitted by applicable law.
      </p>

      <h2>9. How to Request a Refund</h2>
      <p>
        To request a refund within the narrow eligibility windows described above, email{' '}
        <strong>billing@miniassistantai.com</strong> with subject line "Refund Request" and include:
      </p>
      <ul>
        <li>Your registered account email address;</li>
        <li>The exact date and amount of the purchase;</li>
        <li>Your Stripe transaction or receipt ID where available;</li>
        <li>A description of your reason for requesting a refund.</li>
      </ul>
      <p>
        Approved refunds are processed within 5–10 business days to the original payment method. We
        reserve the right to issue Credit adjustments rather than monetary refunds at our discretion.
        Refund decisions are final.
      </p>

      <h2>10. Modifications to This Policy</h2>
      <p>
        We reserve the right to modify this Refund Policy at any time. Changes apply prospectively to
        purchases made after the effective date. The Policy in effect at the time of your purchase
        governs that purchase.
      </p>

    </LegalLayout>
  );
}
