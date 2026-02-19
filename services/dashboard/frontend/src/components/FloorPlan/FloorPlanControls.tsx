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
}: FloorPlanControlsProps) {
  const selectedZoneData = selectedZone ? zones[selectedZone] : null;
  const selectedLive = selectedZone
    ? liveData.find(d => d.zone === selectedZone)
    : null;

  return (
    <div className="w-full lg:w-64 space-y-4">
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
    </div>
  );
}
