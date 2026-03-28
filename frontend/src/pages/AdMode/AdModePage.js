/**
 * AdModePage — top-level Ad Mode page.
 *
 * Shows AdModeLocked if user doesn't have Ad Mode.
 * Shows the full dashboard (tabs) if they do.
 */

import React, { useEffect, useState } from 'react';
import { Zap, BarChart2, User, Image, BookOpen } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import AdModeLocked     from './AdModeLocked';
import AdModeOverview   from './AdModeOverview';
import AdModeBrandProfile from './AdModeBrandProfile';
import AdModeGenerate   from './AdModeGenerate';
import AdModeCampaigns  from './AdModeCampaigns';
import { api } from '../../api/client';

const TABS = [
  { id: 'overview',   label: 'Overview',      icon: BarChart2 },
  { id: 'brand',      label: 'Brand Profile', icon: User },
  { id: 'generate',   label: 'Generate Ads',  icon: Image },
  { id: 'campaigns',  label: 'Saved Campaigns', icon: BookOpen },
];

export default function AdModePage() {
  const { hasAdMode, user } = useApp();
  const [tab, setTab]           = useState('overview');
  const [campaigns, setCampaigns] = useState([]);
  const [profile, setProfile]   = useState(null);

  // Pre-load campaigns and profile status for the Overview
  useEffect(() => {
    if (!hasAdMode) return;
    api.adModeGetCampaigns()
      .then(({ campaigns: c }) => setCampaigns(c))
      .catch(() => {});
    api.adModeGetProfile()
      .then(({ profile: p }) => setProfile(p))
      .catch(() => {});
  }, [hasAdMode]);

  if (!hasAdMode) {
    return <AdModeLocked />;
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Top bar */}
      <div className="flex-shrink-0 flex items-center gap-3 px-6 py-3 border-b border-white/8 bg-[#0d0d12]">
        <div className="flex items-center gap-2">
          <Zap size={15} className="text-violet-400" />
          <span className="text-sm font-semibold text-slate-100">Ad Mode</span>
        </div>
        <div className="h-3 w-px bg-white/10 mx-1" />
        <p className="text-xs text-slate-500">AI-powered ad creation</p>
      </div>

      {/* Tab nav */}
      <div className="flex-shrink-0 flex items-center gap-1 px-4 py-2 border-b border-white/5 bg-[#0d0d12]">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
              ${tab === id
                ? 'bg-white/8 text-slate-200 border border-white/10'
                : 'text-slate-500 hover:text-slate-300 hover:bg-white/5'}`}
          >
            <Icon size={12} />
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {tab === 'overview' && (
          <AdModeOverview
            onNav={setTab}
            profileExists={!!profile}
            campaigns={campaigns}
          />
        )}
        {tab === 'brand'     && <AdModeBrandProfile />}
        {tab === 'generate'  && <AdModeGenerate campaigns={campaigns} />}
        {tab === 'campaigns' && <AdModeCampaigns />}
      </div>
    </div>
  );
}
