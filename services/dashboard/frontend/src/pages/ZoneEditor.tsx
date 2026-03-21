import { useState, useRef, useCallback, useEffect } from 'react';

// ── Types ──────────────────────────────────────────────────────────

interface Point { x: number; y: number }

interface Zone {
  id: string;
  displayName: string;
  polygon: Point[];
  color: string;
}

interface Floorplan {
  building: { width_m: number; height_m: number };
  walls: { points: number[][]; closed: boolean }[];
  columns: { points: number[][] }[];
}

interface DeviceItem {
  id: string;
  zone: string;
  x: number;
  y: number;
  deviceType: string;
  channels: string[];
  orientationDeg: number | null;
  fovDeg: number | null;
  detectionRangeM: number | null;
  dirty?: boolean;
  isNew?: boolean;
}

interface CameraItem {
  id: string;
  zone: string;
  x: number;
  y: number;
  z: number | null;
  fovDeg: number;
  orientationDeg: number;
  resolution: number[];
  dirty?: boolean;
  isNew?: boolean;
}

interface ArucoMarker {
  id: string;
  corners: number[][];
  dirty?: boolean;
}

type SelEntity = { type: 'zone'; id: string }
  | { type: 'device'; id: string }
  | { type: 'camera'; id: string }
  | { type: 'marker'; id: string }
  | null;

type EditorMode = 'select' | 'draw' | 'place-device' | 'place-camera' | 'place-marker';

interface LayerVis { zones: boolean; devices: boolean; cameras: boolean; markers: boolean; cones: boolean }

interface CatalogEntry {
  label: string;
  channels: string[];
  directional: boolean;
  defaultFov?: number;
  defaultRange?: number;
  color: string;
}

interface DiscoveredDevice {
  device_id: string;
  source: string;
  device_type: string;
  zone: string | null;
  label: string | null;
  channels: string[];
  placed: boolean;
  online: boolean | null;
  battery_pct: number | null;
  bridge: string | null;
}

// ── Constants ──────────────────────────────────────────────────────

const COLORS = [
  '#3b82f6','#ef4444','#10b981','#f59e0b','#8b5cf6',
  '#ec4899','#06b6d4','#84cc16','#f97316','#6366f1',
  '#14b8a6','#e11d48','#0ea5e9','#a855f7','#22c55e',
];
const PAD = 2;
const CAM_COLOR = '#ef4444';
const MARKER_COLOR = '#6b7280';

const DEVICE_CATALOG: Record<string, CatalogEntry> = {
  motion:        { label:'Motion (PIR)', channels:['motion','illuminance'], directional:true, defaultFov:120, defaultRange:6, color:'#f59e0b' },
  presence:      { label:'Presence (24GHz)', channels:['motion'], directional:true, defaultFov:120, defaultRange:7, color:'#f59e0b' },
  pir:           { label:'PIR', channels:['motion'], directional:true, defaultFov:110, defaultRange:6, color:'#f59e0b' },
  temp_humidity: { label:'Temp/Humidity', channels:['temperature','humidity'], directional:false, color:'#10b981' },
  illuminance:   { label:'Illuminance', channels:['illuminance'], directional:false, color:'#10b981' },
  contact:       { label:'Contact', channels:['contact'], directional:false, color:'#8b5cf6' },
  plug:          { label:'Smart Plug', channels:['power_state'], directional:false, color:'#3b82f6' },
  light:         { label:'Smart Light', channels:['brightness'], directional:false, color:'#3b82f6' },
  bme680:        { label:'BME680', channels:['temperature','humidity','pressure','gas'], directional:false, color:'#10b981' },
  mhz19c:        { label:'CO2 (MH-Z19C)', channels:['co2'], directional:false, color:'#10b981' },
  sensor:        { label:'Generic Sensor', channels:[], directional:false, color:'#9ca3af' },
};

// ── Helpers ────────────────────────────────────────────────────────

function area(pts: Point[]): number {
  let a = 0;
  for (let i = 0; i < pts.length; i++) {
    const j = (i + 1) % pts.length;
    a += pts[i].x * pts[j].y - pts[j].x * pts[i].y;
  }
  return Math.abs(a) / 2;
}

function toSvg(pts: (Point | number[])[], fy: number): string {
  return pts.map(p => {
    const x = Array.isArray(p) ? p[0] : p.x;
    const y = Array.isArray(p) ? p[1] : p.y;
    return `${x},${fy - y}`;
  }).join(' ');
}

function dist(a: Point, b: Point) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function pointInPolygon(p: Point, poly: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].x, yi = poly[i].y;
    const xj = poly[j].x, yj = poly[j].y;
    if (((yi > p.y) !== (yj > p.y)) && (p.x < (xj - xi) * (p.y - yi) / (yj - yi) + xi)) {
      inside = !inside;
    }
  }
  return inside;
}

function detectZone(p: Point, zones: Zone[]): string {
  for (const z of zones) {
    if (z.polygon.length >= 3 && pointInPolygon(p, z.polygon)) return z.id;
  }
  return 'unknown';
}

/** Build SVG arc path for a directional cone. Angles in degrees, 0=right, CCW in world coords. */
function conePath(cx: number, cy: number, orientDeg: number, fovDeg: number, range: number, fy: number): string {
  const toRad = Math.PI / 180;
  // In SVG, y is flipped, so we negate the angle for correct world→SVG mapping
  const startAngle = -(orientDeg - fovDeg / 2) * toRad;
  const endAngle = -(orientDeg + fovDeg / 2) * toRad;
  const sx = cx + range * Math.cos(startAngle);
  const sy = (fy - cy) + range * Math.sin(startAngle);
  const ex = cx + range * Math.cos(endAngle);
  const ey = (fy - cy) + range * Math.sin(endAngle);
  const largeArc = fovDeg > 180 ? 1 : 0;
  return `M ${cx} ${fy - cy} L ${sx} ${sy} A ${range} ${range} 0 ${largeArc} 0 ${ex} ${ey} Z`;
}

/** Generate a sequential device ID like `motion_01` based on existing devices. */
function nextDeviceId(type: string, existing: DeviceItem[]): string {
  const prefix = type === 'sensor' ? 'sensor' : type;
  const re = new RegExp(`^${prefix}_(\\d+)$`);
  let max = 0;
  for (const d of existing) {
    const m = d.id.match(re);
    if (m) max = Math.max(max, parseInt(m[1], 10));
  }
  return `${prefix}_${String(max + 1).padStart(2, '0')}`;
}

function deviceColor(type: string): string {
  return DEVICE_CATALOG[type]?.color ?? '#9ca3af';
}

function isDirectional(type: string): boolean {
  return DEVICE_CATALOG[type]?.directional ?? false;
}

// Marker center and size from corners
function markerCenter(corners: number[][]): Point {
  const x = corners.reduce((s, c) => s + c[0], 0) / corners.length;
  const y = corners.reduce((s, c) => s + c[1], 0) / corners.length;
  return { x, y };
}

function markerFromCenter(cx: number, cy: number, size: number = 0.1): number[][] {
  const h = size / 2;
  return [[cx - h, cy - h], [cx + h, cy - h], [cx + h, cy + h], [cx - h, cy + h]];
}

// ── Inline styles ─────────────────────────────────────────────────

const sInput: React.CSSProperties = { width:'100%', marginBottom:8, padding:'4px 8px', fontSize:12, background:'#1f2937', border:'1px solid #374151', borderRadius:4, color:'#fff', boxSizing:'border-box' as const };
const sLabel: React.CSSProperties = { display:'block', fontSize:12, color:'#9ca3af', marginBottom:4 };
const sBtn = (active: boolean, c: string): React.CSSProperties => ({ flex:1, padding:'6px 12px', fontSize:12, borderRadius:4, border:'none', cursor:'pointer', fontWeight:500, background:active?c:'#1f2937', color:active?'#fff':'#9ca3af' });

