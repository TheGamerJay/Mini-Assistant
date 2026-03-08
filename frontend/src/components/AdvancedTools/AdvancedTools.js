import React, { useState, useEffect } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Shield, AlertTriangle, CheckCircle, XCircle, Loader2, Cloud, Rocket, Settings, Activity, Database as DbIcon, Box } from 'lucide-react';
import { usePersist } from '../../hooks/usePersist';

const AdvancedTools = () => {
  const [activeTab, setActiveTab] = usePersist('ma_advtools_tab', 'security');

  // Security Scanner State
  const [securityCode, setSecurityCode] = useState('');
  const [securityLoading, setSecurityLoading] = useState(false);
  const [vulnerabilities, setVulnerabilities] = useState([]);

  // Deploy State
  const [deployPlatform, setDeployPlatform] = usePersist('ma_advtools_platform', 'vercel');
  const [deployLoading, setDeployLoading] = useState(false);
  const [deployStatus, setDeployStatus] = useState(null);
  
  // Docker State
  const [dockerContainers, setDockerContainers] = useState([]);
  const [dockerLoading, setDockerLoading] = useState(false);
  
  // Performance Monitor State
  const [perfMetrics, setPerfMetrics] = useState(null);

  // Security Scan
  const scanSecurity = async () => {
    if (!securityCode.trim()) return;
    
    setSecurityLoading(true);
    try {
      const response = await axiosInstance.post('/security/scan', {
        code: securityCode
      });
      
      setVulnerabilities(response.data.vulnerabilities || []);
      toast.success(`Found ${response.data.vulnerabilities?.length || 0} issues`);
    } catch (error) {
      toast.error('Security scan failed');
    } finally {
      setSecurityLoading(false);
    }
  };

  // Deploy
  const deploy = async () => {
    setDeployLoading(true);
    try {
      const response = await axiosInstance.post('/deploy/start', {
        platform: deployPlatform,
        project_path: '/app'
      });
      
      setDeployStatus(response.data);
      toast.success('Deployment started!');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Deployment failed');
    } finally {
      setDeployLoading(false);
    }
  };

  // Docker
  const loadContainers = async () => {
    setDockerLoading(true);
    try {
      const response = await axiosInstance.get('/docker/containers');
      setDockerContainers(response.data.containers || []);
    } catch (error) {
      toast.error('Failed to load containers');
    } finally {
      setDockerLoading(false);
    }
  };

  const startContainer = async (id) => {
    try {
      await axiosInstance.post(`/docker/start/${id}`);
      toast.success('Container started');
      loadContainers();
    } catch (error) {
      toast.error('Failed to start container');
    }
  };

  const stopContainer = async (id) => {
    try {
      await axiosInstance.post(`/docker/stop/${id}`);
      toast.success('Container stopped');
      loadContainers();
    } catch (error) {
      toast.error('Failed to stop container');
    }
  };

  // Performance
  const loadPerformance = async () => {
    try {
      const response = await axiosInstance.get('/monitor/performance');
      setPerfMetrics(response.data);
    } catch (error) {
      console.error('Failed to load metrics');
    }
  };

  useEffect(() => {
    if (activeTab === 'docker') {
      loadContainers();
    } else if (activeTab === 'monitor') {
      loadPerformance();
      const interval = setInterval(loadPerformance, 5000);
      return () => clearInterval(interval);
    }
  }, [activeTab]);

  const tabs = [
    { id: 'security', label: 'SECURITY', icon: Shield },
    { id: 'deploy', label: 'DEPLOY', icon: Rocket },
    { id: 'docker', label: 'DOCKER', icon: Box },
    { id: 'monitor', label: 'MONITOR', icon: Activity },
  ];

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'critical': return 'text-red-400 bg-red-500/10 border-red-500/30';
      case 'high': return 'text-orange-400 bg-orange-500/10 border-orange-500/30';
      case 'medium': return 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30';
      case 'low': return 'text-blue-400 bg-blue-500/10 border-blue-500/30';
      default: return 'text-slate-400 bg-slate-500/10 border-slate-500/30';
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="advanced-tools">
      <div className="p-6 border-b border-cyan-500/20 bg-black/40">
        <div className="flex items-center gap-3 mb-6">
          <Shield className="w-7 h-7 text-cyan-400" />
          <div>
            <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
              ADVANCED TOOLS
            </h2>
            <p className="text-xs text-slate-400 font-mono mt-1">SECURITY, DEPLOY, DOCKER & MONITORING</p>
          </div>
        </div>

        <div className="flex gap-2">
          {tabs.map(tab => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 rounded-sm text-xs font-bold uppercase transition-all ${
                  activeTab === tab.id
                    ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                    : 'bg-black/30 text-slate-400 hover:text-cyan-400'
                }`}
              >
                <Icon className="w-4 h-4 inline mr-2" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {/* SECURITY SCANNER */}
        {activeTab === 'security' && (
          <div className="space-y-6">
            <div>
              <label className="text-sm text-cyan-400 font-mono uppercase mb-2 block">Code to Scan</label>
              <textarea
                value={securityCode}
                onChange={(e) => setSecurityCode(e.target.value)}
                placeholder="Paste code to scan for vulnerabilities..."
                className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono p-4 outline-none resize-none"
                rows={10}
              />
              <button
                onClick={scanSecurity}
                disabled={securityLoading || !securityCode.trim()}
                className="mt-3 px-6 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-sm flex items-center gap-2 disabled:opacity-50"
              >
                {securityLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
                SCAN FOR VULNERABILITIES
              </button>
            </div>

            {vulnerabilities.length > 0 && (
              <div className="space-y-3">
                <h3 className="text-lg font-semibold text-cyan-400">Found {vulnerabilities.length} Issue(s)</h3>
                {vulnerabilities.map((vuln, idx) => (
                  <div key={idx} className={`p-4 rounded-lg border ${getSeverityColor(vuln.severity)}`}>
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <AlertTriangle className="w-5 h-5" />
                        <span className="font-semibold">{vuln.title}</span>
                      </div>
                      <span className="text-xs px-2 py-1 rounded uppercase">{vuln.severity}</span>
                    </div>
                    <p className="text-sm opacity-90 mb-2">{vuln.description}</p>
                    {vuln.fix && (
                      <div className="mt-2 p-2 bg-black/30 rounded">
                        <div className="text-xs opacity-70 mb-1">Fix:</div>
                        <code className="text-xs">{vuln.fix}</code>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* DEPLOY */}
        {activeTab === 'deploy' && (
          <div className="max-w-2xl mx-auto space-y-6">
            <div>
              <label className="text-sm text-cyan-400 font-mono uppercase mb-2 block">Platform</label>
              <div className="grid grid-cols-3 gap-3">
                {['vercel', 'netlify', 'railway'].map(platform => (
                  <button
                    key={platform}
                    onClick={() => setDeployPlatform(platform)}
                    className={`p-4 rounded-lg border transition-all ${
                      deployPlatform === platform
                        ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-400'
                        : 'bg-black/40 border-cyan-900/30 text-slate-400 hover:border-cyan-500/30'
                    }`}
                  >
                    <Cloud className="w-8 h-8 mx-auto mb-2" />
                    <div className="text-sm font-semibold uppercase">{platform}</div>
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={deploy}
              disabled={deployLoading}
              className="w-full px-8 py-4 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-lg flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {deployLoading ? <Loader2 className="w-6 h-6 animate-spin" /> : <Rocket className="w-6 h-6" />}
              DEPLOY NOW
            </button>

            {deployStatus && (
              <div className="p-6 bg-black/40 border border-cyan-900/30 rounded-lg">
                <div className="flex items-center gap-2 mb-4">
                  <CheckCircle className="w-6 h-6 text-green-400" />
                  <span className="text-lg font-semibold text-green-400">Deployment Started!</span>
                </div>
                <div className="space-y-2 text-sm">
                  <div><span className="text-slate-400">Platform:</span> <span className="text-cyan-400">{deployStatus.platform}</span></div>
                  <div><span className="text-slate-400">Status:</span> <span className="text-green-400">{deployStatus.status}</span></div>
                  {deployStatus.url && (
                    <div><span className="text-slate-400">URL:</span> <a href={deployStatus.url} target="_blank" rel="noopener noreferrer" className="text-violet-400 hover:text-violet-300">{deployStatus.url}</a></div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* DOCKER */}
        {activeTab === 'docker' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-cyan-400">Containers</h3>
              <button
                onClick={loadContainers}
                disabled={dockerLoading}
                className="px-4 py-2 bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 hover:bg-cyan-500/30 rounded-sm text-sm font-semibold uppercase"
              >
                REFRESH
              </button>
            </div>

            {dockerContainers.length === 0 ? (
              <div className="text-center py-12 text-slate-500">
                <Box className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p className="text-sm">No containers running</p>
              </div>
            ) : (
              <div className="space-y-3">
                {dockerContainers.map(container => (
                  <div key={container.id} className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-cyan-400 font-mono">{container.name}</div>
                        <div className="text-xs text-slate-500 mt-1">{container.image}</div>
                      </div>
                      <div className="flex gap-2">
                        {container.status === 'running' ? (
                          <button
                            onClick={() => stopContainer(container.id)}
                            className="px-3 py-1.5 bg-red-500/20 text-red-400 border border-red-500/50 hover:bg-red-500/30 rounded-sm text-xs font-semibold uppercase"
                          >
                            STOP
                          </button>
                        ) : (
                          <button
                            onClick={() => startContainer(container.id)}
                            className="px-3 py-1.5 bg-green-500/20 text-green-400 border border-green-500/50 hover:bg-green-500/30 rounded-sm text-xs font-semibold uppercase"
                          >
                            START
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* PERFORMANCE MONITOR */}
        {activeTab === 'monitor' && perfMetrics && (
          <div className="grid grid-cols-2 gap-4">
            <div className="p-6 bg-black/40 border border-cyan-900/30 rounded-lg">
              <div className="text-sm text-cyan-400 font-mono uppercase mb-2">CPU Usage</div>
              <div className="text-3xl font-bold text-white mb-2">{perfMetrics.cpu}%</div>
              <div className="w-full bg-black/50 rounded-full h-2">
                <div className="bg-gradient-to-r from-cyan-500 to-violet-600 h-2 rounded-full" style={{ width: `${perfMetrics.cpu}%` }}></div>
              </div>
            </div>

            <div className="p-6 bg-black/40 border border-cyan-900/30 rounded-lg">
              <div className="text-sm text-cyan-400 font-mono uppercase mb-2">Memory</div>
              <div className="text-3xl font-bold text-white mb-2">{perfMetrics.memory}%</div>
              <div className="w-full bg-black/50 rounded-full h-2">
                <div className="bg-gradient-to-r from-cyan-500 to-violet-600 h-2 rounded-full" style={{ width: `${perfMetrics.memory}%` }}></div>
              </div>
            </div>

            <div className="p-6 bg-black/40 border border-cyan-900/30 rounded-lg">
              <div className="text-sm text-cyan-400 font-mono uppercase mb-2">Disk</div>
              <div className="text-3xl font-bold text-white mb-2">{perfMetrics.disk}%</div>
              <div className="w-full bg-black/50 rounded-full h-2">
                <div className="bg-gradient-to-r from-cyan-500 to-violet-600 h-2 rounded-full" style={{ width: `${perfMetrics.disk}%` }}></div>
              </div>
            </div>

            <div className="p-6 bg-black/40 border border-cyan-900/30 rounded-lg">
              <div className="text-sm text-cyan-400 font-mono uppercase mb-2">Uptime</div>
              <div className="text-3xl font-bold text-white">{perfMetrics.uptime}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AdvancedTools;
