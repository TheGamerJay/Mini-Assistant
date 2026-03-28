/**
 * components/ChatInput.js
 * Textarea-based message input bar with slash commands, image attach, mic, and model selector.
 *
 * Props:
 *   onSubmit(text, imageBase64, preferredModel) — called when user sends
 *   loading                                     — disables while in-flight
 *   variant: 'home'|'chat'
 *   placeholder
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Paperclip, Mic, MicOff, Send, Loader2, X, Image, FileText, Hammer, MessageSquare, Clock, Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '../api/client';
import { useApp } from '../context/AppContext';

// Known slash commands — mirrors backend command_parser.py
const SLASH_COMMANDS = [
  { cmd: '/chat',    desc: 'Normal conversation' },
  { cmd: '/search',  desc: 'Search the web' },
  { cmd: '/image',   desc: 'Generate an image' },
  { cmd: '/analyze', desc: 'Analyze attached image' },
  { cmd: '/code',    desc: 'Write or explain code' },
  { cmd: '/fix',     desc: 'Debug an error or issue' },
  { cmd: '/plan',    desc: 'Plan a multi-step task' },
  { cmd: '/build',   desc: 'Build a web app' },
  { cmd: '/files',   desc: 'Inspect project files' },
  { cmd: '/context', desc: 'Show project context scan' },
  { cmd: '/help',    desc: 'Show all commands' },
];

const ACCEPTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
const ALL_MEDIA_TYPES      = [...ACCEPTED_IMAGE_TYPES];
const ACCEPTED_DOC_TYPES   = ['application/pdf', 'text/plain', 'text/markdown', 'text/csv'];
const ACCEPTED_DOC_EXTS    = ['.pdf', '.txt', '.md', '.csv'];
const MAX_IMAGE_SIZE_MB = 15;
const MAX_DOC_SIZE_MB = 20;

// ── Image helpers ─────────────────────────────────────────────────────────────

/**
 * Resize + JPEG-compress an image file using a canvas.
 * Returns { base64, preview } — both are compressed JPEG data URIs/strings.
 * Max dimension: 800px. Quality: 0.75.
 */
function compressImageFile(file, maxPx = 800, quality = 0.75) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = (e) => {
      const img = new window.Image();
      img.onerror = reject;
      img.onload = () => {
        const { naturalWidth: w, naturalHeight: h } = img;
        const scale = Math.min(1, maxPx / Math.max(w, h));
        const cw = Math.round(w * scale);
        const ch = Math.round(h * scale);
        const canvas = document.createElement('canvas');
        canvas.width = cw;
        canvas.height = ch;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, cw, ch);
        const dataUrl = canvas.toDataURL('image/jpeg', quality);
        resolve({
          base64: dataUrl.split(',')[1],
          preview: dataUrl,
        });
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  });
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// ── Component ─────────────────────────────────────────────────────────────────

