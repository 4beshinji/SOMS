import { authFetch } from '@soms/auth';
import type { Task, SystemStats } from '@soms/types';

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
