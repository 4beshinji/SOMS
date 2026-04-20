import { authFetch } from '@soms/auth';
import type {
  DevicePositionResponse,
  CreateDevicePositionRequest,
  UpdateDevicePositionRequest,
} from '@soms/types';

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
