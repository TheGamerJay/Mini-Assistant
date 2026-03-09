/**
 * layout/MainPanel.js
 * Flex wrapper for the main content area.
 */

import React from 'react';

function MainPanel({ children }) {
  return (
    <div className="flex-1 flex flex-col min-w-0 bg-[#0d0d12] overflow-hidden">
      {children}
    </div>
  );
}

export default MainPanel;
