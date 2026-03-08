import React, { useState } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Send, Loader2, Plus, Trash2, Copy, Check } from 'lucide-react';
import { usePersist } from '../../hooks/usePersist';

const APITester = () => {
  const [url, setUrl] = usePersist('ma_apitester_url', '');
  const [method, setMethod] = usePersist('ma_apitester_method', 'GET');
  const [headers, setHeaders] = usePersist('ma_apitester_headers', [{ key: 'Content-Type', value: 'application/json' }]);
  const [body, setBody] = usePersist('ma_apitester_body', '');
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = usePersist('ma_apitester_history', []);
  const [copied, setCopied] = useState(false);

  const testAPI = async () => {
    if (!url.trim() || loading) return;

    setLoading(true);
    setResponse(null);
    try {
      const headersObj = {};
      headers.forEach(h => {
        if (h.key.trim()) headersObj[h.key] = h.value;
      });

      const res = await axiosInstance.post('/api-tester/request', {
        url: url,
        method: method,
        headers: headersObj,
        body: body || null
      });

      setResponse(res.data);
      
      setHistory(prev => [{
        method,
        url: url.substring(0, 50),
        status: res.data.status,
        timestamp: new Date().toLocaleTimeString()
      }, ...prev.slice(0, 9)]);

      if (res.data.status < 400) {
        toast.success(`${method} request successful`);
      } else {
        toast.error(`Request failed with status ${res.data.status}`);
      }
    } catch (error) {
      const errorResponse = {
        status: error.response?.status || 0,
        error: error.response?.data?.detail || error.message || 'Request failed',
        headers: {},
        data: null
      };
      setResponse(errorResponse);
      toast.error('Request failed');
      console.error('API test error:', error);
    } finally {
      setLoading(false);
    }
  };

  const addHeader = () => {
    setHeaders([...headers, { key: '', value: '' }]);
  };

  const removeHeader = (index) => {
    setHeaders(headers.filter((_, i) => i !== index));
  };

  const updateHeader = (index, field, value) => {
    const newHeaders = [...headers];
    newHeaders[index][field] = value;
    setHeaders(newHeaders);
  };

  const copyResponse = () => {
    if (response?.data) {
      navigator.clipboard.writeText(JSON.stringify(response.data, null, 2));
      setCopied(true);
      toast.success('Response copied!');
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const quickMethods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];

  return (
    <div className="h-full flex" data-testid="api-tester">
      {/* Left Panel - Request */}
      <div className="w-1/2 border-r border-cyan-500/20 flex flex-col bg-black/20">
        <div className="p-6 border-b border-cyan-500/20 bg-black/40">
          <div className="flex items-center gap-3 mb-6">
            <Send className="w-7 h-7 text-cyan-400" />
            <div>
              <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
                API TESTER
              </h2>
              <p className="text-xs text-slate-400 font-mono mt-1">TEST REST APIs LIKE POSTMAN</p>
            </div>
          </div>

          {/* Method & URL */}
          <div className="flex gap-3 mb-6">
            <div className="flex gap-1">
              {quickMethods.map(m => (
                <button
                  key={m}
                  onClick={() => setMethod(m)}
                  className={`px-3 py-2 rounded-sm text-xs font-bold transition-all ${
                    method === m
                      ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                      : 'bg-black/30 text-slate-400 border border-transparent hover:text-cyan-400'
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>

          <div className="flex gap-3 mb-6">
            <input
              data-testid="api-url-input"
              type="text"
              placeholder="https://api.example.com/endpoint"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono px-4 py-3 outline-none text-sm"
            />
            <button
              data-testid="send-request-btn"
              onClick={testAPI}
              disabled={loading || !url.trim()}
              className="px-8 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              SEND
            </button>
          </div>

          {/* Headers */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm text-cyan-400 font-mono uppercase">Headers</div>
              <button
                onClick={addHeader}
                className="text-xs text-violet-400 hover:text-violet-300 flex items-center gap-1"
              >
                <Plus className="w-3 h-3" /> ADD
              </button>
            </div>
            <div className="space-y-2">
              {headers.map((header, idx) => (
                <div key={idx} className="flex gap-2">
                  <input
                    placeholder="Key"
                    value={header.key}
                    onChange={(e) => updateHeader(idx, 'key', e.target.value)}
                    className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 rounded-sm font-mono px-3 py-2 outline-none text-xs"
                  />
                  <input
                    placeholder="Value"
                    value={header.value}
                    onChange={(e) => updateHeader(idx, 'value', e.target.value)}
                    className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 rounded-sm font-mono px-3 py-2 outline-none text-xs"
                  />
                  <button
                    onClick={() => removeHeader(idx)}
                    className="p-2 text-slate-400 hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Body */}
          {['POST', 'PUT', 'PATCH'].includes(method) && (
            <div>
              <div className="text-sm text-cyan-400 font-mono uppercase mb-2">Request Body (JSON)</div>
              <textarea
                data-testid="api-body-input"
                placeholder='{\n  "key": "value"\n}'
                value={body}
                onChange={(e) => setBody(e.target.value)}
                className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono p-3 outline-none resize-none text-sm"
                rows={6}
              />
            </div>
          )}
        </div>
      </div>

      {/* Right Panel - Response */}
      <div className="w-1/2 flex flex-col bg-[#0a0a0f]/50">
        {response ? (
          <>
            <div className="p-4 border-b border-cyan-500/20 bg-black/40 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="text-lg font-semibold text-cyan-400">Response</div>
                <div className={`px-3 py-1 rounded-sm text-xs font-bold ${
                  response.status < 300 ? 'bg-green-500/20 text-green-400' :
                  response.status < 400 ? 'bg-yellow-500/20 text-yellow-400' :
                  'bg-red-500/20 text-red-400'
                }`}>
                  {response.status}
                </div>
              </div>
              <button
                onClick={copyResponse}
                className="px-3 py-1.5 bg-violet-500/20 text-violet-400 border border-violet-500/50 hover:bg-violet-500/30 rounded-sm text-xs font-semibold uppercase flex items-center gap-2"
              >
                {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                {copied ? 'COPIED' : 'COPY'}
              </button>
            </div>

            <div className="flex-1 overflow-auto p-6 space-y-4">
              {/* Response Headers */}
              {response.headers && Object.keys(response.headers).length > 0 && (
                <div>
                  <div className="text-sm text-cyan-400 font-mono uppercase mb-2">Headers</div>
                  <div className="p-3 bg-black/40 border border-cyan-900/30 rounded-lg">
                    <pre className="text-xs text-slate-300 font-mono">
                      {JSON.stringify(response.headers, null, 2)}
                    </pre>
                  </div>
                </div>
              )}

              {/* Response Body */}
              <div>
                <div className="text-sm text-cyan-400 font-mono uppercase mb-2">Body</div>
                <div className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg">
                  <pre className="text-sm text-slate-300 font-mono overflow-auto" data-testid="api-response">
                    {response.data ? JSON.stringify(response.data, null, 2) : response.error || 'No data'}
                  </pre>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <Send className="w-16 h-16 mx-auto text-cyan-500/30" />
              <p className="text-slate-400 font-mono text-sm">Send a request to see response</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default APITester;