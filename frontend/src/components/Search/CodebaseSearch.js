import React, { useState } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Code, Search, Loader2, FileCode } from 'lucide-react';

const CodebaseSearch = () => {
  const [query, setQuery] = useState('');
  const [path, setPath] = useState('/app');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    if (!query.trim() || loading) return;

    setLoading(true);
    try {
      const response = await axiosInstance.post('/search/codebase', {
        query: query,
        path: path,
        max_results: 20
      });
      setResults(response.data.results);
      if (response.data.results.length === 0) {
        toast.info('No matches found');
      }
    } catch (error) {
      toast.error('Search error occurred');
      console.error('Search error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="codebase-search">
      {/* Search Header */}
      <div className="p-6 border-b border-cyan-500/20 bg-black/40">
        <h2 className="text-2xl font-bold text-cyan-400 uppercase mb-6" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
          CODEBASE SEARCH
        </h2>
        
        <div className="space-y-4">
          <div className="flex gap-4">
            <input
              data-testid="code-search-input"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Search code pattern or text..."
              className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono p-4 outline-none"
              disabled={loading}
            />
            <button
              data-testid="code-search-btn"
              onClick={handleSearch}
              disabled={loading || !query.trim()}
              className="px-8 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 hover:shadow-[0_0_20px_rgba(0,243,255,0.5),0_0_15px_rgba(147,51,234,0.3)] uppercase tracking-wider rounded-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {loading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Search className="w-5 h-5" />
              )}
              SEARCH
            </button>
          </div>
          
          <input
            data-testid="search-path-input"
            type="text"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="Search path..."
            className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono px-4 py-2 outline-none"
          />
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto p-6" data-testid="code-search-results">
        {results.length === 0 && !loading && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <Code className="w-16 h-16 mx-auto text-cyan-500/30" />
              <p className="text-slate-400 font-mono text-sm">Search your codebase for patterns</p>
            </div>
          </div>
        )}

        <div className="space-y-3 max-w-6xl">
          {results.map((result, idx) => (
            <div
              key={idx}
              data-testid={`code-result-${idx}`}
              className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg backdrop-blur-sm hover:border-cyan-500/50 transition-colors"
            >
              <div className="flex items-center gap-3 mb-2">
                <FileCode className="w-4 h-4 text-cyan-400" />
                <span className="text-sm font-mono text-cyan-400">{result.file}</span>
                <span className="text-xs text-slate-500">Line {result.line}</span>
              </div>
              <pre className="text-slate-300 text-sm font-mono bg-black/30 p-3 rounded border border-cyan-900/20 overflow-x-auto">
                {result.content}
              </pre>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default CodebaseSearch;