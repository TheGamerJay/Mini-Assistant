import React, { useState, useEffect } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Layers, Plus, Trash2, Play } from 'lucide-react';

const ProjectProfiles = () => {
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newProfile, setNewProfile] = useState({
    name: '',
    path: '/app',
    description: '',
    commands: []
  });
  const [commandInput, setCommandInput] = useState('');

  useEffect(() => {
    loadProfiles();
  }, []);

  const loadProfiles = async () => {
    setLoading(true);
    try {
      const response = await axiosInstance.get('/profiles');
      setProfiles(response.data);
    } catch (error) {
      toast.error('Failed to load profiles');
    } finally {
      setLoading(false);
    }
  };

  const createProfile = async () => {
    if (!newProfile.name.trim()) {
      toast.error('Profile name is required');
      return;
    }

    try {
      await axiosInstance.post('/profiles', newProfile);
      toast.success('Profile created');
      setShowCreate(false);
      setNewProfile({ name: '', path: '/app', description: '', commands: [] });
      setCommandInput('');
      loadProfiles();
    } catch (error) {
      toast.error('Failed to create profile');
    }
  };

  const deleteProfile = async (profileId) => {
    try {
      await axiosInstance.delete(`/profiles/${profileId}`);
      toast.success('Profile deleted');
      loadProfiles();
    } catch (error) {
      toast.error('Failed to delete profile');
    }
  };

  const addCommand = () => {
    if (commandInput.trim()) {
      setNewProfile({
        ...newProfile,
        commands: [...newProfile.commands, commandInput]
      });
      setCommandInput('');
    }
  };

  const removeCommand = (idx) => {
    setNewProfile({
      ...newProfile,
      commands: newProfile.commands.filter((_, i) => i !== idx)
    });
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50 p-6" data-testid="project-profiles">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-cyan-400 uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
            PROJECT PROFILES
          </h2>
          <p className="text-xs text-slate-400 font-mono mt-1">SAVE & RUN COMMANDS PER PROJECT</p>
        </div>
        <button
          data-testid="create-profile-btn"
          onClick={() => setShowCreate(!showCreate)}
          className="px-6 py-2 bg-cyan-500 text-black font-bold hover:bg-cyan-400 rounded-sm uppercase text-sm flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          NEW PROFILE
        </button>
      </div>

      {/* Create Profile Form */}
      {showCreate && (
        <div className="mb-6 p-6 bg-black/40 border border-cyan-500/50 rounded-lg backdrop-blur-sm" data-testid="create-profile-form">
          <h3 className="text-lg font-semibold text-cyan-400 mb-4">CREATE NEW PROFILE</h3>
          <div className="space-y-4">
            <input
              data-testid="profile-name-input"
              type="text"
              placeholder="Profile name"
              value={newProfile.name}
              onChange={(e) => setNewProfile({ ...newProfile, name: e.target.value })}
              className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono p-3 outline-none"
            />
            <input
              data-testid="profile-path-input"
              type="text"
              placeholder="Project path"
              value={newProfile.path}
              onChange={(e) => setNewProfile({ ...newProfile, path: e.target.value })}
              className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono p-3 outline-none"
            />
            <textarea
              data-testid="profile-description-input"
              placeholder="Description (optional)"
              value={newProfile.description}
              onChange={(e) => setNewProfile({ ...newProfile, description: e.target.value })}
              className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono p-3 outline-none"
              rows={2}
            />
            
            <div>
              <label className="text-sm text-cyan-400 font-mono mb-2 block">COMMANDS</label>
              <div className="flex gap-2 mb-2">
                <input
                  data-testid="command-input"
                  type="text"
                  placeholder="Add command"
                  value={commandInput}
                  onChange={(e) => setCommandInput(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && addCommand()}
                  className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono p-2 outline-none"
                />
                <button
                  data-testid="add-command-btn"
                  onClick={addCommand}
                  className="px-4 py-2 bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 hover:bg-cyan-500/30 rounded-sm"
                >
                  ADD
                </button>
              </div>
              <div className="space-y-1">
                {newProfile.commands.map((cmd, idx) => (
                  <div key={idx} className="flex items-center gap-2 p-2 bg-black/30 rounded">
                    <code className="flex-1 text-sm text-cyan-100">{cmd}</code>
                    <button
                      onClick={() => removeCommand(idx)}
                      className="text-red-400 hover:text-red-300"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex gap-3">
              <button
                data-testid="save-profile-btn"
                onClick={createProfile}
                className="px-6 py-2 bg-cyan-500 text-black font-bold hover:bg-cyan-400 rounded-sm uppercase"
              >
                SAVE PROFILE
              </button>
              <button
                onClick={() => setShowCreate(false)}
                className="px-6 py-2 bg-slate-700 text-white hover:bg-slate-600 rounded-sm uppercase"
              >
                CANCEL
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Profiles List */}
      <div className="flex-1 overflow-y-auto">
        <div className="grid gap-4">
          {profiles.map((profile) => (
            <div
              key={profile.id}
              data-testid={`profile-${profile.id}`}
              className="p-6 bg-black/40 border border-cyan-900/30 rounded-lg backdrop-blur-sm hover:border-cyan-500/50 transition-colors"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-cyan-400 mb-1">{profile.name}</h3>
                  <p className="text-xs text-slate-500 font-mono">{profile.path}</p>
                  {profile.description && (
                    <p className="text-sm text-slate-400 mt-2">{profile.description}</p>
                  )}
                </div>
                <button
                  data-testid={`delete-profile-${profile.id}`}
                  onClick={() => deleteProfile(profile.id)}
                  className="p-2 text-slate-400 hover:text-red-400 transition-colors"
                >
                  <Trash2 className="w-5 h-5" />
                </button>
              </div>
              
              {profile.commands.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs text-cyan-400/70 font-mono uppercase">Commands:</div>
                  {profile.commands.map((cmd, idx) => (
                    <div key={idx} className="p-2 bg-black/30 rounded border border-cyan-900/20">
                      <code className="text-sm text-cyan-100">{cmd}</code>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}

          {profiles.length === 0 && !loading && (
            <div className="text-center py-12">
              <Layers className="w-16 h-16 mx-auto text-cyan-500/30 mb-4" />
              <p className="text-slate-400 font-mono text-sm">No profiles yet. Create your first project profile!</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProjectProfiles;