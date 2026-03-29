/**
 * AdModeGenerate — Generate ad sets (Claude copy + DALL-E images).
 */

import React, { useEffect, useState, useCallback } from 'react';
import {
  Sparkles, Loader2, Download, RefreshCw, Copy, CheckCheck,
  Image as ImageIcon, Zap, ChevronDown, ChevronUp
} from 'lucide-react';
import { api } from '../../api/client';
import { toast } from 'sonner';

const GOALS        = ['sales', 'traffic', 'leads', 'awareness'];
const TONES        = ['professional', 'casual', 'bold', 'playful', 'urgent'];
const NUMS         = [1, 2, 3, 4, 5];
const IMAGE_STYLES = [
  'Dark Tech',
  'Product UI / SaaS Dashboard',
  'Solo Founder Workspace',
  'Futuristic AI Interface',
  'Clean Corporate',
  'Startup Team',
  'Minimal Modern',
  'Cinematic',
  'Illustration',
  '3D Render',
  'No Image',
];
const IMAGE_FORMATS  = ['photorealistic', 'illustration', '3D', 'UI mockup'];
const PEOPLE_OPTIONS = [
  { value: 'no',       label: 'No people' },
  { value: 'yes',      label: 'Include people' },
  { value: 'optional', label: 'Optional' },
];
const COPY_ANGLES = [
  { value: '',                  label: 'Auto (best for goal)' },
  { value: 'Direct Response',   label: 'Direct Response' },
  { value: 'Curiosity',         label: 'Curiosity' },
  { value: 'Problem-Solution',  label: 'Problem-Solution' },
  { value: 'Founder Story',     label: 'Founder Story' },
  { value: 'Feature-Driven',    label: 'Feature-Driven' },
];

function inputCls() {
  return 'w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500/40 transition-colors';
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handle = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button onClick={handle} className="text-slate-600 hover:text-slate-400 transition-colors p-1">
      {copied ? <CheckCheck size={12} className="text-emerald-400" /> : <Copy size={12} />}
    </button>
  );
}

