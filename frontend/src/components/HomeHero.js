/**
 * components/HomeHero.js
 * Centered homepage shown when there is no active chat.
 * Props: { onSubmit(text), loading }
 */

import React from 'react';
import ChatInput from './ChatInput';

const SUGGESTED_PROMPTS = [
  'Draw a shonen anime warrior with power aura',
  'Generate a realistic portrait photo',
  'Paint a fantasy dragon at dusk',
  'Explain async/await with examples',
  'Write a Python web scraper',
];

function HomeHero({ onSubmit, loading }) {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-8 px-4">
      {/* Heading */}
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-semibold text-slate-100 tracking-tight">
          What's on your mind today?
        </h1>
        <p className="text-sm text-slate-500">
          Chat with your local AI, generate images, or write code.
        </p>
      </div>

      {/* Input */}
      <div className="w-full max-w-2xl">
        <ChatInput variant="home" onSubmit={onSubmit} loading={loading} />
      </div>

      {/* Suggested prompts */}
      <div className="flex flex-wrap justify-center gap-2 max-w-2xl">
        {SUGGESTED_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onSubmit(prompt)}
            disabled={loading}
            className="rounded-full border border-white/10 text-slate-400 hover:text-white hover:border-white/30 text-xs px-3 py-1.5 cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

export default HomeHero;
