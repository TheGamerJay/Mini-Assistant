/**
 * AvatarMedia.js
 * Renders the correct element for any avatar data URL:
 *   data:video/* → <video> with forced-play via useEffect (autoPlay attr alone is unreliable)
 *   everything else (image, GIF) → <img>
 */

import React, { useState, useRef, useEffect } from 'react';

export default function AvatarMedia({ src, className, fallback = null }) {
  const [videoError, setVideoError] = useState(false);
  const [imgError, setImgError] = useState(false);
  const videoRef = useRef(null);

  // Reset error state when src changes
  useEffect(() => { setImgError(false); setVideoError(false); }, [src]);

  // Force-play the video — autoPlay attribute is blocked in some browsers
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = true;
    const tryPlay = () => v.play().catch(() => {});
    v.addEventListener('canplay', tryPlay);
    tryPlay();
    return () => v.removeEventListener('canplay', tryPlay);
  }, [src]);

  if (!src || videoError || imgError) return fallback;

  if (src.startsWith('data:video/')) {
    return (
      <video
        ref={videoRef}
        src={src}
        loop
        muted
        playsInline
        disablePictureInPicture
        disableRemotePlayback
        controlsList="nopictureinpicture nodownload noremoteplayback"
        className={className}
        onError={() => setVideoError(true)}
        onContextMenu={(e) => e.preventDefault()}
        style={{ pointerEvents: 'none' }}
      />
    );
  }

  return <img src={src} alt="Avatar" className={className} onError={() => setImgError(true)} />;
}
