import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
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
import { fetchDeviceStatus } from '../api/devices';
import { fetchHeatmap as fetchHeatmapData, fetchSpatialConfig } from '../api/spatial';
import {
  classifyDevice,
  type SensorCategory,
} from '../utils/channelConfig';

import type {
  TimeSeriesPoint,
  TimeSeriesResponse,
  ZoneSnapshot,
  EventItem,
  LLMActivity,
  LLMTimelinePoint,
  LLMTimelineResponse,
} from '../api/sensors';
import type { DeviceStatus } from '../api/devices';

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
  DeviceStatus,
  HeatmapData,
  SpatialConfig,
};

// ── Enriched device type ────────────────────────────────────────────

export interface EnrichedDevice extends DeviceStatus {
  spatialType: string | null;
  channels: string[];
  zone: string | null;
  label: string | null;
  category: SensorCategory;
  latestReadings: SensorReading[];
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

export function useLLMTimeline(hours: number = 24) {
  return useQuery({
    queryKey: ['llmTimeline', hours],
    queryFn: () => fetchLLMTimeline(hours),
    refetchInterval: 60_000,
  });
}

export function useDeviceStatus() {
  return useQuery({
    queryKey: ['deviceStatus'],
    queryFn: fetchDeviceStatus,
    refetchInterval: 30_000,
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

/**
 * Merges wallet device status, spatial config, and latest sensor readings
 * into a single enriched device list classified by sensor category.
 */
export function useEnrichedDeviceStatus() {
  const devicesQuery = useDeviceStatus();
  const spatialQuery = useSpatialConfig();
  const sensorQuery = useSensorLatestByDevice();

  const enriched = useMemo(() => {
    if (!devicesQuery.data) return undefined;
    const spatialDevices = spatialQuery.data?.devices ?? {};
    const readings = sensorQuery.data ?? [];

    // Index sensor readings by device_id
    const readingsByDevice = new Map<string, SensorReading[]>();
    for (const r of readings) {
      if (!r.device_id) continue;
      const list = readingsByDevice.get(r.device_id) ?? [];
      list.push(r);
      readingsByDevice.set(r.device_id, list);
    }

    return devicesQuery.data.map((device): EnrichedDevice => {
      const spatial = spatialDevices[device.device_id];
      const spatialType = spatial?.type ?? null;
      const channels = spatial?.channels ?? [];
      const zone = spatial?.zone ?? null;
      const label = spatial?.label ?? null;
      const category = spatialType
        ? classifyDevice(spatialType, channels)
        : 'unknown';
      const latestReadings = readingsByDevice.get(device.device_id) ?? [];

      return {
        ...device,
        spatialType,
        channels,
        zone,
        label,
        category,
        latestReadings,
      };
    });
  }, [devicesQuery.data, spatialQuery.data, sensorQuery.data]);

  return {
    data: enriched,
    isLoading: devicesQuery.isLoading,
    isError: devicesQuery.isError,
  };
}