function AdSetCard({ ad, campaignId, onRefreshImage, onRefreshCopy }) {
  const [expanded, setExpanded]   = useState(true);
  const [regenImg, setRegenImg]   = useState(false);
  const [regenCopy, setRegenCopy] = useState(false);
  const [imgData, setImgData]     = useState(ad.image_base64);
  const [copy, setCopy]           = useState({
    hook:     ad.hook,
    headline: ad.headline,
    caption:  ad.caption,
    cta:      ad.cta,
  });

  const downloadImage = () => {
    if (!imgData) return;
    const link = document.createElement('a');
    link.href  = `data:image/png;base64,${imgData}`;
    link.download = `ad-${ad.angle || 'creative'}-${ad.id?.slice(0, 6)}.png`;
    link.click();
  };

  const handleRegenImage = async () => {
    setRegenImg(true);
    try {
      const result = await api.adModeRegenerateImage(ad.id, ad.image_prompt);
      setImgData(result.image_base64);
      toast.success('Image regenerated');
    } catch (err) {
      toast.error(err?.message || 'Image regeneration failed');
    } finally {
      setRegenImg(false);
    }
  };

  const handleRegenCopy = async () => {
    setRegenCopy(true);
    try {
      const result = await api.adModeRegenerateCopy(ad.id, campaignId);
      setCopy({
        hook:     result.hook     || copy.hook,
        headline: result.headline || copy.headline,
        caption:  result.caption  || copy.caption,
        cta:      result.cta      || copy.cta,
      });
      toast.success('Copy regenerated');
    } catch (err) {
      toast.error(err?.message || 'Copy regeneration failed');
    } finally {
      setRegenCopy(false);
    }
  };

  return (
    <div className="bg-white/3 border border-white/8 rounded-2xl overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-white/3 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-violet-400 bg-violet-500/10 border border-violet-500/20 rounded-md px-2 py-0.5">
            {ad.angle || 'concept'}
          </span>
          <span className="text-sm text-slate-300 font-medium">{copy.headline}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => { e.stopPropagation(); downloadImage(); }}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/8 transition-colors"
            title="Download image"
            disabled={!imgData}
          >
            <Download size={13} />
          </button>
          {expanded ? <ChevronUp size={14} className="text-slate-600" /> : <ChevronDown size={14} className="text-slate-600" />}
        </div>
      </div>

      {expanded && (
        <div className="border-t border-white/5">
          <div className="grid md:grid-cols-2 gap-0">
            {/* Image panel */}
            <div className="bg-black/20 flex items-center justify-center min-h-48 relative group">
              {imgData ? (
                <>
                  <img
                    src={`data:image/png;base64,${imgData}`}
                    alt={copy.headline}
                    className="w-full h-full object-cover max-h-64"
                  />
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-all flex items-center justify-center opacity-0 group-hover:opacity-100 gap-2">
                    <button
                      onClick={handleRegenImage}
                      disabled={regenImg}
                      className="flex items-center gap-1.5 bg-white/90 text-slate-800 text-xs font-medium px-3 py-1.5 rounded-lg transition-colors hover:bg-white"
                    >
                      {regenImg ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                      New Image
                    </button>
                    <button
                      onClick={downloadImage}
                      className="flex items-center gap-1.5 bg-white/90 text-slate-800 text-xs font-medium px-3 py-1.5 rounded-lg transition-colors hover:bg-white"
                    >
                      <Download size={11} /> Download
                    </button>
                  </div>
                </>
              ) : (
                <div className="flex flex-col items-center gap-2 text-slate-600">
                  <ImageIcon size={24} />
                  <p className="text-xs">No image</p>
                  <button
                    onClick={handleRegenImage}
                    disabled={regenImg}
                    className="flex items-center gap-1.5 text-xs text-violet-400 hover:text-violet-300 transition-colors"
                  >
                    {regenImg ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                    Generate Image
                  </button>
                </div>
              )}
            </div>

            {/* Copy panel */}
            <div className="p-5 space-y-4">
              <CopyField label="Hook" text={copy.hook} />
              <CopyField label="Headline" text={copy.headline} />
              <CopyField label="Caption" text={copy.caption} textarea />
              <CopyField label="CTA" text={copy.cta} badge />

              {/* Regen copy button */}
              <button
                onClick={handleRegenCopy}
                disabled={regenCopy}
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 bg-white/5 hover:bg-white/8 border border-white/10 px-3 py-1.5 rounded-lg transition-colors w-full justify-center"
              >
                {regenCopy
                  ? <><Loader2 size={11} className="animate-spin" /> Regenerating copy…</>
                  : <><RefreshCw size={11} /> Regenerate copy</>
                }
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CopyField({ label, text, textarea, badge }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500">{label}</p>
        <CopyButton text={text || ''} />
      </div>
      {badge ? (
        <span className="inline-block bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs px-3 py-1 rounded-lg font-medium">
          {text}
        </span>
      ) : (
        <p className="text-sm text-slate-300 leading-relaxed">{text}</p>
      )}
    </div>
  );
}

export default function AdModeGenerate({ campaigns }) {
  const [profile, setProfile]     = useState(null);
  const [profileLoading, setPL]   = useState(true);
  const [generating, setGenerating] = useState(false);
  const [adSets, setAdSets]       = useState([]);
  const [activeCampaignId, setActiveCampaignId] = useState('');
  const [newCampaignName, setNewCampaignName]   = useState('');
  const [creatingCampaign, setCreatingCampaign] = useState(false);
  const [campaignList, setCampaignList]         = useState(campaigns || []);

  const [form, setForm] = useState({
    goal:               'sales',
    audience:           '',
    tone:               'bold',
    num_concepts:       3,
    image_style:        'Dark Tech',
    image_format:       'photorealistic',
    visual_consistency: true,
    people_in_image:    'no',
    copy_angle:         '',
  });

  useEffect(() => {
    api.adModeGetProfile()
      .then(({ profile: p }) => setProfile(p))
      .catch(() => {})
      .finally(() => setPL(false));
  }, []);

  useEffect(() => {
    setCampaignList(campaigns || []);
  }, [campaigns]);

  const f = (field) => (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  // When selecting an existing campaign, restore its saved visual + copy settings
  const handleCampaignSelect = (e) => {
    const id = e.target.value;
    setActiveCampaignId(id);
    const cam = campaignList.find(c => c.id === id);
    if (!cam) return;
    setForm(prev => ({
      ...prev,
      goal:               cam.goal               || prev.goal,
      tone:               cam.tone               || prev.tone,
      image_style:        cam.image_style        || prev.image_style,
      image_format:       cam.image_format       || prev.image_format,
      visual_consistency: cam.visual_consistency !== undefined ? cam.visual_consistency : prev.visual_consistency,
      people_in_image:    cam.people_in_image    || prev.people_in_image,
      copy_angle:         cam.copy_angle         || '',
    }));
  };

  const handleCreateCampaign = async () => {
    if (!newCampaignName.trim() || !profile) return;
    setCreatingCampaign(true);
    try {
      const { campaign } = await api.adModeCreateCampaign({
        name:                newCampaignName.trim(),
        business_profile_id: profile.id,
        goal:                form.goal,
        tone:                form.tone,
        image_style:         form.image_style,
        image_format:        form.image_format,
        visual_consistency:  form.visual_consistency,
        people_in_image:     form.people_in_image,
        copy_angle:          form.copy_angle || undefined,
      });
      setCampaignList((prev) => [campaign, ...prev]);
      setActiveCampaignId(campaign.id);
      setNewCampaignName('');
      toast.success('Campaign created');
    } catch (err) {
      toast.error(err?.message || 'Failed to create campaign');
    } finally {
      setCreatingCampaign(false);
    }
  };

  const handleGenerate = async () => {
    if (!profile) {
      toast.error('Set up a brand profile first in the Brand Profile tab.');
      return;
    }
    // Auto-create campaign from the name field if none selected yet
    if (!activeCampaignId) {
      if (!newCampaignName.trim()) {
        toast.error('Enter a campaign name and click + Create first.');
        return;
      }
      // Auto-create then generate
      setCreatingCampaign(true);
      try {
        const { campaign } = await api.adModeCreateCampaign({
          name:                newCampaignName.trim(),
          business_profile_id: profile.id,
          goal:                form.goal,
          tone:                form.tone,
          image_style:         form.image_style,
          image_format:        form.image_format,
          visual_consistency:  form.visual_consistency,
          people_in_image:     form.people_in_image,
          copy_angle:          form.copy_angle || undefined,
        });
        setCampaignList((prev) => [campaign, ...prev]);
        setActiveCampaignId(campaign.id);
        setNewCampaignName('');
        // Continue with generation using the new campaign id
        setGenerating(true);
        setAdSets([]);
        const { ad_sets } = await api.adModeGenerate({
          campaign_id:         campaign.id,
          business_profile_id: profile.id,
          goal:                form.goal || undefined,
          audience:            form.audience || undefined,
          tone:                form.tone || undefined,
          num_concepts:        Number(form.num_concepts),
          image_style:         form.image_style,
          image_format:        form.image_format,
          visual_consistency:  form.visual_consistency,
          people_in_image:     form.people_in_image,
          copy_angle:          form.copy_angle || undefined,
        });
        setAdSets(ad_sets);
        toast.success(`Generated ${ad_sets.length} ad concepts`);
      } catch (err) {
        toast.error(err?.message || 'Failed');
      } finally {
        setCreatingCampaign(false);
        setGenerating(false);
      }
      return;
    }
    setGenerating(true);
    setAdSets([]);
    try {
      const { ad_sets } = await api.adModeGenerate({
        campaign_id:         activeCampaignId,
        business_profile_id: profile.id,
        goal:                form.goal || undefined,
        audience:            form.audience || undefined,
        tone:                form.tone || undefined,
        num_concepts:        Number(form.num_concepts),
        image_style:         form.image_style,
        image_format:        form.image_format,
        visual_consistency:  form.visual_consistency,
        people_in_image:     form.people_in_image,
        copy_angle:          form.copy_angle || undefined,
      });
      setAdSets(ad_sets);
      toast.success(`Generated ${ad_sets.length} ad concepts`);
    } catch (err) {
      toast.error(err?.message || 'Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  if (profileLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500 gap-2">
        <Loader2 size={16} className="animate-spin" /> Loading…
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center gap-3">
        <Sparkles size={28} className="text-violet-400" />
        <p className="text-slate-300 font-medium">No Brand Profile Yet</p>
        <p className="text-sm text-slate-500">Generate your brand profile in the Brand Profile tab first.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Settings panel */}
      <div className="bg-white/3 border border-white/8 rounded-2xl p-5">
        <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-4">
          Campaign &amp; Generation Settings
        </p>

        {/* Campaign select / create */}
        <div className="mb-4">
          <label className="block text-xs text-slate-400 mb-1.5 font-medium">Campaign</label>
          {campaignList.length > 0 && (
            <select
              value={activeCampaignId}
              onChange={handleCampaignSelect}
              className={inputCls()}
            >
              <option value="" className="bg-[#111118]">— Select a campaign —</option>
              {campaignList.map((c) => (
                <option key={c.id} value={c.id} className="bg-[#111118]">{c.name}</option>
              ))}
            </select>
          )}
          <div className="flex gap-2 mt-2">
            <input
              value={newCampaignName}
              onChange={(e) => setNewCampaignName(e.target.value)}
              placeholder="New campaign name…"
              className={inputCls()}
            />
            <button
              onClick={handleCreateCampaign}
              disabled={!newCampaignName.trim() || creatingCampaign}
              className="flex-shrink-0 flex items-center gap-1.5 bg-white/8 hover:bg-white/12 border border-white/10 text-slate-200 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors disabled:opacity-50"
            >
              {creatingCampaign ? <Loader2 size={13} className="animate-spin" /> : '+ Create'}
            </button>
          </div>
        </div>

        {/* Goal / Tone / Audience / Count */}
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1.5 font-medium">Goal</label>
            <select value={form.goal} onChange={f('goal')} className={inputCls()}>
              {GOALS.map((g) => <option key={g} value={g} className="bg-[#111118]">{g}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1.5 font-medium">Tone</label>
            <select value={form.tone} onChange={f('tone')} className={inputCls()}>
              {TONES.map((t) => <option key={t} value={t} className="bg-[#111118]">{t}</option>)}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1.5 font-medium">Target Audience <span className="text-slate-600">(optional)</span></label>
            <input
              value={form.audience}
              onChange={f('audience')}
              placeholder={profile?.audience || 'e.g. solo founders 25–40'}
              className={inputCls()}
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1.5 font-medium">Ad Concepts</label>
            <select value={form.num_concepts} onChange={f('num_concepts')} className={inputCls()}>
              {NUMS.map((n) => <option key={n} value={n} className="bg-[#111118]">{n} concept{n > 1 ? 's' : ''}</option>)}
            </select>
          </div>
        </div>

        {/* Copy Angle */}
        <div className="mb-3">
          <label className="block text-xs text-slate-400 mb-1.5 font-medium">Copy Angle</label>
          <select value={form.copy_angle} onChange={f('copy_angle')} className={inputCls()}>
            {COPY_ANGLES.map((a) => <option key={a.value} value={a.value} className="bg-[#111118]">{a.label}</option>)}
          </select>
        </div>

        {/* Image controls */}
        <div className="border-t border-white/5 pt-4 mt-1">
          <p className="text-[10px] font-mono uppercase tracking-widest text-slate-600 mb-3">Image Settings</p>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1.5 font-medium">Image Style</label>
              <select value={form.image_style} onChange={f('image_style')} className={inputCls()}>
                {IMAGE_STYLES.map((s) => <option key={s} value={s} className="bg-[#111118]">{s}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5 font-medium">Image Format</label>
              <select value={form.image_format} onChange={f('image_format')} className={inputCls()}>
                {IMAGE_FORMATS.map((s) => <option key={s} value={s} className="bg-[#111118]">{s}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1.5 font-medium">People in Image</label>
              <select value={form.people_in_image} onChange={f('people_in_image')} className={inputCls()}>
                {PEOPLE_OPTIONS.map((o) => <option key={o.value} value={o.value} className="bg-[#111118]">{o.label}</option>)}
              </select>
            </div>
            <div className="flex flex-col justify-end pb-0.5">
              <label className="block text-xs text-slate-400 mb-1.5 font-medium">Visual Consistency</label>
              <button
                type="button"
                onClick={() => setForm(prev => ({ ...prev, visual_consistency: !prev.visual_consistency }))}
                className={`flex items-center gap-2 px-3 py-2.5 rounded-xl border text-sm font-medium transition-all ${
                  form.visual_consistency
                    ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400'
                    : 'bg-white/5 border-white/10 text-slate-500'
                }`}
              >
                <span className={`w-3 h-3 rounded-full flex-shrink-0 ${form.visual_consistency ? 'bg-cyan-400' : 'bg-slate-600'}`} />
                {form.visual_consistency ? 'Same style across all' : 'Independent styles'}
              </button>
            </div>
          </div>
        </div>

        {/* Generate button */}
        <div className="mt-5">
          <button
            onClick={handleGenerate}
            disabled={generating || creatingCampaign}
            className="w-full flex items-center justify-center gap-2 bg-violet-500 hover:bg-violet-400 text-white px-5 py-3 rounded-xl text-sm font-semibold transition-colors disabled:opacity-50"
          >
            {generating
              ? <><Loader2 size={15} className="animate-spin" /> Generating ads…</>
              : <><Sparkles size={15} /> Generate Ads</>
            }
          </button>
          {generating && (
            <p className="text-center text-[11px] text-slate-500 mt-2">
              Claude is writing copy · DALL·E is generating images · This takes ~30–60s
            </p>
          )}
        </div>
      </div>

      {/* Results */}
      {adSets.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
              {adSets.length} ad concept{adSets.length > 1 ? 's' : ''} generated
            </p>
          </div>
          {adSets.map((ad) => (
            <AdSetCard key={ad.id} ad={ad} campaignId={activeCampaignId} />
          ))}
        </div>
      )}
    </div>
  );
}
