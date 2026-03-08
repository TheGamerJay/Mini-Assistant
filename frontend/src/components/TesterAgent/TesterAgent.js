import React, { useState, useEffect } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { FlaskConical, Play, Plus, Trash2, Loader2, CheckCircle, XCircle, History, Sparkles, FileCode } from 'lucide-react';
import { usePersist } from '../../hooks/usePersist';

const TesterAgent = () => {
  const [url, setUrl] = usePersist('ma_tester_url', '');
  const [testType, setTestType] = usePersist('ma_tester_type', 'smoke');
  const [endpoints, setEndpoints] = usePersist('ma_tester_endpoints', []);
  const [newEndpoint, setNewEndpoint] = useState('');
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [results, setResults] = useState(null);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [generatedTests, setGeneratedTests] = useState('');

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    try {
      const response = await axiosInstance.get('/tester/history');
      setHistory(response.data.test_runs || []);
    } catch (error) {
      console.error('Failed to load history');
    }
  };

  const addEndpoint = () => {
    if (newEndpoint.trim() && !endpoints.includes(newEndpoint.trim())) {
      setEndpoints([...endpoints, newEndpoint.trim()]);
      setNewEndpoint('');
    }
  };

  const removeEndpoint = (ep) => {
    setEndpoints(endpoints.filter(e => e !== ep));
  };

  const runTests = async () => {
    if (!url.trim()) {
      toast.error('Enter a URL to test');
      return;
    }
    
    setLoading(true);
    setResults(null);
    
    try {
      const response = await axiosInstance.post('/tester/run', {
        url: url,
        test_type: testType,
        endpoints: endpoints
      });
      
      setResults(response.data);
      loadHistory();
      
      const { passed, failed } = response.data.summary;
      if (failed === 0) {
        toast.success(`All ${passed} tests passed!`);
      } else {
        toast.warning(`${passed} passed, ${failed} failed`);
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Test run failed');
    } finally {
      setLoading(false);
    }
  };

  const generateTests = async () => {
    if (!url.trim()) {
      toast.error('Enter a URL first');
      return;
    }
    
    setGenerating(true);
    try {
      const response = await axiosInstance.post('/tester/generate', {
        url: url,
        test_type: testType,
        endpoints: endpoints
      });
      setGeneratedTests(response.data.generated_tests);
      toast.success('Test cases generated!');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const testTypes = [
    { id: 'smoke', label: 'Smoke Test', desc: 'Basic availability check' },
    { id: 'api', label: 'API Test', desc: 'Test API endpoints' },
    { id: 'functional', label: 'Functional', desc: 'Feature testing' },
    { id: 'e2e', label: 'End-to-End', desc: 'Full user flow' },
  ];

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="tester-agent">
      <div className="p-6 border-b border-cyan-500/20 bg-black/40">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <FlaskConical className="w-7 h-7 text-blue-400" />
            <div>
              <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text uppercase">
                Tester Agent
              </h2>
              <p className="text-xs text-slate-400 font-mono mt-1">AUTOMATED TESTING</p>
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

        <div className="space-y-4">
          {/* URL Input */}
          <div className="flex gap-3">
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Enter base URL to test (e.g., http://localhost:3000)"
              className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono px-4 py-3 outline-none"
            />
          </div>

          {/* Test Type Selection */}
          <div className="grid grid-cols-4 gap-3">
            {testTypes.map((type) => (
              <button
                key={type.id}
                onClick={() => setTestType(type.id)}
                className={`p-3 rounded-lg border text-left transition-all ${
                  testType === type.id
                    ? 'bg-blue-500/20 border-blue-500/50 text-blue-400'
                    : 'bg-black/40 border-cyan-900/30 text-slate-400 hover:border-blue-500/30'
                }`}
              >
                <div className="font-semibold text-sm">{type.label}</div>
                <div className="text-xs opacity-70 mt-1">{type.desc}</div>
              </button>
            ))}
          </div>

          {/* Endpoints */}
          {(testType === 'api' || testType === 'functional' || testType === 'e2e') && (
            <div>
              <label className="text-xs text-cyan-400 font-mono uppercase mb-2 block">API Endpoints</label>
              <div className="flex gap-2 mb-2">
                <input
                  value={newEndpoint}
                  onChange={(e) => setNewEndpoint(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && addEndpoint()}
                  placeholder="/api/health, /api/users, etc."
                  className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono px-3 py-2 outline-none text-sm"
                />
                <button
                  onClick={addEndpoint}
                  className="px-3 py-2 bg-blue-500/20 text-blue-400 border border-blue-500/50 rounded-sm"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
              {endpoints.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {endpoints.map((ep) => (
                    <span
                      key={ep}
                      className="px-3 py-1 bg-black/40 border border-cyan-900/30 rounded text-sm font-mono text-cyan-400 flex items-center gap-2"
                    >
                      {ep}
                      <button onClick={() => removeEndpoint(ep)} className="text-red-400 hover:text-red-300">
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-3">
            <button
              onClick={runTests}
              disabled={loading}
              className="flex-1 px-6 py-3 bg-gradient-to-r from-blue-500 to-indigo-600 text-white font-bold rounded-sm uppercase flex items-center justify-center gap-2 disabled:opacity-50 hover:shadow-[0_0_20px_rgba(59,130,246,0.5)]"
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Running Tests...
                </>
              ) : (
                <>
                  <Play className="w-5 h-5" />
                  Run Tests
                </>
              )}
            </button>
            <button
              onClick={generateTests}
              disabled={generating}
              className="px-6 py-3 bg-violet-500/20 text-violet-400 border border-violet-500/50 hover:bg-violet-500/30 rounded-sm uppercase flex items-center gap-2 disabled:opacity-50"
            >
              {generating ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Sparkles className="w-5 h-5" />
              )}
              AI Generate
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {showHistory ? (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-cyan-400 uppercase flex items-center gap-2">
              <History className="w-5 h-5" />
              Test Run History
            </h3>
            {history.length === 0 ? (
              <div className="text-center py-12 text-slate-500">
                <History className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p className="text-sm">No test runs yet</p>
              </div>
            ) : (
              <div className="space-y-3">
                {history.map((run) => (
                  <div
                    key={run.id}
                    className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono text-cyan-400 text-sm">{run.url}</span>
                      <span className="text-xs text-slate-500">
                        {new Date(run.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-xs px-2 py-1 bg-blue-500/20 text-blue-400 rounded">
                        {run.test_type}
                      </span>
                      <span className="text-xs text-green-400">
                        {run.summary?.passed || 0} passed
                      </span>
                      <span className="text-xs text-red-400">
                        {run.summary?.failed || 0} failed
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : generatedTests ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-violet-400 uppercase flex items-center gap-2">
                <FileCode className="w-5 h-5" />
                AI Generated Test Cases
              </h3>
              <button
                onClick={() => setGeneratedTests('')}
                className="text-xs text-slate-400 hover:text-white"
              >
                Clear
              </button>
            </div>
            <pre className="bg-black/50 border border-cyan-900/30 rounded-lg p-4 text-sm font-mono text-slate-300 overflow-auto whitespace-pre-wrap">
              {generatedTests}
            </pre>
          </div>
        ) : results ? (
          <div className="space-y-6">
            {/* Summary */}
            <div className="grid grid-cols-3 gap-4">
              <div className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg text-center">
                <div className="text-3xl font-bold text-white">{results.summary.total}</div>
                <div className="text-xs text-slate-400 uppercase mt-1">Total Tests</div>
              </div>
              <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-lg text-center">
                <div className="text-3xl font-bold text-green-400">{results.summary.passed}</div>
                <div className="text-xs text-green-400 uppercase mt-1">Passed</div>
              </div>
              <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-center">
                <div className="text-3xl font-bold text-red-400">{results.summary.failed}</div>
                <div className="text-xs text-red-400 uppercase mt-1">Failed</div>
              </div>
            </div>

            {/* Test Results */}
            <div>
              <h3 className="text-lg font-semibold text-cyan-400 uppercase mb-4">Test Results</h3>
              <div className="space-y-2">
                {results.results.map((test, idx) => (
                  <div
                    key={idx}
                    className={`p-4 rounded-lg border flex items-center justify-between ${
                      test.status === 'PASS'
                        ? 'bg-green-500/10 border-green-500/30'
                        : 'bg-red-500/10 border-red-500/30'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      {test.status === 'PASS' ? (
                        <CheckCircle className="w-5 h-5 text-green-400" />
                      ) : (
                        <XCircle className="w-5 h-5 text-red-400" />
                      )}
                      <div>
                        <div className="font-semibold text-white">{test.name}</div>
                        {test.endpoint && (
                          <div className="text-xs text-slate-400 font-mono">{test.endpoint}</div>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <span className={`text-sm font-semibold ${
                        test.status === 'PASS' ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {test.status}
                      </span>
                      <div className="text-xs text-slate-500">{test.details}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* AI Suggestions */}
            {results.ai_suggestions && (
              <div>
                <h3 className="text-lg font-semibold text-violet-400 uppercase flex items-center gap-2 mb-4">
                  <Sparkles className="w-5 h-5" />
                  AI Test Suggestions
                </h3>
                <div className="p-4 bg-violet-500/10 border border-violet-500/30 rounded-lg">
                  <pre className="text-sm font-mono text-slate-300 whitespace-pre-wrap">
                    {results.ai_suggestions}
                  </pre>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <div className="w-24 h-24 mx-auto rounded-full bg-blue-500/10 border border-blue-500/30 flex items-center justify-center">
                <FlaskConical className="w-12 h-12 text-blue-400 opacity-50" />
              </div>
              <div>
                <p className="text-slate-400 text-lg">Enter a URL to start testing</p>
                <p className="text-slate-500 text-sm mt-2">
                  Run automated tests or let AI generate test cases
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default TesterAgent;
