import React, { useState } from 'react';
import { toast } from 'sonner';
import { Wand2, Check, Copy, Palette, FileJson, FileText, TestTube } from 'lucide-react';

const DevTools = () => {
  const [activeToolTab, setActiveToolTab] = useState('regex');

  // Regex Tester State
  const [regex, setRegex] = useState('');
  const [regexFlags, setRegexFlags] = useState('g');
  const [testString, setTestString] = useState('');
  const [regexMatches, setRegexMatches] = useState([]);

  // JSON Formatter State
  const [jsonInput, setJsonInput] = useState('');
  const [jsonOutput, setJsonOutput] = useState('');
  const [jsonError, setJsonError] = useState('');

  // Markdown State
  const [markdown, setMarkdown] = useState('# Hello Mini Assistant\n\nThis is **bold** and this is *italic*.\n\n- List item 1\n- List item 2\n\n```javascript\nconsole.log("Code block");\n```');

  // Color Picker State
  const [selectedColor, setSelectedColor] = useState('#00f3ff');
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
    // Simple markdown parser
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

  React.useEffect(() => {
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
    <div className=\"h-full flex flex-col bg-[#0a0a0f]/50\" data-testid=\"dev-tools\">
      <div className=\"p-6 border-b border-cyan-500/20 bg-black/40\">
        <div className=\"flex items-center gap-3 mb-6\">
          <Wand2 className=\"w-7 h-7 text-cyan-400\" />
          <div>
            <h2 className=\"text-2xl font-bold text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text uppercase\" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
              DEV UTILITIES
            </h2>
            <p className=\"text-xs text-slate-400 font-mono mt-1\">ESSENTIAL DEVELOPER TOOLS</p>
          </div>
        </div>

        <div className=\"flex gap-2\">
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
                <Icon className=\"w-4 h-4 inline mr-2\" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className=\"flex-1 overflow-auto p-6\">
        {/* REGEX TESTER */}
        {activeToolTab === 'regex' && (
          <div className=\"space-y-4\">
            <div>
              <label className=\"text-sm text-cyan-400 font-mono uppercase mb-2 block\">Regex Pattern</label>
              <div className=\"flex gap-3\">
                <input
                  placeholder="Enter regex pattern (e.g., \d+|[a-z]+)"
                  value={regex}
                  onChange={(e) => setRegex(e.target.value)}\n                  className=\"flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono px-4 py-3 outline-none\"\n                />\n                <input\n                  placeholder=\"Flags\"\n                  value={regexFlags}\n                  onChange={(e) => setRegexFlags(e.target.value)}\n                  className=\"w-20 bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono px-3 py-3 outline-none text-center\"\n                />\n                <button\n                  onClick={testRegex}\n                  className=\"px-6 bg-gradient-to-r from-cyan-500 to-violet-600 text-white font-bold hover:from-cyan-400 hover:to-violet-500 rounded-sm uppercase\"\n                >\n                  TEST\n                </button>\n              </div>\n            </div>\n\n            <div>\n              <label className=\"text-sm text-cyan-400 font-mono uppercase mb-2 block\">Test String</label>\n              <textarea\n                placeholder=\"Enter text to test against...\"\n                value={testString}\n                onChange={(e) => setTestString(e.target.value)}\n                className=\"w-full bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono p-4 outline-none resize-none\"\n                rows={6}\n              />\n            </div>\n\n            {regexMatches.length > 0 && (\n              <div>\n                <label className=\"text-sm text-cyan-400 font-mono uppercase mb-2 block\">Matches ({regexMatches.length})</label>\n                <div className=\"space-y-2\">\n                  {regexMatches.map((match, idx) => (\n                    <div key={idx} className=\"p-3 bg-green-500/10 border border-green-500/30 rounded\">\n                      <div className=\"text-xs text-green-400 mb-1\">Match {idx + 1} at index {match.index}</div>\n                      <div className=\"text-sm text-green-100 font-mono\">{match[0]}</div>\n                    </div>\n                  ))}\n                </div>\n              </div>\n            )}\n          </div>\n        )}\n\n        {/* JSON FORMATTER */}\n        {activeToolTab === 'json' && (\n          <div className=\"grid grid-cols-2 gap-6 h-full\">\n            <div className=\"flex flex-col\">\n              <label className=\"text-sm text-cyan-400 font-mono uppercase mb-2\">Input JSON</label>\n              <textarea\n                placeholder='{ \"key\": \"value\" }'\n                value={jsonInput}\n                onChange={(e) => setJsonInput(e.target.value)}\n                className=\"flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 placeholder:text-cyan-900/50 rounded-sm font-mono p-4 outline-none resize-none\"\n              />\n              <div className=\"flex gap-2 mt-3\">\n                <button\n                  onClick={formatJSON}\n                  className=\"flex-1 px-4 py-2 bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 hover:bg-cyan-500/30 rounded-sm uppercase text-sm font-semibold\"\n                >\n                  FORMAT\n                </button>\n                <button\n                  onClick={minifyJSON}\n                  className=\"flex-1 px-4 py-2 bg-violet-500/20 text-violet-400 border border-violet-500/50 hover:bg-violet-500/30 rounded-sm uppercase text-sm font-semibold\"\n                >\n                  MINIFY\n                </button>\n              </div>\n              {jsonError && (\n                <div className=\"mt-2 p-2 bg-red-500/10 border border-red-500/30 rounded text-xs text-red-400\">\n                  {jsonError}\n                </div>\n              )}\n            </div>\n\n            <div className=\"flex flex-col\">\n              <div className=\"flex items-center justify-between mb-2\">\n                <label className=\"text-sm text-cyan-400 font-mono uppercase\">Output</label>\n                {jsonOutput && (\n                  <button\n                    onClick={copyJSON}\n                    className=\"text-xs text-violet-400 hover:text-violet-300 flex items-center gap-1\"\n                  >\n                    <Copy className=\"w-3 h-3\" /> COPY\n                  </button>\n                )}\n              </div>\n              <pre className=\"flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono p-4 overflow-auto\">\n                {jsonOutput || 'Formatted JSON will appear here...'}\n              </pre>\n            </div>\n          </div>\n        )}\n\n        {/* MARKDOWN PREVIEW */}\n        {activeToolTab === 'markdown' && (\n          <div className=\"grid grid-cols-2 gap-6 h-full\">\n            <div className=\"flex flex-col\">\n              <label className=\"text-sm text-cyan-400 font-mono uppercase mb-2\">Markdown Editor</label>\n              <textarea\n                value={markdown}\n                onChange={(e) => setMarkdown(e.target.value)}\n                className=\"flex-1 bg-black/50 border border-cyan-900/50 text-cyan-100 rounded-sm font-mono p-4 outline-none resize-none text-sm\"\n              />\n            </div>\n\n            <div className=\"flex flex-col\">\n              <label className=\"text-sm text-cyan-400 font-mono uppercase mb-2\">Preview</label>\n              <div \n                className=\"flex-1 bg-black/50 border border-cyan-900/50 rounded-sm p-6 overflow-auto\"\n                dangerouslySetInnerHTML={{ __html: renderMarkdown(markdown) }}\n              />\n            </div>\n          </div>\n        )}\n\n        {/* COLOR PICKER */}\n        {activeToolTab === 'color' && (\n          <div className=\"max-w-2xl mx-auto space-y-6\">\n            <div className=\"flex items-center gap-6\">\n              <div className=\"flex-1\">\n                <label className=\"text-sm text-cyan-400 font-mono uppercase mb-2 block\">Pick Color</label>\n                <input\n                  type=\"color\"\n                  value={selectedColor}\n                  onChange={(e) => setSelectedColor(e.target.value)}\n                  className=\"w-full h-32 rounded-lg border-4 border-cyan-500/50 cursor-pointer\"\n                />\n              </div>\n              <div \n                className=\"w-64 h-32 rounded-lg border-4 border-cyan-500/50\"\n                style={{ backgroundColor: selectedColor }}\n              />\n            </div>\n\n            <div className=\"grid grid-cols-2 gap-4\">\n              {Object.entries(colorFormats).map(([format, value]) => (\n                <div key={format} className=\"p-4 bg-black/40 border border-cyan-900/30 rounded-lg\">\n                  <div className=\"flex items-center justify-between mb-2\">\n                    <span className=\"text-xs text-cyan-400 font-mono uppercase\">{format}</span>\n                    <button\n                      onClick={() => copyColor(format)}\n                      className=\"p-1 text-violet-400 hover:text-violet-300\"\n                    >\n                      <Copy className=\"w-3 h-3\" />\n                    </button>\n                  </div>\n                  <code className=\"text-sm text-slate-300 font-mono\">{value}</code>\n                </div>\n              ))}\n            </div>\n          </div>\n        )}\n      </div>\n    </div>\n  );\n};\n\nexport default DevTools;