import React, { useState } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Train, Rocket, Server, RefreshCw, Loader2, Check, ExternalLink, FolderGit2 } from 'lucide-react';
import { usePersist } from '../../hooks/usePersist';

const RailwayManager = () => {
  const [apiToken, setApiToken] = usePersist('ma_railway_token', '');
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [services, setServices] = useState([]);
  const [deploying, setDeploying] = useState(false);

  const connect = async () => {
    if (!apiToken.trim()) {
      toast.error('Enter your Railway API token');
      return;
    }
    
    setLoading(true);
    try {
      const response = await axiosInstance.post('/railway/projects', {
        api_token: apiToken
      });
      setProjects(response.data.projects || []);
      setConnected(true);
      toast.success('Connected to Railway!');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Connection failed');
    } finally {
      setLoading(false);
    }
  };

  const loadServices = async (project) => {
    setSelectedProject(project);
    try {
      const response = await axiosInstance.post('/railway/services', {
        api_token: apiToken,
        project_id: project.id
      });
      setServices(response.data.services || []);
    } catch (error) {
      toast.error('Failed to load services');
    }
  };

  const deploy = async () => {
    if (!selectedProject) {
      toast.error('Select a project first');
      return;
    }
    
    setDeploying(true);
    try {
      const response = await axiosInstance.post('/railway/deploy', {
        api_token: apiToken,
        project_id: selectedProject.id
      });
      toast.success(response.data.message);
    } catch (error) {
      toast.error('Deploy failed');
    } finally {
      setDeploying(false);
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="railway-manager">
      <div className="p-6 border-b border-cyan-500/20 bg-black/40">
        <div className="flex items-center gap-3 mb-4">
          <Train className="w-7 h-7 text-violet-400" />
          <div>
            <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-violet-400 to-purple-400 bg-clip-text uppercase">
              Railway
            </h2>
            <p className="text-xs text-slate-400 font-mono mt-1">DEPLOYMENT PLATFORM</p>
          </div>
          <a 
            href="https://railway.app/account/tokens" 
            target="_blank" 
            rel="noopener noreferrer"
            className="ml-auto text-xs text-violet-400 hover:text-violet-300 flex items-center gap-1"
          >
            Get API Token <ExternalLink className="w-3 h-3" />
          </a>
        </div>

        {!connected ? (
          <div className="flex gap-3">
            <input
              type="password"
              value={apiToken}
              onChange={(e) => setApiToken(e.target.value)}
              placeholder="Railway API Token"
              className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono px-4 py-3 outline-none"
            />
            <button
              onClick={connect}
              disabled={loading}
              className="px-6 py-2 bg-gradient-to-r from-violet-500 to-purple-600 text-white font-bold rounded-sm uppercase flex items-center gap-2 disabled:opacity-50"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Train className="w-4 h-4" />}
              Connect
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <Check className="w-5 h-5 text-green-400" />
            <span className="text-green-400 font-mono text-sm">Connected to Railway</span>
            <button
              onClick={() => { setConnected(false); setProjects([]); setSelectedProject(null); }}
              className="ml-auto px-3 py-1 text-red-400 border border-red-500/50 rounded-sm text-xs hover:bg-red-500/20"
            >
              Disconnect
            </button>
          </div>
        )}
      </div>

      {connected && (
        <div className="flex-1 flex overflow-hidden">
          {/* Projects List */}
          <div className="w-80 border-r border-cyan-500/20 bg-black/20 overflow-auto">
            <div className="p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs text-violet-400 font-mono uppercase">Projects</span>
                <button onClick={connect} className="p-1 text-slate-400 hover:text-violet-400">
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>
              <div className="space-y-2">
                {projects.map((project) => (
                  <button
                    key={project.id}
                    onClick={() => loadServices(project)}
                    className={`w-full text-left p-4 rounded-lg transition-all ${
                      selectedProject?.id === project.id
                        ? 'bg-violet-500/20 border border-violet-500/50'
                        : 'bg-black/40 border border-cyan-900/30 hover:border-violet-500/30'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <FolderGit2 className="w-4 h-4 text-violet-400" />
                      <span className="font-semibold text-white">{project.name}</span>
                    </div>
                    {project.description && (
                      <p className="text-xs text-slate-500 mt-1">{project.description}</p>
                    )}
                    <div className="text-xs text-slate-500 mt-2">
                      {project.environments?.edges?.length || 0} environments
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Project Details */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {selectedProject ? (
              <>
                <div className="p-6 border-b border-cyan-500/20">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-xl font-bold text-white">{selectedProject.name}</h3>
                      <p className="text-sm text-slate-400 mt-1">{selectedProject.description || 'No description'}</p>
                    </div>
                    <button
                      onClick={deploy}
                      disabled={deploying}
                      className="px-6 py-3 bg-gradient-to-r from-violet-500 to-purple-600 text-white font-bold rounded-sm uppercase flex items-center gap-2 disabled:opacity-50 hover:shadow-[0_0_20px_rgba(147,51,234,0.5)]"
                    >
                      {deploying ? <Loader2 className="w-5 h-5 animate-spin" /> : <Rocket className="w-5 h-5" />}
                      Deploy
                    </button>
                  </div>
                </div>

                {/* Services */}
                <div className="flex-1 overflow-auto p-6">
                  <h4 className="text-sm text-violet-400 font-mono uppercase mb-4">Services</h4>
                  {services.length === 0 ? (
                    <div className="text-center py-12 text-slate-500">
                      <Server className="w-12 h-12 mx-auto mb-3 opacity-30" />
                      <p className="text-sm">No services in this project</p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 gap-4">
                      {services.map((service) => (
                        <div
                          key={service.id}
                          className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg hover:border-violet-500/30 transition-all"
                        >
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-lg bg-violet-500/20 flex items-center justify-center">
                              <Server className="w-5 h-5 text-violet-400" />
                            </div>
                            <div>
                              <div className="font-semibold text-white">{service.name}</div>
                              <div className="text-xs text-slate-500">Service</div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Environments */}
                  {selectedProject.environments?.edges?.length > 0 && (
                    <div className="mt-8">
                      <h4 className="text-sm text-violet-400 font-mono uppercase mb-4">Environments</h4>
                      <div className="flex gap-3">
                        {selectedProject.environments.edges.map((env) => (
                          <div
                            key={env.node.id}
                            className="px-4 py-2 bg-black/40 border border-cyan-900/30 rounded-lg"
                          >
                            <span className="text-sm text-white">{env.node.name}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-slate-500">
                <FolderGit2 className="w-12 h-12 opacity-30" />
                <span className="ml-3">Select a project to view details</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default RailwayManager;
