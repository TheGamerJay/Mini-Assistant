import React, { useState, useEffect, useRef } from 'react';
import { axiosInstance } from '../App';
import { toast } from 'sonner';
import ChatInterface from '../components/Chat/ChatInterface';
import VoiceControl from '../components/Voice/VoiceControl';
import FileExplorer from '../components/Files/FileExplorer';
import CommandTerminal from '../components/Terminal/CommandTerminal';
import WebSearch from '../components/Search/WebSearch';
import CodebaseSearch from '../components/Search/CodebaseSearch';
import ProjectProfiles from '../components/Profiles/ProjectProfiles';
import AppBuilder from '../components/AppBuilder/AppBuilder';
import CodeReview from '../components/CodeReview/CodeReview';
import GitIntegration from '../components/Git/GitIntegration';
import { 
  MessageSquare, 
  Mic, 
  FolderOpen, 
  Terminal, 
  Search, 
  Code, 
  Layers,
  Activity,
  Zap,
  Wand2,
  Shield,
  GitBranch
} from 'lucide-react';

const Dashboard = () => {
  const [activeTab, setActiveTab] = useState('chat');
  const [isOllamaConnected, setIsOllamaConnected] = useState(false);
  const [isVoiceActive, setIsVoiceActive] = useState(false);

  useEffect(() => {
    checkHealth();
  }, []);

  const checkHealth = async () => {
    try {
      const response = await axiosInstance.get('/health');
      setIsOllamaConnected(response.data.ollama === 'connected');
      if (response.data.ollama === 'disconnected') {
        toast.error('Ollama not connected. Please start Ollama service on localhost:11434');
      }
    } catch (error) {
      toast.error('Backend connection error');
    }
  };

  const tabs = [
    { id: 'chat', label: 'CHAT', icon: MessageSquare },
    { id: 'appbuilder', label: 'APP BUILDER', icon: Wand2 },
    { id: 'codereview', label: 'CODE REVIEW', icon: Shield },
    { id: 'git', label: 'GIT & GITHUB', icon: GitBranch },
    { id: 'voice', label: 'VOICE', icon: Mic },
    { id: 'files', label: 'FILES', icon: FolderOpen },
    { id: 'terminal', label: 'TERMINAL', icon: Terminal },
    { id: 'websearch', label: 'WEB SEARCH', icon: Search },
    { id: 'codesearch', label: 'CODE SEARCH', icon: Code },
    { id: 'profiles', label: 'PROFILES', icon: Layers },
  ];

  return (
    <div className="min-h-screen bg-[#050505] text-white">
      {/* Header */}
      <header className="border-b border-cyan-500/20 bg-black/40 backdrop-blur-xl sticky top-0 z-50">
        <div className="px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="relative">
              <div className="absolute inset-0 bg-gradient-to-r from-cyan-500 to-violet-600 blur-xl opacity-50"></div>
              <div className="relative w-12 h-12 rounded-lg bg-gradient-to-br from-cyan-500 via-violet-500 to-violet-600 flex items-center justify-center">
                <Zap className="w-7 h-7 text-white" strokeWidth={2.5} />
              </div>
            </div>
            <div>
              <h1 
                className="text-3xl font-bold tracking-tight uppercase bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text text-transparent" 
                style={{ fontFamily: 'Orbitron, sans-serif' }}
                data-testid="jarvis-title"
              >
                MINI ASSISTANT
              </h1>
              <p className="text-xs text-cyan-400/70 font-mono uppercase tracking-widest">AI ASSISTANT SYSTEM</p>
            </div>
          </div>
          
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-3" data-testid="status-indicator">
              <Activity className={`w-5 h-5 ${isOllamaConnected ? 'text-green-400' : 'text-red-400'}`} />
              <span className="text-sm font-mono uppercase tracking-wider">
                {isOllamaConnected ? 'ONLINE' : 'OFFLINE'}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex h-[calc(100vh-81px)]">
        {/* Sidebar */}
        <aside className="w-64 border-r border-cyan-500/20 bg-black/20 backdrop-blur-sm">
          <nav className="p-4 space-y-2">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  data-testid={`tab-${tab.id}`}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-sm text-left uppercase tracking-wider text-sm font-semibold transition-all ${
                    activeTab === tab.id
                      ? 'bg-gradient-to-r from-cyan-500/20 to-violet-500/20 text-transparent bg-clip-text border border-cyan-500/50 shadow-[0_0_15px_rgba(0,243,255,0.3),0_0_10px_rgba(147,51,234,0.2)]'
                      : 'text-slate-400 hover:text-white hover:bg-white/5 border border-transparent'
                  }`}
                >
                  <Icon className={`w-5 h-5 ${activeTab === tab.id ? 'text-cyan-400' : ''}`} />
                  <span className={activeTab === tab.id ? 'bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text text-transparent' : ''}>{tab.label}</span>
                </button>
              );
            })}
          </nav>
        </aside>

        {/* Content Area */}
        <main className="flex-1 overflow-hidden" data-testid="main-content">
          {activeTab === 'chat' && <ChatInterface />}
          {activeTab === 'appbuilder' && <AppBuilder />}
          {activeTab === 'codereview' && <CodeReview />}
          {activeTab === 'git' && <GitIntegration />}
          {activeTab === 'voice' && <VoiceControl />}
          {activeTab === 'files' && <FileExplorer />}
          {activeTab === 'terminal' && <CommandTerminal />}
          {activeTab === 'websearch' && <WebSearch />}
          {activeTab === 'codesearch' && <CodebaseSearch />}
          {activeTab === 'profiles' && <ProjectProfiles />}
        </main>
      </div>
    </div>
  );
};

export default Dashboard;