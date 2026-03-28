import React from 'react';
import { useApp } from '../../context/AppContext';
import { ArrowLeft } from 'lucide-react';

const FOOTER_LINKS = [
  { label: 'Terms',           page: 'legal-terms' },
  { label: 'Privacy',         page: 'legal-privacy' },
  { label: 'Contact',         page: 'legal-contact' },
  { label: 'Creation Record Info', page: 'creation-record-info' },
];

export default function LegalLayout({ title, lastUpdated, children }) {
  const { getPrevPage, setPage } = useApp();

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-10">
        {/* Back button */}
        <button
          onClick={() => setPage(getPrevPage() || 'chat')}
          className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-300 mb-8 transition-colors"
        >
          <ArrowLeft size={13} /> Back
        </button>

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-slate-100">{title}</h1>
          {lastUpdated && (
            <p className="text-xs text-slate-500 mt-1 font-mono">Last updated: {lastUpdated}</p>
          )}
        </div>

        {/* Content */}
        <div className="prose prose-invert prose-sm max-w-none
          prose-headings:text-slate-200 prose-headings:font-semibold prose-headings:mt-8 prose-headings:mb-3
          prose-h2:text-base prose-h2:border-b prose-h2:border-white/10 prose-h2:pb-2
          prose-p:text-slate-400 prose-p:leading-relaxed
          prose-li:text-slate-400
          prose-strong:text-slate-300
          prose-a:text-cyan-400 prose-a:no-underline hover:prose-a:text-cyan-300">
          {children}
        </div>

        {/* Footer */}
        <div className="mt-16 pt-6 border-t border-white/10 text-center">
          <div className="flex flex-wrap justify-center gap-x-5 gap-y-1 mb-3">
            {FOOTER_LINKS.map(({ label, page }) => (
              <button
                key={page}
                onClick={() => setPage(page)}
                className="text-[11px] text-slate-600 hover:text-slate-400 transition-colors"
              >
                {label}
              </button>
            ))}
          </div>
          <p className="text-[11px] text-slate-600">
            © {new Date().getFullYear()} Mini Assistant. All rights reserved.
          </p>
        </div>
      </div>
    </div>
  );
}
