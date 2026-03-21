import React from 'react';
import LegalLayout from './LegalLayout';

export default function ProhibitedPage() {
  return (
    <LegalLayout title="Prohibited Items & Uses" lastUpdated="March 2026">
      <p>The following types of content and uses are strictly prohibited on Mini Assistant. Violations will result in immediate account suspension and potential legal action.</p>

      <h2>1. Illegal Content</h2>
      <ul>
        <li>Content that violates any applicable local, national, or international law</li>
        <li>Content that facilitates illegal activity or instructs others how to commit crimes</li>
        <li>Stolen intellectual property, pirated software, or counterfeit goods</li>
      </ul>

      <h2>2. Harmful & Dangerous Content</h2>
      <ul>
        <li>Instructions for creating weapons, explosives, or dangerous substances</li>
        <li>Content that promotes self-harm or suicide</li>
        <li>Content designed to facilitate real-world violence or terrorism</li>
      </ul>

      <h2>3. Sexual & Adult Content</h2>
      <ul>
        <li>Any sexually explicit content involving minors (CSAM) — zero tolerance</li>
        <li>Non-consensual intimate imagery or deepfakes</li>
        <li>Explicit sexual content of any kind through our image generation</li>
      </ul>

      <h2>4. Harassment & Hate</h2>
      <ul>
        <li>Content designed to harass, bully, or threaten specific individuals</li>
        <li>Hate speech targeting protected characteristics (race, religion, gender, sexual orientation, disability, etc.)</li>
        <li>Doxxing or sharing private personal information without consent</li>
      </ul>

      <h2>5. Deception & Fraud</h2>
      <ul>
        <li>Generating phishing emails, fake news, or disinformation at scale</li>
        <li>Impersonating real people, companies, or public figures deceptively</li>
        <li>Using the Service to commit fraud or scam other users</li>
      </ul>

      <h2>6. Platform Abuse</h2>
      <ul>
        <li>Automated scraping, spamming, or denial-of-service attacks</li>
        <li>Sharing account credentials or reselling access</li>
        <li>Attempting to bypass safety filters or jailbreak the AI</li>
        <li>Using the Service to train competing AI models</li>
      </ul>

      <h2>Reporting Violations</h2>
      <p>If you encounter prohibited content or suspect a violation, report it to <strong>support@miniassistantai.com</strong>. We take all reports seriously.</p>
    </LegalLayout>
  );
}
