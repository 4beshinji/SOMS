import { useState, useRef, useCallback } from 'react';
import { Send, Mic, MicOff, Loader2, Radio } from 'lucide-react';
import type { VoiceMode } from '../hooks/useVoiceInput';

interface Props {
  onSend: (message: string) => void;
  isLoading: boolean;
  voiceMode: VoiceMode;
  onVoiceModeChange: (mode: VoiceMode) => void;
  isRecording: boolean;
  isTranscribing: boolean;
  onPttDown: () => void;
  onPttUp: () => void;
  dark?: boolean;
}

export default function ChatInput({
  onSend,
  isLoading,
  voiceMode,
  onVoiceModeChange,
  isRecording,
  isTranscribing,
  onPttDown,
  onPttUp,
  dark,
}: Props) {
  const [input, setInput] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isLoading) return;
    onSend(text);
    setInput('');
    if (inputRef.current) inputRef.current.style.height = 'auto';
  }, [input, isLoading, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 100) + 'px';
  };

  const cycleVoiceMode = useCallback(() => {
    const modes: VoiceMode[] = ['off', 'ptt', 'vad'];
    const idx = modes.indexOf(voiceMode);
    onVoiceModeChange(modes[(idx + 1) % modes.length]);
  }, [voiceMode, onVoiceModeChange]);

  const busy = isLoading || isTranscribing;

  return (
    <div className="space-y-2">
      {/* Text input row */}
      <div className="flex items-end gap-2">
        <textarea
          ref={inputRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="メッセージを入力..."
          rows={1}
          disabled={busy}
          className={`flex-1 resize-none rounded-lg border px-3 py-2 text-sm
                     focus:outline-none focus:ring-2 focus:ring-[var(--primary-400)]
                     disabled:opacity-50 max-h-[100px] ${
          dark
            ? 'border-[var(--gray-600)] bg-[var(--gray-800)] text-white placeholder:text-[var(--gray-500)]'
            : 'border-[var(--gray-300)] bg-white text-[var(--gray-900)] placeholder:text-[var(--gray-400)]'
        }`}
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={!input.trim() || busy}
          className="h-9 w-9 shrink-0 rounded-lg bg-[var(--primary-600)] text-white
                     flex items-center justify-center
                     hover:bg-[var(--primary-700)] disabled:opacity-40
                     transition-colors cursor-pointer"
          title="送信"
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Voice controls row */}
      <div className="flex items-center gap-2">
        {/* Voice mode toggle */}
        <button
          type="button"
          onClick={cycleVoiceMode}
          className={`text-xs px-2 py-1 rounded-md transition-colors cursor-pointer ${
            voiceMode === 'off'
              ? 'bg-[var(--gray-100)] text-[var(--gray-500)]'
              : voiceMode === 'ptt'
                ? 'bg-[var(--primary-100)] text-[var(--primary-700)]'
                : 'bg-[var(--error-100)] text-[var(--error-700)]'
          }`}
          title="音声モード切替"
        >
          {voiceMode === 'off' ? 'Voice: OFF' : voiceMode === 'ptt' ? 'PTT' : 'VAD'}
        </button>

        {/* PTT button */}
        {voiceMode === 'ptt' && (
          <button
            type="button"
            onPointerDown={onPttDown}
            onPointerUp={onPttUp}
            onPointerLeave={onPttUp}
            disabled={busy}
            className={`flex items-center gap-1 px-3 py-1 rounded-lg text-xs
                       transition-colors cursor-pointer ${
              isRecording
                ? 'bg-[var(--error-500)] text-white'
                : 'bg-[var(--gray-200)] text-[var(--gray-700)] hover:bg-[var(--gray-300)]'
            }`}
            title="押し続けて録音"
          >
            {isRecording ? <MicOff className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
            {isRecording ? '録音中...' : '押して話す'}
          </button>
        )}

        {/* VAD indicator */}
        {voiceMode === 'vad' && (
          <span className="flex items-center gap-1 text-xs text-[var(--error-600)]">
            <Radio className="h-3.5 w-3.5 animate-pulse" />
            音声検出中
          </span>
        )}

        {/* Transcribing indicator */}
        {isTranscribing && (
          <span className="flex items-center gap-1 text-xs text-[var(--gray-500)]">
            <Loader2 className="h-3 w-3 animate-spin" />
            文字起こし中...
          </span>
        )}
      </div>
    </div>
  );
}
