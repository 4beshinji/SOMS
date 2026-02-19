import type { FloorPlanLayer, ZoneGeometry, LiveSpatialData } from '../../types/spatial';

interface FloorPlanControlsProps {
  activeLayers: Set<FloorPlanLayer>;
  onToggleLayer: (layer: FloorPlanLayer) => void;
  heatmapPeriod: string;
  onHeatmapPeriodChange: (period: string) => void;
  selectedZone: string | null;
  zones: Record<string, ZoneGeometry>;
  liveData: LiveSpatialData[];
  onClearSelection: () => void;
  editMode: boolean;
  onToggleEditMode: () => void;
  placementDeviceId: string;
  onPlacementDeviceIdChange: (v: string) => void;
  placementType: 'sensor' | 'camera';
  onPlacementTypeChange: (v: 'sensor' | 'camera') => void;
  placementChannels: string;
  onPlacementChannelsChange: (v: string) => void;
}

const LAYER_LABELS: Record<FloorPlanLayer, string> = {
  zones: 'zones',
  devices: 'sensors',
  heatmap: 'heatmap',
  persons: 'persons',
  objects: 'objects',
};

const PERIOD_LABELS: Record<string, string> = {
  hour: '1h',
  day: '24h',
  week: '7d',
};

export default function FloorPlanControls({
  activeLayers,
  onToggleLayer,
  heatmapPeriod,
  onHeatmapPeriodChange,
  selectedZone,
  zones,
  liveData,
  onClearSelection,
  editMode,
  onToggleEditMode,
  placementDeviceId,
  onPlacementDeviceIdChange,
  placementType,
  onPlacementTypeChange,
  placementChannels,
  onPlacementChannelsChange,
}: FloorPlanControlsProps) {
  const selectedZoneData = selectedZone ? zones[selectedZone] : null;
  const selectedLive = selectedZone
    ? liveData.find(d => d.zone === selectedZone)
    : null;

  return (
    <>
      {/* Layer toggles */}
      <div className="bg-white rounded-xl shadow-sm border border-[var(--gray-200)] p-4">
        <h3 className="text-sm font-semibold text-[var(--gray-700)] mb-3">
          layers
        </h3>
        <div className="space-y-2">
          {(Object.keys(LAYER_LABELS) as FloorPlanLayer[]).map(layer => (
            <label
              key={layer}
              className="flex items-center gap-2 cursor-pointer"
            >
              <input
                type="checkbox"
                checked={activeLayers.has(layer)}
                onChange={() => onToggleLayer(layer)}
                className="rounded border-[var(--gray-300)] text-[var(--primary-500)]"
              />
              <span className="text-sm text-[var(--gray-700)]">
                {LAYER_LABELS[layer]}
              </span>
            </label>
          ))}
        </div>
      </div>

      {/* Edit mode toggle */}
      <div className="bg-white rounded-xl shadow-sm border border-[var(--gray-200)] p-4">
        <button
          onClick={onToggleEditMode}
          className={`w-full px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
            editMode
              ? 'bg-amber-500 text-white hover:bg-amber-600'
              : 'bg-[var(--gray-100)] text-[var(--gray-700)] hover:bg-[var(--gray-200)]'
          }`}
        >
          {editMode ? '配置モード ON' : '配置モード'}
        </button>

        {editMode && (
          <div className="mt-3 space-y-2">
            <input
              type="text"
              value={placementDeviceId}
              onChange={e => onPlacementDeviceIdChange(e.target.value)}
              placeholder="デバイスID (例: env_01)"
              className="w-full px-2 py-1.5 text-xs border border-[var(--gray-300)] rounded-md focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
            <div className="flex gap-1">
              <button
                onClick={() => onPlacementTypeChange('sensor')}
                className={`flex-1 px-2 py-1 text-xs rounded-md ${
                  placementType === 'sensor'
                    ? 'bg-emerald-500 text-white'
                    : 'bg-[var(--gray-100)] text-[var(--gray-600)]'
                }`}
              >
                sensor
              </button>
              <button
                onClick={() => onPlacementTypeChange('camera')}
                className={`flex-1 px-2 py-1 text-xs rounded-md ${
                  placementType === 'camera'
                    ? 'bg-purple-500 text-white'
                    : 'bg-[var(--gray-100)] text-[var(--gray-600)]'
                }`}
              >
                camera
              </button>
            </div>
            <input
              type="text"
              value={placementChannels}
              onChange={e => onPlacementChannelsChange(e.target.value)}
              placeholder="チャンネル (カンマ区切り)"
              className="w-full px-2 py-1.5 text-xs border border-[var(--gray-300)] rounded-md focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
            <p className="text-[10px] text-[var(--gray-400)]">
              フロアプランをクリックして配置 / 右クリックで削除
            </p>
          </div>
        )}
      </div>

      {/* Heatmap period selector */}
      {activeLayers.has('heatmap') && (
        <div className="bg-white rounded-xl shadow-sm border border-[var(--gray-200)] p-4">
          <h3 className="text-sm font-semibold text-[var(--gray-700)] mb-3">
            heatmap period
          </h3>
          <div className="flex gap-1">
            {Object.entries(PERIOD_LABELS).map(([value, label]) => (
              <button
                key={value}
                onClick={() => onHeatmapPeriodChange(value)}
                className={`flex-1 px-2 py-1.5 text-xs rounded-md transition-colors ${
                  heatmapPeriod === value
                    ? 'bg-[var(--primary-500)] text-white'
                    : 'bg-[var(--gray-100)] text-[var(--gray-600)] hover:bg-[var(--gray-200)]'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Zone detail panel */}
      {selectedZoneData && (
        <div className="bg-white rounded-xl shadow-sm border border-[var(--gray-200)] p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-[var(--gray-700)]">
              {selectedZoneData.display_name}
            </h3>
            <button
              onClick={onClearSelection}
              className="text-xs text-[var(--gray-400)] hover:text-[var(--gray-600)]"
            >
              close
            </button>
          </div>
          <div className="space-y-1 text-xs text-[var(--gray-600)]">
            <p>area: {selectedZoneData.area_m2}m2</p>
            <p>floor: {selectedZoneData.floor}F</p>
            {selectedZoneData.adjacent_zones.length > 0 && (
              <p>adjacent: {selectedZoneData.adjacent_zones.join(', ')}</p>
            )}
            {selectedLive && (
              <>
                <p className="mt-2 font-medium text-[var(--gray-700)]">
                  live detection
                </p>
                <p>persons: {selectedLive.persons.length}</p>
                <p>objects: {selectedLive.objects.length}</p>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
