import React, { useState } from 'react';
import LegalLayout from './LegalLayout';
import { Mail, MessageSquare, Shield, FileText } from 'lucide-react';

export default function ContactPage() {
  const [copied, setCopied] = useState(false);

  const copyEmail = () => {
    navigator.clipboard.writeText('support@miniassistantai.com');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <LegalLayout title="Contact Us" lastUpdated="">
      <p>We're here to help. Choose the right channel for your inquiry below.</p>

      <div className="not-prose grid gap-4 my-6">
        {[
          {
            icon: MessageSquare,
            title: 'General Support',
            desc: 'Account issues, billing questions, feature requests',
            email: 'support@miniassistantai.com',
            color: 'cyan',
          },
          {
            icon: Shield,
            title: 'Trust & Safety',
            desc: 'Report abuse, harmful content, or policy violations',
            email: 'support@miniassistantai.com',
            color: 'red',
          },
          {
            icon: FileText,
            title: 'Legal & DMCA',
            desc: 'Copyright claims, legal notices, privacy requests',
            email: 'support@miniassistantai.com',
            color: 'violet',
          },
          {
            icon: Mail,
            title: 'Business Enquiries',
            desc: 'Partnerships, enterprise plans, press',
            email: 'support@miniassistantai.com',
            color: 'emerald',
          },
        ].map(({ icon: Icon, title, desc, email, color }) => (
          <div key={title} className="flex items-start gap-4 p-4 rounded-xl bg-white/5 border border-white/10">
            <div className={`w-9 h-9 rounded-lg bg-${color}-500/15 flex items-center justify-center flex-shrink-0`}>
              <Icon size={16} className={`text-${color}-400`} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-200">{title}</p>
              <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
              <a
                href={`mailto:${email}`}
                className="text-xs text-cyan-400 hover:text-cyan-300 mt-1 inline-block transition-colors"
              >
                {email}
              </a>
            </div>
          </div>
        ))}
      </div>

      <h2>Response Times</h2>
      <ul>
        <li><strong>General support:</strong> Within 2 business days</li>
        <li><strong>Billing issues:</strong> Within 1 business day</li>
        <li><strong>DMCA / legal:</strong> Within 3 business days</li>
        <li><strong>Urgent safety issues:</strong> Same day</li>
      </ul>

      <h2>Before You Contact Us</h2>
      <p>Many common questions are answered in our documentation. For account and billing questions, you can also manage your plan directly from your account settings.</p>
    </LegalLayout>
  );
}
