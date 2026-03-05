import React, { useState } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { FileText, Loader2, Download, BookOpen } from 'lucide-react';

const DocGenerator = () => {
  const [code, setCode] = useState('');
  const [language, setLanguage] = useState('javascript');
  const [docType, setDocType] = useState('readme');
  const [loading, setLoading] = useState(false);
  const [generatedDocs, setGeneratedDocs] = useState('');

  const docTypes = ['readme', 'api', 'jsdoc', 'docstring', 'swagger'];

  const generateDocs = async () => {
    if (!code.trim() || loading) return;

    setLoading(true);
    try {
      const response = await axiosInstance.post('/doc-generator/generate', {
        code,
        language,
        docType
      });

      setGeneratedDocs(response.data.documentation);
      toast.success('Documentation generated!');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to generate docs');
    } finally {
      setLoading(false);
    }
  };

  const downloadDocs = () => {
    const ext = docType === 'readme' ? 'md' : docType === 'swagger' ? 'yaml' : 'txt';
    const blob = new Blob([generatedDocs], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `documentation.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Documentation downloaded!');
  };

  return (
    <div className="h-full flex" data-testid="doc-generator">
      <div className="w-1/2 border-r border-cyan-500/20 flex flex-col bg-black/20">
        <div className="p-6 border-b border-cyan-500/20 bg-black/40">
          <div className="flex items-center gap-3 mb-6">
            <BookOpen className="w-7 h-7 text-cyan-400" />
            <div>
              <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
                DOC GENERATOR
              </h2>
              <p className="text-xs text-slate-400 font-mono mt-1">AUTO-GENERATE DOCUMENTATION</p>
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
              <option value="java">Java</option>
            </select>

            <select
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
              className="bg-black/50 border border-cyan-500/50 text-cyan-100 px-4 py-2 rounded-sm font-mono text-sm"
            >
              {docTypes.map(type => (
                <option key={type} value={type}>{type.toUpperCase()}</option>
              ))}
            </select>

            <button
              onClick={generateDocs}
              disabled={loading || !code.trim()}
              className="flex-1 px-6 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-sm flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
              GENERATE DOCS
            </button>
          </div>
        </div>

        <div className="flex-1 p-4">
          <label className="text-sm text-cyan-400 font-mono uppercase mb-2 block">Your Code</label>
          <textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Paste your code to generate documentation..."
            className="w-full h-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono p-4 outline-none resize-none text-sm"
          />
        </div>
      </div>

      <div className="w-1/2 flex flex-col bg-[#0a0a0f]/50">
        {generatedDocs ? (
          <>
            <div className="p-4 border-b border-cyan-500/20 bg-black/40 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-cyan-400">Generated Documentation</h3>
              <button
                onClick={downloadDocs}
                className="px-4 py-2 bg-violet-500/20 text-violet-400 border border-violet-500/50 hover:bg-violet-500/30 rounded-sm text-sm font-semibold uppercase flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                DOWNLOAD
              </button>
            </div>

            <div className="flex-1 overflow-auto p-6">
              <pre className="text-sm text-slate-300 bg-black/40 p-4 rounded border border-cyan-900/30 font-mono whitespace-pre-wrap">
                {generatedDocs}
              </pre>
            </div>
          </>
        ) : (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <FileText className="w-16 h-16 mx-auto text-cyan-500/30" />
              <p className="text-slate-400 font-mono text-sm">Generate README, API docs, JSDoc, and more</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DocGenerator;