import { ErrorBoundary } from '@soms/ui';
import { useAuth } from '@soms/auth';
import UIPreview from './UIPreview';
import MonitorHeader from './components/MonitorHeader';
import TaskList from './components/TaskList';
import { useTaskManager } from './hooks/useTaskManager';
import LoginPage from './pages/LoginPage';

function Monitor() {
  const {
    visibleTasks,
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
  } = useTaskManager();

  return (
    <div className="min-h-screen bg-[var(--gray-50)]">
      <MonitorHeader
        systemStats={systemStats}
        supply={supply}
        isAudioEnabled={isAudioEnabled}
        onToggleAudio={() => setIsAudioEnabled(!isAudioEnabled)}
      />
      <TaskList
        tasks={visibleTasks}
        loading={loading}
        acceptedTaskIds={acceptedTaskIds}
        zoneMultipliers={zoneMultipliers}
        onAccept={handleAccept}
        onComplete={handleComplete}
        onIgnore={handleIgnore}
      />
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
