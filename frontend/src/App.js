/**
 * App.js — Mini Assistant
 * Root component. Wraps everything in AppProvider, renders the shell layout.
 *
 * IMPORTANT: axiosInstance is exported at the top for backward-compatibility
 * with existing tool components that import it directly from this file.
 */

import React, { useEffect } from 'react';
import axios from 'axios';
import { Toaster } from 'sonner';

// Context
import { AppProvider, useApp } from './context/AppContext';

// Layout
import Sidebar from './layout/Sidebar';
import MainPanel from './layout/MainPanel';

// Shared components
import TopBar from './components/TopBar';

// Pages
import ChatPage from './pages/ChatPage';
import ImagePage from './pages/ImagePage';
import SettingsModal from './pages/SettingsModal';

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

function pageTitle(page) {
  if (page === 'chat') return 'Chat';
  if (page === 'images') return 'Image Generation';
  if (page === 'settings') return 'Settings';
  return TOOL_PAGES[page]?.title || 'Mini Assistant';
}

// ---------------------------------------------------------------------------
// AppShell — rendered inside AppProvider so it can use useApp()
// ---------------------------------------------------------------------------
function AppShell() {
  const { page, setPage, getPrevPage, serverStatus, setServerStatus } = useApp();

  // Poll server status every 60 s
  useEffect(() => {
    const check = async () => {
      try {
        const data = await api.mainHealth();
        setServerStatus({
          backend: true,
          ollama: data.ollama === 'connected',
          comfyui: data.comfyui === 'connected',
        });
      } catch {
        setServerStatus({ backend: false, ollama: false, comfyui: false });
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
        <div className="flex-1 overflow-hidden">
          {renderContent()}
        </div>
      </MainPanel>

      {/* Settings modal overlays the whole shell */}
      {page === 'settings' && (
        <SettingsModal onClose={() => setPage(getPrevPage())} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// App root
// ---------------------------------------------------------------------------
function App() {
  return (
    <AppProvider>
      <AppShell />
      <Toaster
        position="top-right"
        theme="dark"
        toastOptions={{
          style: {
            background: 'rgba(17, 17, 24, 0.95)',
            border: '1px solid rgba(255,255,255,0.08)',
            color: '#e2e8f0',
            fontFamily: 'Inter, system-ui, sans-serif',
            fontSize: '13px',
          },
        }}
      />
    </AppProvider>
  );
}

export default App;
