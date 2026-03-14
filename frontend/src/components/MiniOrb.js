import React from 'react';

/**
 * MiniOrb — glowing AI identity element.
 * Props:
 *   state: 'idle' | 'thinking' | 'responding'
 *   size: 'sm' | 'md' | 'lg' (default: 'md')
 */
const MiniOrb = ({ state = 'idle', size = 'md' }) => {
  const sizes = { sm: 'w-8 h-8', md: 'w-14 h-14', lg: 'w-20 h-20' };
  const blurSizes = { sm: 'w-12 h-12', md: 'w-20 h-20', lg: 'w-28 h-28' };

  return (
    <div className={`relative flex items-center justify-center ${sizes[size]}`}>
      {/* Outer glow */}
      <div className={`absolute ${blurSizes[size]} rounded-full bg-gradient-to-br from-cyan-500/30 to-violet-600/30 blur-xl ${
        state === 'thinking' ? 'orb-pulse' : state === 'responding' ? 'orb-ripple' : 'orb-idle'
      }`} />
      {/* Core orb */}
      <div className={`relative ${sizes[size]} rounded-full bg-gradient-to-br from-cyan-400 via-cyan-500 to-violet-600 shadow-[0_0_20px_rgba(0,229,255,0.4),0_0_40px_rgba(124,58,237,0.3)] overflow-hidden ${
        state === 'thinking' ? 'orb-pulse' : state === 'responding' ? 'orb-ripple' : 'orb-idle'
      }`}>
        <img
          src="/Logo.png"
          alt="Mini Assistant"
          className="w-full h-full object-contain"
          onError={e => { e.target.style.display = 'none'; }}
        />
      </div>
    </div>
  );
};

export default MiniOrb;
