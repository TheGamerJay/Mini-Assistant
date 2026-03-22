/**
 * AvatarMedia.js
 * Renders the correct element for any avatar data URL:
 *   data:video/* → <video autoPlay loop muted playsInline>
 *   everything else (image, GIF) → <img>
 *
 * Usage:
 *   <AvatarMedia src={avatar} className="w-full h-full object-cover" fallback={<Fallback />} />
 */

import React, { useState } from 'react';

export default function AvatarMedia({ src, className, fallback = null }) {
  const [videoError, setVideoError] = useState(false);

  if (!src || videoError) return fallback;

  if (src.startsWith('data:video/')) {
    return (
      <video
        src={src}
        autoPlay
        loop
        muted
        playsInline
        className={className}
        onError={() => setVideoError(true)}
      />
    );
  }

  return <img src={src} alt="Avatar" className={className} />;
}
