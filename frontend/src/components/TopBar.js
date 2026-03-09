/**
 * components/TopBar.js
 * Slim top bar showing page title and server status badges.
 * Props: { title: string, serverStatus: { backend, ollama, comfyui } }
 */

import React from 'react';
import { AlertTriangle } from 'lucide-react';
import StatusBadge from './StatusBadge';

function TopBar({ title, serverStatus = {} }) {
  const anyOffline =
    serverStatus.backend === false ||
    serverStatus.ollama === false ||
    serverStatus.comfyui === false;

  return (
    <div className="flex-shrink-0">
      <div className="h-12 flex items-center justify-between px-6 border-b border-white/5 bg-black/20">
        <span className="text-sm font-medium text-slate-300 tracking-wide">{title}</span>
        <div className="flex items-center gap-2">
          <StatusBadge label="Backend" status={serverStatus.backend ?? null} />
          <StatusBadge label="Ollama" status={serverStatus.ollama ?? null} />
          <StatusBadge label="ComfyUI" status={serverStatus.comfyui ?? null} />
        </div>
      </div>
      {anyOffline && (
        <div className="px-6 py-1.5 bg-red-950/40 border-b border-red-500/20 text-xs font-mono text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-3 h-3 flex-shrink-0" />
          Backend or AI service offline — some features may not work
        </div>
      )}
    </div>
  );
}

export default TopBar;
