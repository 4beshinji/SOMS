import { useState, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchSpatialConfig, fetchFloorplan } from '../api/spatial';
import type { CameraConfig } from '@soms/types';

// ── Types ─────────────────────────────────────────────────────────

interface CameraMeta {
  camera_id: string;
  zone: string;
  position: [number, number] | null;
  fov_deg: number | null;
  orientation_deg: number | null;
  resolution: [number, number] | null;
}

// ── Helpers ───────────────────────────────────────────────────────

/** Derive IP from camera_id like cam_192_168_128_172 */
function hasIpStream(id: string): boolean {
  const parts = id.replace('cam_', '').split('_');
  return parts.length === 4 && parts.every(p => /^\d+$/.test(p));
}

function snapshotUrl(cameraId: string, bust: number, overlay: boolean = false): string {
  return `/api/cameras/${encodeURIComponent(cameraId)}/snapshot?_t=${bust}${overlay ? '&overlay=1' : ''}`;
}

function camerasFromConfig(cameras: Record<string, CameraConfig>): CameraMeta[] {
  return Object.entries(cameras).map(([id, c]) => ({
    camera_id: id,
    zone: c.zone,
    position: c.position?.length === 2 ? [c.position[0], c.position[1]] as [number, number] : null,
    fov_deg: c.fov_deg ?? null,
    orientation_deg: c.orientation_deg ?? null,
    resolution: c.resolution?.length === 2 ? [c.resolution[0], c.resolution[1]] as [number, number] : null,
  }));
}

// ── SVG Helpers ───────────────────────────────────────────────────

const PAD = 1.5;
const ZONE_COLORS = [
  '#3b82f6','#10b981','#f59e0b','#8b5cf6','#ec4899',
  '#06b6d4','#84cc16','#f97316','#6366f1','#14b8a6',
];

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

// ── Snapshot Card ─────────────────────────────────────────────────

