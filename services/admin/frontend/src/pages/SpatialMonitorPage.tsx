import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  fetchSpatialConfig,
  fetchFloorplan,
  fetchLiveSpatial,
  fetchHeatmap,
  fetchSpatialEvents,
  type SpatialConfig,
  type LiveSpatialData,
  type HeatmapData,
} from '../api/spatial';

// ── Constants ──────────────────────────────────────────────────────

const PAD = 1.5;
const ZONE_COLORS = [
  '#3b82f6','#10b981','#f59e0b','#8b5cf6','#ec4899',
  '#06b6d4','#84cc16','#f97316','#6366f1','#14b8a6',
];

const SEVERITY_STYLES: Record<string, string> = {
  info: 'bg-blue-50 text-blue-700',
  warning: 'bg-yellow-50 text-yellow-700',
  critical: 'bg-red-50 text-red-700',
};

type Layer = 'zones' | 'heatmap' | 'persons' | 'devices' | 'cameras';

// ── Helpers ────────────────────────────────────────────────────────

function toSvg(pts: number[][], fy: number): string {
  return pts.map(([x, y]) => `${x},${fy - y}`).join(' ');
}

function conePath(cx: number, cy: number, orientDeg: number, fovDeg: number, range: number, fy: number): string {
  const toRad = Math.PI / 180;
  const startAngle = -(orientDeg - fovDeg / 2) * toRad;
  const endAngle = -(orientDeg + fovDeg / 2) * toRad;
  const sx = cx + range * Math.cos(startAngle);
  const sy = (fy - cy) + range * Math.sin(startAngle);
  const ex = cx + range * Math.cos(endAngle);
  const ey = (fy - cy) + range * Math.sin(endAngle);
  const largeArc = fovDeg > 180 ? 1 : 0;
  return `M ${cx} ${fy - cy} L ${sx} ${sy} A ${range} ${range} 0 ${largeArc} 0 ${ex} ${ey} Z`;
}

function heatColor(intensity: number): string {
  // 0 → transparent, 1 → red
  const clamped = Math.min(1, Math.max(0, intensity));
  if (clamped === 0) return 'transparent';
  const r = Math.round(255);
  const g = Math.round(255 * (1 - clamped * 0.8));
  const b = Math.round(60 * (1 - clamped));
  return `rgba(${r},${g},${b},${0.15 + clamped * 0.5})`;
}

function relativeTime(ts: string): string {
  const diff = (Date.now() - new Date(ts).getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  return `${Math.round(diff / 3600)}h ago`;
}

// ── Heatmap Overlay ────────────────────────────────────────────────

function HeatmapOverlay({ config, data, fy }: { config: SpatialConfig; data: HeatmapData[]; fy: number }) {
  const cells: { x: number; y: number; w: number; h: number; color: string }[] = [];
  for (const entry of data) {
    const zoneGeo = config.zones[entry.zone];
    if (!zoneGeo || !entry.cell_counts.length) continue;
    // Bounding box of zone polygon
    const xs = zoneGeo.polygon.map(p => p[0]);
    const ys = zoneGeo.polygon.map(p => p[1]);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const cellW = (maxX - minX) / entry.grid_cols;
    const cellH = (maxY - minY) / entry.grid_rows;
    // Find max for normalization
    let maxCount = 0;
    for (const row of entry.cell_counts) for (const c of row) maxCount = Math.max(maxCount, c);
    if (maxCount === 0) continue;
    for (let r = 0; r < entry.cell_counts.length; r++) {
      for (let c = 0; c < entry.cell_counts[r].length; c++) {
        const intensity = entry.cell_counts[r][c] / maxCount;
        if (intensity === 0) continue;
        cells.push({
          x: minX + c * cellW,
          y: fy - (maxY - r * cellH),
          w: cellW,
          h: cellH,
          color: heatColor(intensity),
        });
      }
    }
  }
  return (
    <g>
      {cells.map((c, i) => (
        <rect key={i} x={c.x} y={c.y} width={c.w} height={c.h} fill={c.color} rx={0.1} />
      ))}
    </g>
  );
}

// ── Person Dots ────────────────────────────────────────────────────

function PersonLayer({ data, fy }: { data: LiveSpatialData[]; fy: number }) {
  const persons: { x: number; y: number; trackId: number; confidence: number; zone: string }[] = [];
  for (const snap of data) {
    for (const p of snap.persons) {
      if (p.floor_position_m) {
        persons.push({ x: p.floor_position_m[0], y: p.floor_position_m[1], trackId: p.track_id ?? 0, confidence: p.confidence, zone: snap.zone });
      }
    }
  }
  return (
    <g>
      {persons.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={fy - p.y} r={0.35} fill="rgba(239,68,68,0.25)" stroke="none" />
          <circle cx={p.x} cy={fy - p.y} r={0.15} fill="#ef4444" stroke="#fff" strokeWidth={0.04}>
            <animate attributeName="r" values="0.15;0.2;0.15" dur="2s" repeatCount="indefinite" />
          </circle>
          <text x={p.x} y={fy - p.y - 0.4} textAnchor="middle" fontSize={0.3} fill="#dc2626" fontWeight="bold">
            #{p.trackId}
          </text>
        </g>
      ))}
    </g>
  );
}

