import { authFetch } from '@soms/auth';
import type { SpatialConfig, LiveSpatialData, HeatmapData } from '@soms/types';

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
