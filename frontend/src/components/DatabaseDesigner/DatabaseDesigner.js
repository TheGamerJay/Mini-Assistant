import React, { useState } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Database, Plus, Trash2, Download, Code } from 'lucide-react';

const DatabaseDesigner = () => {
  const [tables, setTables] = useState([]);
  const [showAddTable, setShowAddTable] = useState(false);
  const [newTable, setNewTable] = useState({ name: '', fields: [{ name: 'id', type: 'INTEGER', primary: true }] });
  const [dbType, setDbType] = useState('mongodb');

  const fieldTypes = {
    mongodb: ['String', 'Number', 'Boolean', 'Date', 'ObjectId', 'Array', 'Object'],
    sql: ['INTEGER', 'VARCHAR', 'TEXT', 'BOOLEAN', 'DATE', 'TIMESTAMP', 'FLOAT', 'JSON']
  };

  const addField = () => {
    setNewTable({
      ...newTable,
      fields: [...newTable.fields, { name: '', type: dbType === 'mongodb' ? 'String' : 'VARCHAR', primary: false }]
    });
  };

  const removeField = (index) => {
    setNewTable({
      ...newTable,
      fields: newTable.fields.filter((_, i) => i !== index)
    });
  };

  const updateField = (index, key, value) => {
    const newFields = [...newTable.fields];
    newFields[index][key] = value;
    setNewTable({ ...newTable, fields: newFields });
  };

  const addTable = () => {
    if (!newTable.name.trim()) {
      toast.error('Table name is required');
      return;
    }
    setTables([...tables, { ...newTable, id: Date.now() }]);
    setNewTable({ name: '', fields: [{ name: 'id', type: 'INTEGER', primary: true }] });
    setShowAddTable(false);
    toast.success('Table added');
  };

  const removeTable = (id) => {
    setTables(tables.filter(t => t.id !== id));
    toast.success('Table removed');
  };

  const generateCode = () => {
    if (tables.length === 0) {
      toast.error('Add tables first');
      return;
    }

    let code = '';
    if (dbType === 'mongodb') {
      tables.forEach(table => {
        code += `// ${table.name} Schema\n`;
        code += `const ${table.name}Schema = new Schema({\n`;
        table.fields.forEach(field => {
          if (field.name !== 'id') {
            code += `  ${field.name}: { type: ${field.type}, required: ${field.required || false} },\n`;
          }
        });
        code += `}, { timestamps: true });\n\n`;
        code += `const ${table.name} = model('${table.name}', ${table.name}Schema);\n\n`;
      });
    } else {
      tables.forEach(table => {
        code += `-- ${table.name} Table\n`;
        code += `CREATE TABLE ${table.name} (\n`;
        table.fields.forEach((field, idx) => {
          code += `  ${field.name} ${field.type}`;
          if (field.primary) code += ' PRIMARY KEY';
          if (idx < table.fields.length - 1) code += ',';
          code += '\n';
        });
        code += `);\n\n`;
      });
    }

    navigator.clipboard.writeText(code);
    toast.success('Code copied to clipboard!');
  };

  const exportJSON = () => {
    const blob = new Blob([JSON.stringify(tables, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'database-schema.json';
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Schema exported!');
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="database-designer">
      <div className="p-6 border-b border-cyan-500/20 bg-black/40">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Database className="w-7 h-7 text-cyan-400" />
            <div>
              <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
                DATABASE DESIGNER
              </h2>
              <p className="text-xs text-slate-400 font-mono mt-1">VISUAL SCHEMA BUILDER</p>
            </div>
          </div>
          <div className="flex gap-3">
            <select
              value={dbType}
              onChange={(e) => setDbType(e.target.value)}
              className="bg-black/50 border border-cyan-500/50 text-cyan-100 px-4 py-2 rounded-sm font-mono text-sm"
            >
              <option value="mongodb">MongoDB</option>
              <option value="sql">SQL</option>
            </select>
            <button
              onClick={() => setShowAddTable(true)}
              className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-sm flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              ADD TABLE
            </button>
          </div>
        </div>

        {tables.length > 0 && (
          <div className="flex gap-2">
            <button
              onClick={generateCode}
              className="px-4 py-2 bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 hover:bg-cyan-500/30 rounded-sm text-sm font-semibold uppercase flex items-center gap-2"
            >
              <Code className="w-4 h-4" />
              COPY CODE
            </button>
            <button
              onClick={exportJSON}
              className="px-4 py-2 bg-violet-500/20 text-violet-400 border border-violet-500/50 hover:bg-violet-500/30 rounded-sm text-sm font-semibold uppercase flex items-center gap-2"
            >
              <Download className="w-4 h-4" />
              EXPORT
            </button>
          </div>
        )}
      </div>

      {/* Add Table Modal */}
      {showAddTable && (
        <div className="p-6 border-b border-cyan-500/20 bg-black/30">
          <h3 className="text-lg font-semibold text-cyan-400 mb-4">New Table</h3>
          <div className="space-y-4">
            <input
              placeholder="Table name"
              value={newTable.name}
              onChange={(e) => setNewTable({ ...newTable, name: e.target.value })}
              className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 rounded-sm font-mono px-4 py-2 outline-none"
            />

            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm text-cyan-400 font-mono uppercase">Fields</div>
                <button
                  onClick={addField}
                  className="text-xs text-violet-400 hover:text-violet-300 flex items-center gap-1"
                >
                  <Plus className="w-3 h-3" /> ADD FIELD
                </button>
              </div>
              <div className="space-y-2">
                {newTable.fields.map((field, idx) => (
                  <div key={idx} className="flex gap-2">
                    <input
                      placeholder="Field name"
                      value={field.name}
                      onChange={(e) => updateField(idx, 'name', e.target.value)}
                      className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono px-3 py-2 outline-none text-sm"
                    />
                    <select
                      value={field.type}
                      onChange={(e) => updateField(idx, 'type', e.target.value)}
                      className="bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono px-3 py-2 outline-none text-sm"
                    >
                      {fieldTypes[dbType].map(type => (
                        <option key={type} value={type}>{type}</option>
                      ))}
                    </select>
                    {!field.primary && (
                      <button
                        onClick={() => removeField(idx)}
                        className="p-2 text-slate-400 hover:text-red-400"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={addTable}
                className="px-6 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase"
              >
                CREATE TABLE
              </button>
              <button
                onClick={() => setShowAddTable(false)}
                className="px-6 py-2 bg-slate-700 text-white hover:bg-slate-600 rounded-sm uppercase"
              >
                CANCEL
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tables Display */}
      <div className="flex-1 overflow-auto p-6">
        {tables.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <Database className="w-16 h-16 mx-auto text-cyan-500/30" />
              <p className="text-slate-400 font-mono text-sm">Create your first table to get started</p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {tables.map(table => (
              <div key={table.id} className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-lg font-semibold text-cyan-400">{table.name}</h3>
                  <button
                    onClick={() => removeTable(table.id)}
                    className="p-1 text-slate-400 hover:text-red-400"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
                <div className="space-y-1">
                  {table.fields.map((field, idx) => (
                    <div key={idx} className="flex items-center gap-2 p-2 bg-black/30 rounded text-sm">
                      <span className="text-cyan-100 font-mono">{field.name}</span>
                      <span className="text-slate-500">:</span>
                      <span className="text-violet-400 text-xs">{field.type}</span>
                      {field.primary && <span className="text-xs text-green-400">PK</span>}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default DatabaseDesigner;