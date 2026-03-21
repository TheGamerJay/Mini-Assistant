/**
 * App.js — Mini Assistant
 * Root component. Wraps everything in AppProvider, renders the shell layout.
 *
 * IMPORTANT: axiosInstance is exported at the top for backward-compatibility
 * with existing tool components that import it directly from this file.
 */

import React, { useEffect, useCallback } from 'react';
import { handleCheckoutReturn } from './api/checkout';
import axios from 'axios';
import { Toaster } from 'sonner';
import { GoogleOAuthProvider } from '@react-oauth/google';

// Context
import { AppProvider, useApp } from './context/AppContext';

// Layout
import Sidebar from './layout/Sidebar';
import MainPanel from './layout/MainPanel';

// Shared components
import TopBar from './components/TopBar';
import UsageLimitBanner from './components/UsageLimitBanner';

// Pages
import ChatPage from './pages/ChatPage';
import ImagePage from './pages/ImagePage';
import SettingsModal from './pages/SettingsModal';
import AuthPage from './pages/AuthPage';
import ProfilePage from './pages/ProfilePage';
import AdminPage from './pages/AdminPage';
import UserDashboard from './pages/UserDashboard';
import PurchaseCreditsModal from './components/PurchaseCreditsModal';
import UpgradeModal from './components/UpgradeModal';
import PricingPage from './pages/PricingPage';

// Legal pages
import TermsPage from './pages/legal/TermsPage';
import PrivacyPage from './pages/legal/PrivacyPage';
import RefundPage from './pages/legal/RefundPage';
import ProhibitedPage from './pages/legal/ProhibitedPage';
import DmcaPage from './pages/legal/DmcaPage';
import ContactPage from './pages/legal/ContactPage';

// Existing tool components (kept for backward compat via 'tool-X' pages)
import Dashboard from './pages/Dashboard';
import ChatInterface from './components/Chat/ChatInterface';
import VoiceControl from './components/Voice/VoiceControl';
import FileExplorer from './components/Files/FileExplorer';
import CommandTerminal from './components/Terminal/CommandTerminal';
import WebSearch from './components/Search/WebSearch';
import CodebaseSearch from './components/Search/CodebaseSearch';
import ProjectProfiles from './components/Profiles/ProjectProfiles';
import CodeReview from './components/CodeReview/CodeReview';
import GitIntegration from './components/Git/GitIntegration';
import CodeRunner from './components/CodeRunner/CodeRunner';
import APITester from './components/APITester/APITester';
import DatabaseDesigner from './components/DatabaseDesigner/DatabaseDesigner';
import PackageManager from './components/PackageManager/PackageManager';
import EnvManager from './components/EnvManager/EnvManager';
import SnippetLibrary from './components/SnippetLibrary/SnippetLibrary';
import DevTools from './components/DevTools/DevTools';
import AdvancedTools from './components/AdvancedTools/AdvancedTools';
import PostgresManager from './components/PostgreSQL/PostgresManager';
import RedisManager from './components/Redis/RedisManager';
import RailwayManager from './components/Railway/RailwayManager';
import FixLoop from './components/FixLoop/FixLoop';
import TesterAgent from './components/TesterAgent/TesterAgent';
import AgentPipeline from './components/AgentPipeline/AgentPipeline';
import TaskMonitor from './components/Tasks/TaskMonitor';

// API
import { api } from './api/client';

// ---------------------------------------------------------------------------
// Backward-compatibility export — existing tool components import this
// ---------------------------------------------------------------------------
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';
const API = `${BACKEND_URL}/api`;

export const axiosInstance = axios.create({
  baseURL: API,
  timeout: 180000, // 3 min — accommodates CPU-based slow model inference
});

// ---------------------------------------------------------------------------
// Tool page map: page id → { component, title }
// Note: 'tool-appbuilder' is intentionally removed — App Builder is now
// unified into the Chat workspace (right panel with Preview/Code tabs).
// ---------------------------------------------------------------------------
const TOOL_PAGES = {
  'tool-tasks': { component: TaskMonitor, title: 'Task Monitor' },
  'tool-agent': { component: AgentPipeline, title: 'Agent Pipeline' },
  'tool-codereview': { component: CodeReview, title: 'Code Review' },
  'tool-coderunner': { component: CodeRunner, title: 'Code Runner' },
  'tool-apitester': { component: APITester, title: 'API Tester' },
  'tool-tester': { component: TesterAgent, title: 'Tester Agent' },
  'tool-fixloop': { component: FixLoop, title: 'Fix Loop' },
  'tool-postgres': { component: PostgresManager, title: 'PostgreSQL' },
  'tool-redis': { component: RedisManager, title: 'Redis' },
  'tool-railway': { component: RailwayManager, title: 'Railway' },
  'tool-database': { component: DatabaseDesigner, title: 'DB Designer' },
  'tool-git': { component: GitIntegration, title: 'Git & GitHub' },
  'tool-packages': { component: PackageManager, title: 'Packages' },
  'tool-env': { component: EnvManager, title: 'Env Vars' },
  'tool-snippets': { component: SnippetLibrary, title: 'Snippets' },
  'tool-devtools': { component: DevTools, title: 'Dev Tools' },
  'tool-advanced': { component: AdvancedTools, title: 'Advanced' },
  'tool-files': { component: FileExplorer, title: 'Files' },
  'tool-terminal': { component: CommandTerminal, title: 'Terminal' },
  'tool-websearch': { component: WebSearch, title: 'Web Search' },
  'tool-codesearch': { component: CodebaseSearch, title: 'Code Search' },
  'tool-voice': { component: VoiceControl, title: 'Voice' },
  'tool-profiles': { component: ProjectProfiles, title: 'Profiles' },
  'tool-chat': { component: ChatInterface, title: 'Chat (Legacy)' },
};

