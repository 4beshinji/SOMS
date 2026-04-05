/**
 * Voice input hook with server-side STT and Web Speech API fallback.
 *
 * - Checks STT service availability on mount
 * - Push-to-talk via MediaRecorder → server STT (or Web Speech API fallback)
 * - VAD mode via @ricky0123/vad-web (Silero VAD in-browser) → server STT
 * - Persists mode preference in localStorage
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { transcribeAudio } from '../api';
import { encodeWav } from '../audio/encodeWav';
import type { MicVAD as MicVADType } from '@ricky0123/vad-web';

export type VoiceMode = 'off' | 'ptt' | 'vad';

const STORAGE_KEY = 'soms-voice-mode';

// ── Web Speech API fallback ────────────────────────────────────────

function useWebSpeechFallback(onResult: (text: string) => void) {
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const [isListening, setIsListening] = useState(false);

  const isSupported =
    typeof window !== 'undefined' &&
    !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  const start = useCallback(() => {
    if (!isSupported) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SR();
    recognition.lang = 'ja-JP';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (e: SpeechRecognitionEvent) => {
      const text = e.results[0]?.[0]?.transcript;
      if (text?.trim()) onResult(text.trim());
    };
    recognition.onend = () => setIsListening(false);
    recognition.onerror = () => setIsListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
  }, [isSupported, onResult]);

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
    setIsListening(false);
  }, []);

  return { isSupported, isListening, start, stop };
}

// ── Main hook ──────────────────────────────────────────────────────

export function useVoiceInput(onResult: (text: string) => void) {
  const [mode, setModeState] = useState<VoiceMode>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return (stored as VoiceMode) || 'off';
  });
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [serverAvailable, setServerAvailable] = useState<boolean | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const [vadActive, setVadActive] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const levelRafRef = useRef<number>(0);
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;

  // VAD instance ref
  const vadRef = useRef<MicVADType | null>(null);
  const useServerRef = useRef(false);

  // Web Speech API fallback
  const webSpeech = useWebSpeechFallback(onResult);

  const useServer = serverAvailable === true;
  useServerRef.current = useServer;

  // Persist mode to localStorage
  const setMode = useCallback((m: VoiceMode) => {
    setModeState(m);
    localStorage.setItem(STORAGE_KEY, m);
  }, []);

  // Check STT service availability on mount
  useEffect(() => {
    const check = async () => {
      try {
        // POST with empty body: 422 = service alive, 502/503 = unreachable
        const res = await fetch('/api/stt/v1/audio/transcriptions', {
          method: 'POST',
          body: new FormData(),
        });
        setServerAvailable(res.status < 502);
      } catch {
        setServerAvailable(false);
      }
    };
    check();
  }, []);

  // ── VAD lifecycle ───────────────────────────────────────────────

  useEffect(() => {
    if (mode !== 'vad') {
      if (vadRef.current) {
        vadRef.current.destroy();
        vadRef.current = null;
      }
      setVadActive(false);
      return;
    }

    let cancelled = false;

    const initVad = async () => {
      const { MicVAD } = await import('@ricky0123/vad-web');
      if (cancelled) return;

      const vad = await MicVAD.new({
        baseAssetPath: '/vad/',
        onnxWASMBasePath: '/vad/',
        model: 'v5',
        positiveSpeechThreshold: 0.3,
        negativeSpeechThreshold: 0.15,
        minSpeechFrames: 5,
        preSpeechPadFrames: 12,
        redemptionFrames: 20,

        onSpeechStart: () => {
          if (!cancelled) setIsRecording(true);
        },

        onSpeechEnd: async (audio: Float32Array) => {
          if (cancelled) return;
          setIsRecording(false);
          // Encode and send to STT (same path as PTT's processAudio)
          const wavBlob = encodeWav(audio, 16000);
          if (wavBlob.size < 100) return;
          setIsTranscribing(true);
          try {
            const text = await transcribeAudio(wavBlob);
            if (text.trim()) onResultRef.current(text.trim());
          } catch (e) {
            console.error('VAD STT error:', e);
          } finally {
            setIsTranscribing(false);
          }
        },

        onVADMisfire: () => {
          if (!cancelled) setIsRecording(false);
        },

        onFrameProcessed: (probs) => {
          if (!cancelled) setAudioLevel(probs.isSpeech);
        },
      });

      if (cancelled) {
        vad.destroy();
        return;
      }

      vadRef.current = vad;
      await vad.start();
      setVadActive(true);
    };

    // Timeout guard: abort if init takes > 15s
    const timeout = setTimeout(() => {
      if (!cancelled) {
        console.error('VAD initialization timed out (15s)');
        cancelled = true;
        setVadActive(false);
      }
    }, 15000);

    initVad()
      .catch((e) => {
        if (!cancelled) {
          console.error('VAD initialization failed:', e);
          setVadActive(false);
        }
      })
      .finally(() => clearTimeout(timeout));

    return () => {
      cancelled = true;
      clearTimeout(timeout);
      if (vadRef.current) {
        vadRef.current.destroy();
        vadRef.current = null;
      }
      setVadActive(false);
      setIsRecording(false);
      setAudioLevel(0);
    };
  }, [mode]);

  // ── Server STT: process audio blob ──────────────────────────────

  const processAudio = useCallback(async (blob: Blob) => {
    if (blob.size < 100) return;
    setIsTranscribing(true);
    try {
      const text = await transcribeAudio(blob);
      if (text.trim()) onResultRef.current(text.trim());
    } catch (e) {
      console.error('STT error:', e);
    } finally {
      setIsTranscribing(false);
    }
  }, []);

  // ── PTT: start recording ────────────────────────────────────────

  const startRecording = useCallback(async () => {
    if (!useServer && webSpeech.isSupported) {
      webSpeech.start();
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1 },
      });
      streamRef.current = stream;

      // Set up audio level monitoring
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      audioContextRef.current = ctx;
      analyserRef.current = analyser;

      // Time-domain RMS for instant response (no FFT delay)
      const buf = new Uint8Array(analyser.fftSize);
      const tick = () => {
        analyser.getByteTimeDomainData(buf);
        let sumSq = 0;
        for (let i = 0; i < buf.length; i++) {
          const v = (buf[i] - 128) / 128;
          sumSq += v * v;
        }
        setAudioLevel(Math.min(Math.sqrt(sumSq / buf.length) * 3, 1));
        levelRafRef.current = requestAnimationFrame(tick);
      };
      levelRafRef.current = requestAnimationFrame(tick);

      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        cancelAnimationFrame(levelRafRef.current);
        setAudioLevel(0);
        audioContextRef.current?.close();
        audioContextRef.current = null;
        analyserRef.current = null;
        stream.getTracks().forEach(t => t.stop());
        streamRef.current = null;
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        await processAudio(blob);
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecording(true);
    } catch (e) {
      console.error('Microphone access denied:', e);
    }
  }, [useServer, webSpeech, processAudio]);

  const stopRecording = useCallback(() => {
    if (!useServer && webSpeech.isListening) {
      webSpeech.stop();
      return;
    }

    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  }, [useServer, webSpeech]);

  // PTT handlers
  const onPttDown = useCallback(() => {
    if (mode === 'ptt') startRecording();
  }, [mode, startRecording]);

  const onPttUp = useCallback(() => {
    if (mode === 'ptt') stopRecording();
  }, [mode, stopRecording]);

  // Show mic if server STT available, OR browser has Web Speech API
  const isSupported =
    useServer || webSpeech.isSupported || serverAvailable === null;

  return {
    mode,
    setMode,
    isRecording: isRecording || webSpeech.isListening,
    isTranscribing,
    isSupported,
    useServerSTT: useServer,
    audioLevel,
    vadActive,
    onPttDown,
    onPttUp,
    startRecording,
    stopRecording,
  };
}