// ── Person Count Badge ─────────────────────────────────────────────

function personCount(data: LiveSpatialData[]): number {
  const ids = new Set<number>();
  for (const snap of data) {
    for (const p of snap.persons) {
      ids.add(p.track_id ?? 0);
    }
  }
  return ids.size;
}

// ── Main Component ─────────────────────────────────────────────────

export default function SpatialMonitorPage() {
  const [layers, setLayers] = useState<Record<Layer, boolean>>({
    zones: true, heatmap: false, persons: true, devices: true, cameras: true,
  });
  const [heatPeriod, setHeatPeriod] = useState('hour');

  const configQuery = useQuery({ queryKey: ['spatial-config'], queryFn: fetchSpatialConfig });
  const floorplanQuery = useQuery({ queryKey: ['floorplan'], queryFn: fetchFloorplan, retry: 1 });
  const liveQuery = useQuery({ queryKey: ['spatial-live'], queryFn: () => fetchLiveSpatial(), refetchInterval: 3000, retry: 1 });
  const heatQuery = useQuery({ queryKey: ['spatial-heatmap', heatPeriod], queryFn: () => fetchHeatmap(undefined, heatPeriod), refetchInterval: 60000, enabled: layers.heatmap, retry: 1 });
  const eventsQuery = useQuery({ queryKey: ['spatial-events'], queryFn: () => fetchSpatialEvents(undefined, 30), refetchInterval: 10000, retry: 1 });

  const config = configQuery.data;
  const fy = config?.building.height_m ?? 20;
  const vb = config ? `${-PAD} ${-PAD} ${config.building.width_m + PAD * 2} ${config.building.height_m + PAD * 2}` : '0 0 30 20';

  const zoneList = useMemo(() => {
    if (!config) return [];
    return Object.entries(config.zones).map(([id, z], i) => ({ id, ...z, color: ZONE_COLORS[i % ZONE_COLORS.length] }));
  }, [config]);

  const zn = (zoneId: string) => {
    const z = config?.zones[zoneId];
    return z?.display_name && z.display_name !== zoneId ? z.display_name : zoneId;
  };

  const toggle = (layer: Layer) => setLayers(p => ({ ...p, [layer]: !p[layer] }));

  if (configQuery.isLoading) {
    return <div className="flex items-center justify-center h-96 text-[var(--gray-500)]">Loading spatial config...</div>;
  }
  if (configQuery.isError || !config) {
    return <div className="flex items-center justify-center h-96 text-[var(--error-600)]">Failed to load spatial config</div>;
  }

  const totalPersons = personCount(liveQuery.data ?? []);

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--gray-200)] bg-white flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-bold text-[var(--gray-900)]">Spatial Monitor</h1>
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[var(--primary-50)]">
            <span className="w-2 h-2 rounded-full bg-[var(--primary-500)] animate-pulse" />
            <span className="text-xs font-medium text-[var(--primary-700)]">{totalPersons} person{totalPersons !== 1 ? 's' : ''}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {(['zones', 'persons', 'heatmap', 'devices', 'cameras'] as Layer[]).map(l => (
            <button
              key={l}
              onClick={() => toggle(l)}
              className={`px-2.5 py-1 text-xs font-medium rounded-md border transition-colors ${
                layers[l]
                  ? 'bg-[var(--primary-50)] text-[var(--primary-700)] border-[var(--primary-200)]'
                  : 'bg-white text-[var(--gray-500)] border-[var(--gray-200)] hover:bg-[var(--gray-50)]'
              }`}
            >
              {l.charAt(0).toUpperCase() + l.slice(1)}
            </button>
          ))}
          {layers.heatmap && (
            <select
              value={heatPeriod}
              onChange={e => setHeatPeriod(e.target.value)}
              className="h-7 px-2 text-xs border border-[var(--gray-200)] rounded-md"
            >
              <option value="hour">1h</option>
              <option value="day">24h</option>
              <option value="week">7d</option>
            </select>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Map */}
        <div className="flex-1 bg-[var(--gray-900)] relative">
          <svg viewBox={vb} className="w-full h-full" style={{ background: '#111827' }}>
            {/* Grid */}
            <defs>
              <pattern id="grid" width="1" height="1" patternUnits="userSpaceOnUse">
                <path d="M 1 0 L 0 0 0 1" fill="none" stroke="#1f2937" strokeWidth="0.02" />
              </pattern>
            </defs>
            <rect x={-PAD} y={-PAD} width={config.building.width_m + PAD * 2} height={config.building.height_m + PAD * 2} fill="url(#grid)" />

            {/* Building outline */}
            <rect x={0} y={0} width={config.building.width_m} height={config.building.height_m} fill="none" stroke="#374151" strokeWidth={0.06} />

            {/* Walls & Columns */}
            {floorplanQuery.data?.walls.map((w, i) => w.closed
              ? <polygon key={`w${i}`} points={toSvg(w.points, fy)} fill="#475569" stroke="#64748b" strokeWidth={0.03} />
              : <polyline key={`w${i}`} points={toSvg(w.points, fy)} fill="none" stroke="#64748b" strokeWidth={0.06} />
            )}
            {floorplanQuery.data?.columns.map((c, i) =>
              <polygon key={`c${i}`} points={toSvg(c.points, fy)} fill="#991b1b" stroke="#b91c1c" strokeWidth={0.03} />
            )}

            {/* Zones */}
            {layers.zones && zoneList.map(z => (
              <g key={z.id}>
                <polygon
                  points={toSvg(z.polygon, fy)}
                  fill={z.color}
                  fillOpacity={0.08}
                  stroke={z.color}
                  strokeWidth={0.06}
                  strokeOpacity={0.5}
                />
                {z.polygon.length > 0 && (() => {
                  const cx = z.polygon.reduce((s, p) => s + p[0], 0) / z.polygon.length;
                  const cy = z.polygon.reduce((s, p) => s + p[1], 0) / z.polygon.length;
                  return (
                    <text x={cx} y={fy - cy} textAnchor="middle" dominantBaseline="central" fontSize={0.45} fill={z.color} fillOpacity={0.7} fontWeight="600">
                      {z.display_name}
                    </text>
                  );
                })()}
              </g>
            ))}

            {/* Heatmap */}
            {layers.heatmap && heatQuery.data && (
              <HeatmapOverlay config={config} data={heatQuery.data} fy={fy} />
            )}

            {/* Devices */}
            {layers.devices && Object.entries(config.devices).map(([id, d]) => (
              <g key={id}>
                {d.fov_deg && d.detection_range_m && d.orientation_deg != null && (
                  <path
                    d={conePath(d.position[0], d.position[1], d.orientation_deg, d.fov_deg, d.detection_range_m, fy)}
                    fill="#f59e0b"
                    fillOpacity={0.08}
                    stroke="#f59e0b"
                    strokeWidth={0.03}
                    strokeOpacity={0.3}
                  />
                )}
                <circle cx={d.position[0]} cy={fy - d.position[1]} r={0.2} fill="#10b981" stroke="#064e3b" strokeWidth={0.04} />
                <text x={d.position[0]} y={fy - d.position[1] + 0.55} textAnchor="middle" fontSize={0.25} fill="#6ee7b7">{id}</text>
              </g>
            ))}

            {/* Cameras */}
            {layers.cameras && Object.entries(config.cameras).map(([id, c]) => (
              <g key={id}>
                {c.fov_deg && c.orientation_deg != null && (
                  <path
                    d={conePath(c.position[0], c.position[1], c.orientation_deg, c.fov_deg, 4, fy)}
                    fill="#ef4444"
                    fillOpacity={0.06}
                    stroke="#ef4444"
                    strokeWidth={0.03}
                    strokeOpacity={0.25}
                  />
                )}
                <rect x={c.position[0] - 0.2} y={fy - c.position[1] - 0.15} width={0.4} height={0.3} rx={0.05} fill="#ef4444" stroke="#7f1d1d" strokeWidth={0.04} />
                <text x={c.position[0]} y={fy - c.position[1] + 0.55} textAnchor="middle" fontSize={0.22} fill="#fca5a5">{id.replace('cam_', '').slice(-8)}</text>
              </g>
            ))}

            {/* Live persons */}
            {layers.persons && liveQuery.data && (
              <PersonLayer data={liveQuery.data} fy={fy} />
            )}
          </svg>

          {/* Legend overlay */}
          <div className="absolute bottom-3 left-3 bg-black/60 backdrop-blur rounded-lg px-3 py-2 text-xs text-white/70 space-y-1">
            <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-red-500" /> Person</div>
            <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-emerald-500" /> Device</div>
            <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 bg-red-500 rounded-sm" style={{ width: 10, height: 8 }} /> Camera</div>
          </div>
        </div>

        {/* Event Sidebar */}
        <div className="w-80 bg-white border-l border-[var(--gray-200)] flex flex-col flex-shrink-0 overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--gray-200)] flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--gray-900)]">Events</h2>
            <span className="text-[10px] text-[var(--gray-400)]">{(eventsQuery.data ?? []).length} total</span>
          </div>
          <div className="min-h-0 max-h-[40vh] overflow-y-auto divide-y divide-[var(--gray-100)]">
            {eventsQuery.isLoading ? (
              <div className="p-4 text-sm text-[var(--gray-500)]">Loading...</div>
            ) : eventsQuery.isError ? (
              <div className="p-4 text-sm text-[var(--error-600)]">Failed to load events</div>
            ) : (eventsQuery.data ?? []).length === 0 ? (
              <div className="p-4 text-sm text-[var(--gray-500)]">No recent events</div>
            ) : (
              (eventsQuery.data ?? []).map((ev, i) => (
                <div key={i} className="px-4 py-2.5 hover:bg-[var(--gray-50)]">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${SEVERITY_STYLES[ev.severity] ?? SEVERITY_STYLES.info}`}>
                      {ev.severity}
                    </span>
                    <span className="text-xs font-medium text-[var(--gray-900)]">{zn(ev.zone)}</span>
                    <span className="text-[10px] text-[var(--gray-400)] ml-auto">{relativeTime(ev.timestamp)}</span>
                  </div>
                  <p className="text-xs text-[var(--gray-600)] truncate">
                    {ev.event_type.replace('world_model_', '').replace(/_/g, ' ')}
                    {ev.source_device ? ` (${ev.source_device})` : ''}
                  </p>
                  {ev.data && Object.keys(ev.data).length > 0 && (
                    <p className="text-[10px] text-[var(--gray-400)] mt-0.5 truncate">
                      {Object.entries(ev.data).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(', ')}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Zone person counts */}
          <div className="border-t border-[var(--gray-200)] px-4 py-3">
            <h3 className="text-xs font-semibold text-[var(--gray-700)] mb-2">Zone Occupancy</h3>
            <div className="space-y-1">
              {zoneList.map(z => {
                const count = (liveQuery.data ?? [])
                  .filter(s => s.zone === z.id)
                  .reduce((sum, s) => sum + s.persons.length, 0);
                return (
                  <div key={z.id} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-sm" style={{ background: z.color }} />
                      <span className="text-[var(--gray-700)]">{z.display_name}</span>
                    </div>
                    <span className={`font-medium ${count > 0 ? 'text-[var(--gray-900)]' : 'text-[var(--gray-400)]'}`}>{count}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
