import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { fetchSpatialConfig, fetchLiveSpatial, fetchHeatmap } from '../../api';
import type { FloorPlanLayer } from '../../types/spatial';
import ZoneLayer from './ZoneLayer';
import DeviceLayer from './DeviceLayer';
import HeatmapLayer from './HeatmapLayer';
import PersonLayer from './PersonLayer';
import FloorPlanControls from './FloorPlanControls';

export default function FloorPlanView() {
  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [activeLayers, setActiveLayers] = useState<Set<FloorPlanLayer>>(
    new Set(['zones', 'devices', 'persons'])
  );
  const [heatmapPeriod, setHeatmapPeriod] = useState<string>('hour');

  const configQuery = useQuery({
    queryKey: ['spatialConfig'],
    queryFn: fetchSpatialConfig,
    staleTime: 60000, // Config rarely changes
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

  const config = configQuery.data;
  const liveData = liveQuery.data ?? [];
  const heatmapData = heatmapQuery.data ?? [];

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

  const { building, zones, devices, cameras } = config;
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
          viewBox={viewBox}
          className="w-full h-auto"
          style={{ maxHeight: '70vh' }}
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

          {/* Device positions */}
          {activeLayers.has('devices') && (
            <DeviceLayer
              devices={devices}
              cameras={cameras}
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
      <FloorPlanControls
        activeLayers={activeLayers}
        onToggleLayer={toggleLayer}
        heatmapPeriod={heatmapPeriod}
        onHeatmapPeriodChange={setHeatmapPeriod}
        selectedZone={selectedZone}
        zones={zones}
        liveData={liveData}
        onClearSelection={() => setSelectedZone(null)}
      />
    </div>
  );
}
