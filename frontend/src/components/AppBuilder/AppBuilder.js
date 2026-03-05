import React, { useState } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Wand2, Loader2, Download, Eye, Code } from 'lucide-react';

const AppBuilder = () => {
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [generatedApp, setGeneratedApp] = useState(null);
  const [activeView, setActiveView] = useState('preview');

  const generateApp = async () => {
    if (!description.trim() || loading) return;

    setLoading(true);
    try {
      const response = await axiosInstance.post('/app-builder/generate', {
        description: description,
        framework: 'react'
      });

      setGeneratedApp(response.data);
      toast.success('App generated successfully!');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to generate app');
      console.error('Generation error:', error);
    } finally {
      setLoading(false);
    }
  };

  const downloadApp = () => {
    if (!generatedApp) return;

    const blob = new Blob([JSON.stringify(generatedApp, null, 2)], {
      type: 'application/json'
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'generated-app.json';
    a.click();
    URL.revokeObjectURL(url);
    toast.success('App downloaded!');
  };

  const templates = [
    { name: 'Todo App', desc: 'Simple task management app with CRUD operations' },
    { name: 'Weather App', desc: 'Weather dashboard with API integration' },
    { name: 'Blog Platform', desc: 'Full blog with posts, comments, and users' },
    { name: 'E-commerce', desc: 'Product catalog with cart and checkout' },
    { name: 'Dashboard', desc: 'Analytics dashboard with charts and metrics' },
    { name: 'Chat App', desc: 'Real-time messaging application' }
  ];

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="app-builder">
      {/* Header */}
      <div className="p-6 border-b border-cyan-500/20 bg-black/40">
        <div className="flex items-center gap-3 mb-6">
          <Wand2 className="w-7 h-7 text-cyan-400" />
          <div>
            <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
              APP BUILDER
            </h2>
            <p className="text-xs text-slate-400 font-mono mt-1">AI-POWERED APPLICATION GENERATOR</p>
          </div>
        </div>

        {/* Templates */}
        <div className="mb-4">
          <div className="text-xs text-cyan-400/70 font-mono uppercase mb-2">Quick Templates:</div>
          <div className="flex gap-2 flex-wrap">
            {templates.map((template, idx) => (
              <button
                key={idx}
                onClick={() => setDescription(template.desc)}
                className="px-3 py-1.5 bg-black/30 border border-cyan-500/30 hover:border-violet-500/50 text-cyan-100 text-xs rounded-sm transition-all"
              >
                {template.name}
              </button>
            ))}
          </div>
        </div>

        {/* Input */}
        <div className="space-y-4">
          <textarea
            data-testid="app-description-input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the app you want to build... (e.g., 'Build a todo app with user authentication, dark mode, and drag-drop functionality')"
            className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono p-4 outline-none resize-none"
            rows={4}
            disabled={loading}
          />
          <button
            data-testid="generate-app-btn"
            onClick={generateApp}
            disabled={loading || !description.trim()}
            className="px-8 py-3 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 hover:shadow-[0_0_20px_rgba(0,243,255,0.5),0_0_15px_rgba(147,51,234,0.3)] uppercase tracking-wider rounded-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                GENERATING...
              </>
            ) : (
              <>
                <Wand2 className="w-5 h-5" />
                GENERATE APP
              </>
            )}
          </button>
        </div>
      </div>

      {/* Generated App Display */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {generatedApp ? (
          <>
            <div className="p-4 border-b border-cyan-500/20 bg-black/30 flex items-center justify-between">
              <div className="flex gap-2">
                <button
                  onClick={() => setActiveView('preview')}
                  className={`px-4 py-2 rounded-sm text-sm font-semibold uppercase transition-all ${
                    activeView === 'preview'
                      ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <Eye className="w-4 h-4 inline mr-2" />
                  PREVIEW
                </button>
                <button
                  onClick={() => setActiveView('code')}
                  className={`px-4 py-2 rounded-sm text-sm font-semibold uppercase transition-all ${
                    activeView === 'code'
                      ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <Code className="w-4 h-4 inline mr-2" />
                  CODE
                </button>
              </div>
              <button
                onClick={downloadApp}
                className="px-4 py-2 bg-violet-500/20 text-violet-400 border border-violet-500/50 hover:bg-violet-500/30 rounded-sm text-sm font-semibold uppercase flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                DOWNLOAD
              </button>
            </div>

            <div className="flex-1 overflow-auto p-6">
              {activeView === 'preview' ? (
                <div className="space-y-4">
                  <div className="p-6 bg-black/40 border border-cyan-900/30 rounded-lg">
                    <h3 className="text-lg font-semibold text-cyan-400 mb-4">Generated Application</h3>
                    <pre className="text-slate-300 text-sm bg-black/30 p-4 rounded border border-cyan-900/20 overflow-auto">
                      {JSON.stringify(generatedApp, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {generatedApp.files?.map((file, idx) => (
                    <div key={idx} className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg">
                      <div className="text-sm font-mono text-cyan-400 mb-2">{file.path}</div>
                      <pre className="text-slate-300 text-sm bg-black/30 p-4 rounded border border-cyan-900/20 overflow-auto">
                        {file.content}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <Wand2 className="w-16 h-16 mx-auto text-cyan-500/30" />
              <p className="text-slate-400 font-mono text-sm">Describe your app and let AI build it for you</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AppBuilder;