import React, { useState, useEffect } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Package, Download, Trash2, Loader2, Plus, Check } from 'lucide-react';

const PackageManager = () => {
  const [packageType, setPackageType] = useState('npm');
  const [searchQuery, setSearchQuery] = useState('');
  const [packageName, setPackageName] = useState('');
  const [installedPackages, setInstalledPackages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [installLog, setInstallLog] = useState([]);

  useEffect(() => {
    loadInstalledPackages();
  }, [packageType]);

  const loadInstalledPackages = async () => {
    try {
      const response = await axiosInstance.get(`/packages/list?type=${packageType}`);
      setInstalledPackages(response.data.packages || []);
    } catch (error) {
      console.error('Load packages error:', error);
    }
  };

  const installPackage = async () => {
    if (!packageName.trim() || loading) return;

    setLoading(true);
    try {
      const response = await axiosInstance.post('/packages/install', {
        package: packageName,
        type: packageType
      });

      setInstallLog(prev => [`✓ Installed ${packageName}`, ...prev]);
      toast.success(`${packageName} installed!`);
      setPackageName('');
      loadInstalledPackages();
    } catch (error) {
      const msg = error.response?.data?.detail || 'Installation failed';
      setInstallLog(prev => [`✗ Failed: ${packageName} - ${msg}`, ...prev]);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const uninstallPackage = async (pkg) => {
    setLoading(true);
    try {
      await axiosInstance.post('/packages/uninstall', {
        package: pkg,
        type: packageType
      });

      setInstallLog(prev => [`✓ Uninstalled ${pkg}`, ...prev]);
      toast.success(`${pkg} uninstalled`);
      loadInstalledPackages();
    } catch (error) {
      toast.error('Uninstall failed');
    } finally {
      setLoading(false);
    }
  };

  const popularPackages = {
    npm: ['express', 'react', 'axios', 'lodash', 'moment', 'dotenv', 'mongoose', 'socket.io'],
    pip: ['requests', 'numpy', 'pandas', 'flask', 'django', 'sqlalchemy', 'pytest', 'pillow']
  };

  return (
    <div className="h-full flex" data-testid="package-manager">
      <div className="w-2/3 border-r border-cyan-500/20 flex flex-col bg-black/20">
        <div className="p-6 border-b border-cyan-500/20 bg-black/40">
          <div className="flex items-center gap-3 mb-6">
            <Package className="w-7 h-7 text-cyan-400" />
            <div>
              <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
                PACKAGE MANAGER
              </h2>
              <p className="text-xs text-slate-400 font-mono mt-1">INSTALL NPM & PIP PACKAGES</p>
            </div>
          </div>

          <div className="flex gap-3 mb-6">
            <button
              onClick={() => setPackageType('npm')}
              className={`px-6 py-2 rounded-sm font-bold uppercase transition-all ${
                packageType === 'npm'
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                  : 'bg-black/30 text-slate-400 border border-transparent hover:text-cyan-400'
              }`}
            >
              NPM
            </button>
            <button
              onClick={() => setPackageType('pip')}
              className={`px-6 py-2 rounded-sm font-bold uppercase transition-all ${
                packageType === 'pip'
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                  : 'bg-black/30 text-slate-400 border border-transparent hover:text-cyan-400'
              }`}
            >
              PIP
            </button>
          </div>

          <div className="flex gap-3 mb-6">
            <input
              data-testid="package-name-input"
              type="text"
              placeholder={`Enter ${packageType} package name...`}
              value={packageName}
              onChange={(e) => setPackageName(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && installPackage()}
              className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 rounded-sm font-mono px-4 py-3 outline-none"
              disabled={loading}
            />
            <button
              data-testid="install-package-btn"
              onClick={installPackage}
              disabled={loading || !packageName.trim()}
              className="px-8 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
              INSTALL
            </button>
          </div>

          <div>
            <div className="text-sm text-cyan-400 font-mono uppercase mb-2">Popular Packages:</div>
            <div className="flex gap-2 flex-wrap">
              {popularPackages[packageType].map(pkg => (
                <button
                  key={pkg}
                  onClick={() => setPackageName(pkg)}
                  className="px-3 py-1.5 bg-black/30 border border-violet-500/30 hover:border-violet-500/50 text-violet-400 text-xs rounded-sm transition-all"
                >
                  {pkg}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-6">
          <h3 className="text-lg font-semibold text-cyan-400 mb-4">Installed Packages</h3>
          {installedPackages.length === 0 ? (
            <div className="text-center py-12 text-slate-500">
              <Package className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="text-sm">No packages installed yet</p>
            </div>
          ) : (
            <div className="grid gap-3">
              {installedPackages.map((pkg, idx) => (
                <div key={idx} className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Check className="w-5 h-5 text-green-400" />
                    <div>
                      <div className="text-cyan-100 font-mono">{pkg.name}</div>
                      {pkg.version && <div className="text-xs text-slate-500">v{pkg.version}</div>}
                    </div>
                  </div>
                  <button
                    onClick={() => uninstallPackage(pkg.name)}
                    disabled={loading}
                    className="p-2 text-slate-400 hover:text-red-400 transition-colors disabled:opacity-50"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="w-1/3 flex flex-col bg-[#0a0a0f]/50">
        <div className="p-4 border-b border-cyan-500/20 bg-black/40">
          <h3 className="text-lg font-semibold text-cyan-400">Installation Log</h3>
        </div>
        <div className="flex-1 overflow-auto p-4 space-y-2 font-mono text-sm">
          {installLog.map((log, idx) => (
            <div key={idx} className="p-2 bg-black/30 border border-cyan-900/20 rounded text-cyan-100">
              {log}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default PackageManager;