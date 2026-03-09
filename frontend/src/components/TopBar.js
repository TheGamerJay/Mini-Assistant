/**
 * components/TopBar.js
 * Slim top bar showing page title and server status badges.
 * Props: { title: string, serverStatus: { backend, ollama, comfyui } }
 */

import React from 'react';
import StatusBadge from './StatusBadge';

function TopBar({ title, serverStatus = {} }) {
  return (
    <div className="h-12 flex items-center justify-between px-6 border-b border-white/5 bg-black/20 flex-shrink-0">
      <span className="text-sm font-medium text-slate-300 tracking-wide">{title}</span>
      <div className="flex items-center gap-2">
        <StatusBadge label="Backend" status={serverStatus.backend ?? null} />
        <StatusBadge label="Ollama" status={serverStatus.ollama ?? null} />
        <StatusBadge label="ComfyUI" status={serverStatus.comfyui ?? null} />
      </div>
    </div>
  );
}

export default TopBar;
