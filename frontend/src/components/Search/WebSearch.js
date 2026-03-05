import React, { useState } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Search, ExternalLink, Loader2 } from 'lucide-react';

const WebSearch = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    if (!query.trim() || loading) return;

    setLoading(true);
    try {
      const response = await axiosInstance.post('/search/web', {
        query: query,
        max_results: 10
      });
      setResults(response.data);
      if (response.data.length === 0) {
        toast.info('No results found');
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
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="web-search">
      {/* Search Header */}
      <div className="p-6 border-b border-cyan-500/20 bg-black/40">
        <h2 className="text-2xl font-bold text-cyan-400 uppercase mb-6" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
          WEB SEARCH
        </h2>
        
        <div className="flex gap-4">
          <input
            data-testid="search-input"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Enter search query..."
            className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono p-4 outline-none"
            disabled={loading}
          />
          <button
            data-testid="search-btn"
            onClick={handleSearch}
            disabled={loading || !query.trim()}
            className="px-8 bg-cyan-500 text-black font-bold hover:bg-cyan-400 hover:shadow-[0_0_20px_rgba(0,243,255,0.5)] uppercase tracking-wider rounded-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Search className="w-5 h-5" />
            )}
            SEARCH
          </button>
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto p-6" data-testid="search-results">
        {results.length === 0 && !loading && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <Search className="w-16 h-16 mx-auto text-cyan-500/30" />
              <p className="text-slate-400 font-mono text-sm">Enter a query to search the web</p>
            </div>
          </div>
        )}

        <div className="space-y-4 max-w-4xl">
          {results.map((result, idx) => (
            <div
              key={idx}
              data-testid={`search-result-${idx}`}
              className="p-6 bg-black/40 border border-cyan-900/30 rounded-lg backdrop-blur-sm hover:border-cyan-500/50 transition-colors"
            >
              <a
                href={result.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group"
              >
                <h3 className="text-lg font-semibold text-cyan-400 group-hover:text-cyan-300 mb-2 flex items-center gap-2">
                  {result.title}
                  <ExternalLink className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity" />
                </h3>
                <p className="text-xs text-cyan-500/70 font-mono mb-3">{result.url}</p>
                <p className="text-slate-300 text-sm">{result.body}</p>
              </a>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default WebSearch;