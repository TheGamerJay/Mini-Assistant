/**
 * components/HomeHero.js
 * Centered homepage shown when there is no active chat.
 * First visit: 3-mode onboarding cards (Chat / Build / Image) with templates.
 * Return visits: standard hero with context-aware suggestions.
 */

import React, { useState, useEffect } from 'react';
import ChatInput from './ChatInput';
import MiniOrb from './MiniOrb';
import { useApp } from '../context/AppContext';

// ---------------------------------------------------------------------------
// Mode definitions — each has color, icon, description, and template prompts
// ---------------------------------------------------------------------------
const MODES = [
  {
    id: 'chat',
    label: 'Think',
    icon: '💬',
    tagline: 'Ask anything. Learn anything.',
    description: 'Research, explain, plan, brainstorm — your AI thinking partner.',
    color: '#818cf8',          // indigo
    border: 'rgba(129,140,248,0.25)',
    glow: 'rgba(129,140,248,0.12)',
    glowHover: 'rgba(129,140,248,0.2)',
    templates: [
      'Explain machine learning in simple terms',
      'Give me 5 productivity tips for developers',
      "What's the difference between AI and ML?",
    ],
  },
  {
    id: 'build',
    label: 'Build',
    icon: '⚡',
    tagline: 'Describe it. See it built.',
    description: 'Turn any idea into a fully working interactive app — no code needed.',
    color: '#22d3ee',          // cyan
    border: 'rgba(34,211,238,0.25)',
    glow: 'rgba(34,211,238,0.10)',
    glowHover: 'rgba(34,211,238,0.18)',
    templates: [
      'Build me a snake game with score tracking',
      'Make a tip calculator with dark mode',
      'Create a quiz app with 5 random questions',
    ],
  },
  {
    id: 'image',
    label: 'Create Image',
    icon: '🎨',
    tagline: 'Imagine it. See it rendered.',
    description: 'Generate stunning visuals from any description in seconds.',
    color: '#f472b6',          // pink
    border: 'rgba(244,114,182,0.25)',
    glow: 'rgba(244,114,182,0.10)',
    glowHover: 'rgba(244,114,182,0.18)',
    templates: [
      'Futuristic city skyline at night with neon lights',
      'Anime warrior with glowing power aura',
      'Realistic fantasy dragon soaring at dusk',
    ],
  },
];

// ---------------------------------------------------------------------------
// Return-visit suggestion chips
// ---------------------------------------------------------------------------
const getSuggestions = (lastTopic) => {
  if (!lastTopic) return [
    'Build a calculator app with UI and logic',
    'Scrape a website with Python',
    'Generate a cinematic fantasy image',
    'Edit this image and remove the background',
    'Explain this code step by step',
  ];
  const t = lastTopic.toLowerCase();
  if (/code|python|function|debug|script|javascript|typescript|api/.test(t)) return [
    'Explain this code step by step',
    'Optimize this function for performance',
    'Write unit tests for this',
    'Find potential bugs',
    'Add error handling',
  ];
  if (/anime|draw|generate|image|art|fantasy|realistic|portrait|paint/.test(t)) return [
    'Draw an anime warrior with power aura',
    'Generate a fantasy dragon at dusk',
    'Create a cinematic landscape',
    'Paint a romantic anime couple',
    'Make a realistic studio portrait',
  ];
  if (/chat|hello|hi|help|what|who|explain|tell/.test(t)) return [
    'What can you help me with?',
    'Explain machine learning in simple terms',
    "What's the difference between AI and ML?",
    'Give me 5 productivity tips',
    'Summarize what we just discussed',
  ];
  return [
    'Ask a follow-up question',
    'Try a related image prompt',
    'Write code for this idea',
    'Explain it differently',
    'Go deeper on this topic',
  ];
};

