import React, { useState, useEffect } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Code, Plus, Trash2, Copy, Search, Tag } from 'lucide-react';

const SnippetLibrary = () => {
  const [snippets, setSnippets] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [newSnippet, setNewSnippet] = useState({ title: '', code: '', language: 'javascript', tags: '' });
  const [searchQuery, setSearchQuery] = useState('');
  const [filterLang, setFilterLang] = useState('all');

  useEffect(() => {
    loadSnippets();
  }, []);

  const loadSnippets = async () => {
    try {
      const response = await axiosInstance.get('/snippets/list');
      setSnippets(response.data.snippets || []);
    } catch (error) {
      console.error('Load snippets error:', error);
    }
  };

  const addSnippet = async () => {
    if (!newSnippet.title.trim() || !newSnippet.code.trim()) {
      toast.error('Title and code are required');
      return;
    }

    try {
      await axiosInstance.post('/snippets/create', newSnippet);
      toast.success('Snippet saved!');
      setNewSnippet({ title: '', code: '', language: 'javascript', tags: '' });
      setShowAdd(false);
      loadSnippets();
    } catch (error) {
      toast.error('Failed to save snippet');
    }
  };

  const deleteSnippet = async (id) => {
    try {
      await axiosInstance.delete(`/snippets/delete/${id}`);
      toast.success('Snippet deleted');
      loadSnippets();
    } catch (error) {
      toast.error('Failed to delete snippet');
    }
  };

  const copySnippet = (code) => {
    navigator.clipboard.writeText(code);
    toast.success('Copied to clipboard!');
  };

  const filteredSnippets = snippets.filter(s => {
    const matchesSearch = s.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         s.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         s.tags?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesLang = filterLang === 'all' || s.language === filterLang;
    return matchesSearch && matchesLang;
  });

  const languages = ['javascript', 'python', 'typescript', 'jsx', 'html', 'css', 'sql', 'bash'];

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="snippet-library">
      <div className="p-6 border-b border-cyan-500/20 bg-black/40">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Code className="w-7 h-7 text-cyan-400" />
            <div>
              <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
                SNIPPET LIBRARY
              </h2>
              <p className="text-xs text-slate-400 font-mono mt-1">SAVE & REUSE CODE SNIPPETS</p>
            </div>
          </div>
          <button
            onClick={() => setShowAdd(true)}
            className="px-6 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-sm flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            NEW SNIPPET
          </button>
        </div>

        <div className="flex gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-cyan-500/50" />
            <input
              placeholder="Search snippets..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 rounded-sm font-mono pl-10 pr-4 py-2 outline-none text-sm"
            />
          </div>
          <select
            value={filterLang}
            onChange={(e) => setFilterLang(e.target.value)}
            className="bg-black/50 border border-cyan-500/50 text-cyan-100 px-4 py-2 rounded-sm font-mono text-sm"
          >
            <option value="all">All Languages</option>
            {languages.map(lang => (
              <option key={lang} value={lang}>{lang.toUpperCase()}</option>
            ))}
          </select>
        </div>
      </div>

      {showAdd && (
        <div className="p-6 border-b border-cyan-500/20 bg-black/30">
          <h3 className="text-lg font-semibold text-cyan-400 mb-4">New Snippet</h3>
          <div className="space-y-3">
            <input
              placeholder="Snippet title"
              value={newSnippet.title}
              onChange={(e) => setNewSnippet({ ...newSnippet, title: e.target.value })}
              className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono px-4 py-2 outline-none"
            />
            <select
              value={newSnippet.language}
              onChange={(e) => setNewSnippet({ ...newSnippet, language: e.target.value })}
              className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono px-4 py-2 outline-none"
            >
              {languages.map(lang => (
                <option key={lang} value={lang}>{lang}</option>
              ))}
            </select>
            <input
              placeholder="Tags (comma separated)"
              value={newSnippet.tags}
              onChange={(e) => setNewSnippet({ ...newSnippet, tags: e.target.value })}
              className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono px-4 py-2 outline-none"
            />
            <textarea
              placeholder="Code..."
              value={newSnippet.code}
              onChange={(e) => setNewSnippet({ ...newSnippet, code: e.target.value })}
              className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono p-4 outline-none resize-none"
              rows={8}
            />
            <div className="flex gap-3">
              <button
                onClick={addSnippet}
                className="px-6 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase"
              >
                SAVE
              </button>
              <button
                onClick={() => setShowAdd(false)}
                className="px-6 py-2 bg-slate-700 text-white hover:bg-slate-600 rounded-sm uppercase"
              >
                CANCEL
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-auto p-6">
        {filteredSnippets.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <Code className="w-16 h-16 mx-auto text-cyan-500/30" />
              <p className="text-slate-400 font-mono text-sm">No snippets found. Create your first snippet!</p>
            </div>
          </div>
        ) : (
          <div className="grid gap-4">
            {filteredSnippets.map((snippet) => (
              <div key={snippet.id} className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-cyan-400">{snippet.title}</h3>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-violet-400 font-mono uppercase">{snippet.language}</span>
                      {snippet.tags && (
                        <div className="flex items-center gap-1">
                          <Tag className="w-3 h-3 text-slate-500" />
                          <span className="text-xs text-slate-500">{snippet.tags}</span>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => copySnippet(snippet.code)}
                      className="p-2 text-cyan-400 hover:text-cyan-300 transition-colors"
                    >
                      <Copy className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => deleteSnippet(snippet.id)}
                      className="p-2 text-slate-400 hover:text-red-400 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                <pre className="text-sm text-slate-300 bg-black/30 p-4 rounded border border-cyan-900/20 overflow-auto font-mono">
                  {snippet.code}
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default SnippetLibrary;