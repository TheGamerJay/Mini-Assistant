import React, { useState, useEffect } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { GitBranch, Upload, Download, GitCommit, GitPullRequest, RefreshCw, FolderGit2, Terminal } from 'lucide-react';
import { usePersist } from '../../hooks/usePersist';

const GitIntegration = () => {
  const [status, setStatus] = useState(null);
  const [branches, setBranches] = useState([]);
  const [currentBranch, setCurrentBranch] = useState('');
  const [commitMessage, setCommitMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [repoUrl, setRepoUrl] = usePersist('ma_git_repourl', '');
  const [remoteName, setRemoteName] = usePersist('ma_git_remote', 'origin');
  const [githubToken, setGithubToken] = usePersist('ma_git_token', '');
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    loadGitStatus();
  }, []);

  const loadGitStatus = async () => {
    try {
      const response = await axiosInstance.get('/git/status');
      setStatus(response.data);
      setCurrentBranch(response.data.branch);
      setBranches(response.data.branches || []);
    } catch (error) {
      console.error('Git status error:', error);
    }
  };

  const initRepo = async () => {
    setLoading(true);
    try {
      const response = await axiosInstance.post('/git/init');
      toast.success('Git repository initialized!');
      setLogs(prev => [...prev, response.data.message]);
      loadGitStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to initialize repo');
    } finally {
      setLoading(false);
    }
  };

  const addAll = async () => {
    setLoading(true);
    try {
      const response = await axiosInstance.post('/git/add', { files: ['.'] });
      toast.success('Files staged for commit');
      setLogs(prev => [...prev, 'Staged all changes']);
      loadGitStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to stage files');
    } finally {
      setLoading(false);
    }
  };

  const commit = async () => {
    if (!commitMessage.trim()) {
      toast.error('Please enter a commit message');
      return;
    }

    setLoading(true);
    try {
      const response = await axiosInstance.post('/git/commit', {
        message: commitMessage
      });
      toast.success('Changes committed!');
      setLogs(prev => [...prev, `Committed: ${commitMessage}`]);
      setCommitMessage('');
      loadGitStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Commit failed');
    } finally {
      setLoading(false);
    }
  };

  const push = async () => {
    setLoading(true);
    try {
      const response = await axiosInstance.post('/git/push', {
        remote: remoteName,
        branch: currentBranch
      });
      toast.success('Pushed to GitHub!');
      setLogs(prev => [...prev, `Pushed to ${remoteName}/${currentBranch}`]);
      loadGitStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Push failed');
    } finally {
      setLoading(false);
    }
  };

  const pull = async () => {
    setLoading(true);
    try {
      const response = await axiosInstance.post('/git/pull', {
        remote: remoteName,
        branch: currentBranch
      });
      toast.success('Pulled latest changes');
      setLogs(prev => [...prev, 'Pulled updates']);
      loadGitStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Pull failed');
    } finally {
      setLoading(false);
    }
  };

  const addRemote = async () => {
    if (!repoUrl.trim()) {
      toast.error('Please enter repository URL');
      return;
    }

    setLoading(true);
    try {
      const response = await axiosInstance.post('/git/remote/add', {
        name: remoteName,
        url: repoUrl,
        github_token: githubToken
      });
      toast.success(`Remote '${remoteName}' added!`);
      setLogs(prev => [...prev, `Added remote: ${remoteName}`]);
      setRepoUrl('');
      loadGitStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add remote');
    } finally {
      setLoading(false);
    }
  };

  const createBranch = async (branchName) => {
    setLoading(true);
    try {
      const response = await axiosInstance.post('/git/branch/create', {
        name: branchName
      });
      toast.success(`Branch '${branchName}' created`);
      setLogs(prev => [...prev, `Created branch: ${branchName}`]);
      loadGitStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create branch');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full flex" data-testid="git-integration">
      {/* Left Panel - Controls */}
      <div className="w-2/3 border-r border-cyan-500/20 flex flex-col bg-black/20">
        <div className="p-6 border-b border-cyan-500/20 bg-black/40">
          <div className="flex items-center gap-3 mb-6">
            <FolderGit2 className="w-7 h-7 text-cyan-400" />
            <div>
              <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
                GIT & GITHUB
              </h2>
              <p className="text-xs text-slate-400 font-mono mt-1">VERSION CONTROL INTEGRATION</p>
            </div>
          </div>

          {/* Status */}
          {status && (
            <div className="mb-6 p-4 bg-black/30 border border-cyan-500/30 rounded-lg">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <GitBranch className="w-5 h-5 text-cyan-400" />
                  <span className="text-cyan-400 font-mono text-sm">Branch: {status.branch || 'Not initialized'}</span>
                </div>
                <button
                  onClick={loadGitStatus}
                  className="p-1 text-slate-400 hover:text-cyan-400 transition-colors"
                  title="Refresh"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>
              {status.modified && status.modified.length > 0 && (
                <div className="text-xs text-yellow-400">Modified: {status.modified.length} file(s)</div>
              )}
              {status.staged && status.staged.length > 0 && (
                <div className="text-xs text-green-400">Staged: {status.staged.length} file(s)</div>
              )}
            </div>
          )}

          {/* Repository Setup */}
          {!status?.initialized && (
            <div className="mb-6 space-y-4">
              <div className="text-sm text-cyan-400 font-mono uppercase">Initialize Repository</div>
              <button
                data-testid="init-repo-btn"
                onClick={initRepo}
                disabled={loading}
                className="w-full px-6 py-3 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase flex items-center justify-center gap-2 disabled:opacity-50"
              >
                <FolderGit2 className="w-5 h-5" />
                INITIALIZE GIT
              </button>
            </div>
          )}

          {/* Add Remote */}
          <div className="mb-6 space-y-3">
            <div className="text-sm text-cyan-400 font-mono uppercase">GitHub Remote</div>
            <input
              data-testid="remote-name-input"
              type="text"
              placeholder="Remote name (origin)"
              value={remoteName}
              onChange={(e) => setRemoteName(e.target.value)}
              className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono px-4 py-2 outline-none text-sm"
            />
            <input
              data-testid="repo-url-input"
              type="text"
              placeholder="https://github.com/username/repo.git"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono px-4 py-2 outline-none text-sm"
            />
            <input
              data-testid="github-token-input"
              type="password"
              placeholder="GitHub personal access token (for push/pull)"
              value={githubToken}
              onChange={(e) => setGithubToken(e.target.value)}
              className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono px-4 py-2 outline-none text-sm"
            />
            <button
              data-testid="add-remote-btn"
              onClick={addRemote}
              disabled={loading || !repoUrl.trim()}
              className="w-full px-4 py-2 bg-violet-500/20 text-violet-400 border border-violet-500/50 hover:bg-violet-500/30 rounded-sm uppercase text-sm font-semibold disabled:opacity-50"
            >
              ADD REMOTE
            </button>
          </div>

          {/* Commit Section */}
          <div className="space-y-3">
            <div className="text-sm text-cyan-400 font-mono uppercase">Commit Changes</div>
            <textarea
              data-testid="commit-message-input"
              placeholder="Commit message..."
              value={commitMessage}
              onChange={(e) => setCommitMessage(e.target.value)}
              className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono p-3 outline-none resize-none text-sm"
              rows={3}
            />
            
            <div className="grid grid-cols-2 gap-3">
              <button
                data-testid="stage-all-btn"
                onClick={addAll}
                disabled={loading}
                className="px-4 py-2 bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 hover:bg-cyan-500/30 rounded-sm uppercase text-sm font-semibold disabled:opacity-50"
              >
                STAGE ALL
              </button>
              <button
                data-testid="commit-btn"
                onClick={commit}
                disabled={loading || !commitMessage.trim()}
                className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-sm disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <GitCommit className="w-4 h-4" />
                COMMIT
              </button>
            </div>
          </div>

          {/* Push/Pull */}
          <div className="mt-6 grid grid-cols-2 gap-3">
            <button
              data-testid="push-btn"
              onClick={push}
              disabled={loading}
              className="px-4 py-3 bg-green-500/20 text-green-400 border border-green-500/50 hover:bg-green-500/30 rounded-sm uppercase text-sm font-semibold disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <Upload className="w-4 h-4" />
              PUSH
            </button>
            <button
              data-testid="pull-btn"
              onClick={pull}
              disabled={loading}
              className="px-4 py-3 bg-blue-500/20 text-blue-400 border border-blue-500/50 hover:bg-blue-500/30 rounded-sm uppercase text-sm font-semibold disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <Download className="w-4 h-4" />
              PULL
            </button>
          </div>
        </div>
      </div>

      {/* Right Panel - Logs */}
      <div className="w-1/3 flex flex-col bg-[#0a0a0f]/50">
        <div className="p-4 border-b border-cyan-500/20 bg-black/40">
          <div className="flex items-center gap-2">
            <Terminal className="w-5 h-5 text-cyan-400" />
            <h3 className="text-lg font-semibold text-cyan-400">Git Activity Log</h3>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-2 font-mono text-sm">
          {logs.length === 0 ? (
            <div className="text-center py-12 text-slate-500">
              <Terminal className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Git activity will appear here</p>
            </div>
          ) : (
            logs.map((log, idx) => (
              <div key={idx} className="p-2 bg-black/30 border border-cyan-900/20 rounded text-cyan-100">
                <span className="text-cyan-500">$ </span>{log}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default GitIntegration;