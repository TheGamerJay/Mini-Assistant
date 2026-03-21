import React from 'react';
import LegalLayout from './LegalLayout';

export default function PrivacyPage() {
  return (
    <LegalLayout title="Privacy Policy" lastUpdated="March 2026">
      <h2>1. What We Collect</h2>
      <p>We collect information you provide directly: account name, email address, and payment information (processed by Stripe — we never store card numbers). We also collect usage data such as prompts submitted, features used, and credit consumption to operate the Service.</p>

      <h2>2. How We Use Your Data</h2>
      <ul>
        <li>To provide and improve the Service</li>
        <li>To process payments and manage your account</li>
        <li>To send transactional emails (receipts, account alerts)</li>
        <li>To prevent abuse and enforce our policies</li>
      </ul>

      <h2>3. AI Prompts & Outputs</h2>
      <p>Prompts you send are processed by third-party AI providers (Anthropic for chat, OpenAI for image generation). These providers have their own privacy policies. We do not sell your prompts to third parties. We may retain prompts for a limited period for abuse prevention and quality monitoring.</p>

      <h2>4. Data Sharing</h2>
      <p>We do not sell your personal data. We share data only with:</p>
      <ul>
        <li>AI providers (Anthropic, OpenAI) to process your requests</li>
        <li>Stripe for payment processing</li>
        <li>Infrastructure providers (Railway) to host the Service</li>
        <li>Law enforcement when required by law</li>
      </ul>

      <h2>5. Cookies & Tracking</h2>
      <p>We use session tokens stored in localStorage for authentication. We do not use third-party advertising trackers or sell browsing data.</p>

      <h2>6. Data Retention</h2>
      <p>We retain your account data for as long as your account is active. You may request deletion of your account and associated data at any time via account settings or by contacting support.</p>

      <h2>7. Security</h2>
      <p>We use industry-standard encryption (TLS) for data in transit and secure hashing for passwords. No system is 100% secure — please use a strong, unique password.</p>

      <h2>8. Children's Privacy</h2>
      <p>The Service is not directed to children under 13. We do not knowingly collect data from children under 13. If you believe we have, contact us immediately.</p>

      <h2>9. Your Rights</h2>
      <p>Depending on your location, you may have rights to access, correct, or delete your personal data. Contact miniassistantai@gmail.com to exercise these rights.</p>

      <h2>10. Contact</h2>
      <p>Privacy questions: miniassistantai@gmail.com</p>
    </LegalLayout>
  );
}
