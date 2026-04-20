import { authFetch } from '@soms/auth';
import type { Task, SystemStats } from '@soms/types';

export interface TaskAuditEntry {
  id: number;
  task_id: number;
  action: string;
  actor_user_id: number | null;
  notes: string | null;
  region_id: string;
  timestamp: string;
}

export async function fetchAuditFeed(limit: number = 100): Promise<TaskAuditEntry[]> {
  const res = await authFetch(`/api/tasks/audit?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch audit feed');
  return res.json();
}

export async function fetchTaskQueue(): Promise<Task[]> {
  const res = await authFetch('/api/tasks/queue');
  if (!res.ok) throw new Error('Failed to fetch task queue');
  return res.json();
}

export async function fetchTaskStats(): Promise<SystemStats> {
  const res = await authFetch('/api/tasks/stats');
  if (!res.ok) throw new Error('Failed to fetch task stats');
  return res.json();
}

export async function dispatchTask(taskId: number): Promise<Task> {
  const res = await authFetch(`/api/tasks/${taskId}/dispatch`, { method: 'PUT' });
  if (!res.ok) throw new Error('Failed to dispatch task');
  return res.json();
}

export async function fetchAdminTasks(): Promise<Task[]> {
  const res = await authFetch('/api/tasks/?audience=admin');
  if (!res.ok) throw new Error('Failed to fetch admin tasks');
  return res.json();
}

export async function completeAdminTask(taskId: number): Promise<Task> {
  const res = await authFetch(`/api/tasks/${taskId}/complete`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ report_status: 'resolved' }),
  });
  if (!res.ok) throw new Error('Failed to complete task');
  return res.json();
}
