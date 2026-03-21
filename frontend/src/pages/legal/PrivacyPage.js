import React from 'react';
import LegalLayout from './LegalLayout';

export default function PrivacyPage() {
  return (
    <LegalLayout title="Privacy Policy" lastUpdated="March 21, 2026">

      <p>
        This Privacy Policy describes how Mini Assistant AI ("Company," "we," "us," or "our") collects,
        uses, stores, discloses, and otherwise processes information about you when you access or use the
        Mini Assistant AI platform (the "Service"). By using the Service, you agree to the data practices
        described in this Policy. This Policy is incorporated by reference into our Terms of Service.
      </p>
      <p>
        This Policy does not apply to third-party websites, services, or applications that may link to
        or integrate with our Service.
      </p>

      <h2>1. Information We Collect</h2>
      <p><strong>1.1 Information You Provide Directly</strong></p>
      <ul>
        <li><strong>Account Data:</strong> Name, email address, password (stored as a one-way cryptographic hash — never in plaintext), and profile information provided during registration or account management.</li>
        <li><strong>Authentication Data:</strong> If you register or log in via Google OAuth, we receive your name, email address, and profile picture from Google as permitted by your Google account settings. We do not receive your Google password.</li>
        <li><strong>Payment Data:</strong> Payments are processed by Stripe, Inc. We receive only a transaction confirmation and limited billing metadata (e.g., last four card digits, expiry, billing country). We do not receive, store, or process raw card numbers or full payment credentials at any point.</li>
        <li><strong>Communications:</strong> Messages, support tickets, and other communications you submit to us, including content, timestamps, and associated account information.</li>
        <li><strong>User Content &amp; Prompts:</strong> Prompts, messages, uploaded files, images, and other content you submit to the Service. See Section 9 regarding AI provider processing of prompts.</li>
      </ul>

      <p><strong>1.2 Information We Collect Automatically</strong></p>
      <ul>
        <li><strong>Usage Data:</strong> Pages accessed, features used, Credit consumption, session durations, error events, API request metadata, and interaction timestamps.</li>
        <li><strong>Device &amp; Browser Data:</strong> Browser type and version, operating system, device type, screen resolution, and language settings.</li>
        <li><strong>Device Fingerprint:</strong> We may collect and process a device fingerprint — a composite identifier derived from browser attributes, hardware characteristics, installed fonts, canvas rendering, and other technical signals — for the purposes of detecting ban evasion, fraud prevention, multi-account abuse, and enforcing our Terms of Service. This identifier persists across sessions and may be used to link accounts we determine are operated by the same person.</li>
        <li><strong>Log Data:</strong> IP address, access times, HTTP request and response data, referrer URLs, and diagnostic data. Server logs are retained for up to 90 days and then purged unless required for an active investigation or legal proceeding.</li>
        <li><strong>Acceptance Records:</strong> We record IP address, device identifiers, and timestamp at the point you accept our Terms of Service or complete a purchase. This record constitutes evidence of your consent and agreement.</li>
        <li><strong>Local Storage:</strong> We use browser localStorage to store your authentication token ("ma_token"), UI preferences (e.g., theme), and session state data. This data persists on your device and is transmitted to our servers only as part of normal authenticated API requests.</li>
      </ul>

      <p><strong>1.3 Cookies &amp; Tracking Technologies</strong></p>
      <p>
        We use a minimal set of cookies and browser storage mechanisms, limited to: (a) strictly necessary
        cookies for session management and authentication; and (b) preference cookies for user experience
        persistence. We do not use third-party advertising cookies, behavioral tracking cookies, or
        cross-site tracking technologies. You may configure your browser to refuse cookies, but doing so
        may impair certain Service functionality.
      </p>

      <h2>2. Lawful Basis for Processing</h2>
      <p>
        We process your personal data only where we have a lawful basis to do so. The lawful bases on
        which we rely are:
      </p>
      <ul>
        <li><strong>Performance of a Contract:</strong> Processing necessary to provide you with the Service, manage your account, process payments, fulfill purchases, and communicate account-related matters. Without this processing, we cannot provide the Service.</li>
        <li><strong>Legitimate Interests:</strong> Processing necessary for our legitimate business interests, including: detecting and preventing fraud, abuse, ban evasion, and security threats; enforcing our Terms; improving and securing the Service; maintaining business and compliance records; device fingerprinting for enforcement purposes; and communicating relevant Service updates. We conduct this processing only where our interests are not overridden by your fundamental rights.</li>
        <li><strong>Legal Obligation:</strong> Processing necessary to comply with applicable laws, including tax and financial record-keeping obligations, responses to lawful legal process, and cooperation with regulatory authorities.</li>
        <li><strong>Consent:</strong> Where we rely on your consent (e.g., optional communications), you may withdraw consent at any time without affecting the lawfulness of processing conducted prior to withdrawal. Withdrawal does not affect processing carried out on other lawful bases.</li>
      </ul>

      <h2>3. How We Use Your Information</h2>
      <ul>
        <li>Providing, operating, maintaining, and improving the Service;</li>
        <li>Processing payments and managing account balances and Credit transactions;</li>
        <li>Authenticating your identity and securing your account;</li>
        <li>Responding to support requests and sending service-related communications;</li>
        <li>Monitoring, logging, and reviewing activity to detect, investigate, and prevent fraud, abuse, ban evasion, multi-account abuse, security incidents, and policy violations;</li>
        <li>Enforcing our Terms of Service, Prohibited Uses Policy, and other agreements;</li>
        <li>Complying with applicable legal obligations and responding to lawful requests from authorities;</li>
        <li>Producing aggregated, anonymized analytics to understand usage patterns and guide Service improvements.</li>
      </ul>
      <p>
        <strong>We do not use your prompts or conversation content to train our own AI models.</strong>
      </p>

      <h2>4. Third-Party Processors &amp; Data Sharing</h2>
      <p>
        We share data with third-party service providers only to the extent necessary to operate the
        Service. These providers are contractually bound to process data solely as instructed by us and
        in compliance with applicable law. <strong>We do not sell, rent, or trade your personal
        information to third parties for their marketing or advertising purposes, and we never have.</strong>
      </p>
      <ul>
        <li><strong>Anthropic, PBC (Claude AI):</strong> Your prompts and messages are transmitted to Anthropic's API to generate AI responses. Anthropic processes this data under its own API terms and privacy policy. We do not control Anthropic's independent data practices or retention policies once data is transmitted.</li>
        <li><strong>OpenAI, Inc.:</strong> Where applicable (e.g., image generation), your prompts may be transmitted to OpenAI's API. OpenAI's data use is governed by its API usage policies, which are independent of ours.</li>
        <li><strong>Stripe, Inc.:</strong> All payment processing is handled by Stripe. Stripe may collect, retain, and process payment credentials and identity information under its own privacy policy and applicable financial regulations.</li>
        <li><strong>Railway (Hosting Infrastructure):</strong> We host the Service on Railway. Server-side data, including stored account data, conversation records, logs, device fingerprints, and application data, resides on Railway's infrastructure in the United States.</li>
        <li><strong>Google LLC (OAuth Authentication):</strong> If you use Google Sign-In, your authentication is processed by Google's identity infrastructure subject to Google's Privacy Policy. We receive only the profile data described in Section 1.1.</li>
      </ul>
      <p>
        We may disclose your information without prior notice if required to do so by law, subpoena, court
        order, or governmental or regulatory authority; if we believe in good faith that disclosure is
        necessary to protect the rights, property, or safety of Mini Assistant AI, our users, or the
        public; or in connection with the investigation of fraud, illegal activity, or security incidents.
      </p>
      <p>
        In the event of a merger, acquisition, reorganization, or sale of all or a material portion of
        our assets, your information may be transferred to the acquiring or surviving entity, subject to
        substantially equivalent privacy protections.
      </p>

      <h2>5. Monitoring &amp; Activity Logging</h2>
      <p>
        We log and may actively monitor account activity, API requests, prompt metadata, usage patterns,
        device fingerprints, IP addresses, and related technical data for the purposes of enforcing our
        Terms, detecting abuse and fraud, maintaining security, and complying with legal obligations.
        This monitoring is conducted under our legitimate interest in protecting the integrity of the
        Service and the safety of our users. By using the Service, you consent to this logging and
        monitoring. Monitoring does not obligate us to detect or prevent any particular violation, and
        we assume no liability for failure to identify harmful conduct.
      </p>

      <h2>6. Data Retention</h2>
      <ul>
        <li><strong>Account data:</strong> Retained while your account is active and for up to 90 days following account deletion for backup purging and integrity verification;</li>
        <li><strong>Conversation and prompt data:</strong> Retained while your account is active and deleted within 90 days of account closure, subject to active legal holds;</li>
        <li><strong>Device fingerprint and enforcement data:</strong> Retained for as long as necessary to enforce bans, detect evasion, and protect platform integrity, which may extend beyond account closure;</li>
        <li><strong>Acceptance records (consent logs):</strong> Retained for the duration of any applicable statute of limitations plus a reasonable additional period for dispute resolution purposes;</li>
        <li><strong>Payment and transaction records:</strong> Retained for a minimum of 7 years as required by applicable tax, financial, and regulatory obligations;</li>
        <li><strong>Server logs:</strong> Retained for up to 90 days and then purged, unless required for an active investigation, legal proceeding, or enforcement action.</li>
      </ul>
      <p>
        We may retain data beyond these periods where required by law, subject to a court order, or
        where necessary to protect against, investigate, or respond to active disputes or violations.
      </p>

      <h2>7. Data Security</h2>
      <p>
        We implement commercially reasonable technical and organizational security measures to protect
        your personal data, including TLS encryption for data in transit, bcrypt hashing for passwords,
        and access-controlled server infrastructure. <strong>However, no security system is impenetrable,
        and we cannot guarantee the absolute security of your data.</strong> We disclaim liability for
        unauthorized access, disclosure, or loss of data resulting from third-party breaches, user error,
        novel attack techniques, or other circumstances beyond our reasonable control.
      </p>
      <p>
        You are responsible for maintaining the security of your account credentials and for all activity
        conducted under your account. If you suspect your account has been compromised, notify us
        immediately at <strong>security@miniassistantai.com</strong>.
      </p>

      <h2>8. Your Rights &amp; Choices</h2>
      <p>
        Subject to applicable law and verification of your identity, you may have the right to:
      </p>
      <ul>
        <li><strong>Access:</strong> Request a copy of the personal data we hold about you;</li>
        <li><strong>Correction:</strong> Request correction of inaccurate or incomplete data;</li>
        <li><strong>Deletion:</strong> Request deletion of your personal data, subject to legal retention requirements, active disputes, and our right to retain enforcement-related data;</li>
        <li><strong>Portability:</strong> Request your data in a structured, machine-readable format where technically feasible;</li>
        <li><strong>Objection / Restriction:</strong> Object to or request restriction of certain processing activities, including processing based on legitimate interest;</li>
        <li><strong>Withdraw Consent:</strong> Where processing is based on consent, withdraw consent at any time without affecting prior lawful processing.</li>
      </ul>
      <p>
        Submit written requests to <strong>privacy@miniassistantai.com</strong>. We will respond within
        30 days. We may require identity verification before processing requests. Note that deletion
        requests do not affect device fingerprint and enforcement data we retain under our legitimate
        interest in platform security. Exercising certain rights may limit your ability to use the Service.
      </p>

      <h2>9. AI Provider Data Practices</h2>
      <p>
        When you use AI features, your prompts are transmitted to third-party AI providers (Anthropic,
        OpenAI) to generate responses. We do not control those providers' data retention policies, usage
        practices, or security measures once data leaves our systems. <strong>Do not submit sensitive
        personal data, confidential business information, protected health information (PHI), financial
        account details, or government-issued identification numbers as prompts.</strong> We bear no
        liability for data processed by AI providers in accordance with their own terms.
      </p>

      <h2>10. Children's Privacy</h2>
      <p>
        The Service is not directed to individuals under 18 and we do not knowingly collect personal
        data from minors. If we become aware that a minor has provided personal data, we will promptly
        delete the account and associated data. If you believe a minor has registered, contact{' '}
        <strong>privacy@miniassistantai.com</strong>.
      </p>

      <h2>11. International Users</h2>
      <p>
        The Service is operated from the United States. If you access the Service from outside the
        United States, your personal data will be transferred to and processed in the United States,
        where data protection laws may differ from those in your jurisdiction. By using the Service,
        you consent to this transfer and processing. For users in the European Economic Area, United
        Kingdom, or Switzerland, such transfer occurs on the basis of our legitimate interest in
        providing the Service globally, and we implement appropriate safeguards where required.
      </p>

      <h2>12. Changes to This Policy</h2>
      <p>
        We may update this Privacy Policy at any time. For material changes, we will provide notice
        through the Service or by email before the changes take effect. Continued use of the Service
        after the effective date constitutes acceptance of the updated Policy. The "Last Updated" date
        at the top reflects the most recent revision.
      </p>

      <h2>13. Contact</h2>
      <p>
        Privacy inquiries and data rights requests: <strong>privacy@miniassistantai.com</strong><br />
        Security incidents: <strong>security@miniassistantai.com</strong><br />
        Legal and regulatory matters: <strong>legal@miniassistantai.com</strong>
      </p>

    </LegalLayout>
  );
}
