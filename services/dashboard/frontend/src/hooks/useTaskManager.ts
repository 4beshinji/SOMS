import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Task, TaskReport, ZoneMultiplierInfo } from '@soms/types';
import { useAudioQueue, AudioPriority } from '../audio';
import {
  fetchTasks,
  fetchStats,
  fetchSupply,
  fetchVoiceEvents,
  fetchZoneMultiplier,
  acceptTask,
  completeTask,
} from '../api';

const DEFAULT_DISPLAY_TASKS = 10;
const DISPLAY_TASKS_INCREMENT = 10;
const COMPLETED_DISPLAY_SECONDS = 300; // 5 minutes
const IGNORED_TASKS_KEY = 'soms-ignored-tasks';

export function useTaskManager() {
  const queryClient = useQueryClient();

  const [isAudioEnabled, setIsAudioEnabled] = useState(false);
  const [prevTaskIds, setPrevTaskIds] = useState<Set<number>>(new Set());
  const [playedVoiceEventIds, setPlayedVoiceEventIds] = useState<Set<number>>(new Set());
  const [acceptedTaskIds, setAcceptedTaskIds] = useState<Set<number>>(new Set());
  const [ignoredTaskIds, setIgnoredTaskIds] = useState<Set<number>>(() => {
    try {
      const stored = localStorage.getItem(IGNORED_TASKS_KEY);
      return stored ? new Set(JSON.parse(stored) as number[]) : new Set();
    } catch {
      return new Set();
    }
  });
  const [maxDisplay, setMaxDisplay] = useState(DEFAULT_DISPLAY_TASKS);
  const initialLoadDone = useRef(false);

  const { enqueue, enqueueFromApi } = useAudioQueue(isAudioEnabled);

  const tasksQuery = useQuery({
    queryKey: ['tasks'],
    queryFn: fetchTasks,
    refetchInterval: 5000,
    staleTime: 3000,
  });

  const statsQuery = useQuery({
    queryKey: ['stats'],
    queryFn: fetchStats,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  const supplyQuery = useQuery({
    queryKey: ['supply'],
    queryFn: fetchSupply,
    refetchInterval: 10000,
    staleTime: 5000,
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

    if (!initialLoadDone.current) {
      initialLoadDone.current = true;
      setPrevTaskIds(currentIds);

      const latest = tasks
        .filter(t => !t.is_completed && t.announcement_audio_url)
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0];
      if (latest) {
        enqueue(latest.announcement_audio_url!, AudioPriority.ANNOUNCEMENT);
      }
      return;
    }

    const newTasks = tasks.filter(t => !prevTaskIds.has(t.id) && !t.is_completed);
    for (const task of newTasks) {
      if (task.announcement_audio_url) {
        enqueue(task.announcement_audio_url, AudioPriority.ANNOUNCEMENT);
      }
    }

    setPrevTaskIds(currentIds);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks, isAudioEnabled, loading, enqueue]);

  // Voice event playback
  useEffect(() => {
    if (!isAudioEnabled || !voiceEventsQuery.data) return;
    for (const event of voiceEventsQuery.data) {
      if (!playedVoiceEventIds.has(event.id) && event.audio_url) {
        enqueue(event.audio_url, AudioPriority.VOICE_EVENT);
        setPlayedVoiceEventIds(prev => new Set(prev).add(event.id));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voiceEventsQuery.data, isAudioEnabled, enqueue]);

  // Sort and filter tasks
  const allFilteredTasks = tasks
    .filter(task => {
      if (ignoredTaskIds.has(task.id)) return false;
      if (task.is_completed && task.completed_at) {
        const completedTime = new Date(task.completed_at).getTime();
        const now = new Date().getTime();
        return (now - completedTime) / 1000 < COMPLETED_DISPLAY_SECONDS;
      }
      return true;
    })
    .sort((a, b) => {
      if (a.is_completed !== b.is_completed) return a.is_completed ? 1 : -1;
      const aAccepted = acceptedTaskIds.has(a.id);
      const bAccepted = acceptedTaskIds.has(b.id);
      if (aAccepted !== bAccepted) return aAccepted ? -1 : 1;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });

  const visibleTasks = allFilteredTasks.slice(0, maxDisplay);
  const hasMoreTasks = allFilteredTasks.length > maxDisplay;

  const handleShowMore = () => {
    setMaxDisplay(prev => prev + DISPLAY_TASKS_INCREMENT);
  };

  const handleAccept = (taskId: number) => {
    setAcceptedTaskIds(prev => new Set(prev).add(taskId));
    acceptMutation.mutate(taskId);
    enqueueFromApi(async () => {
      const res = await fetch('/api/voice/acceptance/random');
      if (!res.ok) return null;
      const data = await res.json();
      return data.audio_url ?? null;
    }, AudioPriority.USER_ACTION);
  };

  const handleComplete = (taskId: number, report?: TaskReport) => {
    const task = tasks.find((t: Task) => t.id === taskId);
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
    setIgnoredTaskIds(prev => {
      const next = new Set(prev).add(taskId);
      try { localStorage.setItem(IGNORED_TASKS_KEY, JSON.stringify([...next])); } catch { /* ignore */ }
      return next;
    });
    enqueueFromApi(async () => {
      const res = await fetch('/api/voice/rejection/random');
      if (!res.ok) return null;
      const data = await res.json();
      return data.audio_url ?? null;
    }, AudioPriority.USER_ACTION);
  };

  return {
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
  };
}
