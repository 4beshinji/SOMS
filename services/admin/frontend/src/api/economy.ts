import { authFetch } from '@soms/auth';
import type { SupplyStats } from '@soms/types';

export interface RewardRate {
  device_type: string;
  base_rate: number;
  description?: string;
}

export interface FundingPool {
  id: number;
  title: string;
  goal_jpy: number;
  raised_jpy: number;
  status: string;
  progress_pct: number;
  device_id?: string;
  created_at: string;
}

export interface PoolDetail extends FundingPool {
  contributions: { id: number; user_id: number; amount_jpy: number; created_at: string }[];
}

export async function fetchRewardRates(): Promise<RewardRate[]> {
  const res = await authFetch('/api/wallet/reward-rates');
  if (!res.ok) throw new Error('Failed to fetch reward rates');
  return res.json();
}

export async function updateRewardRate(deviceType: string, baseRate: number): Promise<RewardRate> {
  const res = await authFetch(`/api/wallet/reward-rates/${encodeURIComponent(deviceType)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ base_rate: baseRate }),
  });
  if (!res.ok) throw new Error('Failed to update reward rate');
  return res.json();
}

export async function fetchSupply(): Promise<SupplyStats> {
  const res = await authFetch('/api/wallet/supply');
  if (!res.ok) throw new Error('Failed to fetch supply');
  return res.json();
}

export async function triggerDemurrage(): Promise<{ message: string }> {
  const res = await authFetch('/api/wallet/demurrage/trigger', { method: 'POST' });
  if (!res.ok) throw new Error('Failed to trigger demurrage');
  return res.json();
}

export async function fetchPools(): Promise<FundingPool[]> {
  const res = await authFetch('/api/wallet/admin/pools');
  if (!res.ok) throw new Error('Failed to fetch pools');
  return res.json();
}

export async function fetchPoolDetail(poolId: number): Promise<PoolDetail> {
  const res = await authFetch(`/api/wallet/admin/pools/${poolId}`);
  if (!res.ok) throw new Error('Failed to fetch pool detail');
  return res.json();
}

export async function createPool(title: string, goalJpy: number): Promise<FundingPool> {
  const res = await authFetch('/api/wallet/admin/pools', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, goal_jpy: goalJpy }),
  });
  if (!res.ok) throw new Error('Failed to create pool');
  return res.json();
}

export async function contributeToPool(poolId: number, userId: number, amountJpy: number): Promise<void> {
  const res = await authFetch(`/api/wallet/admin/pools/${poolId}/contribute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, amount_jpy: amountJpy }),
  });
  if (!res.ok) throw new Error('Failed to contribute');
}

export async function activatePool(poolId: number, deviceId: string): Promise<void> {
  const res = await authFetch(`/api/wallet/admin/pools/${poolId}/activate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device_id: deviceId }),
  });
  if (!res.ok) throw new Error('Failed to activate pool');
}
