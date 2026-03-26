import { authFetch } from '@soms/auth';
import type { SensorReading } from '@soms/types';

// ── Types ────────────────────────────────────────────────────────────

export type { SensorReading };

export interface TimeSeriesPoint {
  timestamp: string;
  avg: number;
  max: number;
  min: number;
  count: number;
}

export interface TimeSeriesResponse {
  zone: string | null;
  channel: string | null;
  window: string;
  points: TimeSeriesPoint[];
}

export interface ZoneSnapshot {
  zone: string;
  channels: Record<string, number>;
  event_count: number;
  last_update: string | null;
}

export interface EventItem {
  timestamp: string;
  zone: string;
  event_type: string;
  source_device: string | null;
  severity: string | null;
  data: Record<string, unknown>;
}

export interface LLMActivity {
  cycles: number;
  total_tool_calls: number;
  avg_duration_sec: number;
  hours: number;
}

export interface LLMTimelinePoint {
  timestamp: string;
  cycles: number;
  tool_calls: number;
  avg_duration_sec: number;
}

export interface LLMTimelineResponse {
  hours: number;
  points: LLMTimelinePoint[];
}

// ── Fetch functions ──────────────────────────────────────────────────

export async function fetchSensorLatest(zone?: string): Promise<SensorReading[]> {
  const params = zone ? `?zone=${encodeURIComponent(zone)}` : '';
  const res = await authFetch(`/api/sensors/latest${params}`);
  if (!res.ok) throw new Error('Failed to fetch sensor latest');
  return res.json();
}

export async function fetchSensorLatestByDevice(): Promise<SensorReading[]> {
  const res = await authFetch('/api/sensors/latest-by-device');
  if (!res.ok) throw new Error('Failed to fetch sensor latest by device');
  return res.json();
}

export async function fetchSensorTimeSeries(
  zone?: string,
  channel?: string,
  window: string = '1h',
): Promise<TimeSeriesResponse> {
  const params = new URLSearchParams({ window });
  if (zone) params.set('zone', zone);
  if (channel) params.set('channel', channel);
  const res = await authFetch(`/api/sensors/time-series?${params}`);
  if (!res.ok) throw new Error('Failed to fetch time series');
  return res.json();
}

export async function fetchZoneOverview(): Promise<ZoneSnapshot[]> {
  const res = await authFetch('/api/sensors/zones');
  if (!res.ok) throw new Error('Failed to fetch zone overview');
  return res.json();
}

export async function fetchEvents(
  zone?: string,
  limit: number = 50,
): Promise<EventItem[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (zone) params.set('zone', zone);
  const res = await authFetch(`/api/sensors/events?${params}`);
  if (!res.ok) throw new Error('Failed to fetch events');
  return res.json();
}

export async function fetchLLMActivity(hours: number = 24): Promise<LLMActivity> {
  const res = await authFetch(`/api/sensors/llm-activity?hours=${hours}`);
  if (!res.ok) throw new Error('Failed to fetch LLM activity');
  return res.json();
}

export async function fetchLLMTimeline(hours: number = 24): Promise<LLMTimelineResponse> {
  const res = await authFetch(`/api/sensors/llm-timeline?hours=${hours}`);
  if (!res.ok) throw new Error('Failed to fetch LLM timeline');
  return res.json();
}
