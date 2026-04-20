import { authFetch } from '@soms/auth';

export interface StockStatus {
  count: number;
  max: number;
  generating: boolean;
}

export async function fetchRejectionStatus(): Promise<StockStatus> {
  const res = await authFetch('/api/voice/rejection/status');
  if (!res.ok) throw new Error('Failed to fetch rejection status');
  const data = await res.json();
  return { count: data.stock_count, max: data.max_stock, generating: data.is_generating };
}

export async function clearRejectionStock(): Promise<void> {
  const res = await authFetch('/api/voice/rejection/clear', { method: 'POST' });
  if (!res.ok) throw new Error('Failed to clear rejection stock');
}

export async function fetchAcceptanceStatus(): Promise<StockStatus> {
  const res = await authFetch('/api/voice/acceptance/status');
  if (!res.ok) throw new Error('Failed to fetch acceptance status');
  const data = await res.json();
  return { count: data.stock_count, max: data.max_stock, generating: data.is_generating };
}

export async function clearAcceptanceStock(): Promise<void> {
  const res = await authFetch('/api/voice/acceptance/clear', { method: 'POST' });
  if (!res.ok) throw new Error('Failed to clear acceptance stock');
}
