import { Task, TaskReport } from './components/TaskCard';
import type { SpatialConfig, LiveSpatialData, HeatmapData } from './types/spatial';
import { authFetch } from './auth/authFetch';

export interface SystemStats {
  total_xp: number;
  tasks_completed: number;
  tasks_created: number;
  tasks_active: number;
  tasks_queued: number;
  tasks_completed_last_hour: number;
}

export interface SupplyStats {
  total_issued: number;
  total_burned: number;
  circulating: number;
}

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

// ── Zone Multiplier API ─────────────────────────────────────────────

export interface ZoneMultiplierInfo {
  zone: string;
  multiplier: number;
  device_count: number;
  avg_xp: number;
  devices: { device_id: string; xp: number; contribution: number }[];
}

export const fetchZoneMultiplier = async (zone: string): Promise<ZoneMultiplierInfo> => {
  const res = await authFetch(`/api/wallet/devices/zone-multiplier/${encodeURIComponent(zone)}`);
  if (!res.ok) throw new Error('Failed to fetch zone multiplier');
  return res.json();
};

// ── Sensor API ──────────────────────────────────────────────────────

export interface SensorReading {
  timestamp: string;
  zone: string;
  channel: string;
  value: number;
  device_id: string | null;
}

export const fetchSensorLatest = async (): Promise<SensorReading[]> => {
  const res = await authFetch('/api/sensors/latest');
  if (!res.ok) throw new Error('Failed to fetch sensor latest');
  return res.json();
};

// ── Device Position API ─────────────────────────────────────────────

export interface DevicePositionResponse {
  id: number;
  device_id: string;
  zone: string;
  x: number;
  y: number;
  device_type: string;
  channels: string[];
}

export interface CreateDevicePositionRequest {
  device_id: string;
  zone: string;
  x: number;
  y: number;
  device_type: string;
  channels: string[];
}

export interface UpdateDevicePositionRequest {
  x: number;
  y: number;
  zone?: string;
}

export const fetchDevicePositions = async (): Promise<DevicePositionResponse[]> => {
  const res = await authFetch('/api/devices/positions/');
  if (!res.ok) throw new Error('Failed to fetch device positions');
  return res.json();
};

export const createDevicePosition = async (data: CreateDevicePositionRequest): Promise<DevicePositionResponse> => {
  const res = await authFetch('/api/devices/positions/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create device position');
  return res.json();
};

export const updateDevicePosition = async (deviceId: string, data: UpdateDevicePositionRequest): Promise<DevicePositionResponse> => {
  const res = await authFetch(`/api/devices/positions/${encodeURIComponent(deviceId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update device position');
  return res.json();
};

export const deleteDevicePosition = async (deviceId: string): Promise<void> => {
  const res = await authFetch(`/api/devices/positions/${encodeURIComponent(deviceId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete device position');
};

// ── Spatial API ──────────────────────────────────────────────────────

export const fetchSpatialConfig = async (): Promise<SpatialConfig> => {
  const res = await authFetch('/api/sensors/spatial/config');
  if (!res.ok) throw new Error('Failed to fetch spatial config');
  return res.json();
};

export const fetchLiveSpatial = async (zone?: string): Promise<LiveSpatialData[]> => {
  const params = zone ? `?zone=${encodeURIComponent(zone)}` : '';
  const res = await authFetch(`/api/sensors/spatial/live${params}`);
  if (!res.ok) throw new Error('Failed to fetch live spatial');
  return res.json();
};

export const fetchHeatmap = async (zone?: string, period: string = 'hour'): Promise<HeatmapData[]> => {
  const params = new URLSearchParams({ period });
  if (zone) params.set('zone', zone);
  const res = await authFetch(`/api/sensors/spatial/heatmap?${params}`);
  if (!res.ok) throw new Error('Failed to fetch heatmap');
  return res.json();
};
