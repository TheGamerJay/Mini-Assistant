/**
 * AdModeBrandProfile — business profile setup and editing.
 */

import React, { useEffect, useState } from 'react';
import { Sparkles, Loader2, Check, Edit3, RefreshCw, Save } from 'lucide-react';
import { api } from '../../api/client';
import { toast } from 'sonner';

const GOALS = ['sales', 'traffic', 'leads', 'awareness'];
const TONES = ['professional', 'casual', 'bold', 'playful', 'urgent'];

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs text-slate-400 mb-1.5 font-medium">{label}</label>
      {children}
    </div>
  );
}

function inputCls() {
  return 'w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500/40 transition-colors';
}

export default function AdModeBrandProfile() {
  const [profile, setProfile]     = useState(null);
  const [loading, setLoading]     = useState(true);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving]       = useState(false);
  const [editMode, setEditMode]   = useState(false);

  // Form state
  const [form, setForm] = useState({
    business_name: '',
    product_name:  '',
    description:   '',
    audience:      '',
    goal:          'sales',
    tone:          'professional',
    website_url:   '',
  });

  useEffect(() => {
    api.adModeGetProfile()
      .then(({ profile: p }) => { setProfile(p); populateForm(p); })
      .catch(() => { /* no profile yet */ })
      .finally(() => setLoading(false));
  }, []);

  function populateForm(p) {
    setForm({
      business_name: p.business_name || '',
      product_name:  p.product_name  || '',
      description:   p.description   || '',
      audience:      p.audience       || '',
      goal:          p.goal           || 'sales',
      tone:          p.tone           || 'professional',
      website_url:   p.website_url    || '',
    });
  }

  const handleGenerate = async () => {
    if (!form.business_name || !form.description || !form.audience) {
      toast.error('Please fill in business name, description, and target audience');
      return;
    }
    setGenerating(true);
    try {
      const { profile: p } = await api.adModeProfileGenerate(form);
      setProfile(p);
      populateForm(p);
      setEditMode(false);
      toast.success('Brand profile generated!');
    } catch (err) {
      toast.error(err?.message || 'Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveEdits = async () => {
    setSaving(true);
    try {
      const { profile: p } = await api.adModeUpdateProfile(form);
      setProfile(p);
      setEditMode(false);
      toast.success('Profile saved');
    } catch (err) {
      toast.error(err?.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const f = (field) => (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500 gap-2">
        <Loader2 size={16} className="animate-spin" /> Loading profile…
      </div>
    );
  }

  const generatedData = profile?.generated_profile;

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-100">Brand Profile</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {profile ? 'Your business profile powers all ad generation.' : 'Set up your brand profile to start generating ads.'}
          </p>
        </div>
        {profile && !editMode && (
          <button
            onClick={() => setEditMode(true)}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 bg-white/5 hover:bg-white/8 border border-white/10 px-3 py-1.5 rounded-lg transition-colors"
          >
            <Edit3 size={12} /> Edit
          </button>
        )}
      </div>

      {/* Business Info Form */}
      {(!profile || editMode) && (
        <div className="bg-white/3 border border-white/8 rounded-2xl p-5 space-y-4">
          <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
            Business Information
          </p>

          <div className="grid grid-cols-2 gap-4">
            <Field label="Business Name *">
              <input value={form.business_name} onChange={f('business_name')}
                placeholder="Acme Corp" className={inputCls()} />
            </Field>
            <Field label="Product / Service *">
              <input value={form.product_name} onChange={f('product_name')}
                placeholder="CRM Software" className={inputCls()} />
            </Field>
          </div>

          <Field label="Short Description *">
            <textarea value={form.description} onChange={f('description')}
              placeholder="We help small businesses manage customer relationships with AI-powered automation…"
              rows={3} className={`${inputCls()} resize-none`} />
          </Field>

          <Field label="Target Audience *">
            <input value={form.audience} onChange={f('audience')}
              placeholder="Small business owners aged 30–55, struggling with customer follow-ups"
              className={inputCls()} />
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <Field label="Primary Goal">
              <select value={form.goal} onChange={f('goal')} className={inputCls()}>
                {GOALS.map((g) => (
                  <option key={g} value={g} className="bg-[#111118]">
                    {g.charAt(0).toUpperCase() + g.slice(1)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Brand Tone">
              <select value={form.tone} onChange={f('tone')} className={inputCls()}>
                {TONES.map((t) => (
                  <option key={t} value={t} className="bg-[#111118]">
                    {t.charAt(0).toUpperCase() + t.slice(1)}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <Field label="Website URL (optional)">
            <input value={form.website_url} onChange={f('website_url')}
              placeholder="https://yoursite.com" type="url" className={inputCls()} />
          </Field>

          <div className="flex gap-2 pt-1">
            <button
              onClick={handleGenerate}
              disabled={generating}
              className="flex items-center gap-2 bg-violet-500 hover:bg-violet-400 text-white px-5 py-2.5 rounded-xl text-sm font-medium transition-colors disabled:opacity-50"
            >
              {generating
                ? <><Loader2 size={14} className="animate-spin" /> Generating…</>
                : <><Sparkles size={14} /> {profile ? 'Regenerate Profile' : 'Generate Profile'}</>
              }
            </button>
            {editMode && (
              <>
                <button
                  onClick={handleSaveEdits}
                  disabled={saving}
                  className="flex items-center gap-2 bg-white/8 hover:bg-white/12 border border-white/10 text-slate-200 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors disabled:opacity-50"
                >
                  {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                  Save Changes
                </button>
                <button
                  onClick={() => { setEditMode(false); populateForm(profile); }}
                  className="text-sm text-slate-500 hover:text-slate-300 px-3 transition-colors"
                >
                  Cancel
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Generated Profile Display */}
      {generatedData && !editMode && (
        <div className="space-y-4">
          {generatedData.core_identity && (
            <ProfileSection title="Core Identity" text={generatedData.core_identity} />
          )}
          {generatedData.positioning && (
            <ProfileSection title="Positioning" text={generatedData.positioning} />
          )}
          {generatedData.key_selling_points?.length > 0 && (
            <div className="bg-white/3 border border-white/8 rounded-xl p-4">
              <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-3">Key Selling Points</p>
              <ul className="space-y-1.5">
                {generatedData.key_selling_points.map((pt, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                    <Check size={13} className="text-emerald-400 mt-0.5 flex-shrink-0" /> {pt}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {generatedData.audience_summary && (
            <ProfileSection title="Audience Summary" text={generatedData.audience_summary} />
          )}
          {generatedData.competitive_angle && (
            <ProfileSection title="Competitive Angle" text={generatedData.competitive_angle} />
          )}
          {generatedData.recommended_ad_directions?.length > 0 && (
            <div className="bg-white/3 border border-white/8 rounded-xl p-4">
              <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-3">
                Recommended Ad Directions
              </p>
              <div className="space-y-2">
                {generatedData.recommended_ad_directions.map((d, i) => (
                  <div key={i} className="flex gap-3">
                    <span className="text-[10px] font-mono text-violet-400 bg-violet-500/10 border border-violet-500/20 rounded-md px-2 py-1 flex-shrink-0 mt-0.5 h-fit">
                      {d.angle}
                    </span>
                    <p className="text-xs text-slate-400 leading-relaxed">{d.rationale}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          {generatedData.brand_voice_guidelines && (
            <ProfileSection title="Brand Voice Guidelines" text={generatedData.brand_voice_guidelines} />
          )}
        </div>
      )}
    </div>
  );
}

function ProfileSection({ title, text }) {
  return (
    <div className="bg-white/3 border border-white/8 rounded-xl p-4">
      <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2">{title}</p>
      <p className="text-sm text-slate-300 leading-relaxed">{text}</p>
    </div>
  );
}
