import React, { useState } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Shield, AlertTriangle, CheckCircle, XCircle, Loader2, Cloud, Rocket, Settings, Activity, Database as DbIcon, Box } from 'lucide-react';

const AdvancedTools = () => {
  const [activeTab, setActiveTab] = useState('security');
  
  // Security Scanner State
  const [securityCode, setSecurityCode] = useState('');
  const [securityLoading, setSecurityLoading] = useState(false);
  const [vulnerabilities, setVulnerabilities] = useState([]);
  
  // Deploy State
  const [deployPlatform, setDeployPlatform] = useState('vercel');
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

  React.useEffect(() => {
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
    <div className=\"h-full flex flex-col bg-[#0a0a0f]/50\" data-testid=\"advanced-tools\">
      <div className=\"p-6 border-b border-cyan-500/20 bg-black/40\">
        <div className=\"flex items-center gap-3 mb-6\">
          <Shield className=\"w-7 h-7 text-cyan-400\" />
          <div>
            <h2 className=\"text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase\" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
              ADVANCED TOOLS
            </h2>
            <p className=\"text-xs text-slate-400 font-mono mt-1\">SECURITY, DEPLOY, DOCKER & MONITORING</p>
          </div>
        </div>

        <div className=\"flex gap-2\">
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
                <Icon className=\"w-4 h-4 inline mr-2\" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className=\"flex-1 overflow-auto p-6\">
        {/* SECURITY SCANNER */}
        {activeTab === 'security' && (
          <div className=\"space-y-6\">
            <div>
              <label className=\"text-sm text-cyan-400 font-mono uppercase mb-2 block\">Code to Scan</label>
              <textarea
                value={securityCode}
                onChange={(e) => setSecurityCode(e.target.value)}
                placeholder=\"Paste code to scan for vulnerabilities...\"\n                className=\"w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono p-4 outline-none resize-none\"\n                rows={10}\n              />\n              <button\n                onClick={scanSecurity}\n                disabled={securityLoading || !securityCode.trim()}\n                className=\"mt-3 px-6 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-sm flex items-center gap-2 disabled:opacity-50\"\n              >\n                {securityLoading ? <Loader2 className=\"w-4 h-4 animate-spin\" /> : <Shield className=\"w-4 h-4\" />}\n                SCAN FOR VULNERABILITIES\n              </button>\n            </div>\n\n            {vulnerabilities.length > 0 && (\n              <div className=\"space-y-3\">\n                <h3 className=\"text-lg font-semibold text-cyan-400\">Found {vulnerabilities.length} Issue(s)</h3>\n                {vulnerabilities.map((vuln, idx) => (\n                  <div key={idx} className={`p-4 rounded-lg border ${getSeverityColor(vuln.severity)}`}>\n                    <div className=\"flex items-start justify-between mb-2\">\n                      <div className=\"flex items-center gap-2\">\n                        <AlertTriangle className=\"w-5 h-5\" />\n                        <span className=\"font-semibold\">{vuln.title}</span>\n                      </div>\n                      <span className=\"text-xs px-2 py-1 rounded uppercase\">{vuln.severity}</span>\n                    </div>\n                    <p className=\"text-sm opacity-90 mb-2\">{vuln.description}</p>\n                    {vuln.fix && (\n                      <div className=\"mt-2 p-2 bg-black/30 rounded\">\n                        <div className=\"text-xs opacity-70 mb-1\">Fix:</div>\n                        <code className=\"text-xs\">{vuln.fix}</code>\n                      </div>\n                    )}\n                  </div>\n                ))}\n              </div>\n            )}\n          </div>\n        )}\n\n        {/* DEPLOY */}\n        {activeTab === 'deploy' && (\n          <div className=\"max-w-2xl mx-auto space-y-6\">\n            <div>\n              <label className=\"text-sm text-cyan-400 font-mono uppercase mb-2 block\">Platform</label>\n              <div className=\"grid grid-cols-3 gap-3\">\n                {['vercel', 'netlify', 'railway'].map(platform => (\n                  <button\n                    key={platform}\n                    onClick={() => setDeployPlatform(platform)}\n                    className={`p-4 rounded-lg border transition-all ${\n                      deployPlatform === platform\n                        ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-400'\n                        : 'bg-black/40 border-cyan-900/30 text-slate-400 hover:border-cyan-500/30'\n                    }`}\n                  >\n                    <Cloud className=\"w-8 h-8 mx-auto mb-2\" />\n                    <div className=\"text-sm font-semibold uppercase\">{platform}</div>\n                  </button>\n                ))}\n              </div>\n            </div>\n\n            <button\n              onClick={deploy}\n              disabled={deployLoading}\n              className=\"w-full px-8 py-4 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-lg flex items-center justify-center gap-2 disabled:opacity-50\"\n            >\n              {deployLoading ? <Loader2 className=\"w-6 h-6 animate-spin\" /> : <Rocket className=\"w-6 h-6\" />}\n              DEPLOY NOW\n            </button>\n\n            {deployStatus && (\n              <div className=\"p-6 bg-black/40 border border-cyan-900/30 rounded-lg\">\n                <div className=\"flex items-center gap-2 mb-4\">\n                  <CheckCircle className=\"w-6 h-6 text-green-400\" />\n                  <span className=\"text-lg font-semibold text-green-400\">Deployment Started!</span>\n                </div>\n                <div className=\"space-y-2 text-sm\">\n                  <div><span className=\"text-slate-400\">Platform:</span> <span className=\"text-cyan-400\">{deployStatus.platform}</span></div>\n                  <div><span className=\"text-slate-400\">Status:</span> <span className=\"text-green-400\">{deployStatus.status}</span></div>\n                  {deployStatus.url && (\n                    <div><span className=\"text-slate-400\">URL:</span> <a href={deployStatus.url} target=\"_blank\" rel=\"noopener noreferrer\" className=\"text-violet-400 hover:text-violet-300\">{deployStatus.url}</a></div>\n                  )}\n                </div>\n              </div>\n            )}\n          </div>\n        )}\n\n        {/* DOCKER */}\n        {activeTab === 'docker' && (\n          <div className=\"space-y-4\">\n            <div className=\"flex items-center justify-between\">\n              <h3 className=\"text-lg font-semibold text-cyan-400\">Containers</h3>\n              <button\n                onClick={loadContainers}\n                disabled={dockerLoading}\n                className=\"px-4 py-2 bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 hover:bg-cyan-500/30 rounded-sm text-sm font-semibold uppercase\"\n              >\n                REFRESH\n              </button>\n            </div>\n\n            {dockerContainers.length === 0 ? (\n              <div className=\"text-center py-12 text-slate-500\">\n                <Box className=\"w-12 h-12 mx-auto mb-3 opacity-30\" />\n                <p className=\"text-sm\">No containers running</p>\n              </div>\n            ) : (\n              <div className=\"space-y-3\">\n                {dockerContainers.map(container => (\n                  <div key={container.id} className=\"p-4 bg-black/40 border border-cyan-900/30 rounded-lg\">\n                    <div className=\"flex items-center justify-between\">\n                      <div>\n                        <div className=\"text-cyan-400 font-mono\">{container.name}</div>\n                        <div className=\"text-xs text-slate-500 mt-1\">{container.image}</div>\n                      </div>\n                      <div className=\"flex gap-2\">\n                        {container.status === 'running' ? (\n                          <button\n                            onClick={() => stopContainer(container.id)}\n                            className=\"px-3 py-1.5 bg-red-500/20 text-red-400 border border-red-500/50 hover:bg-red-500/30 rounded-sm text-xs font-semibold uppercase\"\n                          >\n                            STOP\n                          </button>\n                        ) : (\n                          <button\n                            onClick={() => startContainer(container.id)}\n                            className=\"px-3 py-1.5 bg-green-500/20 text-green-400 border border-green-500/50 hover:bg-green-500/30 rounded-sm text-xs font-semibold uppercase\"\n                          >\n                            START\n                          </button>\n                        )}\n                      </div>\n                    </div>\n                  </div>\n                ))}\n              </div>\n            )}\n          </div>\n        )}\n\n        {/* PERFORMANCE MONITOR */}\n        {activeTab === 'monitor' && perfMetrics && (\n          <div className=\"grid grid-cols-2 gap-4\">\n            <div className=\"p-6 bg-black/40 border border-cyan-900/30 rounded-lg\">\n              <div className=\"text-sm text-cyan-400 font-mono uppercase mb-2\">CPU Usage</div>\n              <div className=\"text-3xl font-bold text-white mb-2\">{perfMetrics.cpu}%</div>\n              <div className=\"w-full bg-black/50 rounded-full h-2\">\n                <div className=\"bg-gradient-to-r from-cyan-500 to-violet-600 h-2 rounded-full\" style={{ width: `${perfMetrics.cpu}%` }}></div>\n              </div>\n            </div>\n\n            <div className=\"p-6 bg-black/40 border border-cyan-900/30 rounded-lg\">\n              <div className=\"text-sm text-cyan-400 font-mono uppercase mb-2\">Memory</div>\n              <div className=\"text-3xl font-bold text-white mb-2\">{perfMetrics.memory}%</div>\n              <div className=\"w-full bg-black/50 rounded-full h-2\">\n                <div className=\"bg-gradient-to-r from-cyan-500 to-violet-600 h-2 rounded-full\" style={{ width: `${perfMetrics.memory}%` }}></div>\n              </div>\n            </div>\n\n            <div className=\"p-6 bg-black/40 border border-cyan-900/30 rounded-lg\">\n              <div className=\"text-sm text-cyan-400 font-mono uppercase mb-2\">Disk</div>\n              <div className=\"text-3xl font-bold text-white mb-2\">{perfMetrics.disk}%</div>\n              <div className=\"w-full bg-black/50 rounded-full h-2\">\n                <div className=\"bg-gradient-to-r from-cyan-500 to-violet-600 h-2 rounded-full\" style={{ width: `${perfMetrics.disk}%` }}></div>\n              </div>\n            </div>\n\n            <div className=\"p-6 bg-black/40 border border-cyan-900/30 rounded-lg\">\n              <div className=\"text-sm text-cyan-400 font-mono uppercase mb-2\">Uptime</div>\n              <div className=\"text-3xl font-bold text-white\">{perfMetrics.uptime}</div>\n            </div>\n          </div>\n        )}\n      </div>\n    </div>\n  );\n};\n\nexport default AdvancedTools;