function ChatInput({ onSubmit, loading = false, variant = 'chat', placeholder, chatMode = null, onChatModeChange }) {
  const { pendingTemplate, pendingAutoSubmit, clearPendingTemplate, clearPendingAutoSubmit,
          pendingChatMode, clearPendingChatMode } = useApp();

  // Always-current ref so the auto-submit path doesn't need onSubmit as a dep
  const onSubmitRef = useRef(onSubmit);
  useEffect(() => { onSubmitRef.current = onSubmit; });
  const [value, setValue]           = useState('');
  const [slashHints, setSlashHints] = useState([]);

  // Prompt history — last 10 non-slash prompts, persisted to localStorage
  const [showHistory, setShowHistory] = useState(false);
  const [promptHistory, setPromptHistory] = useState(() => {
    try { return JSON.parse(localStorage.getItem('ma_prompt_history') || '[]'); } catch { return []; }
  });
  const saveToHistory = useCallback((text) => {
    if (!text || text.startsWith('/') || text.length < 4) return;
    setPromptHistory(prev => {
      const next = [text, ...prev.filter(p => p !== text)].slice(0, 10);
      try { localStorage.setItem('ma_prompt_history', JSON.stringify(next)); } catch {}
      return next;
    });
  }, []);

  // Image attach state — supports multiple images
  const [attachedImages, setAttachedImages] = useState([]); // [{ base64, preview, name }, ...]
  // Document attach state
  const [attachedDoc, setAttachedDoc] = useState(null); // { name, text, extracting }
  const [extractingDoc, setExtractingDoc] = useState(false);
  const fileInputRef = useRef(null);

  // Mic / recording state
  const [recording, setRecording]       = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const mediaRecorderRef = useRef(null);

  const textareaRef = useRef(null);

  const defaultPlaceholder =
    chatMode === 'image' ? 'Describe an image to generate…'
    : chatMode === 'build' ? 'Describe an app to build…'
    : chatMode === 'chat'  ? 'Ask anything, search the web, or just chat…'
    : variant === 'home'   ? 'Ask anything, generate an image, or write code…'
    : 'Message Mini Assistant…';
  const resolvedPlaceholder = placeholder || defaultPlaceholder;

  // Consume pending template — fills input, or auto-submits for onboarding
  useEffect(() => {
    if (!pendingTemplate) return;
    // Apply pending chat mode before submitting (set by onboarding)
    if (pendingChatMode && onChatModeChange) {
      onChatModeChange(pendingChatMode);
      clearPendingChatMode();
    }
    if (pendingAutoSubmit) {
      // Fire directly without going through state — instant, no extra render
      onSubmitRef.current(pendingTemplate, null, null);
      clearPendingTemplate();
      clearPendingAutoSubmit();
    } else {
      setValue(pendingTemplate);
      clearPendingTemplate();
      textareaRef.current?.focus();
    }
  }, [pendingTemplate, pendingAutoSubmit, clearPendingTemplate, clearPendingAutoSubmit, pendingChatMode, clearPendingChatMode, onChatModeChange]);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    const maxH = 6 * 24;
    ta.style.height = Math.min(ta.scrollHeight, maxH) + 'px';
  }, [value]);

  // Slash command hints
  useEffect(() => {
    const trimmed = value.trimStart();
    if (!trimmed.startsWith('/')) { setSlashHints([]); return; }
    const parts = trimmed.split(' ');
    if (parts.length > 1) { setSlashHints([]); return; }
    const typed = trimmed.toLowerCase();
    setSlashHints(SLASH_COMMANDS.filter(c => c.cmd.startsWith(typed)));
  }, [value]);

  const applySlashHint = useCallback((cmd) => {
    setValue(cmd + ' ');
    setSlashHints([]);
    textareaRef.current?.focus();
  }, []);

  // ── Submit ──────────────────────────────────────────────────────────────────

  const handleSubmit = useCallback(() => {
    const text = value.trim();
    if ((!text && !attachedImages.length && !attachedDoc) || loading) return;
    setSlashHints([]);
    // Prepend document text if one is attached
    let finalText = text || '';
    if (attachedDoc?.text) {
      const docPrefix = `[Document: ${attachedDoc.name}]\n\`\`\`\n${attachedDoc.text}\n\`\`\`\n\n`;
      finalText = finalText ? docPrefix + finalText : docPrefix.trimEnd();
    }
    const imagesBase64 = attachedImages.length ? attachedImages.map(i => i.base64) : null;
    saveToHistory(text);
    onSubmit(finalText, imagesBase64, null);
    setValue('');
    setAttachedImages([]);
    setAttachedDoc(null);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }, [value, loading, attachedImages, attachedDoc, onSubmit, saveToHistory]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
  }, [handleSubmit]);

  // ── Image attach ────────────────────────────────────────────────────────────

  const processImageFile = useCallback(async (file) => {
    if (!ALL_MEDIA_TYPES.includes(file.type)) {
      toast.error('Supported image types: PNG, JPG, WebP, GIF');
      return null;
    }
    if (file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024) {
      toast.error(`File too large — maximum ${MAX_IMAGE_SIZE_MB} MB.`);
      return null;
    }
    try {
      if (file.type === 'image/gif') {
        // Read GIF as-is — canvas would kill animation
        const dataUrl = await readFileAsDataUrl(file);
        return { base64: dataUrl.split(',')[1], preview: dataUrl, name: file.name };
      } else {
        // JPEG/PNG/WebP — compress + resize to max 800px
        const { base64, preview } = await compressImageFile(file);
        return { base64, preview, name: file.name };
      }
    } catch {
      toast.error('Could not read file.');
      return null;
    }
  }, []);

  const addImages = useCallback(async (files) => {
    const results = await Promise.all(Array.from(files).map(processImageFile));
    const valid = results.filter(Boolean);
    if (!valid.length) return;
    setAttachedImages(prev => {
      const combined = [...prev, ...valid].slice(0, 8); // max 8 images
      return combined;
    });
    if (!value.trim()) setValue('');
    textareaRef.current?.focus();
  }, [processImageFile, value]);

  const processDocFile = useCallback(async (file) => {
    const ext = '.' + (file.name.split('.').pop() || '').toLowerCase();
    const okType = ACCEPTED_DOC_TYPES.includes(file.type) || ACCEPTED_DOC_EXTS.includes(ext);
    if (!okType) { toast.error('Supported document types: PDF, TXT, MD, CSV'); return; }
    if (file.size > MAX_DOC_SIZE_MB * 1024 * 1024) { toast.error(`File too large — max ${MAX_DOC_SIZE_MB} MB`); return; }
    setExtractingDoc(true);
    setAttachedDoc({ name: file.name, text: null });
    try {
      const data = await api.extractTextFromFile(file);
      setAttachedDoc({ name: file.name, text: data.text });
      if (data.truncated) toast.info('Document truncated to 50 000 characters.');
      else toast.success(`Document loaded: ${data.chars.toLocaleString()} characters`);
    } catch (err) {
      toast.error('Could not extract text: ' + (err?.message || 'unknown error'));
      setAttachedDoc(null);
    } finally {
      setExtractingDoc(false);
      textareaRef.current?.focus();
    }
  }, []);

  const handleFileChange = useCallback((e) => {
    const files = e.target.files;
    if (!files?.length) return;
    const mediaFiles = [];
    for (const f of files) {
      const ext = '.' + (f.name.split('.').pop() || '').toLowerCase();
      if (ACCEPTED_DOC_TYPES.includes(f.type) || ACCEPTED_DOC_EXTS.includes(ext)) {
        processDocFile(f);
      } else {
        mediaFiles.push(f);
      }
    }
    if (mediaFiles.length) addImages(mediaFiles);
    e.target.value = '';
  }, [addImages, processDocFile]);

  const openFilePicker = useCallback(() => { fileInputRef.current?.click(); }, []);

  const removeDoc = useCallback(() => {
    setAttachedDoc(null);
    textareaRef.current?.focus();
  }, []);

  const removeImage = useCallback((idx) => {
    setAttachedImages(prev => {
      const next = prev.filter((_, i) => i !== idx);
      if (!next.length && !value.trim()) setValue('');
      return next;
    });
    textareaRef.current?.focus();
  }, [value]);

  // Drag-and-drop onto the input area — supports multiple files
  const handleDrop = useCallback((e) => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files?.length) addImages(files);
  }, [addImages]);

  const handleDragOver = useCallback((e) => { e.preventDefault(); }, []);

  // ── Mic recording ───────────────────────────────────────────────────────────

  const stopAndTranscribe = useCallback(async (recorder, chunks) => {
    setRecording(false);
    setTranscribing(true);
    try {
      const mimeType = recorder.mimeType || 'audio/webm';
      const blob = new Blob(chunks, { type: mimeType });
      const data = await api.transcribeAudio(blob);
      const text = data?.transcription?.trim();
      if (text) {
        setValue(prev => prev ? prev + ' ' + text : text);
        toast.success('Transcribed!');
      } else {
        toast.info('No speech detected — try again.');
      }
    } catch (err) {
      toast.error('Transcription failed: ' + (err?.message || 'unknown error'));
    } finally {
      setTranscribing(false);
      textareaRef.current?.focus();
    }
  }, []);

  const toggleMic = useCallback(async () => {
    if (transcribing) return;

    if (recording) {
      mediaRecorderRef.current?.stop();
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks = [];
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach(t => t.stop());
        stopAndTranscribe(recorder, chunks);
      };

      recorder.start();
      setRecording(true);
      toast.info('Recording… click mic again to stop.');
    } catch (err) {
      if (err.name === 'NotAllowedError') {
        toast.error('Microphone permission denied.');
      } else {
        toast.error('Could not start recording: ' + err.message);
      }
    }
  }, [recording, transcribing, stopAndTranscribe]);

  // ── Render ──────────────────────────────────────────────────────────────────

  const isHome  = variant === 'home';
  const isEmpty = !value.trim() && !attachedImages.length && !attachedDoc;
  const isSlash = value.trimStart().startsWith('/');

  const containerClass = isHome
    ? 'w-full max-w-2xl rounded-2xl bg-[#1a1a26] border border-white/10 flex flex-col focus-within:border-cyan-500/40 focus-within:shadow-[0_0_20px_rgba(0,229,255,0.08)] transition-all'
    : 'w-full rounded-xl bg-[#1a1a26] border border-white/10 flex flex-col focus-within:border-cyan-500/40 focus-within:shadow-[0_0_20px_rgba(0,229,255,0.08)] transition-all';

  return (
    <div
      className="relative w-full"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setShowHistory(false); }}
    >
      {/* Single hidden file input — handles images, videos, and documents */}
      <input
        ref={fileInputRef}
        type="file"
        accept={[...ALL_MEDIA_TYPES, ...ACCEPTED_DOC_TYPES, ...ACCEPTED_DOC_EXTS].join(',')}
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Prompt history dropdown */}
      {showHistory && promptHistory.length > 0 && (
        <div className="absolute bottom-full mb-2 left-0 right-0 z-50 rounded-xl bg-[#13131f] border border-white/10 overflow-hidden shadow-xl">
          <div className="flex items-center gap-2 px-4 py-2 border-b border-white/5">
            <Clock size={10} className="text-slate-600" />
            <span className="text-[10px] text-slate-600 font-mono uppercase tracking-widest">Recent prompts</span>
            <button
              type="button"
              onMouseDown={(e) => { e.preventDefault(); setPromptHistory([]); localStorage.removeItem('ma_prompt_history'); setShowHistory(false); }}
              className="ml-auto text-[10px] text-slate-700 hover:text-red-400 transition-colors"
            >clear</button>
          </div>
          {promptHistory.map((p, i) => (
            <button
              key={i}
              type="button"
              onMouseDown={(e) => { e.preventDefault(); setValue(p); setShowHistory(false); textareaRef.current?.focus(); }}
              className="w-full text-left px-4 py-2.5 text-sm text-slate-400 hover:bg-white/5 hover:text-slate-200 transition-colors truncate"
            >
              {p}
            </button>
          ))}
        </div>
      )}

      {/* Slash command hints dropdown */}
      {slashHints.length > 0 && (
        <div className="absolute bottom-full mb-2 left-0 right-0 z-50 rounded-xl bg-[#13131f] border border-white/10 overflow-hidden shadow-xl">
          {slashHints.map(({ cmd, desc }) => (
            <button
              key={cmd}
              type="button"
              onMouseDown={(e) => { e.preventDefault(); applySlashHint(cmd); }}
              className="w-full text-left px-4 py-2.5 flex items-center gap-3 hover:bg-white/5 transition-colors"
            >
              <span className="text-cyan-400 font-mono text-sm font-medium w-20 flex-shrink-0">{cmd}</span>
              <span className="text-slate-400 text-sm">{desc}</span>
            </button>
          ))}
        </div>
      )}

      <div className={containerClass}>
        {/* Attached images preview strip — multiple images */}
        {attachedImages.length > 0 && (
          <div className="px-4 pt-3 pb-0 flex items-start gap-2 flex-wrap">
            {attachedImages.map((img, idx) => (
              <div key={idx} className="relative group flex-shrink-0">
                <img
                  src={img.preview}
                  alt={img.name}
                  className="h-16 w-16 rounded-lg object-cover border border-white/10"
                />
                <button
                  type="button"
                  onClick={() => removeImage(idx)}
                  className="absolute -top-1.5 -right-1.5 bg-slate-800 border border-white/20 rounded-full p-0.5 text-slate-400 hover:text-white hover:bg-red-500/80 transition-colors opacity-0 group-hover:opacity-100"
                  title="Remove image"
                >
                  <X size={10} />
                </button>
              </div>
            ))}
            <div className="flex flex-col justify-center pt-1 min-w-0">
              <span className="text-xs text-cyan-500/70 flex items-center gap-1">
                <Image size={10} /> {attachedImages.length} file{attachedImages.length > 1 ? 's' : ''} attached
              </span>
              <span className="text-[10px] text-slate-600 mt-0.5">Drop more or click 📎</span>
            </div>
          </div>
        )}

        {/* Attached document preview */}
        {attachedDoc && (
          <div className="px-4 pt-3 pb-0 flex items-center gap-2">
            <div className="flex items-center gap-2 bg-violet-500/10 border border-violet-500/20 rounded-lg px-3 py-2 flex-1 min-w-0">
              {extractingDoc
                ? <Loader2 size={13} className="text-violet-400 animate-spin flex-shrink-0" />
                : <FileText size={13} className="text-violet-400 flex-shrink-0" />}
              <span className="text-xs text-violet-300 truncate">{attachedDoc.name}</span>
              {attachedDoc.text && (
                <span className="text-[10px] text-violet-500/70 flex-shrink-0">
                  {attachedDoc.text.length.toLocaleString()} chars
                </span>
              )}
            </div>
            <button type="button" onClick={removeDoc}
              className="flex-shrink-0 p-1 rounded text-slate-600 hover:text-red-400 transition-colors">
              <X size={12} />
            </button>
          </div>
        )}

        {/* Input row */}
        <div className="flex items-end gap-2 px-5 py-3.5">
          {/* Prompt history */}
          {promptHistory.length > 0 && (
            <button
              type="button"
              onClick={() => setShowHistory(h => !h)}
              className={`flex-shrink-0 p-1.5 rounded-lg transition-colors mb-0.5 ${showHistory ? 'text-cyan-400 bg-cyan-500/10' : 'text-slate-600 hover:text-slate-400 hover:bg-white/5'}`}
              title="Recent prompts"
            >
              <Clock size={16} />
            </button>
          )}
          {/* Attach image */}
          <button
            type="button"
            onClick={openFilePicker}
            disabled={loading}
            className={`flex-shrink-0 p-1.5 rounded-lg transition-colors mb-0.5
              ${attachedImages.length
                ? 'text-cyan-400 hover:text-cyan-300 hover:bg-white/5'
                : 'text-slate-600 hover:text-slate-400 hover:bg-white/5'}`}
            title="Attach image or file as reference"
          >
            <Paperclip size={16} />
          </button>
          {/* Textarea */}
          <textarea
            ref={textareaRef}
            className={`flex-1 bg-transparent text-[15px] font-sans placeholder-slate-600 resize-none outline-none border-none leading-6 max-h-[144px] py-0.5
              ${isSlash ? 'text-cyan-300 font-mono' : 'text-slate-200'}`}
            placeholder={attachedImages.length ? `Ask about ${attachedImages.length > 1 ? 'these images' : 'this image'}…` : attachedDoc ? 'Ask about this document…' : resolvedPlaceholder}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={loading}
            autoFocus={isHome}
          />

          {/* Mic */}
          <button
            type="button"
            onClick={toggleMic}
            disabled={loading}
            className={`flex-shrink-0 p-1.5 rounded-lg transition-colors mb-0.5
              ${recording
                ? 'text-red-400 hover:text-red-300 hover:bg-red-500/10 animate-pulse'
                : transcribing
                  ? 'text-yellow-400 cursor-wait'
                  : 'text-slate-600 hover:text-slate-400 hover:bg-white/5'}`}
            title={recording ? 'Stop recording' : transcribing ? 'Transcribing…' : 'Voice input'}
          >
            {transcribing
              ? <Loader2 size={16} className="animate-spin" />
              : recording
                ? <MicOff size={16} />
                : <Mic size={16} />}
          </button>

          {/* Mode buttons: Generate | Edit | Build | Chat */}
          {onChatModeChange && (
            <>
              {/* Create New Image */}
              <button
                type="button"
                onClick={() => onChatModeChange(chatMode === 'image' ? null : 'image')}
                title={chatMode === 'image' ? 'Create Mode ON — click to exit' : 'Create New Image — generate a brand new image from text'}
                className={`flex-shrink-0 p-2.5 rounded-xl transition-all mb-0.5 ${
                  chatMode === 'image'
                    ? 'bg-gradient-to-br from-pink-500 to-rose-600 text-white shadow-lg shadow-pink-500/40'
                    : 'text-slate-500 hover:text-pink-400 hover:bg-white/5'
                }`}
              >
                <Image size={16} />
              </button>
              {/* Edit Existing Image */}
              <button
                type="button"
                onClick={() => onChatModeChange(chatMode === 'image_edit' ? null : 'image_edit')}
                title={chatMode === 'image_edit' ? 'Edit Mode ON — click to exit' : 'Edit Existing Image — attach your image and describe the change'}
                className={`flex-shrink-0 p-2.5 rounded-xl transition-all mb-0.5 ${
                  chatMode === 'image_edit'
                    ? 'bg-gradient-to-br from-amber-500 to-orange-600 text-white shadow-lg shadow-amber-500/40'
                    : 'text-slate-500 hover:text-amber-400 hover:bg-white/5'
                }`}
              >
                <Pencil size={16} />
              </button>
              <button
                type="button"
                onClick={() => onChatModeChange(chatMode === 'build' ? null : 'build')}
                title={chatMode === 'build' ? 'Build Mode ON — click to exit' : 'Build Mode — every message builds an app'}
                className={`flex-shrink-0 p-2.5 rounded-xl transition-all mb-0.5 ${
                  chatMode === 'build'
                    ? 'bg-gradient-to-br from-cyan-400 to-violet-600 text-white shadow-lg shadow-cyan-500/40'
                    : 'text-slate-500 hover:text-cyan-400 hover:bg-white/5'
                }`}
              >
                <Hammer size={16} />
              </button>
              <button
                type="button"
                onClick={() => onChatModeChange(chatMode === 'chat' ? null : 'chat')}
                title={chatMode === 'chat' ? 'Chat Mode ON — click to exit' : 'Chat Mode — conversation & research, no building or image gen'}
                className={`flex-shrink-0 p-2.5 rounded-xl transition-all mb-0.5 ${
                  chatMode === 'chat'
                    ? 'bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg shadow-blue-500/40'
                    : 'text-slate-500 hover:text-blue-400 hover:bg-white/5'
                }`}
              >
                <MessageSquare size={16} />
              </button>
            </>
          )}

          {/* Send */}
          <button
            type="button"
            onClick={handleSubmit}
            disabled={isEmpty || loading}
            className={`flex-shrink-0 p-2.5 rounded-xl transition-all mb-0.5
              ${isEmpty || loading
                ? 'bg-slate-700/50 text-slate-600 cursor-not-allowed'
                : isSlash || attachedImages.length || attachedDoc
                  ? 'bg-gradient-to-br from-cyan-400 to-cyan-600 text-white hover:from-cyan-300 hover:to-cyan-500 shadow-lg hover:shadow-cyan-500/30'
                  : 'bg-gradient-to-br from-cyan-500 to-violet-600 text-white hover:from-cyan-400 hover:to-violet-500 shadow-lg hover:shadow-cyan-500/20'}`}
            title="Send message"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
      </div>

    </div>
  );
}

export default ChatInput;
