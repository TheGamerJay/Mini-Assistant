import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { Wand2, Check, Copy, Palette, FileJson, FileText, TestTube } from 'lucide-react';
import { usePersist } from '../../hooks/usePersist';

const DevTools = () => {
  const [activeToolTab, setActiveToolTab] = usePersist('ma_devtools_tab', 'regex');

  // Regex Tester State
  const [regex, setRegex] = usePersist('ma_devtools_regex', '');
  const [regexFlags, setRegexFlags] = usePersist('ma_devtools_flags', 'g');
  const [testString, setTestString] = usePersist('ma_devtools_teststr', '');
  const [regexMatches, setRegexMatches] = useState([]);

  // JSON Formatter State
  const [jsonInput, setJsonInput] = usePersist('ma_devtools_json', '');
  const [jsonOutput, setJsonOutput] = useState('');
  const [jsonError, setJsonError] = useState('');

  // Markdown State
  const [markdown, setMarkdown] = usePersist('ma_devtools_md', '# Hello Mini Assistant\n\nThis is **bold** and this is *italic*.\n\n- List item 1\n- List item 2\n\n```javascript\nconsole.log("Code block");\n```');

  // Color Picker State
  const [selectedColor, setSelectedColor] = usePersist('ma_devtools_color', '#00f3ff');
  const [colorFormats, setColorFormats] = useState({});

  // Regex Tester Functions
  const testRegex = () => {
    if (!regex.trim()) {
      toast.error('Enter a regex pattern');
      return;
    }
    try {
      const re = new RegExp(regex, regexFlags);
      const matches = [...testString.matchAll(re)];
      setRegexMatches(matches);
      toast.success(`Found ${matches.length} match(es)`);
    } catch (error) {
      toast.error('Invalid regex pattern');
      setRegexMatches([]);
    }
  };

  // JSON Formatter Functions
  const formatJSON = () => {
    try {
      const parsed = JSON.parse(jsonInput);
      setJsonOutput(JSON.stringify(parsed, null, 2));
      setJsonError('');
      toast.success('JSON formatted');
    } catch (error) {
      setJsonError(error.message);
      toast.error('Invalid JSON');
    }
  };

  const minifyJSON = () => {
    try {
      const parsed = JSON.parse(jsonInput);
      setJsonOutput(JSON.stringify(parsed));
      setJsonError('');
      toast.success('JSON minified');
    } catch (error) {
      setJsonError(error.message);
    }
  };

  const copyJSON = () => {
    navigator.clipboard.writeText(jsonOutput);
    toast.success('Copied!');
  };

  // Markdown Functions
  const renderMarkdown = (text) => {
    let html = text
      .replace(/^### (.*$)/gim, '<h3 class="text-lg font-bold text-cyan-400 mb-2">$1</h3>')
      .replace(/^## (.*$)/gim, '<h2 class="text-xl font-bold text-cyan-400 mb-3">$1</h2>')
      .replace(/^# (.*$)/gim, '<h1 class="text-2xl font-bold text-cyan-400 mb-4">$1</h1>')
      .replace(/\*\*(.*)\*\*/gim, '<strong class="font-bold text-violet-400">$1</strong>')
      .replace(/\*(.*)\*/gim, '<em class="italic text-slate-300">$1</em>')
      .replace(/^- (.*$)/gim, '<li class="ml-4 text-slate-300">• $1</li>')
      .replace(/```(\w+)?\n([\s\S]*?)```/gim, '<pre class="bg-black/50 border border-cyan-900/30 p-4 rounded my-4 overflow-auto"><code class="text-sm font-mono text-cyan-100">$2</code></pre>')
      .replace(/`([^`]+)`/gim, '<code class="bg-cyan-500/10 text-cyan-400 px-2 py-1 rounded text-sm font-mono">$1</code>')
      .replace(/\n/g, '<br />');
    return html;
  };

  // Color Functions
  const hexToRgb = (hex) => {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
      r: parseInt(result[1], 16),
      g: parseInt(result[2], 16),
      b: parseInt(result[3], 16)
    } : null;
  };

  const rgbToHsl = (r, g, b) => {
    r /= 255;
    g /= 255;
    b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    let h, s, l = (max + min) / 2;

    if (max === min) {
      h = s = 0;
    } else {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      switch (max) {
        case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
        case g: h = ((b - r) / d + 2) / 6; break;
        case b: h = ((r - g) / d + 4) / 6; break;
        default: h = 0;
      }
    }

    return {
      h: Math.round(h * 360),
      s: Math.round(s * 100),
      l: Math.round(l * 100)
    };
  };

  const updateColorFormats = (hex) => {
    const rgb = hexToRgb(hex);
    if (rgb) {
      const hsl = rgbToHsl(rgb.r, rgb.g, rgb.b);
      setColorFormats({
        hex: hex,
        rgb: `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})`,
        rgba: `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 1)`,
        hsl: `hsl(${hsl.h}, ${hsl.s}%, ${hsl.l}%)`
      });
    }
  };

  useEffect(() => {
    updateColorFormats(selectedColor);
  }, [selectedColor]);

  const copyColor = (format) => {
    navigator.clipboard.writeText(colorFormats[format]);
    toast.success(`${format.toUpperCase()} copied!`);
  };

  const toolTabs = [
    { id: 'regex', label: 'REGEX TESTER', icon: TestTube },
    { id: 'json', label: 'JSON FORMATTER', icon: FileJson },
    { id: 'markdown', label: 'MARKDOWN', icon: FileText },
    { id: 'color', label: 'COLOR PICKER', icon: Palette },
  ];

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50" data-testid="dev-tools">
      <div className="p-6 border-b border-cyan-500/20 bg-black/40">
        <div className="flex items-center gap-3 mb-6">
          <Wand2 className="w-7 h-7 text-cyan-400" />
          <div>
            <h2 className="text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
              DEV UTILITIES
            </h2>
            <p className="text-xs text-slate-400 font-mono mt-1">ESSENTIAL DEVELOPER TOOLS</p>
          </div>
        </div>

        <div className="flex gap-2">
          {toolTabs.map(tab => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveToolTab(tab.id)}
                className={`px-4 py-2 rounded-sm text-xs font-bold uppercase transition-all ${
                  activeToolTab === tab.id
                    ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                    : 'bg-black/30 text-slate-400 hover:text-cyan-400'
                }`}
              >
                <Icon className="w-4 h-4 inline mr-2" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {/* REGEX TESTER */}
        {activeToolTab === 'regex' && (
          <div className="space-y-4">
            <div>
              <label className="text-sm text-cyan-400 font-mono uppercase mb-2 block">Regex Pattern</label>
              <div className="flex gap-3">
                <input
                  placeholder="Enter regex pattern (e.g., \d+|[a-z]+)"
                  value={regex}
                  onChange={(e) => setRegex(e.target.value)}
                  className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono px-4 py-3 outline-none"
                />
                <input
                  placeholder="Flags"
                  value={regexFlags}
                  onChange={(e) => setRegexFlags(e.target.value)}
                  className="w-20 bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono px-3 py-3 outline-none text-center"
                />
                <button
                  onClick={testRegex}
                  className="px-6 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase"
                >
                  TEST
                </button>
              </div>
            </div>

            <div>
              <label className="text-sm text-cyan-400 font-mono uppercase mb-2 block">Test String</label>
              <textarea
                placeholder="Enter text to test against..."
                value={testString}
                onChange={(e) => setTestString(e.target.value)}
                className="w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono p-4 outline-none resize-none"
                rows={6}
              />
            </div>

            {regexMatches.length > 0 && (
              <div>
                <label className="text-sm text-cyan-400 font-mono uppercase mb-2 block">Matches ({regexMatches.length})</label>
                <div className="space-y-2">
                  {regexMatches.map((match, idx) => (
                    <div key={idx} className="p-3 bg-green-500/10 border border-green-500/30 rounded">
                      <div className="text-xs text-green-400 mb-1">Match {idx + 1} at index {match.index}</div>
                      <div className="text-sm text-green-100 font-mono">{match[0]}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* JSON FORMATTER */}
        {activeToolTab === 'json' && (
          <div className="grid grid-cols-2 gap-6 h-full">
            <div className="flex flex-col">
              <label className="text-sm text-cyan-400 font-mono uppercase mb-2">Input JSON</label>
              <textarea
                placeholder='{ "key": "value" }'
                value={jsonInput}
                onChange={(e) => setJsonInput(e.target.value)}
                className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono p-4 outline-none resize-none"
              />
              <div className="flex gap-2 mt-3">
                <button
                  onClick={formatJSON}
                  className="flex-1 px-4 py-2 bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 hover:bg-cyan-500/30 rounded-sm uppercase text-sm font-semibold"
                >
                  FORMAT
                </button>
                <button
                  onClick={minifyJSON}
                  className="flex-1 px-4 py-2 bg-violet-500/20 text-violet-400 border border-violet-500/50 hover:bg-violet-500/30 rounded-sm uppercase text-sm font-semibold"
                >
                  MINIFY
                </button>
              </div>
              {jsonError && (
                <div className="mt-2 p-2 bg-red-500/10 border border-red-500/30 rounded text-xs text-red-400">
                  {jsonError}
                </div>
              )}
            </div>

            <div className="flex flex-col">
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm text-cyan-400 font-mono uppercase">Output</label>
                {jsonOutput && (
                  <button
                    onClick={copyJSON}
                    className="text-xs text-violet-400 hover:text-violet-300 flex items-center gap-1"
                  >
                    <Copy className="w-3 h-3" /> COPY
                  </button>
                )}
              </div>
              <pre className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono p-4 overflow-auto">
                {jsonOutput || 'Formatted JSON will appear here...'}
              </pre>
            </div>
          </div>
        )}

        {/* MARKDOWN PREVIEW */}
        {activeToolTab === 'markdown' && (
          <div className="grid grid-cols-2 gap-6 h-full">
            <div className="flex flex-col">
              <label className="text-sm text-cyan-400 font-mono uppercase mb-2">Markdown Editor</label>
              <textarea
                value={markdown}
                onChange={(e) => setMarkdown(e.target.value)}
                className="flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono p-4 outline-none resize-none text-sm"
              />
            </div>

            <div className="flex flex-col">
              <label className="text-sm text-cyan-400 font-mono uppercase mb-2">Preview</label>
              <div 
                className="flex-1 bg-black/50 border border-cyan-900/50 rounded-sm p-6 overflow-auto"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(markdown) }}
              />
            </div>
          </div>
        )}

        {/* COLOR PICKER */}
        {activeToolTab === 'color' && (
          <div className="max-w-2xl mx-auto space-y-6">
            <div className="flex items-center gap-6">
              <div className="flex-1">
                <label className="text-sm text-cyan-400 font-mono uppercase mb-2 block">Pick Color</label>
                <input
                  type="color"
                  value={selectedColor}
                  onChange={(e) => setSelectedColor(e.target.value)}
                  className="w-full h-32 rounded-lg border-4 border-cyan-500/50 cursor-pointer"
                />
              </div>
              <div 
                className="w-64 h-32 rounded-lg border-4 border-cyan-500/50"
                style={{ backgroundColor: selectedColor }}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              {Object.entries(colorFormats).map(([format, value]) => (
                <div key={format} className="p-4 bg-black/40 border border-cyan-900/30 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-cyan-400 font-mono uppercase">{format}</span>
                    <button
                      onClick={() => copyColor(format)}
                      className="p-1 text-violet-400 hover:text-violet-300"
                    >
                      <Copy className="w-3 h-3" />
                    </button>
                  </div>
                  <code className="text-sm text-slate-300 font-mono">{value}</code>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DevTools;
