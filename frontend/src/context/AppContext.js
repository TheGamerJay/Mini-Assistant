/**
 * context/AppContext.js
 * App-wide state management via React Context.
 * Provides chat history, project organisation, image gallery, settings, and server status.
 */

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';

// ---------------------------------------------------------------------------
// Module-level Map: stores full base64 images keyed by image id
// (not persisted to localStorage to avoid quota issues)
// ---------------------------------------------------------------------------
const fullImageMap = new Map();

/** Exported so ChatPage / ImagePage can read the full base64 without context overhead */
export { fullImageMap as imageFullMap };

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

/** Resize a base64 PNG/JPEG to a 120×120 JPEG thumbnail at 0.45 quality. */
export function makeThumbnail(base64) {
  return new Promise((resolve) => {
    try {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = 120;
        canvas.height = 120;
        const ctx = canvas.getContext('2d');
        // Cover-crop: maintain aspect ratio, fill square
        const scale = Math.max(120 / img.width, 120 / img.height);
        const w = img.width * scale;
        const h = img.height * scale;
        const ox = (120 - w) / 2;
        const oy = (120 - h) / 2;
        ctx.drawImage(img, ox, oy, w, h);
        resolve(canvas.toDataURL('image/jpeg', 0.45));
      };
      img.onerror = () => resolve(null);
      img.src = base64.startsWith('data:') ? base64 : `data:image/png;base64,${base64}`;
    } catch {
      resolve(null);
    }
  });
}

