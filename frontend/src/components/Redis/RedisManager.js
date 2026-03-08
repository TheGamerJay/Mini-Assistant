import React, { useState } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Database, Key, RefreshCw, Trash2, Plus, Loader2, Check, Search } from 'lucide-react';
import { usePersist } from '../../hooks/usePersist';

const RedisManager = () => {
  const [config, setConfig] = usePersist('ma_redis_config', { host: 'localhost', port: 6379, password: '', db: 0 });
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [keys, setKeys] = useState([]);
  const [selectedKey, setSelectedKey] = useState(null);
  const [keyValue, setKeyValue] = useState(null);
  const [searchFilter, setSearchFilter] = useState('');
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);

  const connect = async () => {
    setLoading(true);
    try {
      const response = await axiosInstance.post('/redis/connect', config);
      setConnected(true);
      toast.success(`Connected to Redis ${response.data.version}`);
      loadKeys();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Connection failed');
    } finally {
      setLoading(false);
    }
  };

  const loadKeys = async () => {
    try {
      const response = await axiosInstance.post('/redis/keys', config);
      setKeys(response.data.keys || []);
    } catch (error) {
      toast.error('Failed to load keys');
    }
  };

  const getKeyValue = async (key) => {
    setSelectedKey(key);
    try {
      const response = await axiosInstance.post('/redis/get', {
        ...config,
        command: 'get',
        args: [key]
      });
      setKeyValue(response.data);
    } catch (error) {
      toast.error('Failed to get value');
    }
  };

  const setKeyValueAction = async () => {
    if (!newKey.trim()) return;
    try {
      await axiosInstance.post('/redis/set', {
        ...config,
        command: 'set',
        args: [newKey, newValue]
      });
      toast.success('Key set successfully');
      setShowAddModal(false);
      setNewKey('');
      setNewValue('');
      loadKeys();
    } catch (error) {
      toast.error('Failed to set key');
    }
  };

  const deleteKey = async (key) => {
    try {
      await axiosInstance.post('/redis/delete', {
        ...config,
        command: 'delete',
        args: [key]
      });
      toast.success('Key deleted');
      setSelectedKey(null);
      setKeyValue(null);
      loadKeys();
    } catch (error) {
      toast.error('Failed to delete key');
    }
  };

  const filteredKeys = keys.filter(k => 
    k.key.toLowerCase().includes(searchFilter.toLowerCase())
  );

  const formatValue = (value) => {
    if (typeof value === 'object') {
      return JSON.stringify(value, null, 2);
    }
    return String(value);
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="redis-manager">
      <div className="p-6 border-b border-cyan-500/20 bg-black/40">
        <div className="flex items-center gap-3 mb-4">
          <Database className="w-7 h-7 text-red-400" />
          <div>
            <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-red-400 to-orange-400 bg-clip-text uppercase">
              Redis
            </h2>
            <p className="text-xs text-slate-400 font-mono mt-1">CACHE MANAGER</p>
          </div>
        </div>

        {!connected ? (
          <div className="grid grid-cols-4 gap-3">
            <input
              value={config.host}
              onChange={(e) => setConfig({...config, host: e.target.value})}
              placeholder="Host"
              className="bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono px-3 py-2 outline-none text-sm"
            />
            <input
              type="number"
              value={config.port}
              onChange={(e) => setConfig({...config, port: parseInt(e.target.value)})}
              placeholder="Port"
              className="bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono px-3 py-2 outline-none text-sm"
            />
            <input
              type="password"
              value={config.password}
              onChange={(e) => setConfig({...config, password: e.target.value})}
              placeholder="Password (optional)"
              className="bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono px-3 py-2 outline-none text-sm"
            />
            <button
              onClick={connect}
              disabled={loading}
              className="px-4 py-2 bg-gradient-to-r from-red-500 to-orange-500 text-white font-bold rounded-sm uppercase flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Database className="w-4 h-4" />}
              Connect
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <Check className="w-5 h-5 text-green-400" />
            <span className="text-green-400 font-mono text-sm">Connected</span>
            <button
              onClick={() => { setConnected(false); setKeys([]); }}
              className="ml-auto px-3 py-1 text-red-400 border border-red-500/50 rounded-sm text-xs hover:bg-red-500/20"
            >
              Disconnect
            </button>
          </div>
        )}
      </div>

      {connected && (
        <div className="flex-1 flex overflow-hidden">
          {/* Keys Sidebar */}
          <div className="w-80 border-r border-cyan-500/20 bg-black/20 flex flex-col">
            <div className="p-4 border-b border-cyan-500/20">
              <div className="flex items-center gap-2 mb-3">
                <div className="flex-1 relative">
                  <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input
                    value={searchFilter}
                    onChange={(e) => setSearchFilter(e.target.value)}
                    placeholder="Search keys..."
                    className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono pl-9 pr-3 py-2 outline-none text-sm"
                  />
                </div>
                <button onClick={loadKeys} className="p-2 text-slate-400 hover:text-cyan-400">
                  <RefreshCw className="w-4 h-4" />
                </button>
                <button onClick={() => setShowAddModal(true)} className="p-2 text-green-400 hover:text-green-300">
                  <Plus className="w-4 h-4" />
                </button>
              </div>
              <div className="text-xs text-slate-500">{keys.length} keys total</div>
            </div>
            
            <div className="flex-1 overflow-auto p-2">
              {filteredKeys.map((k) => (
                <button
                  key={k.key}
                  onClick={() => getKeyValue(k.key)}
                  className={`w-full text-left px-3 py-2 rounded mb-1 transition-all ${
                    selectedKey === k.key
                      ? 'bg-red-500/20 border border-red-500/50'
                      : 'hover:bg-white/5'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-mono text-white truncate">{k.key}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      k.type === 'string' ? 'bg-green-500/20 text-green-400' :
                      k.type === 'list' ? 'bg-blue-500/20 text-blue-400' :
                      k.type === 'hash' ? 'bg-violet-500/20 text-violet-400' :
                      k.type === 'set' ? 'bg-yellow-500/20 text-yellow-400' :
                      'bg-slate-500/20 text-slate-400'
                    }`}>{k.type}</span>
                  </div>
                  {k.ttl > 0 && (
                    <div className="text-xs text-slate-500 mt-1">TTL: {k.ttl}s</div>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Value Display */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {keyValue ? (
              <>
                <div className="p-4 border-b border-cyan-500/20 flex items-center justify-between">
                  <div>
                    <div className="text-lg font-mono text-cyan-400">{keyValue.key}</div>
                    <div className="text-xs text-slate-500">Type: {keyValue.type}</div>
                  </div>
                  <button
                    onClick={() => deleteKey(keyValue.key)}
                    className="px-3 py-1.5 bg-red-500/20 text-red-400 border border-red-500/50 hover:bg-red-500/30 rounded-sm text-xs font-semibold uppercase flex items-center gap-1"
                  >
                    <Trash2 className="w-3 h-3" /> Delete
                  </button>
                </div>
                <div className="flex-1 overflow-auto p-4">
                  <pre className="bg-black/50 border border-cyan-900/30 rounded p-4 text-sm font-mono text-slate-300 overflow-auto">
                    {formatValue(keyValue.value)}
                  </pre>
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-slate-500">
                <Key className="w-12 h-12 opacity-30" />
                <span className="ml-3">Select a key to view its value</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Add Key Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center">
          <div className="bg-[#0a0a0f] border border-cyan-500/30 rounded-lg w-full max-w-md p-6">
            <h3 className="text-xl font-bold text-cyan-400 mb-4 uppercase">Add New Key</h3>
            <div className="space-y-4">
              <div>
                <label className="text-xs text-cyan-400 font-mono uppercase mb-1 block">Key</label>
                <input
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  placeholder="my:key:name"
                  className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono px-3 py-2 outline-none"
                />
              </div>
              <div>
                <label className="text-xs text-cyan-400 font-mono uppercase mb-1 block">Value</label>
                <textarea
                  value={newValue}
                  onChange={(e) => setNewValue(e.target.value)}
                  placeholder="Value..."
                  rows={4}
                  className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono px-3 py-2 outline-none resize-none"
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-slate-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={setKeyValueAction}
                className="px-4 py-2 bg-gradient-to-r from-red-500 to-orange-500 text-white font-bold rounded-sm"
              >
                Add Key
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RedisManager;
