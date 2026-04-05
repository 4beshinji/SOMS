import { useState, useCallback, useRef } from 'react';
import { sendChatStream } from '../api';
import { audioQueue, AudioPriority } from '../audio';

export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  audio_url?: string | null;
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const nextIdRef = useRef(1);

  const send = useCallback(
    (message: string) => {
      const trimmed = message.trim();
      if (!trimmed || isLoading) return;
      setIsLoading(true);

      // Add user message immediately
      const userId = nextIdRef.current++;
      const userMsg: ChatMessage = { id: userId, role: 'user', content: trimmed };
      setMessages(prev => [...prev, userMsg]);

      // Placeholder assistant message (built up as chunks arrive)
      const assistantId = nextIdRef.current++;
      const assistantMsg: ChatMessage = { id: assistantId, role: 'assistant', content: '' };
      setMessages(prev => [...prev, assistantMsg]);

      sendChatStream(
        trimmed,
        // onChunk: append text + enqueue audio immediately
        (chunk) => {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId
                ? { ...m, content: m.content + chunk.text }
                : m,
            ),
          );
          if (chunk.audio_url) {
            audioQueue.enqueue(
              chunk.audio_url,
              AudioPriority.USER_ACTION,
              chunk.tone ?? undefined,
              chunk.motion_id ?? undefined,
            );
          }
        },
        // onDone
        () => setIsLoading(false),
        // onError
        () => {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId && !m.content
                ? { ...m, content: 'エラーが発生しました' }
                : m,
            ),
          );
          setIsLoading(false);
        },
      );
    },
    [isLoading],
  );

  const clear = useCallback(() => {
    setMessages([]);
  }, []);

  return {
    messages,
    send,
    clear,
    isLoading,
  };
}
