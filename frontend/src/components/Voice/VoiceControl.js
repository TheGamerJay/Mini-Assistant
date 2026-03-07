import React, { useState, useRef } from 'react';
import { axiosInstance } from '../../App';
import { toast } from 'sonner';
import { Mic, MicOff, Volume2, Loader2 } from 'lucide-react';

const VoiceControl = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [transcription, setTranscription] = useState('');
  const [response, setResponse] = useState('');
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        audioChunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        await processAudio(audioBlob);
      };

      mediaRecorder.start();
      setIsRecording(true);
      toast.success('Recording started');
    } catch (error) {
      toast.error('Microphone access denied');
      console.error('Recording error:', error);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
      setIsRecording(false);
    }
  };

  const processAudio = async (audioBlob) => {
    setIsProcessing(true);
    try {
      const formData = new FormData();
      formData.append('file', audioBlob, 'audio.wav');

      const sttResponse = await axiosInstance.post('/voice/stt', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      const transcript = sttResponse.data.transcription;
      setTranscription(transcript);
      toast.success('Transcription complete');

      const chatResponse = await axiosInstance.post('/chat', {
        messages: [{ role: 'user', content: transcript }],
        model: 'glm-4.7:cloud'
      });

      const aiResponse = chatResponse.data.response;
      setResponse(aiResponse);
      
      await speakResponse(aiResponse);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Voice processing error');
      console.error('Voice error:', error);
    } finally {
      setIsProcessing(false);
    }
  };

  const speakResponse = async (text) => {
    try {
      const ttsResponse = await axiosInstance.post('/voice/tts', 
        { text: text.substring(0, 500), lang: 'en' },
        { responseType: 'blob' }
      );

      const audioUrl = URL.createObjectURL(ttsResponse.data);
      const audio = new Audio(audioUrl);
      audio.play();
      toast.success('Playing response');
    } catch (error) {
      toast.error('TTS error');
      console.error('TTS error:', error);
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f]/50 p-8" data-testid="voice-control">
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-cyan-400 uppercase" style={{ fontFamily: 'Rajdhani, sans-serif' }}>
          VOICE MODE
        </h2>
        <p className="text-xs text-slate-400 font-mono mt-1">SPEECH-TO-TEXT + TEXT-TO-SPEECH</p>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center space-y-12">
        {/* Voice Visualizer */}
        <div className="relative">
          <div className={`w-40 h-40 rounded-full border-4 flex items-center justify-center transition-all ${
            isRecording 
              ? 'border-cyan-400 bg-cyan-500/20 animate-pulse-glow' 
              : 'border-cyan-500/50 bg-cyan-500/10'
          }`}>
            {isProcessing ? (
              <Loader2 className="w-16 h-16 text-cyan-400 animate-spin" />
            ) : isRecording ? (
              <Mic className="w-16 h-16 text-cyan-400" strokeWidth={2} />
            ) : (
              <MicOff className="w-16 h-16 text-cyan-400/50" strokeWidth={2} />
            )}
          </div>
          {isRecording && (
            <div className="absolute inset-0 rounded-full border-4 border-cyan-400 animate-ping opacity-75"></div>
          )}
        </div>

        {/* Control Button */}
        <button
          data-testid="voice-toggle-btn"
          onClick={isRecording ? stopRecording : startRecording}
          disabled={isProcessing}
          className={`px-12 py-4 rounded-sm font-bold uppercase tracking-wider text-lg transition-all ${
            isRecording
              ? 'bg-red-500 hover:bg-red-400 text-white shadow-[0_0_20px_rgba(255,0,0,0.5)]'
              : 'bg-gradient-to-r from-cyan-500 to-violet-600 hover:from-cyan-400 hover:to-violet-500 text-white shadow-[0_0_20px_rgba(0,243,255,0.5),0_0_15px_rgba(147,51,234,0.3)]'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {isProcessing ? 'PROCESSING...' : isRecording ? 'STOP RECORDING' : 'START RECORDING'}
        </button>

        {/* Transcription Display */}
        {transcription && (
          <div className="w-full max-w-2xl p-6 bg-black/40 border border-cyan-900/30 rounded-lg backdrop-blur-sm" data-testid="transcription-display">
            <div className="text-xs font-mono text-cyan-400/70 uppercase mb-2">TRANSCRIPTION</div>
            <p className="text-slate-300">{transcription}</p>
          </div>
        )}

        {/* Response Display */}
        {response && (
          <div className="w-full max-w-2xl p-6 bg-cyan-500/10 border border-cyan-500/50 rounded-lg backdrop-blur-sm" data-testid="response-display">
            <div className="flex items-center gap-2 text-xs font-mono text-cyan-400 uppercase mb-2">
              <Volume2 className="w-4 h-4" />
              MINI ASSISTANT RESPONSE
            </div>
            <p className="text-cyan-100">{response}</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default VoiceControl;