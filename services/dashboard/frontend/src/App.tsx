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
