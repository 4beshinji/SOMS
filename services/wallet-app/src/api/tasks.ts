/**
 * Task API client for wallet-app.
 *
 * In dev mode, Vite proxies /api/tasks/* -> dashboard backend at :8000.
 * In production, nginx handles the routing.
 */

import { authFetch } from '../auth/authFetch';
import type { Task, TaskReport } from '@soms/types';

const BASE = '/api/tasks';

export async function fetchTasks(): Promise<Task[]> {
  const res = await authFetch(`${BASE}/`);
  if (!res.ok) throw new Error('Failed to fetch tasks');
  const data = await res.json();
  if (!Array.isArray(data)) throw new Error('Invalid tasks response');
  return data;
}

export async function acceptTask(taskId: number): Promise<void> {
  const res = await authFetch(`${BASE}/${taskId}/accept`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error('Failed to accept task');
}

export async function completeTask({
  taskId,
  report,
}: {
  taskId: number;
  report?: TaskReport;
}): Promise<Task> {
  const res = await authFetch(`${BASE}/${taskId}/complete`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      report_status: report?.status || null,
      completion_note: report?.note || null,
    }),
  });
  if (!res.ok) throw new Error('Failed to complete task');
  return res.json();
}