// ---------------------------------------------------------------------------
// ModeCard
// ---------------------------------------------------------------------------
function ModeCard({ mode, selected, onSelect, onTemplate, loading }) {
  const isSelected = selected === mode.id;
  return (
    <div
      onClick={() => onSelect(mode.id)}
      className="relative flex flex-col gap-3 rounded-2xl p-5 cursor-pointer transition-all duration-200 select-none"
      style={{
        background: isSelected ? mode.glow : 'rgba(255,255,255,0.03)',
        border: `1px solid ${isSelected ? mode.border : 'rgba(255,255,255,0.07)'}`,
        boxShadow: isSelected ? `0 0 24px ${mode.glow}` : 'none',
        transform: isSelected ? 'translateY(-2px)' : 'none',
      }}
      onMouseEnter={e => {
        if (!isSelected) {
          e.currentTarget.style.background = mode.glow;
          e.currentTarget.style.borderColor = mode.border;
        }
      }}
      onMouseLeave={e => {
        if (!isSelected) {
          e.currentTarget.style.background = 'rgba(255,255,255,0.03)';
          e.currentTarget.style.borderColor = 'rgba(255,255,255,0.07)';
        }
      }}
    >
      {/* Selected indicator */}
      {isSelected && (
        <div className="absolute top-3 right-3 w-2 h-2 rounded-full" style={{ background: mode.color, boxShadow: `0 0 6px ${mode.color}` }} />
      )}

      {/* Header */}
      <div className="flex items-center gap-2.5">
        <span className="text-2xl leading-none">{mode.icon}</span>
        <div>
          <div className="text-[13px] font-bold text-white">{mode.label}</div>
          <div className="text-[11px] font-medium" style={{ color: mode.color }}>{mode.tagline}</div>
        </div>
      </div>

      {/* Description */}
      <p className="text-[11px] text-slate-500 leading-relaxed">{mode.description}</p>

      {/* Template chips */}
      <div className="flex flex-col gap-1.5 mt-1">
        {mode.templates.map((t) => (
          <button
            key={t}
            disabled={loading}
            onClick={e => { e.stopPropagation(); onTemplate(mode.id, t); }}
            className="text-left text-[11px] px-3 py-2 rounded-xl transition-all duration-150 disabled:opacity-40"
            style={{
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.07)',
              color: '#94a3b8',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = mode.glow;
              e.currentTarget.style.borderColor = mode.border;
              e.currentTarget.style.color = '#e2e8f0';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
              e.currentTarget.style.borderColor = 'rgba(255,255,255,0.07)';
              e.currentTarget.style.color = '#94a3b8';
            }}
          >
            {t}
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
function HomeHero({ onSubmit, loading, lastTopic, chatMode = null, onChatModeChange }) {
  const { user } = useApp();
  const suggestions = getSuggestions(lastTopic);

  // First-visit detection
  const [isFirstVisit, setIsFirstVisit] = useState(false);
  const [selectedMode, setSelectedMode] = useState(null);

  useEffect(() => {
    if (!user?.id) return;
    const key = `ma_onboarding_done_${user.id}`;
    if (!localStorage.getItem(key)) setIsFirstVisit(true);
  }, [user?.id]);

  const handleSubmit = (text) => {
    if (isFirstVisit && user?.id) {
      localStorage.setItem(`ma_onboarding_done_${user.id}`, '1');
      setIsFirstVisit(false);
    }
    onSubmit(text);
  };

  const handleSelectMode = (modeId) => {
    setSelectedMode(modeId);
    if (onChatModeChange) onChatModeChange(modeId);
  };

  const handleTemplate = (modeId, prompt) => {
    // Set the mode then immediately submit the template
    if (onChatModeChange) onChatModeChange(modeId);
    if (isFirstVisit && user?.id) {
      localStorage.setItem(`ma_onboarding_done_${user.id}`, '1');
      setIsFirstVisit(false);
    }
    onSubmit(prompt);
  };

  // ---------------------------------------------------------------------------
  // First-visit view — 3-mode onboarding
  // ---------------------------------------------------------------------------
  if (isFirstVisit) {
    return (
      <div className="relative overflow-hidden h-full flex flex-col items-center justify-center gap-6 px-4 py-8">
        {/* Background glow */}
        <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[500px] rounded-full"
            style={{ background: 'radial-gradient(ellipse, rgba(129,140,248,0.08) 0%, rgba(34,211,238,0.05) 40%, transparent 70%)', filter: 'blur(40px)' }} />
        </div>

        {/* Logo + greeting */}
        <div className="flex flex-col items-center gap-3 text-center">
          <img src="/Logo.png" alt="Mini Assistant"
            className="w-16 h-16 object-contain drop-shadow-[0_0_20px_rgba(139,92,246,0.5)]" />
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
              Welcome{user?.name ? `, ${user.name.split(' ')[0]}` : ''}!
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Pick a mode to get started — or type anything below.
            </p>
          </div>
        </div>

        {/* Mode cards */}
        <div className="w-full max-w-4xl grid grid-cols-1 sm:grid-cols-3 gap-3">
          {MODES.map(mode => (
            <ModeCard
              key={mode.id}
              mode={mode}
              selected={selectedMode}
              onSelect={handleSelectMode}
              onTemplate={handleTemplate}
              loading={loading}
            />
          ))}
        </div>

        {/* Input */}
        <div className="w-full max-w-2xl">
          <ChatInput
            variant="home"
            onSubmit={handleSubmit}
            loading={loading}
            chatMode={selectedMode || chatMode}
            onChatModeChange={handleSelectMode}
          />
          <p className="text-center mt-3 text-[11px] font-mono text-slate-700">
            Mini Assistant AI · Built to think. Designed to execute.
          </p>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Return-visit view — standard hero
  // ---------------------------------------------------------------------------
  return (
    <div className="relative overflow-hidden h-full flex flex-col items-center justify-center gap-8 px-4">
      {/* Radial background glow */}
      <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] rounded-full bg-gradient-radial from-cyan-500/8 via-violet-600/5 to-transparent blur-3xl" />
      </div>

      {/* Mini Orb */}
      <MiniOrb state={loading ? 'thinking' : 'idle'} size="lg" />

      {/* Heading */}
      <div className="text-center space-y-2">
        <h1 className="text-4xl md:text-5xl font-semibold text-slate-100 tracking-tight">
          Give it a task. It executes.
        </h1>
        <p className="text-sm text-slate-500">
          AI that thinks, builds, and creates images
        </p>
      </div>

      {/* Input */}
      <div className="w-full max-w-2xl">
        <ChatInput variant="home" onSubmit={onSubmit} loading={loading} chatMode={chatMode} onChatModeChange={onChatModeChange} />
        <p className="text-center mt-3 text-xs font-mono text-slate-700">
          Mini Assistant AI · Built to think. Designed to execute.
        </p>
      </div>

      {/* Suggested prompts */}
      <div key={lastTopic || 'default'} className="flex flex-wrap justify-center gap-2 max-w-2xl msg-enter">
        {suggestions.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onSubmit(prompt)}
            disabled={loading}
            className="rounded-full border border-white/10 text-slate-400 hover:border-cyan-500/40 hover:text-cyan-300 hover:shadow-[0_0_12px_rgba(0,229,255,0.15)] text-xs px-3 py-1.5 cursor-pointer transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

export default HomeHero;
