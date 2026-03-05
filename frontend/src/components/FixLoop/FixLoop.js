import React, { useState, useEffect } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Bug, Camera, Wrench, Play, Loader2, AlertTriangle, CheckCircle, XCircle, RefreshCw, History, Image, ZoomIn, X } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const FixLoop = () => {
  const [url, setUrl] = useState('');
  const [errorDescription, setErrorDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [showScreenshot, setShowScreenshot] = useState(false);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    try {
      const response = await axiosInstance.get('/fixloop/sessions');
      setSessions(response.data.sessions || []);
    } catch (error) {
      console.error('Failed to load history');
    }
  };

  const startFixLoop = async () => {
    if (!url.trim()) {
      toast.error('Enter a URL to analyze');
      return;
    }
    
    setLoading(true);
    setResult(null);
    
    try {
      const response = await axiosInstance.post('/fixloop/start', {
        url: url,
        error_description: errorDescription,
        auto_fix: true,
        capture_screenshot: true
      });
      
      setResult(response.data);
      loadHistory();
      
      if (response.data.errors?.length > 0) {
        toast.warning(`Found ${response.data.errors.length} error(s)`);
      } else {
        toast.success('No errors detected!');
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case 'critical': return <XCircle className="w-5 h-5 text-red-400" />;
      case 'high': return <AlertTriangle className="w-5 h-5 text-orange-400" />;
      case 'medium': return <AlertTriangle className="w-5 h-5 text-yellow-400" />;
      default: return <Bug className="w-5 h-5 text-blue-400" />;
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'critical': return 'bg-red-500/10 border-red-500/30 text-red-400';
      case 'high': return 'bg-orange-500/10 border-orange-500/30 text-orange-400';
      case 'medium': return 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400';
      default: return 'bg-blue-500/10 border-blue-500/30 text-blue-400';
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="fix-loop">
      <div className="p-6 border-b border-cyan-500/20 bg-black/40">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Bug className="w-7 h-7 text-green-400" />
            <div>
              <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-green-400 to-emerald-400 bg-clip-text uppercase">
                FixLoop
              </h2>
              <p className="text-xs text-slate-400 font-mono mt-1">AUTO ERROR DETECTION & FIX</p>
            </div>
          </div>
          <button
            onClick={() => setShowHistory(!showHistory)}
            className={`px-3 py-2 rounded-sm text-sm font-semibold uppercase flex items-center gap-2 transition-all ${
              showHistory 
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50' 
                : 'text-slate-400 hover:text-cyan-400'
            }`}
          >
            <History className="w-4 h-4" />
            History
          </button>
        </div>

        <div className="space-y-3">
          <div className="flex gap-3">
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Enter URL to analyze (e.g., http://localhost:3000)"
              className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono px-4 py-3 outline-none"
            />
            <button
              onClick={startFixLoop}
              disabled={loading}
              className="px-6 py-2 bg-gradient-to-r from-green-500 to-emerald-600 text-white font-bold rounded-sm uppercase flex items-center gap-2 disabled:opacity-50 hover:shadow-[0_0_20px_rgba(34,197,94,0.5)]"
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Analyzing...
                </>
              ) : (
                <>
                  <Camera className="w-5 h-5" />
                  Scan & Fix
                </>
              )}
            </button>
          </div>
          
          <textarea
            value={errorDescription}
            onChange={(e) => setErrorDescription(e.target.value)}
            placeholder="Describe the error you're seeing (optional - helps AI generate better fixes)"
            className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono px-4 py-3 outline-none resize-none"
            rows={2}
          />
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {showHistory ? (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-cyan-400 uppercase flex items-center gap-2">
              <History className="w-5 h-5" />
              Previous Sessions
            </h3>
            {sessions.length === 0 ? (
              <div className="text-center py-12 text-slate-500">
                <History className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p className="text-sm">No previous sessions</p>
              </div>
            ) : (
              <div className="space-y-3">
                {sessions.map((session) => (
                  <div
                    key={session.id}
                    className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono text-cyan-400 text-sm">{session.url}</span>
                      <span className="text-xs text-slate-500">
                        {new Date(session.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className={`text-xs px-2 py-1 rounded ${
                        session.errors?.length > 0 
                          ? 'bg-red-500/20 text-red-400' 
                          : 'bg-green-500/20 text-green-400'
                      }`}>
                        {session.errors?.length || 0} errors
                      </span>
                      <span className="text-xs text-slate-500">{session.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : result ? (
          <div className="space-y-6">
            {/* Screenshot */}
            {result.screenshot && (
              <div>
                <h3 className="text-lg font-semibold text-cyan-400 uppercase flex items-center gap-2 mb-4">
                  <Camera className="w-5 h-5" />
                  Page Screenshot
                </h3>
                <div className="relative group">
                  <img 
                    src={`${API_URL}${result.screenshot.url}`}
                    alt="Page screenshot"
                    className="w-full rounded-lg border border-cyan-500/30 cursor-pointer hover:border-cyan-500/50 transition-all"
                    onClick={() => setShowScreenshot(true)}
                  />
                  <button
                    onClick={() => setShowScreenshot(true)}
                    className="absolute top-4 right-4 p-2 bg-black/70 text-cyan-400 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <ZoomIn className="w-5 h-5" />
                  </button>
                </div>
              </div>
            )}

            {/* Errors Found */}
            <div>
              <h3 className="text-lg font-semibold text-cyan-400 uppercase flex items-center gap-2 mb-4">
                <AlertTriangle className="w-5 h-5" />
                Errors Detected ({result.errors?.length || 0})
              </h3>
              
              {result.errors?.length === 0 ? (
                <div className="p-6 bg-green-500/10 border border-green-500/30 rounded-lg text-center">
                  <CheckCircle className="w-12 h-12 text-green-400 mx-auto mb-3" />
                  <p className="text-green-400 font-semibold">No errors detected!</p>
                  <p className="text-slate-400 text-sm mt-1">The URL appears to be working correctly.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {result.errors.map((error, idx) => (
                    <div
                      key={idx}
                      className={`p-4 rounded-lg border ${getSeverityColor(error.severity)}`}
                    >
                      <div className="flex items-start gap-3">
                        {getSeverityIcon(error.severity)}
                        <div className="flex-1">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold">{error.type}</span>
                            <span className="text-xs uppercase px-2 py-1 bg-black/30 rounded">
                              {error.severity}
                            </span>
                          </div>
                          <p className="text-sm mt-1 opacity-90">
                            {error.message || error.pattern}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* AI Suggested Fixes */}
            {result.suggested_fixes?.length > 0 && (
              <div>
                <h3 className="text-lg font-semibold text-violet-400 uppercase flex items-center gap-2 mb-4">
                  <Wrench className="w-5 h-5" />
                  AI Suggested Fixes
                </h3>
                <div className="space-y-3">
                  {result.suggested_fixes.map((fix, idx) => (
                    <div
                      key={idx}
                      className="p-4 bg-violet-500/10 border border-violet-500/30 rounded-lg"
                    >
                      <div className="prose prose-invert max-w-none">
                        <div className="whitespace-pre-wrap text-sm text-slate-300 font-mono">
                          {fix.suggestion}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Retry Button */}
            <div className="flex justify-center pt-4">
              <button
                onClick={startFixLoop}
                className="px-6 py-2 bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 hover:bg-cyan-500/30 rounded-sm text-sm font-semibold uppercase flex items-center gap-2"
              >
                <RefreshCw className="w-4 h-4" />
                Re-analyze
              </button>
            </div>
          </div>
        ) : (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <div className="w-24 h-24 mx-auto rounded-full bg-green-500/10 border border-green-500/30 flex items-center justify-center">
                <Bug className="w-12 h-12 text-green-400 opacity-50" />
              </div>
              <div>
                <p className="text-slate-400 text-lg">Enter a URL to analyze for errors</p>
                <p className="text-slate-500 text-sm mt-2">
                  FixLoop will detect errors and suggest AI-powered fixes
                </p>
              </div>
              <div className="flex items-center justify-center gap-8 pt-4 text-sm text-slate-500">
                <div className="flex items-center gap-2">
                  <Camera className="w-4 h-4 text-cyan-400" />
                  <span>Screenshots Errors</span>
                </div>
                <div className="flex items-center gap-2">
                  <Bug className="w-4 h-4 text-yellow-400" />
                  <span>Detects Issues</span>
                </div>
                <div className="flex items-center gap-2">
                  <Wrench className="w-4 h-4 text-green-400" />
                  <span>Suggests Fixes</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Screenshot Modal */}
      {showScreenshot && result?.screenshot && (
        <div 
          className="fixed inset-0 bg-black/90 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setShowScreenshot(false)}
        >
          <div className="relative max-w-6xl w-full max-h-[90vh]">
            <button
              onClick={() => setShowScreenshot(false)}
              className="absolute -top-12 right-0 p-2 text-white/70 hover:text-white transition-colors"
            >
              <X className="w-8 h-8" />
            </button>
            <img 
              src={`${API_URL}${result.screenshot.url}`}
              alt="Page screenshot full view"
              className="w-full h-auto rounded-lg border border-cyan-500/30"
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default FixLoop;