function loadLS(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return fallback;
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function saveLS(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // quota exceeded or private browsing
  }
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------
const AppContext = createContext(null);

export function AppProvider({ children }) {
  // ---- Navigation ----
  const [page, _setPage] = useState('chat');
  const prevPageRef = useRef('chat');

  const setPage = useCallback((p) => {
    _setPage((prev) => {
      if (prev !== 'settings') prevPageRef.current = prev;
      return p;
    });
  }, []);

  const getPrevPage = useCallback(() => prevPageRef.current, []);

  // ---- prevPage state (alias for SettingsModal back-navigation) ----
  const [prevPage, _setPrevPage] = useState('chat');
  const setPrevPage = useCallback((p) => _setPrevPage(p), []);

  // ---- Sidebar ----
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem('ma_sidebar_collapsed') === 'true'
  );
  const toggleSidebar = useCallback(() => setSidebarCollapsed((v) => {
    const next = !v;
    try { localStorage.setItem('ma_sidebar_collapsed', String(next)); } catch {}
    return next;
  }), []);

  // ---- Chats ----
  const [chats, setChats] = useState(() => loadLS('ma_v2_chats', []));
  const [activeChatId, setActiveChatId] = useState(null);

  useEffect(() => { saveLS('ma_v2_chats', chats); }, [chats]);

  const newChat = useCallback(() => {
    const id = crypto.randomUUID();
    const chat = {
      id,
      title: 'New Chat',
      messages: [],
      projectId: null,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    setChats((prev) => [chat, ...prev]);
    setActiveChatId(id);
    return id;
  }, []);

  const selectChat = useCallback((id) => {
    setActiveChatId(id);
    setPage('chat');
  }, [setPage]);

  const deleteChat = useCallback((id) => {
    setChats((prev) => prev.filter((c) => c.id !== id));
    setActiveChatId((prev) => (prev === id ? null : prev));
  }, []);

  const renameChat = useCallback((id, title) => {
    setChats((prev) =>
      prev.map((c) => (c.id === id ? { ...c, title, updatedAt: Date.now() } : c))
    );
  }, []);

  const updateChatMessages = useCallback((id, messages) => {
    setChats((prev) =>
      prev.map((c) => {
        if (c.id !== id) return c;
        // Auto-set title from first user message if still default
        let title = c.title;
        if (title === 'New Chat') {
          const firstUser = messages.find((m) => m.role === 'user');
          if (firstUser) {
            const text = typeof firstUser.content === 'string' ? firstUser.content : '';
            title = text.slice(0, 60) || 'Chat';
          }
        }
        return { ...c, title, messages, updatedAt: Date.now() };
      })
    );
  }, []);

  // ---- Projects ----
  const [projects, setProjects] = useState(() => loadLS('ma_v2_projects', []));

  useEffect(() => { saveLS('ma_v2_projects', projects); }, [projects]);

  const newProject = useCallback((name) => {
    const id = crypto.randomUUID();
    setProjects((prev) => [...prev, { id, name, createdAt: Date.now() }]);
    return id;
  }, []);

  const deleteProject = useCallback((id) => {
    setProjects((prev) => prev.filter((p) => p.id !== id));
    // unassign chats belonging to this project
    setChats((prev) =>
      prev.map((c) => (c.projectId === id ? { ...c, projectId: null } : c))
    );
  }, []);

  const renameProject = useCallback((id, name) => {
    setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, name } : p)));
  }, []);

  const assignChatToProject = useCallback((chatId, projectId) => {
    setChats((prev) =>
      prev.map((c) => (c.id === chatId ? { ...c, projectId, updatedAt: Date.now() } : c))
    );
  }, []);

  // ---- Images ----
  const [images, setImages] = useState(() => loadLS('ma_v2_images', []));

  useEffect(() => { saveLS('ma_v2_images', images); }, [images]);

  const addImage = useCallback(async (thumbDataUrl, prompt, fullBase64) => {
    const id = crypto.randomUUID();
    // Store full base64 in module-level Map (not persisted)
    if (fullBase64) fullImageMap.set(id, fullBase64);
    const entry = { id, thumb: thumbDataUrl, prompt, createdAt: Date.now() };
    setImages((prev) => [entry, ...prev].slice(0, 50));
    return id;
  }, []);

  const getFullImage = useCallback((id) => fullImageMap.get(id) || null, []);

  // ---- Theme ----
  const [theme, _setTheme] = useState(
    () => localStorage.getItem('ma_theme') || 'dark'
  );

  const toggleTheme = useCallback(() => {
    _setTheme((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark';
      localStorage.setItem('ma_theme', next);
      // Apply immediately to the document root
      document.documentElement.setAttribute('data-theme', next);
      return next;
    });
  }, []);

  // Sync on first mount
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- Settings ----
  const defaultSettings = {
    showRouteInfo: true,
    dryRun: false,
    autoReview: true,
    quality: 'balanced',
  };
  const [settings, setSettings] = useState(() =>
    loadLS('ma_v2_settings', defaultSettings)
  );

  useEffect(() => { saveLS('ma_v2_settings', settings); }, [settings]);

  const updateSettings = useCallback((patch) => {
    setSettings((prev) => ({ ...prev, ...patch }));
  }, []);

  // ---- Server Status ----
  const [serverStatus, _setServerStatus] = useState({
    backend: null,
    ollama: null,
    comfyui: null,
  });

  const setServerStatus = useCallback((patch) => {
    _setServerStatus((prev) => ({ ...prev, ...patch }));
  }, []);

  // ---------------------------------------------------------------------------
  const value = {
    // navigation
    page,
    setPage,
    getPrevPage,
    prevPage,
    setPrevPage,
    // sidebar
    sidebarCollapsed,
    setSidebarCollapsed,
    toggleSidebar,
    // chats
    chats,
    activeChatId,
    newChat,
    selectChat,
    deleteChat,
    renameChat,
    updateChatMessages,
    // projects
    projects,
    newProject,
    deleteProject,
    renameProject,
    assignChatToProject,
    // images
    images,
    addImage,
    getFullImage,
    // settings
    settings,
    updateSettings,
    // theme
    theme,
    toggleTheme,
    // server status
    serverStatus,
    setServerStatus,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return ctx;
}

export default AppContext;