const LEGAL_PAGES = {
  'legal-terms':     { component: TermsPage,     title: 'Terms of Service' },
  'legal-privacy':   { component: PrivacyPage,   title: 'Privacy Policy' },
  'legal-refund':    { component: RefundPage,     title: 'Refund Policy' },
  'legal-prohibited':{ component: ProhibitedPage, title: 'Prohibited Items' },
  'legal-dmca':      { component: DmcaPage,       title: 'DMCA & Copyright' },
  'legal-contact':   { component: ContactPage,    title: 'Contact Us' },
};

function pageTitle(page) {
  if (page === 'chat') return 'Chat';
  if (page === 'images') return 'Image Generation';
  if (page === 'settings') return 'Settings';
  if (LEGAL_PAGES[page]) return LEGAL_PAGES[page].title;
  return TOOL_PAGES[page]?.title || 'Mini Assistant';
}

// ---------------------------------------------------------------------------
// AppShell — rendered inside AppProvider so it can use useApp()
// ---------------------------------------------------------------------------
function AppShell() {
  const { page, setPage, getPrevPage, serverStatus, setServerStatus, purchaseModalOpen, setPurchaseModalOpen, upgradeModalOpen, setUpgradeModalOpen } = useApp();

  // Handle Stripe redirect params (?checkout=success|cancelled, ?portal=return)
  useEffect(() => {
    const result = handleCheckoutReturn();
    if (result === 'success') {
      // Go to dashboard — plan + credits will refresh from API
      setPage('dashboard');
    } else if (result === 'cancelled' || result === 'portal_return') {
      setPage('pricing');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll server status every 60 s
  useEffect(() => {
    const check = async () => {
      try {
        const data = await api.mainHealth();
        setServerStatus({
          backend: true,
          openai: data.openai === 'connected',
        });
      } catch {
        setServerStatus({ backend: false, openai: false });
      }
    };

    check();
    const id = setInterval(check, 60000);
    return () => clearInterval(id);
  }, [setServerStatus]);

  // Render current page content
  const renderContent = () => {
    if (page === 'chat') return <ChatPage />;
    // App Builder is unified into Chat workspace — redirect
    if (page === 'tool-appbuilder') { setPage('chat'); return <ChatPage />; }
    if (page === 'images') return <ImagePage />;
    if (page === 'profile') return <ProfilePage />;
    if (page === 'dashboard') return <UserDashboard />;
    if (page === 'admin') return <AdminPage />;
    if (page === 'pricing') return <PricingPage />;

    const legalEntry = LEGAL_PAGES[page];
    if (legalEntry) {
      const LegalComponent = legalEntry.component;
      return <div className="h-full overflow-auto"><LegalComponent /></div>;
    }

    const toolEntry = TOOL_PAGES[page];
    if (toolEntry) {
      const ToolComponent = toolEntry.component;
      return (
        <div className="h-full overflow-auto">
          <ToolComponent />
        </div>
      );
    }

    // Fallback
    return <ChatPage />;
  };

  return (
    <div className="flex h-screen bg-[#0d0d12] text-white overflow-hidden">
      <Sidebar />
      <MainPanel>
        <TopBar title={pageTitle(page)} serverStatus={serverStatus} />
        <UsageLimitBanner />
        <div className="flex-1 overflow-hidden">
          {renderContent()}
        </div>
      </MainPanel>

      {/* Settings modal overlays the whole shell */}
      {page === 'settings' && (
        <SettingsModal onClose={() => setPage(getPrevPage())} />
      )}

      {/* Purchase Credits modal — accessible from anywhere */}
      {purchaseModalOpen && (
        <PurchaseCreditsModal onClose={() => setPurchaseModalOpen(false)} />
      )}

      {/* Global upgrade modal — triggered from anywhere via openUpgradeModal() */}
      <UpgradeModal />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Auth gate — shown inside AppProvider so hooks work
// ---------------------------------------------------------------------------
function AuthGate() {
  const { user, page, setPage } = useApp();
  const toasterProps = {
    position: 'top-right',
    theme: 'dark',
    toastOptions: {
      style: {
        background: 'rgba(17, 17, 24, 0.95)',
        border: '1px solid rgba(255,255,255,0.08)',
        color: '#e2e8f0',
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: '13px',
      },
    },
  };

  // Detect /admin URL path on mount → navigate to admin page
  useEffect(() => {
    if (window.location.pathname === '/admin' && page !== 'admin') {
      setPage('admin');
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Admin page handles its own auth — render standalone outside of AppShell
  if (page === 'admin') {
    return (
      <>
        <AdminPage />
        <Toaster {...toasterProps} />
      </>
    );
  }

  if (!user) {
    return (
      <>
        <AuthPage />
        <Toaster {...toasterProps} />
      </>
    );
  }

  return (
    <>
      <AppShell />
      <Toaster {...toasterProps} />
    </>
  );
}

// ---------------------------------------------------------------------------
// App root
// ---------------------------------------------------------------------------
const GOOGLE_CLIENT_ID = process.env.REACT_APP_GOOGLE_CLIENT_ID || '';

function App() {
  return (
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <AppProvider>
        <AuthGate />
      </AppProvider>
    </GoogleOAuthProvider>
  );
}

export default App;
