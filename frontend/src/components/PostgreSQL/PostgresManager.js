import React, { useState } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Database, Play, Table, Columns, Loader2, Check, X, RefreshCw } from 'lucide-react';
import { usePersist } from '../../hooks/usePersist';

const PostgresManager = () => {
  const [connectionString, setConnectionString] = usePersist('ma_postgres_connstr', '');
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [tables, setTables] = useState([]);
  const [selectedTable, setSelectedTable] = useState(null);
  const [tableSchema, setTableSchema] = useState([]);
  const [query, setQuery] = useState('SELECT * FROM ');
  const [queryResults, setQueryResults] = useState(null);
  const [queryLoading, setQueryLoading] = useState(false);

  const connect = async () => {
    if (!connectionString.trim()) {
      toast.error('Enter a connection string');
      return;
    }
    
    setLoading(true);
    try {
      const response = await axiosInstance.post('/postgres/connect', {
        connection_string: connectionString
      });
      setConnected(true);
      toast.success('Connected to PostgreSQL!');
      loadTables();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Connection failed');
    } finally {
      setLoading(false);
    }
  };

  const loadTables = async () => {
    try {
      const response = await axiosInstance.post('/postgres/tables', {
        connection_string: connectionString
      });
      setTables(response.data.tables || []);
    } catch (error) {
      toast.error('Failed to load tables');
    }
  };

  const loadSchema = async (tableName) => {
    setSelectedTable(tableName);
    try {
      const response = await axiosInstance.post('/postgres/schema', {
        connection_string: connectionString,
        query: tableName
      });
      setTableSchema(response.data.columns || []);
    } catch (error) {
      toast.error('Failed to load schema');
    }
  };

  const runQuery = async () => {
    if (!query.trim()) return;
    
    setQueryLoading(true);
    try {
      const response = await axiosInstance.post('/postgres/query', {
        connection_string: connectionString,
        query: query
      });
      setQueryResults(response.data);
      toast.success(`Query executed: ${response.data.rowCount} rows`);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Query failed');
      setQueryResults(null);
    } finally {
      setQueryLoading(false);
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="postgres-manager">
      <div className="p-6 border-b border-cyan-500/20 bg-black/40">
        <div className="flex items-center gap-3 mb-4">
          <Database className="w-7 h-7 text-cyan-400" />
          <div>
            <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase">
              PostgreSQL
            </h2>
            <p className="text-xs text-slate-400 font-mono mt-1">DATABASE MANAGER</p>
          </div>
        </div>

        {!connected ? (
          <div className="space-y-3">
            <input
              type="password"
              value={connectionString}
              onChange={(e) => setConnectionString(e.target.value)}
              placeholder="postgresql://user:password@host:5432/database"
              className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono px-4 py-3 outline-none"
            />
            <button
              onClick={connect}
              disabled={loading}
              className="px-6 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold rounded-sm uppercase flex items-center gap-2 disabled:opacity-50"
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
              onClick={() => { setConnected(false); setTables([]); setQueryResults(null); }}
              className="ml-auto px-3 py-1 text-red-400 border border-red-500/50 rounded-sm text-xs hover:bg-red-500/20"
            >
              Disconnect
            </button>
          </div>
        )}
      </div>

      {connected && (
        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar - Tables */}
          <div className="w-64 border-r border-cyan-500/20 bg-black/20 overflow-auto">
            <div className="p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs text-cyan-400 font-mono uppercase">Tables</span>
                <button onClick={loadTables} className="p-1 text-slate-400 hover:text-cyan-400">
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>
              <div className="space-y-1">
                {tables.map((table) => (
                  <button
                    key={`${table.schema}.${table.name}`}
                    onClick={() => loadSchema(table.name)}
                    className={`w-full text-left px-3 py-2 rounded text-sm font-mono transition-all ${
                      selectedTable === table.name
                        ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                        : 'text-slate-400 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    <Table className="w-4 h-4 inline mr-2" />
                    {table.name}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Main Content */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Query Editor */}
            <div className="p-4 border-b border-cyan-500/20">
              <label className="text-xs text-cyan-400 font-mono uppercase mb-2 block">SQL Query</label>
              <div className="flex gap-2">
                <textarea
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="SELECT * FROM table_name LIMIT 100"
                  className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono p-3 outline-none resize-none text-sm"
                  rows={3}
                />
                <button
                  onClick={runQuery}
                  disabled={queryLoading}
                  className="px-4 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold rounded-sm disabled:opacity-50"
                >
                  {queryLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5" />}
                </button>
              </div>
            </div>

            {/* Schema View */}
            {selectedTable && tableSchema.length > 0 && !queryResults && (
              <div className="p-4 border-b border-cyan-500/20 bg-black/20">
                <div className="flex items-center gap-2 mb-3">
                  <Columns className="w-4 h-4 text-cyan-400" />
                  <span className="text-sm text-cyan-400 font-mono uppercase">{selectedTable} Schema</span>
                </div>
                <div className="grid grid-cols-4 gap-2 text-xs font-mono">
                  <div className="text-cyan-400">Column</div>
                  <div className="text-cyan-400">Type</div>
                  <div className="text-cyan-400">Nullable</div>
                  <div className="text-cyan-400">Default</div>
                  {tableSchema.map((col, idx) => (
                    <React.Fragment key={idx}>
                      <div className="text-white">{col.column_name}</div>
                      <div className="text-violet-400">{col.data_type}</div>
                      <div className={col.is_nullable === 'YES' ? 'text-yellow-400' : 'text-green-400'}>
                        {col.is_nullable}
                      </div>
                      <div className="text-slate-400 truncate">{col.column_default || '-'}</div>
                    </React.Fragment>
                  ))}
                </div>
              </div>
            )}

            {/* Query Results */}
            {queryResults && (
              <div className="flex-1 overflow-auto p-4">
                <div className="text-xs text-cyan-400 font-mono mb-2">
                  {queryResults.rowCount} rows returned
                </div>
                {queryResults.columns && queryResults.data && (
                  <div className="overflow-auto">
                    <table className="w-full text-sm font-mono">
                      <thead>
                        <tr className="border-b border-cyan-500/30">
                          {queryResults.columns.map((col) => (
                            <th key={col} className="text-left p-2 text-cyan-400">{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {queryResults.data.map((row, idx) => (
                          <tr key={idx} className="border-b border-cyan-900/30 hover:bg-cyan-500/5">
                            {queryResults.columns.map((col) => (
                              <td key={col} className="p-2 text-slate-300">
                                {JSON.stringify(row[col])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default PostgresManager;
