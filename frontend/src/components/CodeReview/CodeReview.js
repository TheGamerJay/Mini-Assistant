import React, { useState } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Shield, Loader2, AlertTriangle, CheckCircle, XCircle, Zap } from 'lucide-react';
import { usePersist } from '../../hooks/usePersist';

const detectLanguage = (code) => {
  const c = code.trim();
  if (!c) return null;
  if (/^<!DOCTYPE|^<html/i.test(c)) return 'html';
  if (/^\s*[.#][\w-]+\s*\{|:\s*(margin|padding|color|font|display)\s*:/m.test(c)) return 'css';
  if (/\bimport\s+React|jsx|<[A-Z][A-Za-z]+|className=/.test(c)) return 'jsx';
  if (/:\s*(string|number|boolean|any)\b|interface\s+\w+\s*\{|<[A-Z]\w*>/.test(c)) return 'typescript';
  if (/^def |^class |^import |^from |^\s*print\(|^if __name__|^\s*elif /.test(c) || /\bdef\s+\w+\s*\(/.test(c)) return 'python';
  if (/\bconsole\.\w+|require\(|module\.exports|process\.env/.test(c)) return 'javascript';
  if (/\bconst |let |var |=>\s*\{|function\s+\w+/.test(c)) return 'javascript';
  return null;
};

const CodeReview = () => {
  const [code, setCode] = usePersist('ma_codereview_code', '');
  const [language, setLanguage] = usePersist('ma_codereview_lang', 'javascript');
  const [autoDetected, setAutoDetected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [fixedCode, setFixedCode] = useState('');

  const handleCodeChange = (e) => {
    const val = e.target.value;
    setCode(val);
    const detected = detectLanguage(val);
    if (detected) {
      setLanguage(detected);
      setAutoDetected(true);
    } else {
      setAutoDetected(false);
    }
  };

  const analyzeCode = async () => {
    if (!code.trim() || loading) return;

    setLoading(true);
    try {
      const response = await axiosInstance.post('/code-review/analyze', {
        code: code,
        language: language
      });

      setAnalysis(response.data.analysis);
      setFixedCode(response.data.fixed_code || '');
      toast.success('Code analysis complete!');
    } catch (error) {
      if (error.response?.status !== 402) {
        toast.error(error.response?.data?.detail || 'Analysis failed');
      }
    } finally {
      setLoading(false);
    }
  };

  const applyFix = () => {
    if (fixedCode) {
      setCode(fixedCode);
      toast.success('Fixed code applied!');
    }
  };

  const getIssueIcon = (severity) => {
    switch (severity) {
      case 'error':
        return <XCircle className="w-5 h-5 text-red-400" />;
      case 'warning':
        return <AlertTriangle className="w-5 h-5 text-yellow-400" />;
      default:
        return <CheckCircle className="w-5 h-5 text-green-400" />;
    }
  };

  return (
    <div className="h-full flex" data-testid="code-review">
      {/* Left Panel - Code Input */}
      <div className="w-1/2 border-r border-cyan-500/20 flex flex-col bg-black/20">
        <div className="p-4 border-b border-cyan-500/20 bg-black/40">
          <div className="flex items-center gap-3 mb-4">
            <Shield className="w-6 h-6 text-cyan-400" />
            <h2 className="text-xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
              CODE REVIEW & FIX
            </h2>
          </div>
          
          <div className="flex gap-4 items-center">
            <div className="flex flex-col gap-1">
              <select
                data-testid="language-select"
                value={language}
                onChange={(e) => { setLanguage(e.target.value); setAutoDetected(false); }}
                className="bg-black/50 border border-cyan-500/50 text-cyan-100 px-4 py-2 rounded-sm font-mono text-sm focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 outline-none"
              >
                <option value="javascript">JavaScript</option>
                <option value="python">Python</option>
                <option value="typescript">TypeScript</option>
                <option value="jsx">React/JSX</option>
                <option value="html">HTML</option>
                <option value="css">CSS</option>
              </select>
              {autoDetected && (
                <span className="text-xs text-cyan-400 font-mono text-center">AUTO-DETECTED</span>
              )}
            </div>
            
            <button
              data-testid="analyze-code-btn"
              onClick={analyzeCode}
              disabled={loading || !code.trim()}
              className="flex-1 px-6 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-sm flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  ANALYZING...
                </>
              ) : (
                <>
                  <Shield className="w-4 h-4" />
                  ANALYZE & FIX
                </>
              )}
            </button>
          </div>
        </div>

        <div className="flex-1 p-4">
          <textarea
            data-testid="code-input"
            value={code}
            onChange={handleCodeChange}
            placeholder="Paste your code here — language will be auto-detected..."
            className="w-full h-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono text-sm p-4 outline-none resize-none"
            disabled={loading}
          />
        </div>
      </div>

      {/* Right Panel - Analysis Results */}
      <div className="w-1/2 flex flex-col bg-[#0a0a0f]/50">
        {analysis ? (
          <>
            <div className="p-4 border-b border-cyan-500/20 bg-black/40 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-cyan-400">Analysis Results</h3>
              {fixedCode && (
                <button
                  data-testid="apply-fix-btn"
                  onClick={applyFix}
                  className="px-4 py-2 bg-green-500/20 text-green-400 border border-green-500/50 hover:bg-green-500/30 rounded-sm text-sm font-semibold uppercase flex items-center gap-2"
                >
                  <Zap className="w-4 h-4" />
                  APPLY FIX
                </button>
              )}
            </div>

            <div className="flex-1 overflow-auto p-6 space-y-4">
              {/* Issues */}
              {analysis.issues?.map((issue, idx) => (
                <div
                  key={idx}
                  className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg"
                >
                  <div className="flex items-start gap-3 mb-2">
                    {getIssueIcon(issue.severity)}
                    <div className="flex-1">
                      <div className="text-sm font-semibold text-slate-200">{issue.title}</div>
                      <div className="text-xs text-slate-400 mt-1">{issue.description}</div>
                      {issue.line && (
                        <div className="text-xs text-cyan-500 mt-1">Line {issue.line}</div>
                      )}
                    </div>
                  </div>
                  {issue.suggestion && (
                    <div className="mt-3 p-3 bg-cyan-500/10 border border-cyan-500/30 rounded">
                      <div className="text-xs text-cyan-400 font-mono">Suggestion:</div>
                      <div className="text-sm text-slate-300 mt-1">{issue.suggestion}</div>
                    </div>
                  )}
                </div>
              ))}

              {/* Fixed Code */}
              {fixedCode && (
                <div className="p-4 bg-black/40 border border-green-500/30 rounded-lg">
                  <div className="flex items-center gap-2 mb-3">
                    <CheckCircle className="w-5 h-5 text-green-400" />
                    <div className="text-sm font-semibold text-green-400">FIXED CODE</div>
                  </div>
                  <pre className="text-slate-300 text-sm bg-black/30 p-4 rounded border border-cyan-900/20 overflow-auto">
                    {fixedCode}
                  </pre>
                </div>
              )}

              {/* Summary */}
              <div className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg">
                <div className="text-sm font-semibold text-cyan-400 mb-2">Summary</div>
                <div className="text-sm text-slate-300">{analysis.summary}</div>
              </div>
            </div>
          </>
        ) : (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <Shield className="w-16 h-16 mx-auto text-cyan-500/30" />
              <p className="text-slate-400 font-mono text-sm">Paste code to analyze and fix issues</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default CodeReview;