// ── Component ──────────────────────────────────────────────────────

export default function ZoneEditor() {
  const svgRef = useRef<SVGSVGElement>(null);
  const [fp, setFp] = useState<Floorplan | null>(null);
  const [zones, setZones] = useState<Zone[]>([]);
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [cameras, setCameras] = useState<CameraItem[]>([]);
  const [markers, setMarkers] = useState<ArucoMarker[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [mode, setMode] = useState<EditorMode>('select');
  const [drawing, setDrawing] = useState<Point[]>([]);
  const [selEntity, setSelEntity] = useState<SelEntity>(null);
  const [cursor, setCursor] = useState<Point | null>(null);
  const [editVtx, setEditVtx] = useState<{ zid: string; vi: number } | null>(null);
  const [dragEntity, setDragEntity] = useState<{ type: string; id: string } | null>(null);
  const [rotateEntity, setRotateEntity] = useState<{ type: string; id: string } | null>(null);
  const [layers, setLayers] = useState<LayerVis>({ zones: true, devices: true, cameras: true, markers: true, cones: true });
  const [placeDeviceType, setPlaceDeviceType] = useState('sensor');
  const [discovered, setDiscovered] = useState<DiscoveredDevice[]>([]);
  const [pendingBind, setPendingBind] = useState<DiscoveredDevice | null>(null);
  const [vb, setVb] = useState({ x: -PAD, y: -PAD, w: 34, h: 19 });
  const vbRef = useRef(vb);
  vbRef.current = vb;
  const [panning, setPanning] = useState(false);
  const panRef = useRef<{ cx: number; cy: number; vx: number; vy: number } | null>(null);

  // ── Fetch ─────────────────────────────────────────────────────

  useEffect(() => {
    Promise.all([
      fetch('/api/sensors/spatial/floorplan').then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json(); }),
      fetch('/api/sensors/spatial/zones').then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json(); }),
      fetch('/api/sensors/spatial/config').then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json(); }),
      fetch('/api/sensors/spatial/aruco').then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json(); }),
    ]).then(([f, z, cfg, ar]) => {
      setFp(f);
      setVb({ x: -PAD, y: -PAD, w: f.building.width_m + PAD * 2, h: f.building.height_m + PAD * 2 });
      setZones(Object.entries(z.zones || {}).map(([id, d]: [string, any], i) => ({
        id,
        displayName: d.display_name || id,
        polygon: (d.polygon || []).map((p: number[]) => ({ x: p[0], y: p[1] })),
        color: COLORS[i % COLORS.length],
      })));
      // Devices from spatial config
      const devs: DeviceItem[] = Object.entries(cfg.devices || {}).map(([id, d]: [string, any]) => ({
        id, zone: d.zone || 'unknown', x: d.position?.[0] ?? 0, y: d.position?.[1] ?? 0,
        deviceType: d.type || 'sensor', channels: d.channels || [],
        orientationDeg: d.orientation_deg ?? null, fovDeg: d.fov_deg ?? null,
        detectionRangeM: d.detection_range_m ?? null,
      }));
      setDevices(devs);
      // Cameras from spatial config
      const cams: CameraItem[] = Object.entries(cfg.cameras || {}).map(([id, d]: [string, any]) => ({
        id, zone: d.zone || 'unknown', x: d.position?.[0] ?? 0, y: d.position?.[1] ?? 0,
        z: d.z ?? null, fovDeg: d.fov_deg ?? 90, orientationDeg: d.orientation_deg ?? 0,
        resolution: d.resolution || [640, 480],
      }));
      setCameras(cams);
      // ArUco markers
      const mkrs: ArucoMarker[] = Object.entries(ar.aruco_markers || {}).map(([id, d]: [string, any]) => ({
        id, corners: d.corners || [],
      }));
      setMarkers(mkrs);
    }).catch(e => setErr(e.message));
    // Discovery (non-blocking)
    fetch('/api/devices/discovery').then(r => r.ok ? r.json() : []).then(setDiscovered).catch(() => {});
  }, []);

  // ── SVG→World ─────────────────────────────────────────────────

  const toWorld = useCallback((cx: number, cy: number): Point | null => {
    const s = svgRef.current;
    if (!s || !fp) return null;
    const pt = s.createSVGPoint();
    pt.x = cx; pt.y = cy;
    const ctm = s.getScreenCTM();
    if (!ctm) return null;
    const sp = pt.matrixTransform(ctm.inverse());
    return { x: Math.round(sp.x * 100) / 100, y: Math.round((fp.building.height_m - sp.y) * 100) / 100 };
  }, [fp]);

  // ── Mouse ─────────────────────────────────────────────────────

  const onMove = useCallback((e: React.MouseEvent) => {
    const w = toWorld(e.clientX, e.clientY);
    if (w) setCursor(w);
    if (panning && panRef.current) {
      const s = svgRef.current;
      if (!s) return;
      const r = s.getBoundingClientRect();
      const v = vbRef.current;
      const nx = panRef.current.vx - (e.clientX - panRef.current.cx) * v.w / r.width;
      const ny = panRef.current.vy - (e.clientY - panRef.current.cy) * v.h / r.height;
      if (Number.isFinite(nx) && Number.isFinite(ny)) setVb(p => ({ ...p, x: nx, y: ny }));
    }
    if (editVtx && w) {
      setZones(p => p.map(z => {
        if (z.id !== editVtx.zid) return z;
        const np = [...z.polygon]; np[editVtx.vi] = w; return { ...z, polygon: np };
      }));
    }
    // Drag device/camera/marker
    if (dragEntity && w) {
      if (dragEntity.type === 'device') {
        setDevices(p => p.map(d => d.id === dragEntity.id ? { ...d, x: w.x, y: w.y, zone: detectZone(w, zones), dirty: true } : d));
      } else if (dragEntity.type === 'camera') {
        setCameras(p => p.map(c => c.id === dragEntity.id ? { ...c, x: w.x, y: w.y, zone: detectZone(w, zones), dirty: true } : c));
      } else if (dragEntity.type === 'marker') {
        setMarkers(p => p.map(m => {
          if (m.id !== dragEntity.id) return m;
          const c = markerCenter(m.corners);
          const dx = w.x - c.x, dy = w.y - c.y;
          return { ...m, corners: m.corners.map(([cx2, cy2]) => [cx2 + dx, cy2 + dy]), dirty: true };
        }));
      }
    }
    // Rotate handle
    if (rotateEntity && w) {
      if (rotateEntity.type === 'device') {
        setDevices(p => p.map(d => {
          if (d.id !== rotateEntity.id) return d;
          const angle = Math.atan2(w.y - d.y, w.x - d.x) * 180 / Math.PI;
          return { ...d, orientationDeg: Math.round(angle), dirty: true };
        }));
      } else if (rotateEntity.type === 'camera') {
        setCameras(p => p.map(c => {
          if (c.id !== rotateEntity.id) return c;
          const angle = Math.atan2(w.y - c.y, w.x - c.x) * 180 / Math.PI;
          return { ...c, orientationDeg: Math.round(angle), dirty: true };
        }));
      }
    }
  }, [toWorld, panning, editVtx, dragEntity, rotateEntity, zones]);

  const beginPan = useCallback((cx: number, cy: number) => {
    setPanning(true);
    panRef.current = { cx, cy, vx: vbRef.current.x, vy: vbRef.current.y };
  }, []);

  const onDown = useCallback((e: React.MouseEvent) => {
    if (e.button === 1 || e.button === 2) { e.preventDefault(); beginPan(e.clientX, e.clientY); return; }
    if (mode === 'select' && e.button === 0) {
      const t = e.target as SVGElement;
      if (t.tagName === 'svg' || t.dataset.bg) { beginPan(e.clientX, e.clientY); setSelEntity(null); }
    }
  }, [mode, beginPan]);

  const onUp = useCallback(() => {
    setPanning(false); panRef.current = null; setEditVtx(null);
    setDragEntity(null); setRotateEntity(null);
  }, []);

  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const s = svgRef.current;
    if (!s) return;
    const pt = s.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
    const ctm = s.getScreenCTM();
    if (!ctm) return;
    const sp = pt.matrixTransform(ctm.inverse());
    const f = e.deltaY > 0 ? 1.1 : 0.9;
    setVb(v => {
      const nw = Math.max(3, Math.min(v.w * f, 80));
      const nh = Math.max(2, Math.min(v.h * f, 50));
      const nx = sp.x - (sp.x - v.x) * (nw / v.w);
      const ny = sp.y - (sp.y - v.y) * (nh / v.h);
      return Number.isFinite(nx) && Number.isFinite(ny) ? { x: nx, y: ny, w: nw, h: nh } : v;
    });
  }, []);

  // ── Drawing (zone) ──────────────────────────────────────────

  const finish = useCallback(() => {
    if (drawing.length < 3) return;
    const i = zones.length;
    const nz: Zone = { id: `zone_${String(i).padStart(2,'0')}`, displayName: `zone_${String(i).padStart(2,'0')}`, polygon: drawing, color: COLORS[i % COLORS.length] };
    setZones(p => [...p, nz]);
    setDrawing([]);
    setSelEntity({ type: 'zone', id: nz.id });
    setMode('select');
  }, [drawing, zones]);

  const cancel = useCallback(() => { setDrawing([]); setPendingBind(null); setMode('select'); }, []);

  // ── Placement click ─────────────────────────────────────────

  const onClick = useCallback((e: React.MouseEvent) => {
    if (panning) return;
    const w = toWorld(e.clientX, e.clientY);
    if (!w) return;

    if (mode === 'draw') {
      if (drawing.length >= 3 && dist(w, drawing[0]) < vbRef.current.w * 0.015) { finish(); return; }
      setDrawing(p => [...p, w]);
      return;
    }

    if (mode === 'place-device') {
      const bind = pendingBind;
      const devType = bind ? bind.device_type : placeDeviceType;
      const cat = DEVICE_CATALOG[devType] || DEVICE_CATALOG.sensor;
      const id = bind ? bind.device_id : nextDeviceId(placeDeviceType, devices);
      const nd: DeviceItem = {
        id, zone: bind?.zone || detectZone(w, zones), x: w.x, y: w.y,
        deviceType: devType, channels: bind ? bind.channels : cat.channels,
        orientationDeg: cat.directional ? 0 : null,
        fovDeg: cat.directional ? (cat.defaultFov ?? 90) : null,
        detectionRangeM: cat.directional ? (cat.defaultRange ?? 5) : null,
        dirty: true, isNew: true,
      };
      setDevices(p => [...p, nd]);
      setSelEntity({ type: 'device', id });
      setPendingBind(null);
      setMode('select');
      return;
    }

    if (mode === 'place-camera') {
      const id = `cam_${Date.now().toString(36)}`;
      const nc: CameraItem = {
        id, zone: detectZone(w, zones), x: w.x, y: w.y, z: 2.5,
        fovDeg: 90, orientationDeg: 0, resolution: [640, 480],
        dirty: true, isNew: true,
      };
      setCameras(p => [...p, nc]);
      setSelEntity({ type: 'camera', id });
      setMode('select');
      return;
    }

    if (mode === 'place-marker') {
      const maxId = markers.length > 0 ? Math.max(...markers.map(m => parseInt(m.id) || 0)) : -1;
      const id = String(maxId + 1);
      const nm: ArucoMarker = { id, corners: markerFromCenter(w.x, w.y), dirty: true };
      setMarkers(p => [...p, nm]);
      setSelEntity({ type: 'marker', id });
      setMode('select');
      return;
    }
  }, [mode, drawing, toWorld, panning, finish, zones, placeDeviceType, markers]);

  // ── Zone ops ────────────────────────────────────────────────

  const delZone = useCallback((id: string) => {
    setZones(p => p.filter(z => z.id !== id));
    setSelEntity(s => s?.type === 'zone' && s.id === id ? null : s);
  }, []);
  const renZone = useCallback((id: string, n: string) => { setZones(p => p.map(z => z.id === id ? { ...z, displayName: n } : z)); }, []);
  const chgId = useCallback((old: string, nw: string) => {
    if (!/^[a-z0-9_]+$/.test(nw)) return;
    setZones(p => p.map(z => z.id === old ? { ...z, id: nw } : z));
    setSelEntity(s => s?.type === 'zone' && s.id === old ? { type: 'zone', id: nw } : s);
  }, []);
  const delVtx = useCallback((zid: string, vi: number) => {
    setZones(p => p.map(z => z.id !== zid || z.polygon.length <= 3 ? z : { ...z, polygon: z.polygon.filter((_, i) => i !== vi) }));
  }, []);

  // ── Device/Camera/Marker ops ────────────────────────────────

  const delDevice = useCallback((id: string) => {
    setDevices(p => p.filter(d => d.id !== id));
    setSelEntity(s => s?.type === 'device' && s.id === id ? null : s);
  }, []);

  const delCamera = useCallback((id: string) => {
    setCameras(p => p.filter(c => c.id !== id));
    setSelEntity(s => s?.type === 'camera' && s.id === id ? null : s);
  }, []);

  const delMarker = useCallback((id: string) => {
    setMarkers(p => p.filter(m => m.id !== id));
    setSelEntity(s => s?.type === 'marker' && s.id === id ? null : s);
  }, []);

  const chgDeviceId = useCallback((oldId: string, newId: string) => {
    if (!/^[a-z0-9_]+$/.test(newId)) return;
    if (devices.some(d => d.id !== oldId && d.id === newId)) return; // uniqueness
    setDevices(p => p.map(d => d.id === oldId ? { ...d, id: newId, dirty: true } : d));
    setSelEntity(s => s?.type === 'device' && s.id === oldId ? { type: 'device', id: newId } : s);
  }, [devices]);

  const refreshDiscovery = useCallback(() => {
    fetch('/api/devices/discovery').then(r => r.ok ? r.json() : []).then(setDiscovered).catch(() => {});
  }, []);

  // ── Keys ────────────────────────────────────────────────────

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape') cancel();
      if (e.key === 'Enter' && drawing.length >= 3) finish();
      if (e.key === 'Delete' && selEntity) {
        if (selEntity.type === 'zone') delZone(selEntity.id);
        else if (selEntity.type === 'device') delDevice(selEntity.id);
        else if (selEntity.type === 'camera') delCamera(selEntity.id);
        else if (selEntity.type === 'marker') delMarker(selEntity.id);
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [drawing, selEntity, cancel, finish, delZone, delDevice, delCamera, delMarker]);

  // ── Save All ────────────────────────────────────────────────

  const save = useCallback(async () => {
    const parts: string[] = [];
    try {
      // 1. Zones
      const zd: Record<string, any> = {};
      for (const z of zones) {
        const a = area(z.polygon);
        zd[z.id] = {
          display_name: z.displayName,
          polygon: z.polygon.map(p => [Math.round(p.x*100)/100, Math.round(p.y*100)/100]),
          area_m2: Math.round(a * 10) / 10, floor: 1, adjacent_zones: [],
          grid_cols: Math.max(1, Math.round(Math.sqrt(a) / 1.5)),
          grid_rows: Math.max(1, Math.round(Math.sqrt(a) / 1.5)),
        };
      }
      const zr = await fetch('/api/sensors/spatial/zones', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ zones: zd }) });
      if (!zr.ok) throw new Error(`zones: ${zr.status}`);
      parts.push(`${zones.length} zones`);

      // 2. Dirty devices
      const dirtyDevs = devices.filter(d => d.dirty);
      for (const d of dirtyDevs) {
        if (d.isNew) {
          const r = await fetch('/api/devices/positions/', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              device_id: d.id, zone: d.zone, x: d.x, y: d.y,
              device_type: d.deviceType, channels: d.channels,
              orientation_deg: d.orientationDeg, fov_deg: d.fovDeg, detection_range_m: d.detectionRangeM,
            }),
          });
          if (!r.ok) throw new Error(`device ${d.id}: ${r.status}`);
        } else {
          const r = await fetch(`/api/devices/positions/${encodeURIComponent(d.id)}`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              x: d.x, y: d.y, zone: d.zone,
              orientation_deg: d.orientationDeg, fov_deg: d.fovDeg, detection_range_m: d.detectionRangeM,
            }),
          });
          if (!r.ok) throw new Error(`device ${d.id}: ${r.status}`);
        }
      }
      if (dirtyDevs.length) parts.push(`${dirtyDevs.length} devices`);
      setDevices(p => p.map(d => ({ ...d, dirty: false, isNew: false })));

      // 3. Dirty cameras
      const dirtyCams = cameras.filter(c => c.dirty);
      for (const c of dirtyCams) {
        const r = await fetch(`/api/devices/cameras/${encodeURIComponent(c.id)}`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ zone: c.zone, x: c.x, y: c.y, z: c.z, fov_deg: c.fovDeg, orientation_deg: c.orientationDeg }),
        });
        if (!r.ok) throw new Error(`camera ${c.id}: ${r.status}`);
      }
      if (dirtyCams.length) parts.push(`${dirtyCams.length} cameras`);
      setCameras(p => p.map(c => ({ ...c, dirty: false, isNew: false })));

      // 4. Dirty markers → save all
      const dirtyM = markers.filter(m => m.dirty);
      if (dirtyM.length) {
        const md: Record<string, any> = {};
        for (const m of markers) {
          md[m.id] = { corners: m.corners.map(c => [Math.round(c[0]*100)/100, Math.round(c[1]*100)/100]) };
        }
        const mr = await fetch('/api/sensors/spatial/aruco', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ aruco_markers: md }) });
        if (!mr.ok) throw new Error(`markers: ${mr.status}`);
        parts.push(`${markers.length} markers`);
        setMarkers(p => p.map(m => ({ ...m, dirty: false })));
      }

      setSaveMsg(parts.join(', ') + ' saved');
      setTimeout(() => setSaveMsg(null), 3000);
      refreshDiscovery();
    } catch (e: any) { setSaveMsg(`Error: ${e.message}`); }
  }, [zones, devices, cameras, markers, refreshDiscovery]);

  // ── Render ──────────────────────────────────────────────────

  if (err) return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'100vh', background:'#030712', color:'#fff' }}>
      <div><h2>Failed to load</h2><p style={{color:'#9ca3af'}}>{err}</p></div>
    </div>
  );

  if (!fp) return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'100vh', background:'#030712', color:'#9ca3af' }}>
      Loading...
    </div>
  );

  const fy = fp.building.height_m;
  const sel = selEntity?.type === 'zone' ? zones.find(z => z.id === selEntity.id) : null;
  const selDev = selEntity?.type === 'device' ? devices.find(d => d.id === selEntity.id) : null;
  const selCam = selEntity?.type === 'camera' ? cameras.find(c => c.id === selEntity.id) : null;
  const selMkr = selEntity?.type === 'marker' ? markers.find(m => m.id === selEntity.id) : null;

  const isPlacing = mode === 'place-device' || mode === 'place-camera' || mode === 'place-marker';

  return (
    <div style={{ display:'flex', height:'100vh', background:'#030712', color:'#e5e7eb', userSelect:'none' }}>
      {/* Sidebar */}
      <div style={{ width:288, background:'#111827', borderRight:'1px solid #1f2937', display:'flex', flexDirection:'column', overflow:'hidden', flexShrink:0 }}>
        {/* Toolbar */}
        <div style={{ padding:12, borderBottom:'1px solid #1f2937' }}>
          <h1 style={{ fontSize:14, fontWeight:700, color:'#fff', marginBottom:12 }}>Zone Editor</h1>
          {/* Mode buttons row 1 */}
          <div style={{ display:'flex', gap:4, marginBottom:6 }}>
            <button onClick={() => { setMode('select'); setDrawing([]); }} style={sBtn(mode==='select','#2563eb')}>Select</button>
            <button onClick={() => setMode('draw')} style={sBtn(mode==='draw','#16a34a')}>Draw Zone</button>
          </div>
          {/* Mode buttons row 2 — placement */}
          <div style={{ display:'flex', gap:4, marginBottom:8 }}>
            <button onClick={() => setMode('place-device')} style={sBtn(mode==='place-device','#f59e0b')}>+ Device</button>
            <button onClick={() => setMode('place-camera')} style={sBtn(mode==='place-camera','#ef4444')}>+ Camera</button>
            <button onClick={() => setMode('place-marker')} style={sBtn(mode==='place-marker','#6b7280')}>+ Marker</button>
          </div>

          {/* Layer toggles */}
          <div style={{ display:'flex', gap:4, marginBottom:8 }}>
            {([['Z','zones'],['D','devices'],['C','cameras'],['M','markers'],['F','cones']] as const).map(([lbl, key]) => (
              <button key={key} onClick={() => setLayers(p => ({ ...p, [key]: !p[key] }))}
                style={{ flex:1, padding:'3px 0', fontSize:10, fontWeight:600, borderRadius:3, border:'none', cursor:'pointer',
                  background: layers[key] ? '#374151' : '#1f2937', color: layers[key] ? '#fff' : '#4b5563' }}>
                {lbl}</button>
            ))}
          </div>

          <button onClick={save} style={{ width:'100%', padding:'6px 12px', fontSize:12, borderRadius:4, border:'none', cursor:'pointer', fontWeight:500, background:'#4f46e5', color:'#fff' }}>
            Save All</button>
          {saveMsg && <p style={{ fontSize:12, marginTop:6, color: saveMsg.startsWith('Error')?'#f87171':'#4ade80' }}>{saveMsg}</p>}
        </div>

        {/* Place-device type selector */}
        {mode === 'place-device' && (
          <div style={{ padding:'8px 12px', background: pendingBind ? 'rgba(30,58,95,0.4)' : 'rgba(120,80,0,0.2)', borderBottom:'1px solid #1f2937', fontSize:12, color: pendingBind ? '#93c5fd' : '#fcd34d' }}>
            {pendingBind ? (
              <>Placing <b>{pendingBind.device_id}</b> ({pendingBind.device_type}){pendingBind.label ? ` — ${pendingBind.label}` : ''}<br/>Click on the floor plan to place.</>
            ) : (
              <>
                <label style={sLabel}>Device Type</label>
                <select value={placeDeviceType} onChange={e => setPlaceDeviceType(e.target.value)}
                  style={{ ...sInput, marginBottom:4 }}>
                  {Object.entries(DEVICE_CATALOG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
                Click on the floor plan to place.
              </>
            )}
            <br/><button onClick={() => { setPendingBind(null); cancel(); }} style={{ marginTop:4, color:'#f87171', background:'none', border:'none', cursor:'pointer', textDecoration:'underline', fontSize:12 }}>Cancel (Esc)</button>
          </div>
        )}

        {mode === 'place-camera' && (
          <div style={{ padding:'8px 12px', background:'rgba(120,0,0,0.2)', borderBottom:'1px solid #1f2937', fontSize:12, color:'#fca5a5' }}>
            Click on the floor plan to place a camera.
            <br/><button onClick={cancel} style={{ marginTop:4, color:'#f87171', background:'none', border:'none', cursor:'pointer', textDecoration:'underline', fontSize:12 }}>Cancel (Esc)</button>
          </div>
        )}

        {mode === 'place-marker' && (
          <div style={{ padding:'8px 12px', background:'rgba(80,80,80,0.2)', borderBottom:'1px solid #1f2937', fontSize:12, color:'#d1d5db' }}>
            Click on the floor plan to place an ArUco marker.
            <br/><button onClick={cancel} style={{ marginTop:4, color:'#f87171', background:'none', border:'none', cursor:'pointer', textDecoration:'underline', fontSize:12 }}>Cancel (Esc)</button>
          </div>
        )}

        {mode === 'draw' && (
          <div style={{ padding:'8px 12px', background:'rgba(20,83,45,0.3)', borderBottom:'1px solid #1f2937', fontSize:12, color:'#86efac' }}>
            Click to place vertices. Click first vertex or Enter to close.
            <br/>
            <button onClick={cancel} style={{ marginTop:4, color:'#f87171', background:'none', border:'none', cursor:'pointer', textDecoration:'underline', fontSize:12 }}>Cancel (Esc)</button>
            {drawing.length >= 3 && <button onClick={finish} style={{ marginTop:4, marginLeft:8, color:'#4ade80', background:'none', border:'none', cursor:'pointer', textDecoration:'underline', fontSize:12 }}>Finish (Enter)</button>}
          </div>
        )}

        {/* Entity lists */}
        <div style={{ flex:1, overflowY:'auto', padding:12 }}>
          {/* Zones */}
          <h2 style={{ fontSize:11, fontWeight:600, color:'#6b7280', textTransform:'uppercase', marginBottom:8 }}>Zones ({zones.length})</h2>
          {zones.map(z => (
            <div key={z.id} onClick={() => setSelEntity({ type: 'zone', id: z.id })}
              style={{ marginBottom:4, padding:6, borderRadius:4, fontSize:11, cursor:'pointer',
                background: selEntity?.type==='zone'&&selEntity.id===z.id?'#374151':'rgba(31,41,55,0.5)',
                outline: selEntity?.type==='zone'&&selEntity.id===z.id?'1px solid #3b82f6':'none' }}>
              <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                <div style={{ width:10, height:10, borderRadius:2, flexShrink:0, background:z.color }}/>
                <span style={{ fontWeight:500, color:'#fff', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{z.displayName}</span>
                <span style={{ marginLeft:'auto', color:'#6b7280' }}>{area(z.polygon).toFixed(1)}m²</span>
              </div>
            </div>
          ))}

          {/* Devices */}
          {devices.length > 0 && <>
            <h2 style={{ fontSize:11, fontWeight:600, color:'#6b7280', textTransform:'uppercase', marginTop:12, marginBottom:8 }}>Devices ({devices.length})</h2>
            {devices.map(d => (
              <div key={d.id} onClick={() => setSelEntity({ type: 'device', id: d.id })}
                style={{ marginBottom:4, padding:6, borderRadius:4, fontSize:11, cursor:'pointer',
                  background: selEntity?.type==='device'&&selEntity.id===d.id?'#374151':'rgba(31,41,55,0.5)',
                  outline: selEntity?.type==='device'&&selEntity.id===d.id?`1px solid ${deviceColor(d.deviceType)}`:'none' }}>
                <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                  <div style={{ width:10, height:10, borderRadius:10, flexShrink:0, background:deviceColor(d.deviceType) }}/>
                  <span style={{ fontWeight:500, color:'#fff', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{d.id}</span>
                  {d.dirty && <span style={{ color:'#f59e0b' }}>*</span>}
                </div>
              </div>
            ))}
          </>}

          {/* Cameras */}
          {cameras.length > 0 && <>
            <h2 style={{ fontSize:11, fontWeight:600, color:'#6b7280', textTransform:'uppercase', marginTop:12, marginBottom:8 }}>Cameras ({cameras.length})</h2>
            {cameras.map(c => (
              <div key={c.id} onClick={() => setSelEntity({ type: 'camera', id: c.id })}
                style={{ marginBottom:4, padding:6, borderRadius:4, fontSize:11, cursor:'pointer',
                  background: selEntity?.type==='camera'&&selEntity.id===c.id?'#374151':'rgba(31,41,55,0.5)',
                  outline: selEntity?.type==='camera'&&selEntity.id===c.id?`1px solid ${CAM_COLOR}`:'none' }}>
                <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                  <div style={{ width:10, height:10, borderRadius:2, flexShrink:0, background:CAM_COLOR }}/>
                  <span style={{ fontWeight:500, color:'#fff', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{c.id}</span>
                  {c.dirty && <span style={{ color:'#f59e0b' }}>*</span>}
                </div>
              </div>
            ))}
          </>}

          {/* Markers */}
          {markers.length > 0 && <>
            <h2 style={{ fontSize:11, fontWeight:600, color:'#6b7280', textTransform:'uppercase', marginTop:12, marginBottom:8 }}>ArUco Markers ({markers.length})</h2>
            {markers.map(m => (
              <div key={m.id} onClick={() => setSelEntity({ type: 'marker', id: m.id })}
                style={{ marginBottom:4, padding:6, borderRadius:4, fontSize:11, cursor:'pointer',
                  background: selEntity?.type==='marker'&&selEntity.id===m.id?'#374151':'rgba(31,41,55,0.5)',
                  outline: selEntity?.type==='marker'&&selEntity.id===m.id?`1px solid ${MARKER_COLOR}`:'none' }}>
                <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                  <div style={{ width:10, height:10, borderRadius:1, flexShrink:0, background:MARKER_COLOR }}/>
                  <span style={{ fontWeight:500, color:'#fff' }}>ID {m.id}</span>
                  {m.dirty && <span style={{ color:'#f59e0b' }}>*</span>}
                </div>
              </div>
            ))}
          </>}

          {/* Discovered — Unplaced */}
          {(() => {
            const unplaced = discovered.filter(d => !d.placed);
            if (!unplaced.length) return null;
            return <>
              <div style={{ display:'flex', alignItems:'center', gap:6, marginTop:12, marginBottom:8 }}>
                <h2 style={{ fontSize:11, fontWeight:600, color:'#6b7280', textTransform:'uppercase', margin:0 }}>
                  Discovered ({unplaced.length})
                </h2>
                <button onClick={refreshDiscovery}
                  style={{ padding:'1px 6px', fontSize:10, borderRadius:3, border:'1px solid #374151', background:'none', color:'#9ca3af', cursor:'pointer' }}>
                  ↻
                </button>
              </div>
              {unplaced.map(d => (
                <div key={d.device_id}
                  onClick={() => {
                    const cat = DEVICE_CATALOG[d.device_type];
                    setPendingBind(d);
                    if (cat) setPlaceDeviceType(d.device_type);
                    setMode('place-device');
                  }}
                  style={{ marginBottom:4, padding:6, borderRadius:4, fontSize:11, cursor:'pointer',
                    background: pendingBind?.device_id === d.device_id ? '#1e3a5f' : 'rgba(31,41,55,0.5)',
                    outline: pendingBind?.device_id === d.device_id ? '1px solid #3b82f6' : 'none' }}>
                  <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                    <div style={{ width:8, height:8, borderRadius:8, flexShrink:0,
                      background: d.online === true ? '#22c55e' : d.online === false ? '#ef4444' : '#6b7280' }}/>
                    <span style={{ fontWeight:500, color:'#d1d5db', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{d.device_id}</span>
                    {d.bridge && <span style={{ fontSize:9, padding:'1px 4px', borderRadius:3, background:'#1f2937', color:'#9ca3af' }}>{d.bridge}</span>}
                  </div>
                  {d.label && <div style={{ fontSize:10, color:'#6b7280', marginTop:2, paddingLeft:14 }}>{d.label}</div>}
                </div>
              ))}
            </>;
          })()}
        </div>

        {/* Property Panel */}
        {sel && (
          <div style={{ padding:12, borderTop:'1px solid #1f2937', maxHeight:240, overflowY:'auto' }}>
            <h3 style={{ fontSize:11, fontWeight:600, color:'#6b7280', textTransform:'uppercase', marginBottom:8 }}>Zone Properties</h3>
            <label style={sLabel}>ID</label>
            <input value={sel.id} onChange={e => chgId(sel.id, e.target.value)} style={sInput}/>
            <label style={sLabel}>Display Name</label>
            <input value={sel.displayName} onChange={e => renZone(sel.id, e.target.value)} style={sInput}/>
            <div style={{ display:'flex', justifyContent:'space-between', fontSize:12, color:'#6b7280', marginBottom:8 }}>
              <span>{sel.polygon.length} vertices</span><span>{area(sel.polygon).toFixed(1)} m²</span>
            </div>
            <button onClick={() => delZone(sel.id)}
              style={{ width:'100%', padding:'4px 8px', fontSize:12, borderRadius:4, border:'none', cursor:'pointer', background:'rgba(127,29,29,0.5)', color:'#f87171' }}>
              Delete Zone</button>
          </div>
        )}

        {selDev && (
          <div style={{ padding:12, borderTop:'1px solid #1f2937', maxHeight:300, overflowY:'auto' }}>
            <h3 style={{ fontSize:11, fontWeight:600, color:'#6b7280', textTransform:'uppercase', marginBottom:8 }}>Device Properties</h3>
            <label style={sLabel}>ID</label>
            {selDev.isNew ? (
              <input value={selDev.id} onChange={e => chgDeviceId(selDev.id, e.target.value)}
                style={{ ...sInput, borderColor:'#f59e0b' }} placeholder="e.g. env_01"/>
            ) : (
              <input value={selDev.id} readOnly style={{ ...sInput, opacity:0.6 }}/>
            )}
            {selDev.isNew && <p style={{ fontSize:10, color:'#fbbf24', margin:'-4px 0 6px' }}>Confirm device ID before saving</p>}
            <label style={sLabel}>Type</label>
            <select value={selDev.deviceType} onChange={e => {
              const cat = DEVICE_CATALOG[e.target.value] || DEVICE_CATALOG.sensor;
              setDevices(p => p.map(d => d.id === selDev.id ? {
                ...d, deviceType: e.target.value, channels: cat.channels, dirty: true,
                fovDeg: cat.directional ? (cat.defaultFov ?? d.fovDeg ?? 90) : null,
                detectionRangeM: cat.directional ? (cat.defaultRange ?? d.detectionRangeM ?? 5) : null,
                orientationDeg: cat.directional ? (d.orientationDeg ?? 0) : null,
              } : d));
            }} style={sInput}>
              {Object.entries(DEVICE_CATALOG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
            <label style={sLabel}>Zone</label>
            <input value={selDev.zone} readOnly style={{ ...sInput, opacity:0.6 }}/>
            <div style={{ display:'flex', gap:8, marginBottom:8 }}>
              <div style={{ flex:1 }}>
                <label style={sLabel}>X</label>
                <input type="number" step="0.1" value={selDev.x} onChange={e => setDevices(p => p.map(d => d.id === selDev.id ? { ...d, x: +e.target.value, dirty: true } : d))} style={sInput}/>
              </div>
              <div style={{ flex:1 }}>
                <label style={sLabel}>Y</label>
                <input type="number" step="0.1" value={selDev.y} onChange={e => setDevices(p => p.map(d => d.id === selDev.id ? { ...d, y: +e.target.value, dirty: true } : d))} style={sInput}/>
              </div>
            </div>
            {isDirectional(selDev.deviceType) && <>
              <div style={{ display:'flex', gap:8, marginBottom:8 }}>
                <div style={{ flex:1 }}>
                  <label style={sLabel}>Orient.</label>
                  <input type="number" step="5" value={selDev.orientationDeg ?? 0}
                    onChange={e => setDevices(p => p.map(d => d.id === selDev.id ? { ...d, orientationDeg: +e.target.value, dirty: true } : d))} style={sInput}/>
                </div>
                <div style={{ flex:1 }}>
                  <label style={sLabel}>FOV</label>
                  <input type="number" step="5" value={selDev.fovDeg ?? 90}
                    onChange={e => setDevices(p => p.map(d => d.id === selDev.id ? { ...d, fovDeg: +e.target.value, dirty: true } : d))} style={sInput}/>
                </div>
                <div style={{ flex:1 }}>
                  <label style={sLabel}>Range</label>
                  <input type="number" step="0.5" value={selDev.detectionRangeM ?? 5}
                    onChange={e => setDevices(p => p.map(d => d.id === selDev.id ? { ...d, detectionRangeM: +e.target.value, dirty: true } : d))} style={sInput}/>
                </div>
              </div>
            </>}
            <label style={sLabel}>Channels</label>
            <input value={selDev.channels.join(', ')} readOnly style={{ ...sInput, opacity:0.6 }}/>
            <button onClick={() => delDevice(selDev.id)}
              style={{ width:'100%', padding:'4px 8px', fontSize:12, borderRadius:4, border:'none', cursor:'pointer', background:'rgba(127,29,29,0.5)', color:'#f87171' }}>
              Delete Device</button>
          </div>
        )}

        {selCam && (
          <div style={{ padding:12, borderTop:'1px solid #1f2937', maxHeight:300, overflowY:'auto' }}>
            <h3 style={{ fontSize:11, fontWeight:600, color:'#6b7280', textTransform:'uppercase', marginBottom:8 }}>Camera Properties</h3>
            <label style={sLabel}>ID</label>
            <input value={selCam.id} readOnly style={{ ...sInput, opacity:0.6 }}/>
            <label style={sLabel}>Zone</label>
            <input value={selCam.zone} readOnly style={{ ...sInput, opacity:0.6 }}/>
            <div style={{ display:'flex', gap:8, marginBottom:8 }}>
              <div style={{ flex:1 }}>
                <label style={sLabel}>X</label>
                <input type="number" step="0.1" value={selCam.x} onChange={e => setCameras(p => p.map(c => c.id === selCam.id ? { ...c, x: +e.target.value, dirty: true } : c))} style={sInput}/>
              </div>
              <div style={{ flex:1 }}>
                <label style={sLabel}>Y</label>
                <input type="number" step="0.1" value={selCam.y} onChange={e => setCameras(p => p.map(c => c.id === selCam.id ? { ...c, y: +e.target.value, dirty: true } : c))} style={sInput}/>
              </div>
              <div style={{ flex:1 }}>
                <label style={sLabel}>Z (h)</label>
                <input type="number" step="0.1" value={selCam.z ?? 2.5} onChange={e => setCameras(p => p.map(c => c.id === selCam.id ? { ...c, z: +e.target.value, dirty: true } : c))} style={sInput}/>
              </div>
            </div>
            <div style={{ display:'flex', gap:8, marginBottom:8 }}>
              <div style={{ flex:1 }}>
                <label style={sLabel}>Orient.</label>
                <input type="number" step="5" value={selCam.orientationDeg}
                  onChange={e => setCameras(p => p.map(c => c.id === selCam.id ? { ...c, orientationDeg: +e.target.value, dirty: true } : c))} style={sInput}/>
              </div>
              <div style={{ flex:1 }}>
                <label style={sLabel}>FOV</label>
                <input type="number" step="5" value={selCam.fovDeg}
                  onChange={e => setCameras(p => p.map(c => c.id === selCam.id ? { ...c, fovDeg: +e.target.value, dirty: true } : c))} style={sInput}/>
              </div>
            </div>
            <label style={sLabel}>Resolution</label>
            <input value={selCam.resolution.join(' x ')} readOnly style={{ ...sInput, opacity:0.6 }}/>
            <button onClick={() => delCamera(selCam.id)}
              style={{ width:'100%', padding:'4px 8px', fontSize:12, borderRadius:4, border:'none', cursor:'pointer', background:'rgba(127,29,29,0.5)', color:'#f87171' }}>
              Delete Camera</button>
          </div>
        )}

        {selMkr && (
          <div style={{ padding:12, borderTop:'1px solid #1f2937', maxHeight:240, overflowY:'auto' }}>
            <h3 style={{ fontSize:11, fontWeight:600, color:'#6b7280', textTransform:'uppercase', marginBottom:8 }}>ArUco Marker</h3>
            <label style={sLabel}>ID</label>
            <input value={selMkr.id} onChange={e => {
              const nid = e.target.value;
              if (!/^\d+$/.test(nid)) return;
              setMarkers(p => p.map(m => m.id === selMkr.id ? { ...m, id: nid, dirty: true } : m));
              setSelEntity({ type: 'marker', id: nid });
            }} style={sInput}/>
            <label style={sLabel}>Center</label>
            {(() => { const c = markerCenter(selMkr.corners); return (
              <input value={`${c.x.toFixed(2)}, ${c.y.toFixed(2)}`} readOnly style={{ ...sInput, opacity:0.6 }}/>
            ); })()}
            <label style={sLabel}>Corners (read-only)</label>
            {selMkr.corners.map((c, i) => (
              <div key={i} style={{ fontSize:11, color:'#6b7280', marginBottom:2 }}>
                [{c[0].toFixed(2)}, {c[1].toFixed(2)}]
              </div>
            ))}
            <button onClick={() => delMarker(selMkr.id)} style={{ width:'100%', marginTop:8, padding:'4px 8px', fontSize:12, borderRadius:4, border:'none', cursor:'pointer', background:'rgba(127,29,29,0.5)', color:'#f87171' }}>
              Delete Marker</button>
          </div>
        )}

        {/* Status bar */}
        <div style={{ padding:'8px 12px', borderTop:'1px solid #1f2937', fontSize:12, color:'#6b7280', display:'flex', justifyContent:'space-between' }}>
          <span>{cursor ? `${cursor.x.toFixed(2)}, ${cursor.y.toFixed(2)} m` : ''}</span>
          <span>{fp.building.width_m}x{fp.building.height_m}m</span>
        </div>
      </div>

      {/* SVG Canvas */}
      <div style={{ flex:1, overflow:'hidden' }}>
        <svg ref={svgRef} width="100%" height="100%"
          viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
          preserveAspectRatio="xMidYMid meet"
          onMouseMove={onMove} onMouseDown={onDown} onMouseUp={onUp} onMouseLeave={onUp}
          onClick={onClick} onWheel={onWheel} onContextMenu={e => e.preventDefault()}
          style={{ cursor: isPlacing||mode==='draw'?'crosshair':panning?'grabbing':'grab', display:'block' }}>

          <rect data-bg="1" x={vb.x} y={vb.y} width={vb.w} height={vb.h} fill="#0a0a0f"/>

          {/* Grid */}
          {Array.from({length: Math.ceil(fp.building.width_m)+1}, (_,i) =>
            <line key={`v${i}`} x1={i} y1={0} x2={i} y2={fy} stroke="#1a1a2e" strokeWidth={i%5===0?0.04:0.02}/>
          )}
          {Array.from({length: Math.ceil(fp.building.height_m)+1}, (_,i) =>
            <line key={`h${i}`} x1={0} y1={i} x2={fp.building.width_m} y2={i} stroke="#1a1a2e" strokeWidth={i%5===0?0.04:0.02}/>
          )}

          <rect x={0} y={0} width={fp.building.width_m} height={fy} fill="none" stroke="#334155" strokeWidth={0.06}/>

          {/* Zones */}
          {layers.zones && zones.map(z => {
            if (z.polygon.length < 3) return null;
            const cx = z.polygon.reduce((s,p) => s+p.x, 0) / z.polygon.length;
            const cy = z.polygon.reduce((s,p) => s+p.y, 0) / z.polygon.length;
            const isSel = selEntity?.type==='zone'&&selEntity.id===z.id;
            return (
              <g key={z.id}>
                <polygon points={toSvg(z.polygon, fy)} fill={z.color} fillOpacity={isSel?0.35:0.2}
                  stroke={z.color} strokeWidth={isSel?0.08:0.04} strokeOpacity={0.8}
                  onClick={e => { if (mode==='select') { e.stopPropagation(); setSelEntity({type:'zone',id:z.id}); }}}
                  style={{ cursor: mode==='select'?'pointer':undefined }}/>
                <text x={cx} y={fy-cy} textAnchor="middle" dominantBaseline="central"
                  fill={z.color} fontSize={vb.w*0.012} fontWeight="600" pointerEvents="none">
                  {z.displayName}</text>
                {isSel && mode==='select' && z.polygon.map((p,vi) =>
                  <circle key={vi} cx={p.x} cy={fy-p.y} r={vb.w*0.006}
                    fill="white" stroke={z.color} strokeWidth={0.04} style={{cursor:'move'}}
                    onMouseDown={e => { e.stopPropagation(); setEditVtx({zid:z.id, vi}); }}
                    onDoubleClick={e => { e.stopPropagation(); delVtx(z.id, vi); }}/>
                )}
              </g>
            );
          })}

          {/* Walls */}
          {fp.walls.map((w,i) => w.closed
            ? <polygon key={`w${i}`} points={toSvg(w.points, fy)} fill="#475569" stroke="#64748b" strokeWidth={0.03}/>
            : <polyline key={`w${i}`} points={toSvg(w.points, fy)} fill="none" stroke="#64748b" strokeWidth={0.06}/>
          )}

          {/* Columns */}
          {fp.columns.map((c,i) =>
            <polygon key={`c${i}`} points={toSvg(c.points, fy)} fill="#991b1b" stroke="#b91c1c" strokeWidth={0.03}/>
          )}

          {/* Device FOV cones (behind icons) */}
          {layers.cones && layers.devices && devices.map(d => {
            if (!isDirectional(d.deviceType) || d.fovDeg == null || d.detectionRangeM == null || d.orientationDeg == null) return null;
            const col = deviceColor(d.deviceType);
            return (
              <path key={`dc-${d.id}`} d={conePath(d.x, d.y, d.orientationDeg, d.fovDeg, d.detectionRangeM, fy)}
                fill={col} fillOpacity={0.12} stroke={col} strokeOpacity={0.4} strokeWidth={0.03} pointerEvents="none"/>
            );
          })}

          {/* Camera FOV cones */}
          {layers.cones && layers.cameras && cameras.map(c => (
            <path key={`cc-${c.id}`} d={conePath(c.x, c.y, c.orientationDeg, c.fovDeg, 8, fy)}
              fill={CAM_COLOR} fillOpacity={0.1} stroke={CAM_COLOR} strokeOpacity={0.35} strokeWidth={0.03} pointerEvents="none"/>
          ))}

          {/* Device icons */}
          {layers.devices && devices.map(d => {
            const col = deviceColor(d.deviceType);
            const isSel = selEntity?.type==='device'&&selEntity.id===d.id;
            const r = vb.w * 0.005;
            return (
              <g key={`d-${d.id}`}>
                <circle cx={d.x} cy={fy-d.y} r={isSel?r*1.4:r} fill={col} fillOpacity={0.9}
                  stroke={isSel?'#fff':col} strokeWidth={isSel?0.06:0.03}
                  style={{ cursor:'pointer' }}
                  onClick={e => { e.stopPropagation(); setSelEntity({type:'device',id:d.id}); }}
                  onMouseDown={e => { if (mode==='select') { e.stopPropagation(); setDragEntity({type:'device',id:d.id}); }}}/>
                <text x={d.x} y={fy-d.y-r*2} textAnchor="middle" fill={col} fontSize={vb.w*0.008} fontWeight="500" pointerEvents="none">
                  {d.id.length > 12 ? d.id.slice(-10) : d.id}</text>
                {/* Rotation handle for directional devices */}
                {isSel && mode==='select' && isDirectional(d.deviceType) && d.orientationDeg != null && (() => {
                  const ha = vb.w * 0.02;
                  const rad = -(d.orientationDeg) * Math.PI / 180;
                  const hx = d.x + ha * Math.cos(rad);
                  const hy = (fy - d.y) + ha * Math.sin(rad);
                  return (
                    <g>
                      <line x1={d.x} y1={fy-d.y} x2={hx} y2={hy} stroke="#fff" strokeWidth={0.03} strokeDasharray="0.06 0.04" pointerEvents="none"/>
                      <circle cx={hx} cy={hy} r={vb.w*0.004} fill="#fff" stroke={col} strokeWidth={0.03} style={{ cursor:'crosshair' }}
                        onMouseDown={e => { e.stopPropagation(); setRotateEntity({type:'device',id:d.id}); }}/>
                    </g>
                  );
                })()}
              </g>
            );
          })}

          {/* Camera icons */}
          {layers.cameras && cameras.map(c => {
            const isSel = selEntity?.type==='camera'&&selEntity.id===c.id;
            const r = vb.w * 0.006;
            return (
              <g key={`c-${c.id}`}>
                {/* Camera body (small rect) */}
                <rect x={c.x - r} y={fy - c.y - r*0.7} width={r*2} height={r*1.4} rx={r*0.2}
                  fill={CAM_COLOR} fillOpacity={0.9} stroke={isSel?'#fff':CAM_COLOR} strokeWidth={isSel?0.06:0.03}
                  style={{ cursor:'pointer' }}
                  onClick={e => { e.stopPropagation(); setSelEntity({type:'camera',id:c.id}); }}
                  onMouseDown={e => { if (mode==='select') { e.stopPropagation(); setDragEntity({type:'camera',id:c.id}); }}}/>
                <text x={c.x} y={fy-c.y-r*1.6} textAnchor="middle" fill={CAM_COLOR} fontSize={vb.w*0.008} fontWeight="500" pointerEvents="none">
                  {c.id.length > 16 ? c.id.slice(-12) : c.id}</text>
                {/* Rotation handle */}
                {isSel && mode==='select' && (() => {
                  const ha = vb.w * 0.025;
                  const rad = -(c.orientationDeg) * Math.PI / 180;
                  const hx = c.x + ha * Math.cos(rad);
                  const hy = (fy - c.y) + ha * Math.sin(rad);
                  return (
                    <g>
                      <line x1={c.x} y1={fy-c.y} x2={hx} y2={hy} stroke="#fff" strokeWidth={0.03} strokeDasharray="0.06 0.04" pointerEvents="none"/>
                      <circle cx={hx} cy={hy} r={vb.w*0.004} fill="#fff" stroke={CAM_COLOR} strokeWidth={0.03} style={{ cursor:'crosshair' }}
                        onMouseDown={e => { e.stopPropagation(); setRotateEntity({type:'camera',id:c.id}); }}/>
                    </g>
                  );
                })()}
              </g>
            );
          })}

          {/* ArUco Markers */}
          {layers.markers && markers.map(m => {
            const c = markerCenter(m.corners);
            const isSel = selEntity?.type==='marker'&&selEntity.id===m.id;
            const sz = 0.3;
            return (
              <g key={`m-${m.id}`}>
                <rect x={c.x - sz/2} y={fy - c.y - sz/2} width={sz} height={sz}
                  fill="#374151" fillOpacity={0.8} stroke={isSel?'#fff':MARKER_COLOR} strokeWidth={isSel?0.06:0.03}
                  style={{ cursor:'pointer' }}
                  onClick={e => { e.stopPropagation(); setSelEntity({type:'marker',id:m.id}); }}
                  onMouseDown={e => { if (mode==='select') { e.stopPropagation(); setDragEntity({type:'marker',id:m.id}); }}}/>
                <text x={c.x} y={fy - c.y + 0.04} textAnchor="middle" dominantBaseline="central"
                  fill="#d1d5db" fontSize={vb.w*0.007} fontWeight="700" pointerEvents="none">
                  {m.id}</text>
                {/* Show corners when selected */}
                {isSel && m.corners.map((corner, ci) =>
                  <circle key={ci} cx={corner[0]} cy={fy - corner[1]} r={vb.w*0.003}
                    fill="#fbbf24" stroke="#fff" strokeWidth={0.02} pointerEvents="none"/>
                )}
              </g>
            );
          })}

          {/* Drawing (zone) */}
          {drawing.length > 0 && <g>
            <polyline points={toSvg(drawing, fy) + (cursor ? ` ${cursor.x},${fy-cursor.y}` : '')}
              fill="none" stroke="#22c55e" strokeWidth={0.06} strokeDasharray="0.15 0.08"/>
            {drawing.length >= 3 && cursor &&
              <line x1={cursor.x} y1={fy-cursor.y} x2={drawing[0].x} y2={fy-drawing[0].y}
                stroke="#22c55e" strokeWidth={0.03} strokeDasharray="0.1 0.06" opacity={0.4}/>
            }
            {drawing.map((p,i) =>
              <circle key={i} cx={p.x} cy={fy-p.y}
                r={i===0 && drawing.length>=3 ? vb.w*0.009 : vb.w*0.005}
                fill={i===0 && drawing.length>=3 ? '#22c55e' : 'white'}
                stroke="#22c55e" strokeWidth={0.04}/>
            )}
          </g>}

          {/* Placement cursor preview */}
          {isPlacing && cursor && (
            <g pointerEvents="none">
              {mode === 'place-device' && (
                <circle cx={cursor.x} cy={fy-cursor.y} r={vb.w*0.005}
                  fill={DEVICE_CATALOG[placeDeviceType]?.color ?? '#9ca3af'} fillOpacity={0.6}
                  stroke="#fff" strokeWidth={0.03} strokeDasharray="0.06 0.04"/>
              )}
              {mode === 'place-camera' && (
                <rect x={cursor.x - vb.w*0.006} y={fy-cursor.y - vb.w*0.004} width={vb.w*0.012} height={vb.w*0.008}
                  fill={CAM_COLOR} fillOpacity={0.6} stroke="#fff" strokeWidth={0.03} strokeDasharray="0.06 0.04"/>
              )}
              {mode === 'place-marker' && (
                <rect x={cursor.x - 0.15} y={fy-cursor.y - 0.15} width={0.3} height={0.3}
                  fill="#374151" fillOpacity={0.6} stroke="#fff" strokeWidth={0.03} strokeDasharray="0.06 0.04"/>
              )}
            </g>
          )}

          {/* Scale */}
          <line x1={vb.x+vb.w*0.03} y1={vb.y+vb.h*0.95} x2={vb.x+vb.w*0.03+5} y2={vb.y+vb.h*0.95} stroke="#94a3b8" strokeWidth={0.05}/>
          <text x={vb.x+vb.w*0.03+2.5} y={vb.y+vb.h*0.93} textAnchor="middle" fill="#94a3b8" fontSize={vb.w*0.012}>5m</text>
        </svg>
      </div>
    </div>
  );
}
