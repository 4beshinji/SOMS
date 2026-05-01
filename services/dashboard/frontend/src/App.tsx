import { useEffect, useState, useRef, useCallback } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Bot, User, Trash2, ChevronDown, Moon, Sun } from 'lucide-react';
import { ErrorBoundary } from '@soms/ui';
import UIPreview from './UIPreview';
import ZoneEditor from './pages/ZoneEditor';
import WallView from './pages/WallView';
import MonitorHeader from './components/MonitorHeader';
import TaskCard from './components/TaskCard';
import ShoppingPanel from './components/ShoppingPanel';
import InventoryPanel from './components/InventoryPanel';
import ChatInput from './components/ChatInput';
import AvatarContainer from './components/avatar/AvatarContainer';
import { useTaskManager } from './hooks/useTaskManager';
import { useChat } from './hooks/useChat';
import { useVoiceInput } from './hooks/useVoiceInput';
import { DisplayIdentityContext, useDisplayIdentityProvider } from './hooks/useDisplayIdentity';

const DEFAULT_AVATAR_URL = '/models/otomachi_una.pmx';

function useTheme() {
  const [dark, setDark] = useState(() => localStorage.getItem('soms-theme') === 'dark');
  const toggle = useCallback(() => {
    setDark(prev => {
      const next = !prev;
      localStorage.setItem('soms-theme', next ? 'dark' : 'light');
      return next;
    });
  }, []);
  return { dark, toggle };
}

