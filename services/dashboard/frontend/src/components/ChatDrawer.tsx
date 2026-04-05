import { useEffect, useRef, useCallback, useState } from 'react';
import { motion } from 'framer-motion';
import { X, Bot, User, Trash2 } from 'lucide-react';
import { useChat } from '../hooks/useChat';
import { useVoiceInput } from '../hooks/useVoiceInput';
import ChatInput from './ChatInput';
import AvatarContainer from './avatar/AvatarContainer';

interface Props {
  onClose: () => void;
}

const DEFAULT_AVATAR_URL = '/models/otomachi_una.pmx';

export default function ChatDrawer({ onClose }: Props) {
  const { messages, send, clear, isLoading } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [avatarUrl] = useState<string | null>(() => {
    return localStorage.getItem('soms-avatar-url') || DEFAULT_AVATAR_URL;
  });

  // Voice input: on recognized text, auto-send
  const handleVoiceResult = useCallback(
    (text: string) => {
      send(text);
    },
    [send],
  );

  const voice = useVoiceInput(handleVoiceResult);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length, isLoading]);

  return (
    <motion.div
      className="fixed inset-y-0 right-0 z-50 w-full sm:w-96 bg-white shadow-2xl
                 flex flex-col"
      initial={{ x: '100%' }}
      animate={{ x: 0 }}
      exit={{ x: '100%' }}
      transition={{ type: 'spring', damping: 25, stiffness: 300 }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--gray-200)]">
        <h2 className="text-sm font-semibold text-[var(--gray-900)] flex items-center gap-2">
          <Bot className="h-4 w-4 text-[var(--primary-600)]" />
          Chat
        </h2>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <button
              onClick={clear}
              className="p-1.5 rounded-md text-[var(--gray-400)] hover:text-[var(--gray-600)]
                         hover:bg-[var(--gray-100)] transition-colors cursor-pointer"
              title="会話をクリア"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={onClose}
            className="p-1.5 rounded-md text-[var(--gray-400)] hover:text-[var(--gray-600)]
                       hover:bg-[var(--gray-100)] transition-colors cursor-pointer"
            title="閉じる"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Avatar */}
      <div className="h-48 border-b border-[var(--gray-200)] bg-[var(--gray-50)]">
        <AvatarContainer modelUrl={avatarUrl} className="w-full h-full" />
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && !isLoading && (
          <p className="text-sm text-[var(--gray-400)] text-center py-12">
            質問してみてください
          </p>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'assistant' && (
              <Bot className="h-4 w-4 text-[var(--primary-600)] shrink-0 mt-1" />
            )}
            <div
              className={`max-w-[80%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap break-words ${
                msg.role === 'user'
                  ? 'bg-[var(--primary-600)] text-white'
                  : 'bg-[var(--gray-100)] text-[var(--gray-900)]'
              }`}
            >
              {msg.content}
            </div>
            {msg.role === 'user' && (
              <User className="h-4 w-4 text-[var(--gray-400)] shrink-0 mt-1" />
            )}
          </div>
        ))}

        {isLoading && (
          <div className="flex gap-2 items-center">
            <Bot className="h-4 w-4 text-[var(--primary-600)] shrink-0" />
            <div className="flex gap-1">
              <span className="w-2 h-2 bg-[var(--primary-400)] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-2 h-2 bg-[var(--primary-400)] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-2 h-2 bg-[var(--primary-400)] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="px-4 py-3 border-t border-[var(--gray-200)]">
        <ChatInput
          onSend={send}
          isLoading={isLoading}
          voiceMode={voice.mode}
          onVoiceModeChange={voice.setMode}
          isRecording={voice.isRecording}
          isTranscribing={voice.isTranscribing}
          onPttDown={voice.onPttDown}
          onPttUp={voice.onPttUp}
        />
      </div>
    </motion.div>
  );
}
