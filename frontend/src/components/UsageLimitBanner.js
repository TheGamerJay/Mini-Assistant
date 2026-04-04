/**
 * UsageLimitBanner.js
 * Shows a one-time toast when subscription or API key is missing.
 * Replaces the old credit-balance warning banner.
 */

import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { useApp } from '../context/AppContext';

export default function UsageLimitBanner() {
  const { isSubscribed, apiKeyVerified, page, openUpgradeModal } = useApp();
  const shownRef = useRef({ noSub: false, noKey: false });

  useEffect(() => {
    // Skip on billing/settings pages — user is already aware
    if (page === 'pricing' || page === 'dashboard' || page === 'settings') return;

    if (!isSubscribed && !shownRef.current.noSub) {
      shownRef.current.noSub = true;
      toast('Subscribe to unlock AI execution.', {
        id:       'no-sub',
        duration: 8000,
        action: {
          label:   'Subscribe',
          onClick: () => openUpgradeModal('no_subscription'),
        },
      });
    } else if (isSubscribed && !apiKeyVerified && !shownRef.current.noKey) {
      shownRef.current.noKey = true;
      toast('Add your API key to start using the AI.', {
        id:       'no-api-key',
        duration: 8000,
        action: {
          label:   'Add Key',
          onClick: () => openUpgradeModal('no_api_key'),
        },
      });
    }
  }, [isSubscribed, apiKeyVerified, page, openUpgradeModal]);

  return null;
}
