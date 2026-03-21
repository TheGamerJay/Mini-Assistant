import React from 'react';
import LegalLayout from './LegalLayout';
import { Mail, Shield, AlertOctagon, FileText, Clock, CreditCard } from 'lucide-react';

const CONTACTS = [
  {
    icon: Mail,
    category: 'General Support',
    email: 'support@miniassistantai.com',
    description: 'Account issues, technical problems, feature questions, and general platform assistance.',
    response: 'Within 2 business days',
  },
  {
    icon: CreditCard,
    category: 'Billing & Payments',
    email: 'billing@miniassistantai.com',
    description: 'Refund requests, payment disputes, subscription management, invoice inquiries, and Credit balance questions. You must contact us here before initiating any payment dispute with your bank.',
    response: 'Within 3 business days',
  },
  {
    icon: Shield,
    category: 'Legal, Privacy & Compliance',
    email: 'legal@miniassistantai.com',
    description: 'Terms of Service inquiries, privacy rights requests (access, deletion, portability), data processing questions, and formal legal notices. Service of legal process must be directed here.',
    response: 'Within 5 business days',
  },
  {
    icon: Shield,
    category: 'Security Incidents',
    email: 'security@miniassistantai.com',
    description: 'Suspected account compromise, vulnerability disclosures, unauthorized access reports, and data security concerns.',
    response: 'Within 24 hours (business days)',
  },
  {
    icon: AlertOctagon,
    category: 'Abuse & Policy Violations',
    email: 'abuse@miniassistantai.com',
    description: 'Reporting prohibited content, platform abuse, impersonation, ban evasion, or other policy violations. Include as much detail as possible — screenshots and timestamps are helpful.',
    response: 'Reviewed within 24 hours',
  },
  {
    icon: FileText,
    category: 'DMCA & Copyright',
    email: 'dmca@miniassistantai.com',
    description: 'Copyright infringement takedown notices and counter-notices under 17 U.S.C. § 512. Notices must meet all statutory requirements — see our DMCA Policy for full requirements.',
    response: 'Within 5 business days',
  },
];

export default function ContactPage() {
  return (
    <LegalLayout title="Contact Us" lastUpdated="March 21, 2026">

      <p>
        Use the appropriate contact channel below for your inquiry. Directing your message to the correct
        team ensures the fastest possible response. <strong>We do not provide phone support.</strong> All
        inquiries must be submitted by email.
      </p>

      <div className="space-y-4 mt-6">
        {CONTACTS.map(({ icon: Icon, category, email, description, response }) => (
          <div
            key={email}
            className="rounded-xl border border-white/8 bg-white/[0.02] p-5 flex gap-4 items-start"
          >
            <div className="w-9 h-9 rounded-lg bg-cyan-500/10 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Icon size={15} className="text-cyan-400" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-slate-200">{category}</p>
              <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{description}</p>
              <a
                href={`mailto:${email}`}
                className="inline-block mt-2 text-xs font-mono text-cyan-400 hover:text-cyan-300 transition-colors"
              >
                {email}
              </a>
              <div className="flex items-center gap-1.5 mt-1.5">
                <Clock size={10} className="text-slate-600 flex-shrink-0" />
                <span className="text-[10px] text-slate-600 font-mono">{response}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <h2>Response Times</h2>
      <p>
        Response time estimates apply during standard business hours, Monday through Friday, 9 AM to 6 PM
        Eastern Time, excluding US federal holidays. We aim to meet these targets but cannot guarantee
        response times during periods of high volume or circumstances outside our control. Response time
        estimates are not service level commitments.
      </p>
      <p>
        For urgent security incidents, include "URGENT" in the subject line of your email to{' '}
        <strong>security@miniassistantai.com</strong>. Urgent security reports are triaged on a best-effort
        basis outside standard hours.
      </p>

      <h2>What to Include in Your Message</h2>
      <p>To ensure we can assist you efficiently, include the following in every inquiry:</p>
      <ul>
        <li>Your registered account email address;</li>
        <li>A clear, specific description of your issue or request;</li>
        <li>Relevant screenshots, transaction IDs, Stripe receipt numbers, or reference numbers where applicable;</li>
        <li>The date and approximate time the issue occurred or the purchase was made.</li>
      </ul>
      <p>
        Incomplete submissions may delay our ability to respond. We are not obligated to respond to
        communications that do not include sufficient information to identify the account or the issue.
      </p>

      <h2>Billing Disputes — Mandatory Pre-Dispute Contact</h2>
      <p>
        Before initiating any payment dispute, chargeback, or reversal with your bank or card issuer,
        you are required under our Terms of Service to contact us at{' '}
        <strong>billing@miniassistantai.com</strong> and allow at least five (5) business days for us to
        respond. Initiating a dispute without first contacting us is a material breach of our Terms of
        Service and may result in permanent account termination. See our Refund Policy and Terms of
        Service for full details.
      </p>

      <h2>Legal Process &amp; Formal Notices</h2>
      <p>
        Service of legal process, subpoenas, court orders, regulatory requests, and all formal legal
        notices must be directed to <strong>legal@miniassistantai.com</strong> with the document
        attached in PDF format. We review and respond to valid legal process in accordance with
        applicable law. Informal or unverified legal demands sent to general support channels are not
        treated as valid legal notices.
      </p>

      <h2>Privacy Rights Requests</h2>
      <p>
        To exercise your privacy rights — including data access, correction, deletion, or portability
        requests under applicable law — email <strong>privacy@miniassistantai.com</strong> with
        "Privacy Rights Request" in the subject line. We may require identity verification before
        processing any request. We respond to verified requests within 30 days.
      </p>

    </LegalLayout>
  );
}
