/**
 * components/HomeHero.js
 * Centered homepage shown when there is no active chat.
 * Props: { onSubmit(text), loading, lastTopic }
 */

import React from 'react';
import ChatInput from './ChatInput';
import MiniOrb from './MiniOrb';

const getSuggestions = (lastTopic) => {
  if (!lastTopic) return [
    'Draw a shonen anime warrior with power aura',
    'Generate a realistic portrait photo',
    'Paint a fantasy dragon at dusk',
    'Explain async/await with examples',
    'Write a Python web scraper',
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
    'What is the difference between AI and ML?',
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

function HomeHero({ onSubmit, loading, lastTopic }) {
  const suggestions = getSuggestions(lastTopic);

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
          What's on your mind today?
        </h1>
        <p className="text-sm text-slate-500">
          Chat With Your Mini Assistant
        </p>
      </div>

      {/* Input */}
      <div className="w-full max-w-2xl">
        <ChatInput variant="home" onSubmit={onSubmit} loading={loading} />
        <p className="text-center mt-3 text-xs font-mono text-slate-700">
          Powered by Mini Assistant
        </p>
      </div>

      {/* Suggested prompts — re-mounts on lastTopic change for fade animation */}
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
