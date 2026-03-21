import React from 'react';
import LegalLayout from './LegalLayout';

export default function PrivacyPage() {
  return (
    <LegalLayout title="Privacy Policy" lastUpdated="March 21, 2026">

      <p>
        This Privacy Policy describes how Mini Assistant ("Company," "we," "us," or "our") collects, uses,
        stores, and discloses information about you when you access or use the Mini Assistant platform
        (the "Service"). By using the Service, you agree to the practices described in this Policy.
      </p>
      <p>
        This Policy does not apply to third-party websites, services, or applications that may link to or
        integrate with our Service.
      </p>

      <h2>1. Information We Collect</h2>
      <p><strong>1.1 Information You Provide Directly</strong></p>
      <ul>
        <li><strong>Account Data:</strong> Name, email address, password (stored as a one-way hash), and profile information provided during registration or account management.</li>
        <li><strong>Authentication Data:</strong> If you register or log in via Google OAuth, we receive your name, email address, and profile picture from Google as permitted by your Google account settings.</li>
        <li><strong>Payment Data:</strong> Payment transactions are processed by Stripe, Inc. We receive only a transaction confirmation and limited billing metadata (last four card digits, expiry, billing country). We do not receive, store, or process raw card numbers or full payment credentials.</li>
        <li><strong>Communications:</strong> Messages you send to our support team, including content, timestamps, and associated account information.</li>
        <li><strong>User Content:</strong> Prompts, messages, uploaded files, and other content you submit to the Service.</li>
      </ul>

      <p><strong>1.2 Information We Collect Automatically</strong></p>
      <ul>
        <li><strong>Usage Data:</strong> Pages accessed, features used, credit consumption, session durations, error events, and interaction timestamps.</li>
        <li><strong>Device &amp; Browser Data:</strong> Browser type and version, operating system, device type, screen resolution, and language settings.</li>
        <li><strong>Log Data:</strong> IP address, access times, HTTP request/response data, referrer URLs, and diagnostic data. Logs are retained for up to 90 days.</li>
        <li><strong>Local Storage:</strong> We use browser localStorage to store your authentication token ("ma_token"), user preferences, and session state. This data remains on your device and is not transmitted to third parties except as part of normal authenticated API requests to our servers.</li>
      </ul>

      <p><strong>1.3 Cookies</strong></p>
      <p>
        We use a minimal set of cookies and browser storage mechanisms, limited to: session management and
        authentication (strictly necessary); and user preference persistence (e.g., theme). We do not use
        third-party advertising cookies or cross-site tracking cookies. You may configure your browser to
        refuse cookies, though this may impair certain functionality.
      </p>

      <h2>2. How We Use Your Information</h2>
      <ul>
        <li>Providing, operating, maintaining, and improving the Service;</li>
        <li>Processing payments and managing your account balance and credit transactions;</li>
        <li>Authenticating your identity and securing your account;</li>
        <li>Responding to support requests and communicating service-related notices;</li>
        <li>Detecting, investigating, and preventing fraud, abuse, security incidents, and policy violations;</li>
        <li>Enforcing our Terms of Service and other policies;</li>
        <li>Complying with applicable legal obligations;</li>
        <li>Producing aggregated, anonymized analytics to understand usage patterns and improve Service quality.</li>
      </ul>
      <p>
        <strong>We do not use your prompts or conversation content to train our own AI models.</strong>
      </p>

      <h2>3. Third-Party Processors &amp; Data Sharing</h2>
      <p>
        We share data with third-party service providers solely to the extent necessary to operate the Service.
        These providers are contractually bound to process data only as instructed and in compliance with applicable
        law. We do not sell, rent, or trade your personal information to third parties for marketing or advertising
        purposes.
      </p>
      <ul>
        <li><strong>Anthropic (Claude AI):</strong> Your prompts and messages are transmitted to Anthropic to generate AI responses. Anthropic's data use is governed by its API usage policies. We do not control Anthropic's independent data practices.</li>
        <li><strong>OpenAI:</strong> Where applicable (e.g., image generation or speech transcription), your prompts may be transmitted to OpenAI. OpenAI's data use is governed by its API terms.</li>
        <li><strong>Stripe, Inc.:</strong> Payment processing. Stripe may collect and retain payment and identity data under its own privacy policy.</li>
        <li><strong>Cloud Hosting &amp; Infrastructure:</strong> We use Railway and related infrastructure providers. Server-side data including logs and stored content resides on these platforms.</li>
        <li><strong>Google (OAuth):</strong> If you use Google Sign-In, Google's authentication infrastructure processes your identity credentials subject to Google's Privacy Policy.</li>
      </ul>
      <p>
        We may disclose your information without prior notice if required by law, subpoena, court order, or
        governmental authority; if we believe disclosure is necessary to protect the rights, property, or safety
        of Mini Assistant, our users, or the public; or in connection with an investigation of suspected fraud or
        illegal activity.
      </p>
      <p>
        In the event of a merger, acquisition, or sale of assets, your information may be transferred to the
        acquiring entity subject to equivalent privacy protections.
      </p>

      <h2>4. Data Retention</h2>
      <ul>
        <li><strong>Account data:</strong> Retained until account deletion, plus up to 90 days for backup purging;</li>
        <li><strong>Conversation data:</strong> Retained while your account is active; deleted within 90 days of account closure;</li>
        <li><strong>Payment records:</strong> Retained for 7 years as required by tax and financial regulations;</li>
        <li><strong>Server logs:</strong> Retained for up to 90 days, then purged unless required for an active investigation.</li>
      </ul>

      <h2>5. Data Security</h2>
      <p>
        We implement commercially reasonable technical and organizational security measures, including encrypted
        data transmission (TLS) and hashed credential storage. However, <strong>no security system is
        impenetrable.</strong> We cannot guarantee the absolute security of your data and disclaim liability for
        unauthorized access or loss resulting from circumstances beyond our reasonable control. You are responsible
        for maintaining the security of your account credentials. Report suspected account compromise to{' '}
        <strong>security@miniassistantai.com</strong> immediately.
      </p>

      <h2>6. Your Rights &amp; Choices</h2>
      <p>
        Depending on your jurisdiction, you may have the right to: access a copy of your personal data; request
        correction of inaccurate data; request deletion of your data subject to legal retention obligations;
        receive your data in a portable format; or object to certain processing activities.
      </p>
      <p>
        Submit written requests to <strong>privacy@miniassistantai.com</strong>. We will respond within 30 days
        and may require identity verification. You may delete your account at any time through your profile
        settings, which initiates permanent erasure subject to retention periods above.
      </p>

      <h2>7. Children's Privacy</h2>
      <p>
        The Service is not directed to individuals under 18. We do not knowingly collect data from minors. If
        you believe a minor has registered, contact <strong>privacy@miniassistantai.com</strong> and we will
        delete the account promptly.
      </p>

      <h2>8. International Users</h2>
      <p>
        The Service is operated from the United States. If you access the Service from outside the United States,
        your data will be transferred to and processed in the United States. By using the Service, you consent
        to this transfer and processing.
      </p>

      <h2>9. AI Provider Data Practices</h2>
      <p>
        Your prompts are transmitted to third-party AI providers (Anthropic, OpenAI) to generate responses.
        We do not control those providers' independent data retention or usage practices. Do not submit sensitive
        personal data, confidential business information, or protected health information as prompts.
      </p>

      <h2>10. Changes to This Policy</h2>
      <p>
        We may update this Privacy Policy at any time. For material changes, we will provide notice through the
        Service or by email before changes take effect. Continued use of the Service constitutes acceptance.
      </p>

      <h2>11. Contact</h2>
      <p>
        Privacy inquiries: <strong>privacy@miniassistantai.com</strong><br />
        Legal matters: <strong>legal@miniassistantai.com</strong>
      </p>

    </LegalLayout>
  );
}
