import React from 'react';
import LegalLayout from './LegalLayout';
import { Mail, Shield, AlertOctagon, FileText, Clock } from 'lucide-react';

const CONTACTS = [
  {
    icon: Mail,
    category: 'General Support',
    email: 'support@miniassistantai.com',
    description: 'Account issues, billing questions, feature requests, and general assistance.',
    response: 'Within 2 business days',
  },
  {
    icon: FileText,
    category: 'Billing & Payments',
    email: 'billing@miniassistantai.com',
    description: 'Payment disputes, refund requests, subscription management, and invoice inquiries.',
    response: 'Within 3 business days',
  },
  {
    icon: Shield,
    category: 'Legal & Privacy',
    email: 'legal@miniassistantai.com',
    description: 'Terms of Service inquiries, privacy rights requests, data deletion, and legal notices.',
    response: 'Within 5 business days',
  },
  {
    icon: AlertOctagon,
    category: 'Abuse & Policy Violations',
    email: 'abuse@miniassistantai.com',
    description: 'Report prohibited content, platform abuse, account impersonation, or security concerns.',
    response: 'Reviewed within 24 hours',
  },
  {
    icon: FileText,
    category: 'DMCA & Copyright',
    email: 'dmca@miniassistantai.com',
    description: 'Copyright infringement notices and counter-notices under the DMCA.',
    response: 'Within 5 business days',
  },
];

export default function ContactPage() {
  return (
    <LegalLayout title="Contact Us" lastUpdated="March 21, 2026">

      <p>
        Use the appropriate contact below for your inquiry. Directing your message to the correct team
        ensures the fastest possible response. We do not provide phone support at this time.
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
        Response time estimates apply during standard business hours (Monday–Friday, 9 AM–6 PM ET), excluding
        US federal holidays. We aim to meet these targets but cannot guarantee response times during periods of
        high volume, holidays, or circumstances outside our control.
      </p>
      <p>
        For security incidents or active abuse requiring urgent attention, include "URGENT" in the subject
        line of your email to <strong>abuse@miniassistantai.com</strong>. Urgent reports are reviewed on a
        best-effort basis outside of business hours.
      </p>

      <h2>What to Include</h2>
      <p>To help us assist you efficiently, include the following in your message:</p>
      <ul>
        <li>Your registered account email address;</li>
        <li>A clear description of your issue or request;</li>
        <li>Relevant screenshots, transaction IDs, or reference numbers where applicable;</li>
        <li>The date the issue occurred or the purchase was made.</li>
      </ul>

      <h2>Notice for Legal Process</h2>
      <p>
        Service of legal process, subpoenas, court orders, and law enforcement requests must be directed to{' '}
        <strong>legal@miniassistantai.com</strong> with the document attached in PDF format. We review and
        respond to valid legal process in accordance with applicable law.
      </p>

    </LegalLayout>
  );
}
