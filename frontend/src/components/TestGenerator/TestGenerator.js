import React, { useState } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { TestTube, Loader2, Download, Code, CheckCircle } from 'lucide-react';

const TestGenerator = () => {
  const [code, setCode] = useState('');
  const [language, setLanguage] = useState('javascript');
  const [framework, setFramework] = useState('jest');
  const [loading, setLoading] = useState(false);
  const [generatedTests, setGeneratedTests] = useState('');
  const [coverage, setCoverage] = useState(null);

  const frameworks = {
    javascript: ['jest', 'mocha', 'vitest'],
    python: ['pytest', 'unittest', 'nose'],
    typescript: ['jest', 'vitest']
  };

  const generateTests = async () => {
    if (!code.trim() || loading) return;

    setLoading(true);
    try {
      const response = await axiosInstance.post('/test-generator/generate', {
        code,
        language,
        framework
      });

      setGeneratedTests(response.data.tests);
      setCoverage(response.data.coverage);
      toast.success('Tests generated successfully!');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to generate tests');
    } finally {
      setLoading(false);
    }
  };

  const downloadTests = () => {
    const blob = new Blob([generatedTests], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `test.${language === 'python' ? 'py' : 'js'}`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Test file downloaded!');
  };

  return (
    <div className="h-full flex" data-testid="test-generator">
      <div className="w-1/2 border-r border-cyan-500/20 flex flex-col bg-black/20">
        <div className="p-6 border-b border-cyan-500/20 bg-black/40">
          <div className="flex items-center gap-3 mb-6">
            <TestTube className="w-7 h-7 text-cyan-400" />
            <div>
              <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
                TEST GENERATOR
              </h2>
              <p className="text-xs text-slate-400 font-mono mt-1">AI-POWERED UNIT TEST CREATION</p>
            </div>
          </div>

          <div className="flex gap-3 mb-4">
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="bg-black/50 border border-cyan-500/50 text-cyan-100 px-4 py-2 rounded-sm font-mono text-sm"
            >
              <option value="javascript">JavaScript</option>
              <option value="typescript">TypeScript</option>
              <option value="python">Python</option>
            </select>

            <select
              value={framework}
              onChange={(e) => setFramework(e.target.value)}
              className="bg-black/50 border border-cyan-500/50 text-cyan-100 px-4 py-2 rounded-sm font-mono text-sm"
            >
              {frameworks[language].map(f => (
                <option key={f} value={f}>{f.toUpperCase()}</option>
              ))}
            </select>

            <button
              onClick={generateTests}
              disabled={loading || !code.trim()}
              className="flex-1 px-6 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-sm flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <TestTube className="w-4 h-4" />}
              GENERATE TESTS
            </button>
          </div>
        </div>

        <div className="flex-1 p-4">
          <label className="text-sm text-cyan-400 font-mono uppercase mb-2 block">Your Code</label>
          <textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Paste your code here to generate tests..."
            className="w-full h-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono p-4 outline-none resize-none text-sm"
          />
        </div>
      </div>

      <div className="w-1/2 flex flex-col bg-[#0a0a0f]/50">
        {generatedTests ? (
          <>
            <div className="p-4 border-b border-cyan-500/20 bg-black/40 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-cyan-400">Generated Tests</h3>
                {coverage && (
                  <div className="flex gap-4 mt-2 text-xs">
                    <span className="text-green-400">Coverage: {coverage.percentage}%</span>
                    <span className="text-cyan-400">Tests: {coverage.count}</span>
                  </div>
                )}
              </div>
              <button
                onClick={downloadTests}
                className="px-4 py-2 bg-violet-500/20 text-violet-400 border border-violet-500/50 hover:bg-violet-500/30 rounded-sm text-sm font-semibold uppercase flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                DOWNLOAD
              </button>
            </div>

            <div className="flex-1 overflow-auto p-6">
              <pre className="text-sm text-slate-300 bg-black/40 p-4 rounded border border-cyan-900/30 font-mono">
                {generatedTests}
              </pre>

              {coverage?.untested?.length > 0 && (
                <div className="mt-4 p-4 bg-yellow-500/10 border border-yellow-500/30 rounded">
                  <div className="text-sm font-semibold text-yellow-400 mb-2">Untested Functions:</div>
                  <ul className="text-xs text-yellow-300 space-y-1">
                    {coverage.untested.map((fn, idx) => (
                      <li key={idx}>• {fn}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <TestTube className="w-16 h-16 mx-auto text-cyan-500/30" />
              <p className="text-slate-400 font-mono text-sm">Paste code and generate comprehensive tests</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default TestGenerator;