function SnapshotCard({
  cam,
  selected,
  onSelect,
  bust,
  streamAvailable,
  overlay,
}: {
  cam: CameraMeta;
  selected: boolean;
  onSelect: () => void;
  bust: number;
  streamAvailable: boolean;
  overlay: boolean;
}) {
  const [imgError, setImgError] = useState(false);
  // Reset error state when bust changes (new refresh cycle)
  const [lastBust, setLastBust] = useState(bust);
  if (bust !== lastBust) {
    setLastBust(bust);
    if (imgError) setImgError(false);
  }

  const label = cam.camera_id.replace('cam_', '').replace(/_/g, '.');
  const canShowStream = hasIpStream(cam.camera_id) && streamAvailable;

  return (
    <div
      onClick={onSelect}
      className={`rounded-xl overflow-hidden cursor-pointer transition-all ${
        selected
          ? 'ring-2 ring-[var(--primary-500)] shadow-lg scale-[1.02]'
          : 'ring-1 ring-[var(--gray-200)] hover:ring-[var(--gray-300)] hover:shadow'
      }`}
    >
      {/* Snapshot */}
      <div className="relative bg-[var(--gray-900)] aspect-video">
        {canShowStream && !imgError ? (
          <img
            src={snapshotUrl(cam.camera_id, bust, overlay)}
            alt={cam.camera_id}
            className="w-full h-full object-cover"
            onError={() => setImgError(true)}
            loading="lazy"
          />
        ) : (
          <div className="flex flex-col items-center justify-center w-full h-full text-[var(--gray-500)] text-xs gap-1">
            <svg className="w-8 h-8 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
            </svg>
            {!hasIpStream(cam.camera_id) ? 'MCP device (no HTTP stream)' : imgError ? 'Stream unavailable' : 'Perception service offline'}
          </div>
        )}
        {/* Zone badge */}
        <span className="absolute top-1.5 left-1.5 px-1.5 py-0.5 bg-black/60 text-white text-[10px] font-medium rounded">
          {cam.zone || 'unknown'}
        </span>
      </div>

      {/* Info */}
      <div className="px-3 py-2 bg-white">
        <div className="flex items-center gap-1.5">
          <p className="text-xs font-semibold text-[var(--gray-900)] truncate flex-1">{label}</p>
          {!cam.position && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-yellow-100 text-yellow-700 font-medium flex-shrink-0">Unplaced</span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-0.5 text-[10px] text-[var(--gray-500)]">
          {cam.resolution && <span>{cam.resolution[0]}x{cam.resolution[1]}</span>}
          {cam.fov_deg != null && <span>FOV {cam.fov_deg}°</span>}
          {cam.position ? <span>({cam.position[0].toFixed(1)}, {cam.position[1].toFixed(1)})</span> : <span>{cam.zone}</span>}
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────

export default function CameraSetupPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [bust, setBust] = useState(Date.now());
  const [showOverlay, setShowOverlay] = useState(false);
  const [snapshotServerUp, setSnapshotServerUp] = useState(true);

  const configQuery = useQuery({
    queryKey: ['spatial-config'],
    queryFn: fetchSpatialConfig,
  });
  const floorplanQuery = useQuery({ queryKey: ['floorplan'], queryFn: fetchFloorplan, retry: 1 });

  // Fetch camera list from perception snapshot server (fallback when spatial config has none)
  const perceptionQuery = useQuery<CameraMeta[]>({
    queryKey: ['perception-cameras'],
    queryFn: async () => {
      const res = await fetch('/api/cameras/', { signal: AbortSignal.timeout(3000) });
      if (!res.ok) throw new Error('perception offline');
      setSnapshotServerUp(true);
      const list = await res.json() as Array<{
        camera_id: string; zone: string;
        position: [number, number] | null;
        fov_deg: number | null; orientation_deg: number | null;
        resolution: [number, number] | null; has_stream: boolean;
      }>;
      return list.map(c => ({
        camera_id: c.camera_id,
        zone: c.zone,
        position: c.position,
        fov_deg: c.fov_deg,
        orientation_deg: c.orientation_deg,
        resolution: c.resolution,
      }));
    },
    retry: 1,
    refetchInterval: 30000,
  });
  // Track server availability from query state
  if (perceptionQuery.isError && snapshotServerUp) setSnapshotServerUp(false);

  // Tick bust for snapshot refresh
  useQuery({
    queryKey: ['snapshot-tick'],
    queryFn: () => { setBust(Date.now()); return null; },
    refetchInterval: 5000,
    enabled: snapshotServerUp,
  });

  const config = configQuery.data;
  const fy = config?.building.height_m ?? 20;
  const vb = config
    ? `${-PAD} ${-PAD} ${config.building.width_m + PAD * 2} ${config.building.height_m + PAD * 2}`
    : '0 0 30 20';

  // Merge camera lists: spatial config (has positions) + perception (has stream info)
  const cameras = useMemo(() => {
    const map = new Map<string, CameraMeta>();
    // 1) spatial config cameras (authoritative for position/FOV)
    if (config?.cameras) {
      for (const cam of camerasFromConfig(config.cameras)) {
        map.set(cam.camera_id, cam);
      }
    }
    // 2) perception cameras (fills in cameras not in spatial config)
    if (perceptionQuery.data) {
      for (const cam of perceptionQuery.data) {
        if (!map.has(cam.camera_id)) {
          map.set(cam.camera_id, cam);
        }
      }
    }
    return Array.from(map.values());
  }, [config, perceptionQuery.data]);

  const zoneList = useMemo(() => {
    if (!config) return [];
    return Object.entries(config.zones).map(([id, z], i) => ({
      id, ...z, color: ZONE_COLORS[i % ZONE_COLORS.length],
    }));
  }, [config]);

  const selectedCam = useMemo(
    () => cameras.find(c => c.camera_id === selectedId) ?? null,
    [cameras, selectedId],
  );

  const handleCameraClick = useCallback((id: string) => {
    setSelectedId(prev => (prev === id ? null : id));
  }, []);

  if (configQuery.isLoading) {
    return <div className="flex items-center justify-center h-96 text-[var(--gray-500)]">Loading...</div>;
  }
  if (configQuery.isError || !config) {
    return <div className="flex items-center justify-center h-96 text-[var(--error-600)]">Failed to load spatial config</div>;
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--gray-200)] bg-white flex items-center gap-4 flex-shrink-0">
        <h1 className="text-lg font-bold text-[var(--gray-900)]">Camera Setup</h1>
        <span className="text-xs text-[var(--gray-500)]">{cameras.length} cameras</span>
        <button
          onClick={() => setShowOverlay(o => !o)}
          className={`px-2.5 py-1 text-xs font-medium rounded-md border transition-colors ${
            showOverlay
              ? 'bg-green-50 text-green-700 border-green-200'
              : 'bg-white text-[var(--gray-500)] border-[var(--gray-200)] hover:bg-[var(--gray-50)]'
          }`}
        >
          YOLO Overlay
        </button>
        {!snapshotServerUp && (
          <span className="text-[10px] px-2 py-0.5 rounded bg-yellow-50 text-yellow-700 border border-yellow-200">
            Snapshot server offline — showing config only
          </span>
        )}
      </div>

      {/* Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left pane: Map + Preview */}
        <div className="flex-1 bg-[var(--gray-900)] relative min-w-0 flex flex-col">
          {/* Selected camera preview */}
          {selectedCam && snapshotServerUp && hasIpStream(selectedCam.camera_id) && (
            <div className="relative flex-shrink-0 bg-black border-b border-[var(--gray-700)]" style={{ height: '45%' }}>
              <img
                key={selectedCam.camera_id + bust}
                src={snapshotUrl(selectedCam.camera_id, bust, showOverlay)}
                alt={selectedCam.camera_id}
                className="w-full h-full object-contain"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
              {/* Camera info overlay */}
              <div className="absolute top-3 left-3 flex items-center gap-2">
                <span className="px-2 py-1 bg-black/70 text-white text-sm font-semibold rounded-lg backdrop-blur">
                  {selectedCam.camera_id.replace('cam_', '').replace(/_/g, '.')}
                </span>
                <span className="px-2 py-1 bg-blue-600/80 text-white text-xs font-medium rounded-lg backdrop-blur">
                  {selectedCam.zone || 'unknown zone'}
                </span>
                {!selectedCam.position && (
                  <span className="px-2 py-1 bg-yellow-600/80 text-white text-xs rounded-lg backdrop-blur">
                    Unplaced
                  </span>
                )}
              </div>
              {/* Close button */}
              <button
                onClick={() => setSelectedId(null)}
                className="absolute top-3 right-3 w-7 h-7 flex items-center justify-center bg-black/60 hover:bg-black/80 text-white rounded-full backdrop-blur transition-colors"
              >
                ✕
              </button>
            </div>
          )}

          {/* Floor Map */}
          <div className="flex-1 relative min-h-0">
            <svg viewBox={vb} className="w-full h-full" style={{ background: '#111827' }}>
              {/* Grid */}
              <defs>
                <pattern id="cam-grid" width="1" height="1" patternUnits="userSpaceOnUse">
                  <path d="M 1 0 L 0 0 0 1" fill="none" stroke="#1f2937" strokeWidth="0.02" />
                </pattern>
              </defs>
              <rect
                x={-PAD} y={-PAD}
                width={config.building.width_m + PAD * 2}
                height={config.building.height_m + PAD * 2}
                fill="url(#cam-grid)"
              />

              {/* Building outline */}
              <rect x={0} y={0} width={config.building.width_m} height={config.building.height_m}
                fill="none" stroke="#374151" strokeWidth={0.06} />

              {/* Walls & Columns */}
              {floorplanQuery.data?.walls.map((w, i) => w.closed
                ? <polygon key={`w${i}`} points={toSvg(w.points, fy)} fill="#475569" stroke="#64748b" strokeWidth={0.03} />
                : <polyline key={`w${i}`} points={toSvg(w.points, fy)} fill="none" stroke="#64748b" strokeWidth={0.06} />
              )}
              {floorplanQuery.data?.columns.map((c, i) =>
                <polygon key={`c${i}`} points={toSvg(c.points, fy)} fill="#991b1b" stroke="#b91c1c" strokeWidth={0.03} />
              )}

              {/* Zones */}
              {zoneList.map(z => (
                <g key={z.id}>
                  <polygon
                    points={toSvg(z.polygon, fy)}
                    fill={z.color} fillOpacity={0.06}
                    stroke={z.color} strokeWidth={0.04} strokeOpacity={0.3}
                  />
                  {z.polygon.length > 0 && (() => {
                    const cx = z.polygon.reduce((s, p) => s + p[0], 0) / z.polygon.length;
                    const cy = z.polygon.reduce((s, p) => s + p[1], 0) / z.polygon.length;
                    return (
                      <text x={cx} y={fy - cy} textAnchor="middle" dominantBaseline="central"
                        fontSize={0.4} fill={z.color} fillOpacity={0.5} fontWeight="600">
                        {z.display_name}
                      </text>
                    );
                  })()}
                </g>
              ))}

              {/* Camera FOV cones + icons */}
              {cameras.map(cam => {
                if (!cam.position) return null;
                const [px, py] = cam.position;
                const isSelected = cam.camera_id === selectedId;
                const fillColor = isSelected ? '#3b82f6' : '#ef4444';
                const fillOpacity = isSelected ? 0.15 : 0.06;
                const strokeColor = isSelected ? '#3b82f6' : '#ef4444';

                return (
                  <g key={cam.camera_id}
                    onClick={() => handleCameraClick(cam.camera_id)}
                    style={{ cursor: 'pointer' }}>
                    {/* FOV cone */}
                    {cam.fov_deg != null && cam.orientation_deg != null && (
                      <path
                        d={conePath(px, py, cam.orientation_deg, cam.fov_deg, 4, fy)}
                        fill={fillColor} fillOpacity={fillOpacity}
                        stroke={strokeColor} strokeWidth={0.04} strokeOpacity={0.4}
                      />
                    )}
                    {/* Camera body */}
                    <rect
                      x={px - 0.25} y={fy - py - 0.18}
                      width={0.5} height={0.36} rx={0.06}
                      fill={fillColor} stroke={isSelected ? '#1d4ed8' : '#7f1d1d'}
                      strokeWidth={isSelected ? 0.06 : 0.04}
                    />
                    {/* Selection ring */}
                    {isSelected && (
                      <circle cx={px} cy={fy - py} r={0.6} fill="none"
                        stroke="#3b82f6" strokeWidth={0.04} strokeDasharray="0.15 0.1">
                        <animate attributeName="stroke-dashoffset" values="0;0.5" dur="1s" repeatCount="indefinite" />
                      </circle>
                    )}
                    {/* Label */}
                    <text x={px} y={fy - py + 0.65} textAnchor="middle"
                      fontSize={0.25} fill={isSelected ? '#93c5fd' : '#fca5a5'} fontWeight={isSelected ? '700' : '500'}>
                      {cam.camera_id.replace('cam_', '').slice(-8)}
                    </text>
                  </g>
                );
              })}
            </svg>

            {/* Legend */}
            <div className="absolute bottom-3 left-3 bg-black/60 backdrop-blur rounded-lg px-3 py-2 text-xs text-white/70 space-y-1">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 bg-red-500 rounded-sm" style={{ width: 10, height: 8 }} /> Camera
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 bg-blue-500 rounded-sm" style={{ width: 10, height: 8 }} /> Selected
              </div>
            </div>
          </div>
        </div>

        {/* Camera Cards Panel */}
        <div className="w-96 bg-[var(--gray-50)] border-l border-[var(--gray-200)] flex flex-col flex-shrink-0 overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--gray-200)] bg-white">
            <h2 className="text-sm font-semibold text-[var(--gray-900)]">Camera Feeds</h2>
            <p className="text-[10px] text-[var(--gray-500)] mt-0.5">Click a camera to highlight on map</p>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {cameras.length === 0 ? (
              <div className="text-sm text-[var(--gray-500)] text-center py-8">
                No cameras in spatial config.
              </div>
            ) : (
              cameras.map(cam => (
                <SnapshotCard
                  key={cam.camera_id}
                  cam={cam}
                  selected={cam.camera_id === selectedId}
                  onSelect={() => handleCameraClick(cam.camera_id)}
                  bust={bust}
                  streamAvailable={snapshotServerUp}
                  overlay={showOverlay}
                />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
