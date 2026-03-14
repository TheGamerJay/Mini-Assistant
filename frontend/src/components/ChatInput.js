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
import { Paperclip, Mic, MicOff, Send, Loader2, X, Image } from 'lucide-react';
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
const MAX_IMAGE_SIZE_MB = 15;

// ── Image helpers ─────────────────────────────────────────────────────────────

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      // Strip data:image/...;base64, prefix — backend expects raw base64
      const base64 = reader.result.split(',')[1];
      resolve(base64);
    };
    reader.onerror = reject;
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

function ChatInput({ onSubmit, loading = false, variant = 'chat', placeholder }) {
  const { pendingTemplate, clearPendingTemplate } = useApp();
  const [value, setValue]           = useState('');
  const [slashHints, setSlashHints] = useState([]);

  // Image attach state
  const [attachedImage, setAttachedImage] = useState(null); // { base64, preview, name }
  const fileInputRef = useRef(null);

  // Mic / recording state
  const [recording, setRecording]       = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const mediaRecorderRef = useRef(null);

  const textareaRef = useRef(null);

  const defaultPlaceholder =
    variant === 'home'
      ? 'Ask anything, generate an image, or write code…'
      : 'Message Mini Assistant…';
  const resolvedPlaceholder = placeholder || defaultPlaceholder;

  // Consume pending template from sidebar
  useEffect(() => {
    if (pendingTemplate) {
      setValue(pendingTemplate);
      clearPendingTemplate();
      textareaRef.current?.focus();
    }
  }, [pendingTemplate, clearPendingTemplate]);

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
    if ((!text && !attachedImage) || loading) return;
    setSlashHints([]);
    onSubmit(text || '/analyze', attachedImage?.base64 || null, null);
    setValue('');
    setAttachedImage(null);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }, [value, loading, attachedImage, onSubmit]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
  }, [handleSubmit]);

  // ── Image attach ────────────────────────────────────────────────────────────

  const processImageFile = useCallback(async (file) => {
    if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) {
      toast.error('Only JPEG, PNG, WebP, and GIF images are supported.');
      return;
    }
    if (file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024) {
      toast.error(`Image too large — maximum ${MAX_IMAGE_SIZE_MB} MB.`);
      return;
    }
    try {
      const [base64, preview] = await Promise.all([
        readFileAsBase64(file),
        readFileAsDataUrl(file),
      ]);
      setAttachedImage({ base64, preview, name: file.name });
      if (!value.trim()) setValue('/analyze ');
      textareaRef.current?.focus();
    } catch {
      toast.error('Could not read image file.');
    }
  }, [value]);

  const handleFileChange = useCallback((e) => {
    const file = e.target.files?.[0];
    if (file) processImageFile(file);
    e.target.value = '';
  }, [processImageFile]);

  const openFilePicker = useCallback(() => { fileInputRef.current?.click(); }, []);

  const removeImage = useCallback(() => {
    setAttachedImage(null);
    if (value.trimStart().startsWith('/analyze')) setValue('');
    textareaRef.current?.focus();
  }, [value]);

  // Drag-and-drop onto the input area
  const handleDrop = useCallback((e) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) processImageFile(file);
  }, [processImageFile]);

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
  const isEmpty = !value.trim() && !attachedImage;
  const isSlash = value.trimStart().startsWith('/');

  const containerClass = isHome
    ? 'w-full max-w-2xl rounded-2xl bg-[#1a1a26] border border-white/10 flex flex-col focus-within:border-cyan-500/40 focus-within:shadow-[0_0_20px_rgba(0,229,255,0.08)] transition-all'
    : 'w-full rounded-xl bg-[#1a1a26] border border-white/10 flex flex-col focus-within:border-cyan-500/40 focus-within:shadow-[0_0_20px_rgba(0,229,255,0.08)] transition-all';

  return (
    <div
      className="relative w-full"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
    >
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_IMAGE_TYPES.join(',')}
        className="hidden"
        onChange={handleFileChange}
      />

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
        {/* Attached image preview strip */}
        {attachedImage && (
          <div className="px-4 pt-3 pb-0 flex items-start gap-2">
            <div className="relative group flex-shrink-0">
              <img
                src={attachedImage.preview}
                alt={attachedImage.name}
                className="h-16 w-16 rounded-lg object-cover border border-white/10"
              />
              <button
                type="button"
                onClick={removeImage}
                className="absolute -top-1.5 -right-1.5 bg-slate-800 border border-white/20 rounded-full p-0.5 text-slate-400 hover:text-white hover:bg-red-500/80 transition-colors opacity-0 group-hover:opacity-100"
                title="Remove image"
              >
                <X size={10} />
              </button>
            </div>
            <div className="flex flex-col justify-center pt-1 min-w-0">
              <span className="text-xs text-slate-400 truncate max-w-[180px]">{attachedImage.name}</span>
              <span className="text-xs text-cyan-500/70 mt-0.5 flex items-center gap-1">
                <Image size={10} /> Ready to analyze
              </span>
            </div>
          </div>
        )}

        {/* Input row */}
        <div className="flex items-end gap-2 px-5 py-3.5">
          {/* Attach */}
          <button
            type="button"
            onClick={openFilePicker}
            disabled={loading}
            className={`flex-shrink-0 p-1.5 rounded-lg transition-colors mb-0.5
              ${attachedImage
                ? 'text-cyan-400 hover:text-cyan-300 hover:bg-white/5'
                : 'text-slate-600 hover:text-slate-400 hover:bg-white/5'}`}
            title="Attach image (drag & drop also works)"
          >
            <Paperclip size={16} />
          </button>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            className={`flex-1 bg-transparent text-[15px] font-sans placeholder-slate-600 resize-none outline-none border-none leading-6 max-h-[144px] py-0.5
              ${isSlash ? 'text-cyan-300 font-mono' : 'text-slate-200'}`}
            placeholder={attachedImage ? 'Ask about this image…' : resolvedPlaceholder}
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

          {/* Send */}
          <button
            type="button"
            onClick={handleSubmit}
            disabled={isEmpty || loading}
            className={`flex-shrink-0 p-2.5 rounded-xl transition-all mb-0.5
              ${isEmpty || loading
                ? 'bg-slate-700/50 text-slate-600 cursor-not-allowed'
                : isSlash || attachedImage
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
