import { useState, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { sendChat } from '../api';
import { audioQueue, AudioPriority } from '../audio';
import type { ChatResponse } from '@soms/types';

export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  audio_url?: string | null;
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [nextId, setNextId] = useState(1);

  const mutation = useMutation({
    mutationFn: sendChat,
    onMutate: (message: string) => {
      // Optimistic: add user message immediately
      const userMsg: ChatMessage = {
        id: nextId,
        role: 'user',
        content: message,
      };
      setMessages(prev => [...prev, userMsg]);
      setNextId(n => n + 1);
    },
    onSuccess: (data: ChatResponse) => {
      const assistantMsg: ChatMessage = {
        id: nextId,
        role: 'assistant',
        content: data.content,
        audio_url: data.audio_url,
      };
      setMessages(prev => [...prev, assistantMsg]);
      setNextId(n => n + 1);

      // Play TTS audio with tone and motion
      if (data.audio_url) {
        audioQueue.enqueue(
          data.audio_url,
          AudioPriority.USER_ACTION,
          data.tone ?? undefined,
          data.motion_id ?? undefined,
        );
      }
    },
    onError: () => {
      const errorMsg: ChatMessage = {
        id: nextId,
        role: 'assistant',
        content: 'エラーが発生しました',
      };
      setMessages(prev => [...prev, errorMsg]);
      setNextId(n => n + 1);
    },
  });

  const send = useCallback(
    (message: string) => {
      const trimmed = message.trim();
      if (!trimmed || mutation.isPending) return;
      mutation.mutate(trimmed);
    },
    [mutation],
  );

  const clear = useCallback(() => {
    setMessages([]);
  }, []);

  return {
    messages,
    send,
    clear,
    isLoading: mutation.isPending,
  };
}
