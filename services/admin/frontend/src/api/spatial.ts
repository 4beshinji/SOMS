import { authFetch } from '@soms/auth';
import type { SpatialConfig, LiveSpatialData, HeatmapData } from '@soms/types';

export type { SpatialConfig, LiveSpatialData, HeatmapData };

export interface SpatialEvent {
  timestamp: string;
  zone: string;
  event_type: string;
  source_device: string | null;
  severity: string;
  data: Record<string, unknown>;
}

export interface Floorplan {
  building: { width_m: number; height_m: number };
  walls: { points: number[][]; closed: boolean }[];
  columns: { points: number[][] }[];
}

export async function fetchFloorplan(): Promise<Floorplan> {
  const res = await authFetch('/api/sensors/spatial/floorplan');
  if (!res.ok) throw new Error('Failed to fetch floorplan');
  return res.json();
}

export async function fetchSpatialConfig(): Promise<SpatialConfig> {
  const res = await authFetch('/api/sensors/spatial/config');
  if (!res.ok) throw new Error('Failed to fetch spatial config');
  return res.json();
}

export async function fetchLiveSpatial(zone?: string): Promise<LiveSpatialData[]> {
  const params = zone ? `?zone=${encodeURIComponent(zone)}` : '';
  const res = await authFetch(`/api/sensors/spatial/live${params}`);
  if (!res.ok) throw new Error('Failed to fetch live spatial');
  return res.json();
}

export async function fetchHeatmap(zone?: string, period: string = 'hour'): Promise<HeatmapData[]> {
  const params = new URLSearchParams({ period });
  if (zone) params.set('zone', zone);
  const res = await authFetch(`/api/sensors/spatial/heatmap?${params}`);
  if (!res.ok) throw new Error('Failed to fetch heatmap');
  return res.json();
}

export async function fetchSpatialEvents(zone?: string, limit: number = 50): Promise<SpatialEvent[]> {
  const qs = new URLSearchParams();
  if (zone) qs.set('zone', zone);
  qs.set('limit', String(limit));
  const res = await authFetch(`/api/sensors/events?${qs}`);
  if (!res.ok) throw new Error('Failed to fetch events');
  return res.json();
}