function Monitor() {
  const {
    visibleTasks,
    hasMoreTasks,
    loading,
    systemStats,
    isAudioEnabled,
    setIsAudioEnabled,
    acceptedTaskIds,
    handleAccept,
    handleComplete,
    handleIgnore,
    handleShowMore,
  } = useTaskManager();

  const { messages, send, clear, isLoading } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);
  const theme = useTheme();

  const [avatarUrl] = useState<string | null>(() => {
    const fromQuery = new URLSearchParams(window.location.search).get('avatar');
    return fromQuery || localStorage.getItem('soms-avatar-url') || DEFAULT_AVATAR_URL;
  });

  // Voice input
  const handleVoiceResult = useCallback((text: string) => send(text), [send]);
  const voice = useVoiceInput(handleVoiceResult);

  // Auto-scroll chat
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length, isLoading]);

  const bg = theme.dark ? 'bg-[var(--gray-900)]' : 'bg-[var(--gray-50)]';
  const avatarBg = theme.dark
    ? 'bg-gradient-to-b from-[var(--gray-800)] to-[var(--gray-900)]'
    : 'bg-gradient-to-b from-white to-[var(--gray-100)]';
  const sidebarBg = theme.dark ? 'bg-[var(--gray-900)]' : 'bg-white';
  const borderColor = theme.dark ? 'border-[var(--gray-700)]' : 'border-[var(--gray-200)]';
  const textMuted = theme.dark ? 'text-[var(--gray-400)]' : 'text-[var(--gray-500)]';
  const textPrimary = theme.dark ? 'text-white' : 'text-[var(--gray-900)]';
  const bubbleAssistant = theme.dark ? 'bg-black/50 text-white' : 'bg-white/90 text-[var(--gray-900)] shadow-sm';
  const inputBg = theme.dark ? 'bg-[var(--gray-900)]' : 'bg-white';

  return (
    <div className={`h-screen flex flex-col ${bg} overflow-hidden`}>
      {/* Full Header */}
      <MonitorHeader
        systemStats={systemStats}
        isAudioEnabled={isAudioEnabled}
        onToggleAudio={() => setIsAudioEnabled(!isAudioEnabled)}
      >
        {/* Theme toggle injected into header */}
        <button
          onClick={theme.toggle}
          className="p-2 rounded-full transition-colors cursor-pointer text-[var(--gray-500)] hover:text-[var(--gray-700)]"
          aria-label={theme.dark ? 'ライトモード' : 'ダークモード'}
        >
          {theme.dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>
      </MonitorHeader>

      {/* Main Content */}
      <div className="flex-1 flex min-h-0">
        {/* Left: Avatar + Chat (primary) */}
        <div className="flex-1 flex flex-col min-w-0 relative">
          {/* Avatar — bust-up, fills top portion */}
          <div className={`flex-1 min-h-0 relative ${avatarBg}`}>
            <AvatarContainer modelUrl={avatarUrl} className="w-full h-full" />

            {/* Chat messages overlay on bottom of avatar area */}
            <div className="absolute inset-x-0 bottom-0 max-h-[50%] flex flex-col pointer-events-none">
              <div
                ref={scrollRef}
                className="flex-1 overflow-y-auto px-4 py-2 space-y-2 pointer-events-auto
                           [mask-image:linear-gradient(to_bottom,transparent_0%,black_20%,black_100%)]"
              >
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    {msg.role === 'assistant' && (
                      <Bot className="h-4 w-4 text-[var(--primary-400)] shrink-0 mt-1" />
                    )}
                    <div
                      className={`max-w-[70%] rounded-xl px-3 py-1.5 text-sm whitespace-pre-wrap break-words  ${
                        msg.role === 'user'
                          ? 'bg-[var(--primary-600)]/90 text-white'
                          : bubbleAssistant
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
                    <Bot className="h-4 w-4 text-[var(--primary-400)] shrink-0" />
                    <div className="flex gap-1">
                      <span className="w-2 h-2 bg-[var(--primary-400)] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-2 h-2 bg-[var(--primary-400)] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-2 h-2 bg-[var(--primary-400)] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Clear button */}
            {messages.length > 0 && (
              <button
                onClick={clear}
                className="absolute top-2 right-2 p-1.5 rounded-full bg-black/30 text-white/60
                           hover:bg-black/50 hover:text-white transition-colors cursor-pointer z-10"
                title="会話をクリア"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* Chat Input */}
          <div className={`${inputBg} border-t ${borderColor} px-4 py-3`}>
            <ChatInput
              onSend={send}
              isLoading={isLoading}
              voiceMode={voice.mode}
              onVoiceModeChange={voice.setMode}
              isRecording={voice.isRecording}
              isTranscribing={voice.isTranscribing}
              audioLevel={voice.audioLevel}
              vadActive={voice.vadActive}
              onPttDown={voice.onPttDown}
              onPttUp={voice.onPttUp}
              dark={theme.dark}
            />
          </div>
        </div>

        {/* Right: Tasks + Shopping */}
        <aside className={`hidden lg:flex flex-col w-[380px] border-l ${borderColor} ${sidebarBg}`}>
          {/* Tasks — scrollable */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">
            <h2 className={`text-xs font-semibold ${textMuted} uppercase tracking-wider px-1`}>
              Tasks
            </h2>
            {loading ? (
              <p className={`text-sm ${textMuted} text-center py-8`}>読み込み中...</p>
            ) : visibleTasks.length === 0 ? (
              <p className={`text-sm ${textMuted} text-center py-8`}>タスクなし</p>
            ) : (
              <AnimatePresence>
                {visibleTasks.map((task, i) => (
                  <motion.div
                    key={task.id}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    transition={{ delay: i * 0.05 }}
                  >
                    <TaskCard
                      task={task}
                      isAccepted={acceptedTaskIds.has(task.id)}
                      onAccept={handleAccept}
                      onComplete={handleComplete}
                      onIgnore={handleIgnore}
                    />
                  </motion.div>
                ))}
              </AnimatePresence>
            )}
            {hasMoreTasks && (
              <button
                onClick={handleShowMore}
                className="w-full py-2 text-xs text-[var(--primary-500)] hover:text-[var(--primary-400)]
                           flex items-center justify-center gap-1 cursor-pointer"
              >
                <ChevronDown className="h-3 w-3" /> もっと見る
              </button>
            )}
          </div>

          {/* Inventory Status */}
          <div className={`border-t ${borderColor}`}>
            <InventoryPanel />
          </div>

          {/* Shopping — fixed at bottom */}
          <div className={`border-t ${borderColor} max-h-[40%] overflow-y-auto`}>
            <ShoppingPanel />
          </div>
        </aside>
      </div>
    </div>
  );
}

function AuthenticatedApp() {
  const displayIdentity = useDisplayIdentityProvider();
  return (
    <DisplayIdentityContext.Provider value={displayIdentity}>
      <ErrorBoundary>
        <Monitor />
      </ErrorBoundary>
    </DisplayIdentityContext.Provider>
  );
}

const _params = new URLSearchParams(window.location.search);
const _page = _params.get('view') === 'wall'
  ? 'wall'
  : _params.has('preview')
    ? 'preview'
    : _params.has('zone-editor')
      ? 'zone-editor'
      : 'main';

export default function App() {
  switch (_page) {
    case 'wall':
      return <WallView />;
    case 'preview':
      return <UIPreview />;
    case 'zone-editor':
      return <ZoneEditor />;
    default:
      return <AuthenticatedApp />;
  }
}
