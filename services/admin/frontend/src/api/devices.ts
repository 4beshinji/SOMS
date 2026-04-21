import { authFetch } from '@soms/auth';
import type {
  DevicePositionResponse,
  CreateDevicePositionRequest,
  UpdateDevicePositionRequest,
} from '@soms/types';

// ── Device health (brain DeviceRegistry snapshot via backend proxy) ──

export interface DeviceHealth {
  device_id: string;
  device_type: string | null;
  state: string;  // online | sleeping | offline | unknown
  battery_pct: number | null;
  trusted: boolean;
  capabilities: string[];
  power_mode: string;
  last_seen: string;  // ISO
}

export async function fetchDeviceHealth(): Promise<DeviceHealth[]> {
  const res = await authFetch('/api/devices/status');
  if (!res.ok) throw new Error(`Failed to fetch device health (${res.status})`);
  const data = await res.json();
  return data.devices ?? [];
}

// ── Device position CRUD ─────────────────────────────────────────────

export async function fetchDevicePositions(): Promise<DevicePositionResponse[]> {
  const res = await authFetch('/api/devices/positions/');
  if (!res.ok) throw new Error('Failed to fetch device positions');
  return res.json();
}

export async function createDevicePosition(
  data: CreateDevicePositionRequest,
): Promise<DevicePositionResponse> {
  const res = await authFetch('/api/devices/positions/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create device position');
  return res.json();
}

export async function updateDevicePosition(
  deviceId: string,
  data: UpdateDevicePositionRequest,
): Promise<DevicePositionResponse> {
  const res = await authFetch(`/api/devices/positions/${encodeURIComponent(deviceId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update device position');
  return res.json();
}

export async function deleteDevicePosition(deviceId: string): Promise<void> {
  const res = await authFetch(`/api/devices/positions/${encodeURIComponent(deviceId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete device position');
}
