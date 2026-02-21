import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import TaskCard, { TaskReport } from './components/TaskCard';
import { FloorPlanView } from './components/FloorPlan';
import { useAudioQueue, AudioPriority } from './audio';
import {
  fetchTasks,
  fetchStats,
  fetchSupply,
  fetchVoiceEvents,
  fetchZoneMultiplier,
  acceptTask,
  completeTask,
  type ZoneMultiplierInfo,
} from './api';
import { authFetch } from './auth/authFetch';
import { ErrorBoundary } from './components/ErrorBoundary';
import AnalyticsPage from './pages/AnalyticsPage';

type ActiveView = 'tasks' | 'floorplan' | 'analytics';

function Dashboard() {
  const queryClient = useQueryClient();

  const [activeView, setActiveView] = useState<ActiveView>('tasks');
  const [isAudioEnabled, setIsAudioEnabled] = useState(false);
  const [prevTaskIds, setPrevTaskIds] = useState<Set<number>>(new Set());
  const [playedVoiceEventIds, setPlayedVoiceEventIds] = useState<Set<number>>(new Set());
  const [acceptedTaskIds, setAcceptedTaskIds] = useState<Set<number>>(new Set());
  const [ignoredTaskIds, setIgnoredTaskIds] = useState<Set<number>>(new Set());
  const initialLoadDone = useRef(false);

  // Configuration
  const MAX_DISPLAY_TASKS = 10;
  const COMPLETED_Display_SECONDS = 300; // 5 minutes

  const { enqueue, enqueueFromApi } = useAudioQueue(isAudioEnabled);

  const tasksQuery = useQuery({
    queryKey: ['tasks'],
    queryFn: fetchTasks,
    refetchInterval: 5000,
  });

  const statsQuery = useQuery({
    queryKey: ['stats'],
    queryFn: fetchStats,
    refetchInterval: 10000,
  });

  const supplyQuery = useQuery({
    queryKey: ['supply'],
    queryFn: fetchSupply,
    refetchInterval: 10000,
  });

  const voiceEventsQuery = useQuery({
    queryKey: ['voiceEvents'],
    queryFn: fetchVoiceEvents,
    refetchInterval: 3000,
    enabled: isAudioEnabled,
  });

  const acceptMutation = useMutation({
    mutationFn: acceptTask,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tasks'] }),
  });

  const completeMutation = useMutation({
    mutationFn: completeTask,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tasks'] }),
  });

  const tasks = Array.isArray(tasksQuery.data) ? tasksQuery.data : [];
  const loading = tasksQuery.isLoading;
  const systemStats = statsQuery.data ?? null;
  const supply = supplyQuery.data ?? null;

  // Collect unique zones from active tasks for multiplier fetching
  const activeZones = useMemo(() => {
    const zones = new Set<string>();
    for (const t of tasks) {
      if (t.zone && !t.is_completed) zones.add(t.zone);
    }
    return Array.from(zones);
  }, [tasks]);

  const zoneMultiplierQueries = useQueries({
    queries: activeZones.map(zone => ({
      queryKey: ['zoneMultiplier', zone],
      queryFn: () => fetchZoneMultiplier(zone),
      refetchInterval: 30000,
      staleTime: 15000,
    })),
  });

  const zoneMultipliers = useMemo(() => {
    const map: Record<string, ZoneMultiplierInfo> = {};
    activeZones.forEach((zone, i) => {
      const data = zoneMultiplierQueries[i]?.data;
      if (data) map[zone] = data;
    });
    return map;
  }, [activeZones, zoneMultiplierQueries]);

  // Restore accepted state from server on data load
  useEffect(() => {
    if (!Array.isArray(tasksQuery.data)) return;
    const serverAccepted = new Set(
      tasksQuery.data
        .filter(t => t.assigned_to != null && !t.is_completed)
        .map(t => t.id)
    );
    if (serverAccepted.size > 0) {
      setAcceptedTaskIds(prev => new Set([...prev, ...serverAccepted]));
    }
  }, [tasksQuery.data]);

  // Handle auto-playback for NEW tasks + play latest on first enable
  useEffect(() => {
    if (!isAudioEnabled || loading || tasks.length === 0) return;

    const currentIds = new Set(tasks.map(t => t.id));

    // On first activation, play the latest uncompleted task's announcement
    if (!initialLoadDone.current) {
      initialLoadDone.current = true;
      setPrevTaskIds(currentIds);

      const latest = tasks
        .filter(t => !t.is_completed && t.announcement_audio_url)
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0];
      if (latest) {
        console.log("Initial announcement:", latest.title, latest.announcement_audio_url);
        enqueue(latest.announcement_audio_url!, AudioPriority.ANNOUNCEMENT);
      }
      return;
    }

    // Find genuinely new, uncompleted tasks
    const newTasks = tasks.filter(t => !prevTaskIds.has(t.id) && !t.is_completed);

    for (const task of newTasks) {
      if (task.announcement_audio_url) {
        console.log("Announcement sound trigger:", task.title, task.announcement_audio_url);
        enqueue(task.announcement_audio_url, AudioPriority.ANNOUNCEMENT);
      }
    }

    setPrevTaskIds(currentIds);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- prevTaskIds intentionally captures previous render's value
  }, [tasks, isAudioEnabled, loading, enqueue]);

  // Voice event playback side effect
  useEffect(() => {
    if (!isAudioEnabled || !voiceEventsQuery.data) return;
    for (const event of voiceEventsQuery.data) {
      if (!playedVoiceEventIds.has(event.id) && event.audio_url) {
        enqueue(event.audio_url, AudioPriority.VOICE_EVENT);
        setPlayedVoiceEventIds(prev => new Set(prev).add(event.id));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- playedVoiceEventIds intentionally excluded to avoid re-enqueue loop
  }, [voiceEventsQuery.data, isAudioEnabled, enqueue]);

  // Sort and Filter Tasks
  const visibleTasks = tasks
    .filter(task => {
      // Hide ignored tasks
      if (ignoredTaskIds.has(task.id)) return false;
      // Filter out completed tasks older than config time
      if (task.is_completed && task.completed_at) {
        const completedTime = new Date(task.completed_at).getTime();
        const now = new Date().getTime();
        return (now - completedTime) / 1000 < COMPLETED_Display_SECONDS;
      }
      return true;
    })
    .sort((a, b) => {
      // 1. Active tasks first
      if (a.is_completed !== b.is_completed) {
        return a.is_completed ? 1 : -1;
      }
      // 2. Accepted tasks float to top among active
      const aAccepted = acceptedTaskIds.has(a.id);
      const bAccepted = acceptedTaskIds.has(b.id);
      if (aAccepted !== bAccepted) {
        return aAccepted ? -1 : 1;
      }
      // 3. Sort by creation date (Newest first)
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    })
    .slice(0, MAX_DISPLAY_TASKS);

  const handleAccept = (taskId: number) => {
    setAcceptedTaskIds(prev => new Set(prev).add(taskId));
    acceptMutation.mutate(taskId);

    enqueueFromApi(async () => {
      const res = await authFetch('/api/voice/acceptance/random');
      if (!res.ok) return null;
      const data = await res.json();
      return data.audio_url ?? null;
    }, AudioPriority.USER_ACTION);
  };

  const handleComplete = (taskId: number, report?: TaskReport) => {
    const task = tasks.find(t => t.id === taskId);

    if (task?.completion_audio_url) {
      enqueue(task.completion_audio_url, AudioPriority.USER_ACTION);
    }

    completeMutation.mutate({ taskId, report });
    setAcceptedTaskIds(prev => {
      const next = new Set(prev);
      next.delete(taskId);
      return next;
    });
  };

  const handleIgnore = (taskId: number) => {
    setIgnoredTaskIds(prev => new Set(prev).add(taskId));

    enqueueFromApi(async () => {
      const res = await authFetch('/api/voice/rejection/random');
      if (!res.ok) return null;
      const data = await res.json();
      return data.audio_url ?? null;
    }, AudioPriority.USER_ACTION);
  };

  return (
    <div className="min-h-screen bg-[var(--gray-50)]">
      {/* Header */}
      <header className="bg-white border-b border-[var(--gray-200)] elevation-1">
        <div className="max-w-6xl mx-auto px-6 py-6">
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="flex justify-between items-center"
          >
            <div>
              <h1 className="text-4xl font-bold text-[var(--primary-500)]">
                SOMS
              </h1>
              <p className="text-[var(--gray-600)] mt-1">
                共生型オフィス管理システム
              </p>
            </div>

            {/* View Tabs */}
            <div className="flex items-center gap-1 bg-[var(--gray-100)] rounded-lg p-1">
              <button
                onClick={() => setActiveView('tasks')}
                className={`px-4 py-2 text-sm rounded-md transition-all ${
                  activeView === 'tasks'
                    ? 'bg-white text-[var(--primary-600)] shadow-sm font-medium'
                    : 'text-[var(--gray-500)] hover:text-[var(--gray-700)]'
                }`}
              >
                Tasks
              </button>
              <button
                onClick={() => setActiveView('floorplan')}
                className={`px-4 py-2 text-sm rounded-md transition-all ${
                  activeView === 'floorplan'
                    ? 'bg-white text-[var(--primary-600)] shadow-sm font-medium'
                    : 'text-[var(--gray-500)] hover:text-[var(--gray-700)]'
                }`}
              >
                Floor Plan
              </button>
              <button
                onClick={() => setActiveView('analytics')}
                className={`px-4 py-2 text-sm rounded-md transition-all ${
                  activeView === 'analytics'
                    ? 'bg-white text-[var(--primary-600)] shadow-sm font-medium'
                    : 'text-[var(--gray-500)] hover:text-[var(--gray-700)]'
                }`}
              >
                Analytics
              </button>
            </div>

            {/* System Stats + Supply */}
            <div className="flex items-center gap-4">
              {systemStats && (
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gradient-to-r from-purple-100 to-pink-100 border border-[var(--xp-purple)]">
                    <span className="font-bold text-sm text-[var(--xp-purple-dark)]">{systemStats.total_xp} XP</span>
                  </div>
                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--gray-100)] border border-[var(--gray-300)]">
                    <span className="text-sm text-[var(--gray-700)]">{systemStats.tasks_completed} 完了</span>
                  </div>
                </div>
              )}
              {supply && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gradient-to-r from-yellow-100 to-amber-100 border border-[var(--gold)]">
                  <span className="text-sm font-medium text-[var(--gold-dark)]">
                    {supply.circulating} 流通
                  </span>
                </div>
              )}
            </div>

            {/* Audio Toggle */}
            <button
              onClick={() => setIsAudioEnabled(!isAudioEnabled)}
              className={`p-3 rounded-full transition-all duration-300 ${isAudioEnabled
                ? 'bg-[var(--primary-100)] text-[var(--primary-600)] shadow-inner'
                : 'bg-[var(--gray-100)] text-[var(--gray-400)]'
                }`}
              title={isAudioEnabled ? "音声オン" : "音声オフ"}
            >
              {isAudioEnabled ? (
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 5L6 9H2v6h4l5 4V5z"></path><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 5L6 9H2v6h4l5 4V5z"></path><line x1="23" y1="9" x2="17" y2="15"></line><line x1="17" y1="9" x2="23" y2="15"></line></svg>
              )}
            </button>
          </motion.div>
        </div>
      </header>

      {/* Main Content */}
      {activeView === 'analytics' ? (
        <AnalyticsPage />
      ) : (
        <main className="max-w-6xl mx-auto px-6 py-8">
          {activeView === 'tasks' ? (
            <>
              <div className="mb-6">
                <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-2">
                  お願い事一覧
                </h2>
                <p className="text-[var(--gray-600)]">
                  タスクを完了して報酬を受け取りましょう。スマホのウォレットアプリで QR コードを読み取ってください。
                </p>
              </div>

              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="text-center">
                    <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-[var(--primary-500)] border-t-transparent"></div>
                    <p className="text-[var(--gray-600)] mt-4">タスクを読み込み中...</p>
                  </div>
                </div>
              ) : tasks.length === 0 ? (
                <div className="text-center py-12">
                  <p className="text-[var(--gray-500)] text-lg">現在利用可能なタスクはありません。</p>
                  <p className="text-[var(--gray-400)] text-sm mt-2">新しいタスクが追加されるまでお待ちください！</p>
                </div>
              ) : (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.5 }}
                  className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
                >
                  {visibleTasks.map((task, index) => (
                    <motion.div
                      key={task.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: index * 0.1 }}
                    >
                      <TaskCard
                        task={task}
                        isAccepted={acceptedTaskIds.has(task.id)}
                        zoneMultiplier={task.zone ? zoneMultipliers[task.zone] : undefined}
                        onAccept={handleAccept}
                        onComplete={handleComplete}
                        onIgnore={handleIgnore}
                      />
                    </motion.div>
                  ))}
                </motion.div>
              )}
            </>
          ) : (
            <>
              <div className="mb-6">
                <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-2">
                  Floor Plan
                </h2>
                <p className="text-[var(--gray-600)]">
                  Office spatial overview with real-time occupancy data.
                </p>
              </div>
              <FloorPlanView />
            </>
          )}
        </main>
      )}
    </div>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <Dashboard />
    </ErrorBoundary>
  );
}

export default App;
