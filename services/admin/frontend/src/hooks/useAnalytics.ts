import { useQuery } from '@tanstack/react-query';
import type { HeatmapData, SpatialConfig, SensorReading } from '@soms/types';
import {
  fetchSensorTimeSeries,
  fetchZoneOverview,
  fetchSensorLatest,
  fetchSensorLatestByDevice,
  fetchEvents,
  fetchLLMActivity,
  fetchLLMTimeline,
} from '../api/sensors';
import { fetchHeatmap as fetchHeatmapData, fetchSpatialConfig } from '../api/spatial';

import type {
  TimeSeriesPoint,
  TimeSeriesResponse,
  ZoneSnapshot,
  EventItem,
  LLMActivity,
  LLMTimelinePoint,
  LLMTimelineResponse,
} from '../api/sensors';

// ── Re-export types for consumers ───────────────────────────────────

export type {
  SensorReading,
  TimeSeriesPoint,
  TimeSeriesResponse,
  ZoneSnapshot,
  EventItem,
  LLMActivity,
  LLMTimelinePoint,
  LLMTimelineResponse,
  HeatmapData,
  SpatialConfig,
};

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

export function useLLMTimeline(hours: number = 24) {
  return useQuery({
    queryKey: ['llmTimeline', hours],
    queryFn: () => fetchLLMTimeline(hours),
    refetchInterval: 60_000,
  });
}

export function useHeatmap(zone?: string, period: string = 'hour') {
  return useQuery({
    queryKey: ['heatmap', zone, period],
    queryFn: () => fetchHeatmapData(zone, period),
    refetchInterval: 60_000,
  });
}

export function useSpatialConfig() {
  return useQuery({
    queryKey: ['spatial-config'],
    queryFn: fetchSpatialConfig,
    staleTime: 5 * 60_000,
  });
}

export function useSensorLatestByDevice() {
  return useQuery({
    queryKey: ['sensorLatestByDevice'],
    queryFn: fetchSensorLatestByDevice,
    refetchInterval: 30_000,
  });
}

