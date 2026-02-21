import { useQuery } from '@tanstack/react-query';
import { authFetch } from '../auth/authFetch';

// ── Types ────────────────────────────────────────────────────────────

export interface SensorReading {
  timestamp: string;
  zone: string;
  channel: string;
  value: number;
  device_id: string | null;
}

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
  data: Record<string, unknown>;
}

export interface LLMActivity {
  cycles: number;
  total_tool_calls: number;
  avg_duration_sec: number;
  hours: number;
}

// ── Fetch functions ──────────────────────────────────────────────────

async function fetchSensorTimeSeries(
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

async function fetchLLMActivity(hours: number = 24): Promise<LLMActivity> {
  const res = await authFetch(`/api/sensors/llm-activity?hours=${hours}`);
  if (!res.ok) throw new Error('Failed to fetch LLM activity');
  return res.json();
}

async function fetchZoneOverview(): Promise<ZoneSnapshot[]> {
  const res = await authFetch('/api/sensors/zones');
  if (!res.ok) throw new Error('Failed to fetch zone overview');
  return res.json();
}

async function fetchSensorLatest(zone?: string): Promise<SensorReading[]> {
  const params = zone ? `?zone=${encodeURIComponent(zone)}` : '';
  const res = await authFetch(`/api/sensors/latest${params}`);
  if (!res.ok) throw new Error('Failed to fetch sensor latest');
  return res.json();
}

async function fetchEvents(
  zone?: string,
  limit: number = 50,
): Promise<EventItem[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (zone) params.set('zone', zone);
  const res = await authFetch(`/api/sensors/events?${params}`);
  if (!res.ok) throw new Error('Failed to fetch events');
  return res.json();
}

// ── Hooks ────────────────────────────────────────────────────────────

export function useSensorTimeSeries(
  zone?: string,
  channel?: string,
  window: string = '1h',
) {
  return useQuery({
    queryKey: ['sensorTimeSeries', zone, channel, window],
    queryFn: () => fetchSensorTimeSeries(zone, channel, window),
    refetchInterval: 30_000,
  });
}

export function useLLMActivity(hours: number = 24) {
  return useQuery({
    queryKey: ['llmActivity', hours],
    queryFn: () => fetchLLMActivity(hours),
    refetchInterval: 60_000,
  });
}

export function useZoneOverview() {
  return useQuery({
    queryKey: ['zoneOverview'],
    queryFn: fetchZoneOverview,
    refetchInterval: 15_000,
  });
}

export function useSensorLatest(zone?: string) {
  return useQuery({
    queryKey: ['sensorLatest', zone],
    queryFn: () => fetchSensorLatest(zone),
    refetchInterval: 15_000,
  });
}

export function useEvents(zone?: string, limit: number = 50) {
  return useQuery({
    queryKey: ['events', zone, limit],
    queryFn: () => fetchEvents(zone, limit),
    refetchInterval: 15_000,
  });
}

// ── LLM Timeline ────────────────────────────────────────────────────

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

async function fetchLLMTimeline(hours: number = 24): Promise<LLMTimelineResponse> {
  const res = await authFetch(`/api/sensors/llm-timeline?hours=${hours}`);
  if (!res.ok) throw new Error('Failed to fetch LLM timeline');
  return res.json();
}

export function useLLMTimeline(hours: number = 24) {
  return useQuery({
    queryKey: ['llmTimeline', hours],
    queryFn: () => fetchLLMTimeline(hours),
    refetchInterval: 60_000,
  });
}
