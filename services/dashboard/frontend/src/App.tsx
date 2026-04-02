import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ErrorBoundary } from '@soms/ui';
import UIPreview from './UIPreview';
import ZoneEditor from './pages/ZoneEditor';
import MonitorHeader from './components/MonitorHeader';
import TaskList from './components/TaskList';
import ShoppingPanel from './components/ShoppingPanel';
import { useTaskManager } from './hooks/useTaskManager';

function Monitor() {
  const {
    visibleTasks,
    hasMoreTasks,
    loading,
    systemStats,
    supply,
    isAudioEnabled,
    setIsAudioEnabled,
    acceptedTaskIds,
    zoneMultipliers,
    handleAccept,
    handleComplete,
    handleIgnore,
    handleShowMore,
  } = useTaskManager();

  const [voiceCredit, setVoiceCredit] = useState<{ engine: string; character: string } | null>(null);
  const [showCredit, setShowCredit] = useState(false);
  useEffect(() => {
    fetch('/api/voice/credit')
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setVoiceCredit(data); })
      .catch(() => {});
  }, []);

  return (
    <div className="min-h-screen bg-[var(--gray-50)]">
      <MonitorHeader
        systemStats={systemStats}
        supply={supply}
        isAudioEnabled={isAudioEnabled}
        onToggleAudio={() => setIsAudioEnabled(!isAudioEnabled)}
      />
      <div className="max-w-7xl mx-auto px-4 py-4 grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
        <TaskList
          tasks={visibleTasks}
          loading={loading}
          hasMoreTasks={hasMoreTasks}
          acceptedTaskIds={acceptedTaskIds}
          zoneMultipliers={zoneMultipliers}
          onAccept={handleAccept}
          onComplete={handleComplete}
          onIgnore={handleIgnore}
          onShowMore={handleShowMore}
        />
        <aside>
          <ShoppingPanel />
        </aside>
      </div>
      {voiceCredit && (
        <footer className="max-w-7xl mx-auto px-4 pb-3 pt-1 text-right">
          <button
            onClick={() => setShowCredit(true)}
            className="text-[10px] text-[var(--gray-400)] underline hover:text-[var(--gray-600)] cursor-pointer"
          >
            クレジット
          </button>
        </footer>
      )}

      <AnimatePresence>
        {showCredit && voiceCredit && (
          <motion.div
            className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowCredit(false)}
          >
            <motion.div
              className="bg-white rounded-2xl p-6 max-w-xs mx-4 text-center shadow-xl"
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              onClick={(e: React.MouseEvent) => e.stopPropagation()}
            >
              <h2 className="text-lg font-bold text-[var(--gray-900)] mb-4">クレジット</h2>
              <div className="space-y-2 text-sm text-[var(--gray-700)]">
                <p>
                  <span className="text-[var(--gray-500)]">音声エンジン：</span>
                  <a
                    href="https://voicevox.hiroshiba.jp/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium text-[var(--primary-600)] underline"
                  >
                    {voiceCredit.engine}
                  </a>
                </p>
                <p>
                  <span className="text-[var(--gray-500)]">キャラクター：</span>
                  <span className="font-medium">{voiceCredit.character}</span>
                </p>
              </div>
              <button
                onClick={() => setShowCredit(false)}
                className="mt-5 px-6 py-2 bg-[var(--gray-100)] hover:bg-[var(--gray-200)] text-[var(--gray-700)] text-sm rounded-lg transition-colors cursor-pointer"
              >
                閉じる
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AuthenticatedApp() {
  return (
    <ErrorBoundary>
      <Monitor />
    </ErrorBoundary>
  );
}

// Route by query parameter — no hooks, no conditional rendering issues
const _params = new URLSearchParams(window.location.search);
const _page = _params.has('preview')
  ? 'preview'
  : _params.has('zone-editor')
    ? 'zone-editor'
    : 'main';

export default function App() {
  switch (_page) {
    case 'preview':
      return <UIPreview />;
    case 'zone-editor':
      return <ZoneEditor />;
    default:
      return <AuthenticatedApp />;
  }
}
