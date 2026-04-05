import { useState, useCallback, useRef } from 'react';
import { transcribeAudio } from '../api';
import { encodeWav } from '../audio/encodeWav';

export type VoiceMode = 'off' | 'ptt' | 'vad';

export function useVoiceInput(onResult: (text: string) => void) {
  const [mode, setMode] = useState<VoiceMode>('off');
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1 },
      });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        streamRef.current = null;

        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        if (blob.size < 100) return; // too short

        setIsTranscribing(true);
        try {
          const text = await transcribeAudio(blob);
          if (text.trim()) onResult(text.trim());
        } catch (e) {
          console.error('STT error:', e);
        } finally {
          setIsTranscribing(false);
        }
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecording(true);
    } catch (e) {
      console.error('Microphone access denied:', e);
    }
  }, [onResult]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  }, []);

  // PTT handlers
  const onPttDown = useCallback(() => {
    if (mode === 'ptt') startRecording();
  }, [mode, startRecording]);

  const onPttUp = useCallback(() => {
    if (mode === 'ptt') stopRecording();
  }, [mode, stopRecording]);

  // VAD callback for @ricky0123/vad-react
  const onVadSpeechEnd = useCallback(
    async (audio: Float32Array) => {
      if (mode !== 'vad') return;
      setIsTranscribing(true);
      try {
        const wavBlob = encodeWav(audio, 16000);
        const text = await transcribeAudio(wavBlob);
        if (text.trim()) onResult(text.trim());
      } catch (e) {
        console.error('VAD STT error:', e);
      } finally {
        setIsTranscribing(false);
      }
    },
    [mode, onResult],
  );

  return {
    mode,
    setMode,
    isRecording,
    isTranscribing,
    onPttDown,
    onPttUp,
    onVadSpeechEnd,
    startRecording,
    stopRecording,
  };
}
