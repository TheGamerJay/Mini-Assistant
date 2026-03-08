import React, { useState, useEffect } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Settings, Plus, Trash2, Eye, EyeOff, Save, Key } from 'lucide-react';
import { usePersist } from '../../hooks/usePersist';

const EnvManager = () => {
  const [envType, setEnvType] = usePersist('ma_env_type', 'frontend');
  const [envVars, setEnvVars] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showValues, setShowValues] = useState({});

  useEffect(() => {
    loadEnvVars();
  }, [envType]);

  const loadEnvVars = async () => {
    try {
      const response = await axiosInstance.get(`/env/read?type=${envType}`);
      const vars = response.data.variables || [];
      setEnvVars(vars);
    } catch (error) {
      console.error('Load env error:', error);
    }
  };

  const addVar = () => {
    setEnvVars([...envVars, { key: '', value: '', id: Date.now() }]);
  };

  const removeVar = (id) => {
    setEnvVars(envVars.filter(v => v.id !== id));
  };

  const updateVar = (id, field, value) => {
    setEnvVars(envVars.map(v => v.id === id ? { ...v, [field]: value } : v));
  };

  const toggleShowValue = (id) => {
    setShowValues(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const saveEnvVars = async () => {
    setLoading(true);
    try {
      await axiosInstance.post('/env/write', {
        type: envType,
        variables: envVars.filter(v => v.key.trim())
      });
      toast.success('Environment variables saved!');
      loadEnvVars();
    } catch (error) {
      toast.error('Failed to save environment variables');
    } finally {
      setLoading(false);
    }
  };

  const commonVars = {
    frontend: [
      { key: 'REACT_APP_API_URL', value: 'http://localhost:8001' },
      { key: 'REACT_APP_ENV', value: 'development' },
      { key: 'REACT_APP_BACKEND_URL', value: '' },
    ],
    backend: [
      { key: 'DATABASE_URL', value: '' },
      { key: 'SECRET_KEY', value: '' },
      { key: 'API_KEY', value: '' },
      { key: 'PORT', value: '8001' },
    ]
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="env-manager">
      <div className="p-6 border-b border-cyan-500/20 bg-black/40">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Settings className="w-7 h-7 text-cyan-400" />
            <div>
              <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
                ENV MANAGER
              </h2>
              <p className="text-xs text-slate-400 font-mono mt-1">MANAGE ENVIRONMENT VARIABLES</p>
            </div>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => setEnvType('frontend')}
              className={`px-6 py-2 rounded-sm font-bold uppercase transition-all ${
                envType === 'frontend'
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                  : 'bg-black/30 text-slate-400 hover:text-cyan-400'
              }`}
            >
              FRONTEND
            </button>
            <button
              onClick={() => setEnvType('backend')}
              className={`px-6 py-2 rounded-sm font-bold uppercase transition-all ${
                envType === 'backend'
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                  : 'bg-black/30 text-slate-400 hover:text-cyan-400'
              }`}
            >
              BACKEND
            </button>
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={addVar}
            className="px-4 py-2 bg-violet-500/20 text-violet-400 border border-violet-500/50 hover:bg-violet-500/30 rounded-sm text-sm font-semibold uppercase flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            ADD VARIABLE
          </button>
          <button
            onClick={saveEnvVars}
            disabled={loading}
            className="px-6 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-sm flex items-center gap-2 disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            SAVE ALL
          </button>
        </div>

        <div className="mt-4">
          <div className="text-xs text-cyan-400/70 font-mono uppercase mb-2">Quick Add:</div>
          <div className="flex gap-2 flex-wrap">
            {commonVars[envType].map((v, idx) => (
              <button
                key={idx}
                onClick={() => setEnvVars([...envVars, { ...v, id: Date.now() + idx }])}
                className="px-3 py-1.5 bg-black/30 border border-violet-500/30 hover:border-violet-500/50 text-violet-400 text-xs rounded-sm"
              >
                {v.key}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {envVars.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <Key className="w-16 h-16 mx-auto text-cyan-500/30" />
              <p className="text-slate-400 font-mono text-sm">No environment variables. Click "ADD VARIABLE" to start.</p>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {envVars.map((v) => (
              <div key={v.id} className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg">
                <div className="flex gap-3">
                  <input
                    placeholder="KEY"
                    value={v.key}
                    onChange={(e) => updateVar(v.id, 'key', e.target.value)}
                    className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 rounded-sm font-mono px-4 py-2 outline-none"
                  />
                  <div className="flex-1 relative">
                    <input
                      type={showValues[v.id] ? 'text' : 'password'}
                      placeholder="VALUE"
                      value={v.value}
                      onChange={(e) => updateVar(v.id, 'value', e.target.value)}
                      className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 rounded-sm font-mono px-4 py-2 pr-10 outline-none"
                    />
                    <button
                      onClick={() => toggleShowValue(v.id)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-cyan-400"
                    >
                      {showValues[v.id] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <button
                    onClick={() => removeVar(v.id)}
                    className="p-2 text-slate-400 hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default EnvManager;