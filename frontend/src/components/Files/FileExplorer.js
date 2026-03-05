import React, { useState, useEffect } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Folder, File, ChevronRight, ChevronDown, Edit, Save } from 'lucide-react';

const FileExplorer = () => {
  const [currentPath, setCurrentPath] = useState('/app');
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState('');

  useEffect(() => {
    loadFiles(currentPath);
  }, [currentPath]);

  const loadFiles = async (path) => {
    setLoading(true);
    try {
      const response = await axiosInstance.post('/files/list', { path });
      setFiles(response.data.items);
    } catch (error) {
      toast.error('Failed to load files');
    } finally {
      setLoading(false);
    }
  };

  const handleFileClick = async (item) => {
    if (item.is_dir) {
      setCurrentPath(item.path);
      setSelectedFile(null);
    } else {
      setSelectedFile(item);
      try {
        const response = await axiosInstance.post('/files/read', { path: item.path });
        setFileContent(response.data.content);
        setEditedContent(response.data.content);
        setIsEditing(false);
      } catch (error) {
        toast.error('Failed to read file');
      }
    }
  };

  const handleSave = async () => {
    try {
      await axiosInstance.post('/files/write', { 
        path: selectedFile.path, 
        content: editedContent 
      });
      setFileContent(editedContent);
      setIsEditing(false);
      toast.success('File saved successfully');
    } catch (error) {
      toast.error('Failed to save file');
    }
  };

  return (
    <div className="h-full flex" data-testid="file-explorer">
      {/* File List */}
      <div className="w-1/3 border-r border-cyan-500/20 bg-black/20 overflow-y-auto">
        <div className="p-4 border-b border-cyan-500/20">
          <h2 className="text-xl font-bold text-cyan-400 uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
            FILE EXPLORER
          </h2>
          <p className="text-xs text-slate-400 font-mono mt-1">{currentPath}</p>
        </div>

        {currentPath !== '/app' && (
          <button
            data-testid="back-btn"
            onClick={() => setCurrentPath(currentPath.split('/').slice(0, -1).join('/') || '/app')}
            className="w-full p-3 text-left text-cyan-400 hover:bg-cyan-500/10 border-b border-cyan-900/20 font-mono text-sm"
          >
            ../ (Back)
          </button>
        )}

        <div className="divide-y divide-cyan-900/20">
          {files.map((item, idx) => (
            <button
              key={idx}
              data-testid={`file-item-${item.name}`}
              onClick={() => handleFileClick(item)}
              className={`w-full p-3 text-left hover:bg-cyan-500/10 transition-colors flex items-center gap-3 ${
                selectedFile?.path === item.path ? 'bg-cyan-500/20' : ''
              }`}
            >
              {item.is_dir ? (
                <Folder className="w-5 h-5 text-cyan-400" />
              ) : (
                <File className="w-5 h-5 text-slate-400" />
              )}
              <div className="flex-1 min-w-0">
                <div className="text-sm text-slate-200 truncate font-mono">{item.name}</div>
                {!item.is_dir && (
                  <div className="text-xs text-slate-500">{(item.size / 1024).toFixed(1)} KB</div>
                )}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* File Content */}
      <div className="flex-1 flex flex-col bg-[#0a0a0f]/50">
        {selectedFile ? (
          <>
            <div className="p-4 border-b border-cyan-500/20 bg-black/40 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-cyan-400 font-mono">{selectedFile.name}</h3>
                <p className="text-xs text-slate-400">{selectedFile.path}</p>
              </div>
              <div className="flex gap-2">
                {isEditing ? (
                  <button
                    data-testid="save-file-btn"
                    onClick={handleSave}
                    className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase text-sm flex items-center gap-2"
                  >
                    <Save className="w-4 h-4" />
                    SAVE
                  </button>
                ) : (
                  <button
                    data-testid="edit-file-btn"
                    onClick={() => setIsEditing(true)}
                    className="px-4 py-2 bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 hover:bg-cyan-500/30 rounded-sm uppercase text-sm flex items-center gap-2"
                  >
                    <Edit className="w-4 h-4" />
                    EDIT
                  </button>
                )}
              </div>
            </div>
            <div className="flex-1 overflow-auto p-6">
              {isEditing ? (
                <textarea
                  data-testid="file-editor"
                  value={editedContent}
                  onChange={(e) => setEditedContent(e.target.value)}
                  className="w-full h-full bg-black/50 border border-cyan-900/50 text-cyan-100 font-mono text-sm p-4 rounded-sm outline-none focus:border-cyan-400 resize-none"
                />
              ) : (
                <pre className="text-slate-300 font-mono text-sm bg-black/30 p-4 rounded-sm border border-cyan-900/30 overflow-auto">
                  {fileContent}
                </pre>
              )}
            </div>
          </>
        ) : (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <File className="w-16 h-16 mx-auto text-cyan-500/30" />
              <p className="text-slate-400 font-mono text-sm">Select a file to view or edit</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default FileExplorer;