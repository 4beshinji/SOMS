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
  audioLevel: number;
  vadActive: boolean;
  onPttDown: () => void;
  onPttUp: () => void;
  dark?: boolean;
}

function AudioLevelBar({ level, dark }: { level: number; dark?: boolean }) {
  const barCount = 5;
  const active = Math.ceil(level * barCount);
  return (
    <div className="flex items-end gap-[2px] h-4">
      {Array.from({ length: barCount }, (_, i) => (
        <div
          key={i}
          className="w-[3px] rounded-full"
          style={{
            height: `${6 + i * 2}px`,
            backgroundColor:
              i < active
                ? i < 3
                  ? 'var(--primary-500)'
                  : 'var(--error-500)'
                : dark
                  ? 'var(--gray-700)'
                  : 'var(--gray-300)',
          }}
        />
      ))}
    </div>
  );
}

export default function ChatInput({
  onSend,
  isLoading,
  voiceMode,
  onVoiceModeChange,
  isRecording,
  isTranscribing,
  audioLevel,
  vadActive,
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

  // Segmented button palette
  const groupBg =
    voiceMode === 'off'
      ? dark ? 'bg-[var(--gray-800)]' : 'bg-[var(--gray-100)]'
      : voiceMode === 'ptt'
        ? dark ? 'bg-[var(--primary-900)]' : 'bg-[var(--primary-50)]'
        : dark ? 'bg-[var(--error-900)]' : 'bg-[var(--error-50)]';

  const modeText =
    voiceMode === 'off'
      ? dark ? 'text-[var(--gray-500)]' : 'text-[var(--gray-500)]'
      : voiceMode === 'ptt'
        ? dark ? 'text-[var(--primary-400)]' : 'text-[var(--primary-700)]'
        : dark ? 'text-[var(--error-400)]' : 'text-[var(--error-700)]';

  const divider =
    voiceMode === 'off'
      ? dark ? 'bg-[var(--gray-700)]' : 'bg-[var(--gray-300)]'
      : voiceMode === 'ptt'
        ? dark ? 'bg-[var(--primary-700)]' : 'bg-[var(--primary-200)]'
        : dark ? 'bg-[var(--error-700)]' : 'bg-[var(--error-200)]';

  const micColor =
    voiceMode === 'off'
      ? dark ? 'text-[var(--gray-600)]' : 'text-[var(--gray-400)]'
      : voiceMode === 'ptt'
        ? dark ? 'text-[var(--primary-400)]' : 'text-[var(--primary-600)]'
        : dark ? 'text-[var(--error-400)]' : 'text-[var(--error-600)]';

  // VAD mic button: glow when speech probability is high
  const vadSpeechGlow =
    voiceMode === 'vad' && vadActive && audioLevel > 0.2;

  return (
    <div className="space-y-1">
      {/* Input row: [textarea] [MODE|MIC] [send] */}
      <div className="flex items-end gap-2">
        {/* Text input */}
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

        {/* Voice controls: segmented [MODE | MIC] */}
        <div className={`flex shrink-0 h-9 rounded-lg overflow-hidden ${groupBg}`}>
          {/* Mode label */}
          <button
            type="button"
            onClick={cycleVoiceMode}
            className={`px-2.5 text-xs font-medium cursor-pointer
                       flex items-center transition-colors ${modeText}`}
            title="音声モード切替 (OFF → PTT → VAD)"
          >
            {voiceMode === 'off' ? 'OFF' : voiceMode === 'ptt' ? 'PTT' : 'VAD'}
          </button>

          {/* Divider */}
          <div className={`w-px self-stretch my-1.5 ${divider}`} />

          {/* Mic / PTT button */}
          <button
            type="button"
            {...(voiceMode === 'ptt'
              ? {
                  onPointerDown: onPttDown,
                  onPointerUp: onPttUp,
                  onPointerLeave: onPttUp,
                }
              : {})}
            disabled={voiceMode === 'off' || busy}
            className={`w-9 flex items-center justify-center transition-all
                       ${voiceMode !== 'off' ? 'cursor-pointer' : 'cursor-default'}
                       ${isRecording && voiceMode === 'ptt' ? 'bg-[var(--error-500)] text-white' : ''}
                       ${isRecording && voiceMode === 'vad' ? 'bg-[var(--error-500)] text-white' : ''}`}
            style={
              isRecording
                ? { boxShadow: `0 0 ${6 + audioLevel * 20}px var(--error-400)` }
                : vadSpeechGlow
                  ? { boxShadow: `0 0 ${4 + audioLevel * 14}px var(--error-300)` }
                  : undefined
            }
            title={
              voiceMode === 'ptt'
                ? '押し続けて録音'
                : voiceMode === 'vad'
                  ? '音声自動検出中'
                  : ''
            }
          >
            {voiceMode === 'vad' ? (
              isRecording ? (
                <Mic className="h-4 w-4 text-white" />
              ) : (
                <Radio className={`h-4 w-4 ${vadActive ? 'animate-pulse' : ''} ${micColor}`} />
              )
            ) : isRecording ? (
              <MicOff className="h-4 w-4" />
            ) : (
              <Mic className={`h-4 w-4 ${micColor}`} />
            )}
          </button>
        </div>

        {/* Send button */}
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

      {/* Status row: level bars + indicators */}
      <div className="flex items-center gap-2 min-h-[16px]">
        {/* VAD mode: always show level bar when active */}
        {voiceMode === 'vad' && vadActive && (
          <div className="flex items-center gap-1.5">
            <AudioLevelBar level={audioLevel} dark={dark} />
            <span className={`text-xs ${
              isRecording ? 'text-[var(--error-500)]' : 'text-[var(--error-600)]'
            }`}>
              {isRecording ? '録音中' : '音声検出中'}
            </span>
          </div>
        )}

        {/* VAD initializing */}
        {voiceMode === 'vad' && !vadActive && (
          <span className="flex items-center gap-1 text-xs text-[var(--gray-500)]">
            <Loader2 className="h-3 w-3 animate-spin" />
            VAD 初期化中...
          </span>
        )}

        {/* PTT recording */}
        {voiceMode === 'ptt' && isRecording && (
          <div className="flex items-center gap-1.5">
            <AudioLevelBar level={audioLevel} dark={dark} />
            <span className="text-xs text-[var(--error-500)]">録音中</span>
          </div>
        )}

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
