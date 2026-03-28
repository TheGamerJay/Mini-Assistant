/**
 * AdModeCampaigns — list and browse saved campaigns and ad sets.
 */

import React, { useEffect, useState } from 'react';
import { Target, ChevronRight, Loader2, Image as ImageIcon, Download, RefreshCw, Copy, CheckCheck } from 'lucide-react';
import { api } from '../../api/client';
import { toast } from 'sonner';

function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false);
  const handle = () => {
    navigator.clipboard.writeText(text || '').then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button onClick={handle} className="text-slate-600 hover:text-slate-400 transition-colors">
      {copied ? <CheckCheck size={12} className="text-emerald-400" /> : <Copy size={12} />}
    </button>
  );
}

function AdSetMini({ ad }) {
  const [regenImg, setRegenImg] = useState(false);
  const [imgData, setImgData]   = useState(ad.image_base64);

  const download = () => {
    if (!imgData) return;
    const link = document.createElement('a');
    link.href  = `data:image/png;base64,${imgData}`;
    link.download = `ad-${ad.angle || 'creative'}.png`;
    link.click();
  };

  const handleRegenImage = async () => {
    setRegenImg(true);
    try {
      const result = await api.adModeRegenerateImage(ad.id, ad.image_prompt);
      setImgData(result.image_base64);
      toast.success('Image regenerated');
    } catch (err) {
      toast.error(err?.message || 'Failed');
    } finally {
      setRegenImg(false);
    }
  };

  return (
    <div className="bg-white/3 border border-white/8 rounded-xl overflow-hidden">
      {/* Image */}
      <div className="relative bg-black/20 h-36 flex items-center justify-center group">
        {imgData ? (
          <>
            <img
              src={`data:image/png;base64,${imgData}`}
              alt={ad.headline}
              className="h-full w-full object-cover"
            />
            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/50 transition-all flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100">
              <button
                onClick={handleRegenImage}
                disabled={regenImg}
                className="bg-white/90 text-slate-800 text-xs font-medium px-2.5 py-1.5 rounded-lg hover:bg-white flex items-center gap-1"
              >
                {regenImg ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />} New image
              </button>
              <button
                onClick={download}
                className="bg-white/90 text-slate-800 text-xs font-medium px-2.5 py-1.5 rounded-lg hover:bg-white flex items-center gap-1"
              >
                <Download size={10} /> Save
              </button>
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center gap-1.5 text-slate-600">
            <ImageIcon size={20} />
            <p className="text-[10px]">No image</p>
          </div>
        )}
      </div>

      {/* Copy */}
      <div className="p-3 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <span className="text-[9px] font-mono text-violet-400 bg-violet-500/10 border border-violet-500/20 rounded px-1.5 py-0.5">
              {ad.angle}
            </span>
            <p className="text-xs font-semibold text-slate-200 mt-1 truncate">{ad.headline}</p>
          </div>
          <CopyBtn text={`${ad.hook}\n\n${ad.headline}\n\n${ad.caption}\n\nCTA: ${ad.cta}`} />
        </div>
        <p className="text-[10px] text-slate-500 leading-relaxed line-clamp-2">{ad.caption}</p>
        <span className="inline-block bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-[10px] px-2 py-0.5 rounded-md">
          {ad.cta}
        </span>
      </div>
    </div>
  );
}

export default function AdModeCampaigns() {
  const [campaigns, setCampaigns]   = useState([]);
  const [loading, setLoading]       = useState(true);
  const [openId, setOpenId]         = useState(null);
  const [detail, setDetail]         = useState(null);
  const [detailLoading, setDL]      = useState(false);

  useEffect(() => {
    api.adModeGetCampaigns()
      .then(({ campaigns: c }) => setCampaigns(c))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const openCampaign = async (id) => {
    if (openId === id) { setOpenId(null); setDetail(null); return; }
    setOpenId(id);
    setDetail(null);
    setDL(true);
    try {
      const { campaign, ad_sets } = await api.adModeGetCampaign(id);
      setDetail({ campaign, ad_sets });
    } catch {
      toast.error('Failed to load campaign details');
    } finally {
      setDL(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500 gap-2">
        <Loader2 size={16} className="animate-spin" /> Loading campaigns…
      </div>
    );
  }

  if (!campaigns.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center gap-4">
        <Target size={28} className="text-slate-600" />
        <div>
          <p className="text-slate-300 font-medium mb-1">Create your first ad in seconds.</p>
          <p className="text-sm text-slate-500">Describe your product and let AI generate high-converting ads for you.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {campaigns.map((c) => (
        <div key={c.id} className="bg-white/3 border border-white/8 rounded-2xl overflow-hidden">
          {/* Campaign row */}
          <button
            onClick={() => openCampaign(c.id)}
            className="w-full flex items-center gap-3 px-4 py-3.5 text-left hover:bg-white/3 transition-colors"
          >
            <div className="h-9 w-9 rounded-xl bg-violet-500/10 flex items-center justify-center flex-shrink-0">
              <Target size={15} className="text-violet-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-200 truncate">{c.name}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">
                {c.ad_set_count || 0} ad sets · {c.goal} · {c.tone}
              </p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span className={`text-[10px] px-2 py-0.5 rounded-full border ${
                c.status === 'active'
                  ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                  : 'bg-slate-500/10 border-slate-500/20 text-slate-500'
              }`}>
                {c.status}
              </span>
              <ChevronRight
                size={14}
                className={`text-slate-600 transition-transform ${openId === c.id ? 'rotate-90' : ''}`}
              />
            </div>
          </button>

          {/* Ad sets detail */}
          {openId === c.id && (
            <div className="border-t border-white/5 p-4">
              {detailLoading ? (
                <div className="flex items-center gap-2 text-slate-500 text-xs py-4">
                  <Loader2 size={13} className="animate-spin" /> Loading ad sets…
                </div>
              ) : detail?.ad_sets?.length ? (
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {detail.ad_sets.map((ad) => (
                    <AdSetMini key={ad.id} ad={ad} />
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500 py-4 text-center">No ad sets in this campaign yet.</p>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
