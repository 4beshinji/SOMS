import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useMemo, useCallback, useRef } from 'react';
import {
  fetchSpatialConfig,
  fetchLiveSpatial,
  fetchHeatmap,
  fetchSensorLatest,
  fetchDevicePositions,
  createDevicePosition,
  updateDevicePosition,
  deleteDevicePosition,
} from '../../api';
import type { DevicePositionResponse } from '../../api';
import type { FloorPlanLayer, ZoneGeometry } from '../../types/spatial';
import ZoneLayer from './ZoneLayer';
import DeviceLayer from './DeviceLayer';
import HeatmapLayer from './HeatmapLayer';
import PersonLayer from './PersonLayer';
import CameraFov from './CameraFov';
import FloorPlanControls from './FloorPlanControls';
import DeviceDetailPanel from './DeviceDetailPanel';

/** Ray-casting point-in-polygon test */
function pointInPolygon(x: number, y: number, polygon: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

/** Find which zone contains a point */
function findZoneAtPoint(
  x: number,
  y: number,
  zones: Record<string, ZoneGeometry>,
): string | null {
  for (const [zoneId, zone] of Object.entries(zones)) {
    if (pointInPolygon(x, y, zone.polygon)) return zoneId;
  }
  return null;
}

export default function FloorPlanView() {
  const queryClient = useQueryClient();
  const svgRef = useRef<SVGSVGElement>(null);

  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [activeLayers, setActiveLayers] = useState<Set<FloorPlanLayer>>(
    new Set(['zones', 'devices', 'persons'])
  );
  const [heatmapPeriod, setHeatmapPeriod] = useState<string>('hour');
  const [editMode, setEditMode] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);

  // Edit mode placement form state
  const [placementDeviceId, setPlacementDeviceId] = useState('');
  const [placementType, setPlacementType] = useState<'sensor' | 'camera'>('sensor');
  const [placementChannels, setPlacementChannels] = useState('temperature,humidity');

  const configQuery = useQuery({
    queryKey: ['spatialConfig'],
    queryFn: fetchSpatialConfig,
    staleTime: 60000,
  });

  const liveQuery = useQuery({
    queryKey: ['liveSpatial'],
    queryFn: () => fetchLiveSpatial(),
    refetchInterval: 3000,
    enabled: activeLayers.has('persons') || activeLayers.has('objects'),
  });

  const heatmapQuery = useQuery({
    queryKey: ['heatmap', heatmapPeriod],
    queryFn: () => fetchHeatmap(undefined, heatmapPeriod),
    refetchInterval: 30000,
    enabled: activeLayers.has('heatmap'),
  });

  // Phase 1: Sensor latest data
  const sensorQuery = useQuery({
    queryKey: ['sensorLatest'],
    queryFn: fetchSensorLatest,
    refetchInterval: 10000,
    enabled: activeLayers.has('devices'),
  });

  // Phase 2: Device positions from DB
  const devicePosQuery = useQuery({
    queryKey: ['devicePositions'],
    queryFn: fetchDevicePositions,
    staleTime: 30000,
  });

  // Mutations
  const createMutation = useMutation({
    mutationFn: createDevicePosition,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devicePositions'] });
      queryClient.invalidateQueries({ queryKey: ['spatialConfig'] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ deviceId, data }: { deviceId: string; data: { x: number; y: number; zone?: string } }) =>
      updateDevicePosition(deviceId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devicePositions'] });
      queryClient.invalidateQueries({ queryKey: ['spatialConfig'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDevicePosition,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devicePositions'] });
      queryClient.invalidateQueries({ queryKey: ['spatialConfig'] });
      setSelectedDevice(null);
    },
  });

  const config = configQuery.data;
  const liveData = liveQuery.data ?? [];
  const heatmapData = heatmapQuery.data ?? [];

  // Convert sensor readings to device_id -> {channel: value} map
  const sensorData = useMemo(() => {
    const readings = sensorQuery.data;
    if (!readings) return undefined;
    const map: Record<string, Record<string, number>> = {};
    for (const r of readings) {
      const key = r.device_id ?? `${r.zone}_unknown`;
      if (!map[key]) map[key] = {};
      map[key][r.channel] = r.value;
    }
    return map;
  }, [sensorQuery.data]);

  // Merge config devices with DB positions (DB wins)
  const mergedDevices = useMemo(() => {
    if (!config) return {};
    const base = { ...config.devices };
    const dbPositions = devicePosQuery.data ?? [];
    for (const pos of dbPositions) {
      base[pos.device_id] = {
        zone: pos.zone,
        position: [pos.x, pos.y],
        type: pos.device_type,
        channels: pos.channels,
      };
    }
    return base;
  }, [config, devicePosQuery.data]);

  // Set of device_ids that exist in DB (for edit mode — these are draggable/deletable)
  const dbDeviceIds = useMemo(() => {
    const positions: DevicePositionResponse[] | undefined = devicePosQuery.data;
    if (!positions) return new Set<string>();
    return new Set<string>(positions.map((p: DevicePositionResponse) => p.device_id));
  }, [devicePosQuery.data]);

  // SVG click → place device
  const handleSvgClick = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (!editMode || !placementDeviceId.trim() || !config) return;

      const svg = svgRef.current;
      if (!svg) return;

      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const svgPt = pt.matrixTransform(svg.getScreenCTM()?.inverse());

      const x = svgPt.x;
      const y = svgPt.y;
      const zone = findZoneAtPoint(x, y, config.zones) ?? 'unknown';

      createMutation.mutate({
        device_id: placementDeviceId.trim(),
        zone,
        x: Math.round(x * 100) / 100,
        y: Math.round(y * 100) / 100,
        device_type: placementType,
        channels: placementChannels.split(',').map(c => c.trim()).filter(Boolean),
      });

      setPlacementDeviceId('');
    },
    [editMode, placementDeviceId, placementType, placementChannels, config, createMutation],
  );

  // Drag handler for moving devices
  const handleDeviceDragEnd = useCallback(
    (deviceId: string, x: number, y: number) => {
      if (!config) return;
      const zone = findZoneAtPoint(x, y, config.zones);
      updateMutation.mutate({
        deviceId,
        data: { x: Math.round(x * 100) / 100, y: Math.round(y * 100) / 100, zone: zone ?? undefined },
      });
    },
    [config, updateMutation],
  );

  const handleDeviceDelete = useCallback(
    (deviceId: string) => {
      if (confirm(`デバイス "${deviceId}" を削除しますか？`)) {
        deleteMutation.mutate(deviceId);
      }
    },
    [deleteMutation],
  );

  const handleDeviceSelect = useCallback(
    (deviceId: string | null) => {
      if (!editMode) {
        setSelectedDevice(prev => (prev === deviceId ? null : deviceId));
      }
    },
    [editMode],
  );

  if (configQuery.isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-[var(--primary-500)] border-t-transparent"></div>
          <p className="text-[var(--gray-600)] mt-4">フロアプランを読み込み中...</p>
        </div>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="text-center py-12">
        <p className="text-[var(--gray-500)] text-lg">空間設定が見つかりません</p>
        <p className="text-[var(--gray-400)] text-sm mt-2">config/spatial.yaml を作成してください</p>
      </div>
    );
  }

  const { building, zones, cameras } = config;
  const viewBox = `0 0 ${building.width_m} ${building.height_m}`;

  const toggleLayer = (layer: FloorPlanLayer) => {
    setActiveLayers(prev => {
      const next = new Set(prev);
      if (next.has(layer)) {
        next.delete(layer);
      } else {
        next.add(layer);
      }
      return next;
    });
  };

  return (
    <div className="flex flex-col lg:flex-row gap-4">
      {/* SVG Floor Plan */}
      <div className="flex-1 bg-white rounded-xl shadow-sm border border-[var(--gray-200)] p-4">
        <svg
          ref={svgRef}
          viewBox={viewBox}
          className={`w-full h-auto ${editMode ? 'cursor-crosshair' : ''}`}
          style={{ maxHeight: '70vh' }}
          onClick={handleSvgClick}
        >
          {/* Grid background */}
          <defs>
            <pattern id="grid" width="1" height="1" patternUnits="userSpaceOnUse">
              <path d="M 1 0 L 0 0 0 1" fill="none" stroke="#e5e7eb" strokeWidth="0.02" />
            </pattern>
          </defs>
          <rect width={building.width_m} height={building.height_m} fill="url(#grid)" />

          {/* Zone polygons */}
          {activeLayers.has('zones') && (
            <ZoneLayer
              zones={zones}
              selectedZone={selectedZone}
              onZoneClick={setSelectedZone}
            />
          )}

          {/* Heatmap overlay */}
          {activeLayers.has('heatmap') && (
            <HeatmapLayer
              zones={zones}
              heatmapData={heatmapData}
            />
          )}

          {/* Camera FOV sectors */}
          {activeLayers.has('cameras') && (
            <CameraFov cameras={cameras} />
          )}

          {/* Device positions */}
          {activeLayers.has('devices') && (
            <DeviceLayer
              devices={mergedDevices}
              cameras={cameras}
              sensorData={sensorData}
              editMode={editMode}
              dbDeviceIds={dbDeviceIds}
              selectedDevice={selectedDevice}
              onDeviceSelect={handleDeviceSelect}
              onDeviceDragEnd={handleDeviceDragEnd}
              onDeviceDelete={handleDeviceDelete}
              svgRef={svgRef}
            />
          )}

          {/* Person dots */}
          {activeLayers.has('persons') && (
            <PersonLayer
              zones={zones}
              liveData={liveData}
              showObjects={activeLayers.has('objects')}
            />
          )}

          {/* Building outline */}
          <rect
            width={building.width_m}
            height={building.height_m}
            fill="none"
            stroke="#374151"
            strokeWidth="0.1"
          />
        </svg>

        {/* Building name */}
        <div className="text-center mt-2 text-sm text-[var(--gray-500)]">
          {building.name} ({building.width_m}m x {building.height_m}m)
        </div>
      </div>

      {/* Controls sidebar */}
      <div className="w-full lg:w-64 space-y-4">
        <FloorPlanControls
          activeLayers={activeLayers}
          onToggleLayer={toggleLayer}
          heatmapPeriod={heatmapPeriod}
          onHeatmapPeriodChange={setHeatmapPeriod}
          selectedZone={selectedZone}
          zones={zones}
          liveData={liveData}
          onClearSelection={() => setSelectedZone(null)}
          editMode={editMode}
          onToggleEditMode={() => {
            setEditMode(prev => !prev);
            if (editMode) setSelectedDevice(null);
          }}
          placementDeviceId={placementDeviceId}
          onPlacementDeviceIdChange={setPlacementDeviceId}
          placementType={placementType}
          onPlacementTypeChange={setPlacementType}
          placementChannels={placementChannels}
          onPlacementChannelsChange={setPlacementChannels}
        />

        {/* Device detail panel */}
        {selectedDevice && !editMode && (
          <DeviceDetailPanel
            deviceId={selectedDevice}
            device={mergedDevices[selectedDevice]}
            sensorData={sensorData?.[selectedDevice]}
            onClose={() => setSelectedDevice(null)}
            onDelete={dbDeviceIds.has(selectedDevice) ? () => handleDeviceDelete(selectedDevice) : undefined}
          />
        )}
      </div>
    </div>
  );
}
