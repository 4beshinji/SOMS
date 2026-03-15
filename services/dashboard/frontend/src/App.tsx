import { ErrorBoundary } from '@soms/ui';
import { useAuth } from '@soms/auth';
import UIPreview from './UIPreview';
import MonitorHeader from './components/MonitorHeader';
import TaskList from './components/TaskList';
import ShoppingPanel from './components/ShoppingPanel';
import { useTaskManager } from './hooks/useTaskManager';
import LoginPage from './pages/LoginPage';

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
    </div>
  );
}

export default function App() {
  if (new URLSearchParams(window.location.search).has('preview')) {
    return <UIPreview />;
  }

  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[var(--gray-50)]">
        <div className="text-[var(--gray-500)]">読み込み中...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <ErrorBoundary>
      <Monitor />
    </ErrorBoundary>
  );
}
