import { useState, useCallback, useRef } from 'react';
import { sendChatStream } from '../api';
import { audioQueue, AudioPriority } from '../audio';

export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  audio_url?: string | null;
}

// Dev-only seed: shown when running `vite dev` so the chat UI isn't empty for design review.
// Disable by appending `?chat=empty` to the URL, or remove the constant for prod-only behavior.
const DEV_SEED: ChatMessage[] = import.meta.env.DEV && !new URLSearchParams(window.location.search).has('chat')
  ? [
      { id: 1, role: 'user', content: 'おはよう' },
      { id: 2, role: 'assistant', content: 'おはようございます。今朝は気温22℃、湿度58%、過ごしやすそうですね。' },
      { id: 3, role: 'user', content: '今日のタスク何があったっけ' },
      { id: 4, role: 'assistant', content: '現在3件のアクティブタスクがあります。会議室Bの空調、ホワイトボード消去、コーヒー豆の補充です。優先度が高いのは空調の件ですね。' },
      { id: 5, role: 'user', content: 'コーヒー豆って今どれくらい残ってる?' },
      { id: 6, role: 'assistant', content: '在庫センサの計測では180g、約2杯分です。最低基準を下回ったので補充タスクを起こしました。' },
      { id: 7, role: 'user', content: 'ありがとう、後で買ってくる' },
      { id: 8, role: 'assistant', content: 'お任せします。買い物リストの「コーヒー豆 (深煎り)」は2袋でカルディ予定になっています。変更があれば教えてください。' },
    ]
  : [];

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>(DEV_SEED);
  const [isLoading, setIsLoading] = useState(false);
  const nextIdRef = useRef(DEV_SEED.length + 1);

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
