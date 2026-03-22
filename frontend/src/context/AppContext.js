/**
 * context/AppContext.js
 * App-wide state management via React Context.
 * Provides chat history, project organisation, image gallery, settings, and server status.
 * Auth is now backed by MongoDB + JWT tokens via the backend API.
 */

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { api, getToken, setToken, clearToken } from '../api/client';
import { trackEvent } from '../utils/trackEvent';

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

/**
 * Decode JWT payload without verifying signature (client-side only, for reading claims).
 * Returns null on failure.
 */
function decodeJwtPayload(token) {
  try {
    const base64Url = token.split('.')[1];
    if (!base64Url) return null;
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
}

/**
 * Read the user id from the stored JWT token (used in useState initializers
 * before any async code can run).
 */
function getSessionId() {
  const token = getToken();
  if (!token) return null;
  const payload = decodeJwtPayload(token);
  if (!payload) return null;
  // Check expiry
  if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) return null;
  return payload.sub || null;
}

/** Scope a storage key to a user id so each account has its own data bucket. */
function uk(base, uid) {
  return uid ? `${base}_${uid}` : base;
}

/**
 * One-time migration: if the user-scoped key is empty but the old unscoped
 * key has data, copy it over and remove the old key.
 */
function migrateLS(base, uid, fallback) {
  if (!uid) return loadLS(base, fallback);
  const scopedKey = `${base}_${uid}`;
  const existing = localStorage.getItem(scopedKey);
  if (existing !== null) return JSON.parse(existing); // already migrated
  const old = localStorage.getItem(base);
  if (old !== null) {
    try {
      localStorage.setItem(scopedKey, old);
      localStorage.removeItem(base);
      return JSON.parse(old);
    } catch { /* quota */ }
  }
  return fallback;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------
const AppContext = createContext(null);

export function AppProvider({ children }) {
  // ---- Navigation ----
  const [page, _setPage] = useState(() => {
    const saved = localStorage.getItem('ma_active_page');
    const invalid = !saved || saved === 'settings' || saved === 'admin';
    return invalid ? 'chat' : saved;
  });
  const prevPageRef = useRef('chat');

  const setPage = useCallback((p) => {
    _setPage((prev) => {
      if ((prev !== 'settings' && prev !== 'admin') || p.startsWith('legal-')) prevPageRef.current = prev;
      try { if (p !== 'admin') localStorage.setItem('ma_active_page', p); } catch {}
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
  const [chats, setChats] = useState(() => migrateLS('ma_v2_chats', getSessionId(), []));
  const [activeChatId, setActiveChatId] = useState(() => {
    return localStorage.getItem('ma_active_chat_id') || null;
  });

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
  const [projects, setProjects] = useState(() => migrateLS('ma_v2_projects', getSessionId(), []));

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
  const [images, setImages] = useState(() => migrateLS('ma_v2_images', getSessionId(), []));

  const addImage = useCallback(async (thumbDataUrl, prompt, fullBase64) => {
    const id = crypto.randomUUID();
    // Store full base64 in module-level Map (not persisted)
    if (fullBase64) fullImageMap.set(id, fullBase64);
    const entry = { id, thumb: thumbDataUrl, prompt, createdAt: Date.now() };
    setImages((prev) => [entry, ...prev].slice(0, 50));
    return id;
  }, []);

  const getFullImage = useCallback((id) => fullImageMap.get(id) || null, []);

  // ---- Settings ----
  const defaultSettings = {
    showRouteInfo: true,
    dryRun: false,
    autoReview: true,
    quality: 'balanced',
  };
  const [settings, setSettings] = useState(() =>
    migrateLS('ma_v2_settings', getSessionId(), defaultSettings)
  );

  const updateSettings = useCallback((patch) => {
    setSettings((prev) => ({ ...prev, ...patch }));
  }, []);

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

  // ---- Auth ----
  // Initialise user from JWT token synchronously (no network call needed to render).
  const [user, _setUser] = useState(() => {
    const token = getToken();
    if (!token) return null;
    const payload = decodeJwtPayload(token);
    if (!payload) return null;
    if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) {
      clearToken();
      return null;
    }
    return { id: payload.sub, name: payload.name, email: payload.email, role: payload.role };
  });

  // ---- Credits ----
  const [credits, setCredits] = useState(null); // null = loading
  const [plan, setPlan]       = useState('free');
  const isSubscribed = plan !== 'free';
  const [purchaseModalOpen, setPurchaseModalOpen] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  // ---- Onboarding build prompt bridge ----
  // OnboardingModal sets this; AppBuilder reads + clears it to auto-fill + build
  const [pendingBuildPrompt, _setPendingBuildPrompt] = useState(null);
  const firePendingBuildPrompt = useCallback((text) => { _setPendingBuildPrompt(text); }, []);
  const clearPendingBuildPrompt = useCallback(() => { _setPendingBuildPrompt(null); }, []);

  // ---- Global upgrade modal ----
  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
  const [upgradeReason, setUpgradeReason]       = useState('generic');
  const openUpgradeModal = useCallback((reason = 'generic') => {
    setUpgradeReason(reason);
    setUpgradeModalOpen(true);
    trackEvent('upgrade_modal_opened', { trigger_type: reason });
    if (reason === 'credits') trackEvent('credits_exhausted', { trigger_type: reason });
  }, []);

  const refreshCredits = useCallback(() => {
    api.authCredits().then(({ credits: c, plan: p }) => {
      setCredits(c);
      setPlan(p);
    }).catch(() => {});
  }, []);

  // On mount: verify token with backend and refresh user object (including avatar).
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.authMe()
      .then((profile) => {
        _setUser((prev) => ({ ...prev, ...profile }));
        if (profile.credits !== undefined) setCredits(profile.credits);
        if (profile.plan !== undefined) setPlan(profile.plan);
        if (profile.avatar !== undefined) {
          _setAvatar(profile.avatar || null);
          // Cache avatar locally so it survives backend restarts
          const uid = profile.id || getSessionId();
          if (uid) {
            if (profile.avatar) {
              try { localStorage.setItem(`ma_avatar_${uid}`, profile.avatar); } catch {}
            } else {
              localStorage.removeItem(`ma_avatar_${uid}`);
            }
          }
        }
      })
      .catch((err) => {
        // Only log out on explicit 401 (invalid/expired token).
        // Server errors (503, 405, network) keep the cached user alive.
        if (err?.status === 401) {
          clearToken();
          _setUser(null);
        }
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Reload per-user data buckets when user logs in or out
  const _prevUidRef = useRef(user?.id || null);
  useEffect(() => {
    const uid = user?.id || null;
    if (uid === _prevUidRef.current) return; // same user, no reload needed
    _prevUidRef.current = uid;
    const def = { showRouteInfo: true, dryRun: false, autoReview: true, quality: 'balanced' };
    setChats(loadLS(uk('ma_v2_chats', uid), []));
    setProjects(loadLS(uk('ma_v2_projects', uid), []));
    setImages(loadLS(uk('ma_v2_images', uid), []));
    setSettings(loadLS(uk('ma_v2_settings', uid), def));
    setActiveChatId(null);
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // After login, load all user data from backend (backend is source of truth)
  const _backendLoadedRef = useRef(false);
  useEffect(() => {
    if (!user?.id) {
      _backendLoadedRef.current = false;
      return;
    }
    if (_backendLoadedRef.current) return;
    _backendLoadedRef.current = true;
    api.dbGetChats()
      .then((data) => { if (data?.chats?.length) setChats(data.chats); })
      .catch(() => {});
    api.dbGetProjects()
      .then((data) => { if (data?.projects?.length) setProjects(data.projects); })
      .catch(() => {});
    api.dbGetSettings()
      .then((data) => { if (data?.settings && Object.keys(data.settings).length) setSettings((prev) => ({ ...prev, ...data.settings })); })
      .catch(() => {});
    api.dbGetTemplates()
      .then((data) => { if (data?.templates?.length) setPromptTemplates(data.templates); })
      .catch(() => {});
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Persist per-user data to localStorage whenever it changes
  useEffect(() => { saveLS(uk('ma_v2_chats',    user?.id), chats);    }, [chats,    user?.id]);
  useEffect(() => { saveLS(uk('ma_v2_projects', user?.id), projects); }, [projects, user?.id]);
  useEffect(() => { saveLS(uk('ma_v2_images',   user?.id), images);   }, [images,   user?.id]);
  useEffect(() => { saveLS(uk('ma_v2_settings', user?.id), settings); }, [settings, user?.id]);

  // Persist active chat + page so refresh restores the same view
  useEffect(() => {
    try {
      if (activeChatId) localStorage.setItem('ma_active_chat_id', activeChatId);
      else localStorage.removeItem('ma_active_chat_id');
    } catch {}
  }, [activeChatId]);

  // On mount: validate restored activeChatId — clear it if the chat no longer exists
  useEffect(() => {
    if (activeChatId && chats.length > 0 && !chats.find(c => c.id === activeChatId)) {
      setActiveChatId(null);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Debounced sync of chats to backend
  const _chatSyncTimer = useRef(null);
  const _initialChatsRef = useRef(true);
  useEffect(() => {
    if (!user?.id) return;
    if (_initialChatsRef.current) { _initialChatsRef.current = false; return; }
    clearTimeout(_chatSyncTimer.current);
    _chatSyncTimer.current = setTimeout(() => {
      api.dbSaveChats(chats).catch(() => {});
    }, 3000);
    return () => clearTimeout(_chatSyncTimer.current);
  }, [chats, user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Debounced sync of projects to backend
  const _projectSyncTimer = useRef(null);
  const _initialProjectsRef = useRef(true);
  useEffect(() => {
    if (!user?.id) return;
    if (_initialProjectsRef.current) { _initialProjectsRef.current = false; return; }
    clearTimeout(_projectSyncTimer.current);
    _projectSyncTimer.current = setTimeout(() => {
      api.dbSaveProjects(projects).catch(() => {});
    }, 3000);
    return () => clearTimeout(_projectSyncTimer.current);
  }, [projects, user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Debounced sync of settings to backend
  const _settingsSyncTimer = useRef(null);
  const _initialSettingsRef = useRef(true);
  useEffect(() => {
    if (!user?.id) return;
    if (_initialSettingsRef.current) { _initialSettingsRef.current = false; return; }
    clearTimeout(_settingsSyncTimer.current);
    _settingsSyncTimer.current = setTimeout(() => {
      api.dbSaveSettings(settings).catch(() => {});
    }, 3000);
    return () => clearTimeout(_settingsSyncTimer.current);
  }, [settings, user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const _templatesSyncTimer = useRef(null);
  const _initialTemplatesRef = useRef(true);

  const logout = useCallback(() => {
    clearToken();
    _setUser(null);
    _setAvatar(null);
    _backendLoadedRef.current = false;
    _initialChatsRef.current = true;
    _initialProjectsRef.current = true;
    _initialSettingsRef.current = true;
    _initialTemplatesRef.current = true;
  }, []);

  const loginWithGoogle = useCallback(async (credential) => {
    const res = await api.authGoogle(credential);
    setToken(res.token);
    const session = { id: res.user.id, name: res.user.name, email: res.user.email, role: res.user.role };
    _setUser(session);
    if (res.user.avatar) _setAvatar(res.user.avatar);
    return session;
  }, []);

  const loginWithCredentials = useCallback(async (email, password) => {
    try {
      const res = await api.authLogin(email, password);
      setToken(res.token);
      const session = { id: res.user.id, name: res.user.name, email: res.user.email, role: res.user.role };
      _setUser(session);
      // Fetch avatar
      api.authMe().then((profile) => {
        if (profile.avatar !== undefined) _setAvatar(profile.avatar || null);
      }).catch(() => {});
      return session;
    } catch (err) {
      // Fallback: try legacy localStorage auth so existing accounts still work
      const users = JSON.parse(localStorage.getItem('ma_users') || '[]');
      const found = users.find(u => u.email.toLowerCase() === email.toLowerCase());
      if (!found) throw new Error(err.message || 'No account found with this email.');
      const encoder = new TextEncoder();
      const buf = await crypto.subtle.digest('SHA-256', encoder.encode(password + 'ma_salt_2025'));
      const hash = Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
      if (found.passwordHash !== hash) throw new Error('Incorrect password.');
      const session = { id: found.id, name: found.name, email: found.email, role: found.role || 'user' };
      _setUser(session);
      return session;
    }
  }, []);

  const register = useCallback(async (name, email, password, securityQuestion, securityAnswer, referralCode) => {
    try {
      const res = await api.authRegister(name, email, password, securityQuestion, securityAnswer, referralCode);
      setToken(res.token);
      const session = { id: res.user.id, name: res.user.name, email: res.user.email, role: res.user.role };
      _setUser(session);
      return session;
    } catch (err) {
      // Fallback: localStorage registration (used when backend is unavailable)
      const users = JSON.parse(localStorage.getItem('ma_users') || '[]');
      if (users.find(u => u.email.toLowerCase() === email.toLowerCase())) {
        throw new Error(err.message || 'An account with this email already exists.');
      }
      const encoder = new TextEncoder();
      const buf = await crypto.subtle.digest('SHA-256', encoder.encode(password + 'ma_salt_2025'));
      const passwordHash = Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
      let securityAnswerHash = null;
      if (securityQuestion && securityAnswer) {
        const aBuf = await crypto.subtle.digest('SHA-256', encoder.encode(securityAnswer.trim().toLowerCase() + 'ma_salt_2025'));
        securityAnswerHash = Array.from(new Uint8Array(aBuf)).map(b => b.toString(16).padStart(2, '0')).join('');
      }
      const isFirst = users.length === 0;
      const newUser = {
        id: crypto.randomUUID(), name, email, passwordHash,
        securityQuestion: securityQuestion || null,
        securityAnswerHash,
        role: isFirst ? 'admin' : 'user',
        createdAt: Date.now(),
      };
      users.push(newUser);
      localStorage.setItem('ma_users', JSON.stringify(users));
      const session = { id: newUser.id, name, email, role: newUser.role };
      _setUser(session);
      return session;
    }
  }, []);

  // getUserSecurityQuestion is now async (hits backend, falls back to localStorage)
  const getUserSecurityQuestion = useCallback(async (email) => {
    try {
      const res = await api.authSecurityQuestion(email);
      return res?.security_question || null;
    } catch {
      // Fallback: localStorage
      const users = JSON.parse(localStorage.getItem('ma_users') || '[]');
      const found = users.find(u => u.email.toLowerCase() === email.toLowerCase());
      return found?.securityQuestion || null;
    }
  }, []);

  const resetPasswordWithSecurityAnswer = useCallback(async (email, answer, newPassword) => {
    try {
      await api.authResetPassword(email, answer, newPassword);
    } catch (err) {
      // Fallback: localStorage
      const users = JSON.parse(localStorage.getItem('ma_users') || '[]');
      const found = users.find(u => u.email.toLowerCase() === email.toLowerCase());
      if (!found) throw new Error('No account found with this email.');
      if (!found.securityAnswerHash) throw new Error('No security question set for this account. Please contact support.');
      const encoder = new TextEncoder();
      const buf = await crypto.subtle.digest('SHA-256', encoder.encode(answer.trim().toLowerCase() + 'ma_salt_2025'));
      const hash = Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
      if (found.securityAnswerHash !== hash) throw new Error('Incorrect answer. Please try again.');
      const newBuf = await crypto.subtle.digest('SHA-256', encoder.encode(newPassword + 'ma_salt_2025'));
      found.passwordHash = Array.from(new Uint8Array(newBuf)).map(b => b.toString(16).padStart(2, '0')).join('');
      localStorage.setItem('ma_users', JSON.stringify(users));
    }
  }, []);

  // ---- Avatar ----
  const [avatar, _setAvatar] = useState(() => {
    const uid = getSessionId();
    return uid ? (localStorage.getItem(`ma_avatar_${uid}`) || null) : null;
  });

  const updateAvatar = useCallback(async (dataUrl) => {
    if (!user?.id) return;
    _setAvatar(dataUrl);
    // Always cache locally so avatar survives backend restarts
    try { localStorage.setItem(`ma_avatar_${user.id}`, dataUrl); } catch {}
    try { await api.authUpdateAvatar(dataUrl); } catch {}
  }, [user?.id]);

  const removeAvatar = useCallback(async () => {
    if (!user?.id) return;
    _setAvatar(null);
    localStorage.removeItem(`ma_avatar_${user.id}`);
    try { await api.authUpdateAvatar(null); } catch {}
  }, [user?.id]);

  // ---- Profile mutations ----
  const updateDisplayName = useCallback(async (name) => {
    if (!user?.id || !name.trim()) return;
    _setUser((prev) => prev ? { ...prev, name: name.trim() } : prev);
    try {
      await api.authUpdateProfile(name.trim());
    } catch {
      // Fallback: localStorage
      const users = JSON.parse(localStorage.getItem('ma_users') || '[]');
      const idx = users.findIndex(u => u.id === user.id);
      if (idx !== -1) {
        users[idx].name = name.trim();
        localStorage.setItem('ma_users', JSON.stringify(users));
      }
    }
  }, [user]);

  const changePassword = useCallback(async (currentPwd, newPwd) => {
    if (!user?.id) throw new Error('Not logged in.');
    try {
      await api.authChangePassword(currentPwd, newPwd);
    } catch (err) {
      // Fallback: localStorage
      const users = JSON.parse(localStorage.getItem('ma_users') || '[]');
      const found = users.find(u => u.id === user.id);
      if (!found) throw new Error('Account not found.');
      const encoder = new TextEncoder();
      const currentBuf = await crypto.subtle.digest('SHA-256', encoder.encode(currentPwd + 'ma_salt_2025'));
      const currentHash = Array.from(new Uint8Array(currentBuf)).map(b => b.toString(16).padStart(2, '0')).join('');
      if (found.passwordHash !== currentHash) throw new Error('Current password is incorrect.');
      const newBuf = await crypto.subtle.digest('SHA-256', encoder.encode(newPwd + 'ma_salt_2025'));
      found.passwordHash = Array.from(new Uint8Array(newBuf)).map(b => b.toString(16).padStart(2, '0')).join('');
      localStorage.setItem('ma_users', JSON.stringify(users));
    }
  }, [user]);

  const deleteAccount = useCallback(async () => {
    if (!user?.id) return;
    const uid = user.id;
    try {
      await api.authDeleteAccount();
    } catch {
      // Fallback: localStorage cleanup
      const users = JSON.parse(localStorage.getItem('ma_users') || '[]');
      localStorage.setItem('ma_users', JSON.stringify(users.filter(u => u.id !== uid)));
    }
    // Remove all user-scoped local data regardless
    ['ma_v2_chats', 'ma_v2_projects', 'ma_v2_images', 'ma_v2_settings'].forEach(k => {
      localStorage.removeItem(`${k}_${uid}`);
    });
    localStorage.removeItem(`ma_avatar_${uid}`);
    clearToken();
    _setUser(null);
    _setAvatar(null);
    _backendLoadedRef.current = false;
    _initialChatsRef.current = true;
    _initialProjectsRef.current = true;
    _initialSettingsRef.current = true;
    _initialTemplatesRef.current = true;
  }, [user]);

  // ---- Server Status ----
  const [serverStatus, _setServerStatus] = useState({
    backend: null,
    ollama: null,
    comfyui: null,
  });

  const setServerStatus = useCallback((patch) => {
    _setServerStatus((prev) => ({ ...prev, ...patch }));
  }, []);

  // ---- Pinned chats ----
  const togglePinChat = useCallback((id) => {
    setChats((prev) => prev.map((c) => c.id === id ? { ...c, pinned: !c.pinned } : c));
  }, []);

  // ---- Message ratings ----
  const rateMessage = useCallback((chatId, msgIdx, rating) => {
    setChats((prev) => prev.map((c) => {
      if (c.id !== chatId) return c;
      const msgs = [...c.messages];
      msgs[msgIdx] = { ...msgs[msgIdx], rating };
      return { ...c, messages: msgs };
    }));
  }, []);

  // ---- Message pinning ----
  const pinMessage = useCallback((chatId, msgIdx) => {
    setChats((prev) => prev.map((c) => {
      if (c.id !== chatId) return c;
      const msgs = [...c.messages];
      msgs[msgIdx] = { ...msgs[msgIdx], pinned: !msgs[msgIdx].pinned };
      return { ...c, messages: msgs };
    }));
  }, []);

  // ---- Prompt templates ----
  const [promptTemplates, setPromptTemplates] = useState(() =>
    migrateLS('ma_v2_templates', getSessionId(), [])
  );
  useEffect(() => { saveLS(uk('ma_v2_templates', user?.id), promptTemplates); }, [promptTemplates, user?.id]); // eslint-disable-line

  // Debounced sync of prompt templates to backend
  useEffect(() => {
    if (!user?.id) return;
    if (_initialTemplatesRef.current) { _initialTemplatesRef.current = false; return; }
    clearTimeout(_templatesSyncTimer.current);
    _templatesSyncTimer.current = setTimeout(() => {
      api.dbSaveTemplates(promptTemplates).catch(() => {});
    }, 3000);
    return () => clearTimeout(_templatesSyncTimer.current);
  }, [promptTemplates, user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const addPromptTemplate = useCallback((title, text) => {
    const t = { id: crypto.randomUUID(), title: title.trim(), text: text.trim(), createdAt: Date.now() };
    setPromptTemplates((prev) => [t, ...prev]);
  }, []);

  const deletePromptTemplate = useCallback((id) => {
    setPromptTemplates((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // ---- Conversation forking ----
  const forkChat = useCallback((chatId, upToMsgIdx) => {
    const source = chats.find(c => c.id === chatId);
    if (!source) return;
    const id = crypto.randomUUID();
    const forkedMessages = source.messages.slice(0, upToMsgIdx + 1);
    const chat = {
      id,
      title: `Fork: ${source.title.slice(0, 45)}`,
      messages: forkedMessages,
      projectId: source.projectId || null,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    setChats((prev) => [chat, ...prev]);
    setActiveChatId(id);
    setPage('chat');
    return id;
  }, [chats, setPage]);

  // ---- Tasks ----
  const [tasks, setTasks] = useState([]);

  useEffect(() => {
    if (!user?.id) return;
    api.getTasks().then(data => { if (data?.tasks) setTasks(data.tasks); }).catch(() => {});
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const addTask = useCallback(async (text) => {
    try {
      const data = await api.addTask(text);
      if (data?.task) setTasks(prev => [...prev, data.task]);
    } catch { /* non-fatal */ }
  }, []);

  const toggleTask = useCallback(async (id) => {
    setTasks(prev => prev.map(t => t.id === id ? { ...t, done: !t.done } : t));
    const task = tasks.find(t => t.id === id);
    if (task) api.updateTask(id, { done: !task.done }).catch(() => {});
  }, [tasks]);

  const deleteTask = useCallback(async (id) => {
    setTasks(prev => prev.filter(t => t.id !== id));
    api.deleteTask(id).catch(() => {});
  }, []);

  // Pending template — Sidebar fires it, ChatInput consumes it
  // autoSubmit=true → ChatInput fires onSubmit immediately (used by onboarding)
  const [pendingTemplate,    _setPendingTemplate]    = useState(null);
  const [pendingAutoSubmit,  _setPendingAutoSubmit]  = useState(false);
  const firePendingTemplate  = useCallback((text, autoSubmit = false) => {
    _setPendingAutoSubmit(autoSubmit);
    _setPendingTemplate(text);
  }, []);
  const clearPendingTemplate    = useCallback(() => _setPendingTemplate(null), []);
  const clearPendingAutoSubmit  = useCallback(() => _setPendingAutoSubmit(false), []);

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
    // auth
    user,
    logout,
    loginWithGoogle,
    loginWithCredentials,
    register,
    credits,
    plan,
    isSubscribed,
    refreshCredits,
    purchaseModalOpen,
    setPurchaseModalOpen,
    mobileSidebarOpen,
    setMobileSidebarOpen,
    upgradeModalOpen,
    setUpgradeModalOpen,
    upgradeReason,
    openUpgradeModal,
    getUserSecurityQuestion,
    resetPasswordWithSecurityAnswer,
    // profile
    avatar,
    updateAvatar,
    removeAvatar,
    updateDisplayName,
    changePassword,
    deleteAccount,
    // pinned chats
    togglePinChat,
    // message ratings
    rateMessage,
    pinMessage,
    // prompt templates
    promptTemplates,
    addPromptTemplate,
    deletePromptTemplate,
    // conversation forking
    forkChat,
    // tasks
    tasks,
    addTask,
    toggleTask,
    deleteTask,
    // pending template bridge
    pendingTemplate,
    pendingAutoSubmit,
    firePendingTemplate,
    clearPendingTemplate,
    clearPendingAutoSubmit,
    // onboarding build prompt bridge
    pendingBuildPrompt,
    firePendingBuildPrompt,
    clearPendingBuildPrompt,
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
