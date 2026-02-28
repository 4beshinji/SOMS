import type { Task, TaskReport, SystemStats, SupplyStats, ZoneMultiplierInfo } from '@soms/types';
import { authFetch } from '@soms/auth';

export type { Task, TaskReport, SystemStats, SupplyStats, ZoneMultiplierInfo };

export const fetchTasks = async (): Promise<Task[]> => {
  const res = await authFetch('/api/tasks/');
  if (!res.ok) throw new Error('Failed to fetch tasks');
  const data = await res.json();
  if (!Array.isArray(data)) throw new Error('Invalid tasks response: expected array');
  return data;
};

export const fetchStats = async (): Promise<SystemStats> => {
  const res = await authFetch('/api/tasks/stats');
  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
};

export const fetchSupply = async (): Promise<SupplyStats> => {
  const res = await authFetch('/api/wallet/supply');
  if (!res.ok) throw new Error('Failed to fetch supply');
  return res.json();
};

export const fetchVoiceEvents = async (): Promise<{ id: number; audio_url: string }[]> => {
  const res = await authFetch('/api/voice-events/recent');
  if (!res.ok) throw new Error('Failed to fetch voice events');
  return res.json();
};

export const acceptTask = async (taskId: number): Promise<void> => {
  const res = await authFetch(`/api/tasks/${taskId}/accept`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error('Failed to accept task');
};

export const completeTask = async ({
  taskId,
  report,
}: {
  taskId: number;
  report?: TaskReport;
}): Promise<Task> => {
  const res = await authFetch(`/api/tasks/${taskId}/complete`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      report_status: report?.status || null,
      completion_note: report?.note || null,
    }),
  });
  if (!res.ok) throw new Error('Failed to complete task');
  return res.json();
};

export const fetchZoneMultiplier = async (zone: string): Promise<ZoneMultiplierInfo> => {
  const res = await authFetch(`/api/wallet/devices/zone-multiplier/${encodeURIComponent(zone)}`);
  if (!res.ok) throw new Error('Failed to fetch zone multiplier');
  return res.json();
};
