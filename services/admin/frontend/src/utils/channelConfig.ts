// ── Channel metadata ─────────────────────────────────────────────────

export const CHANNEL_CONFIG: Record<string, { label: string; unit: string; color: string }> = {
  temperature: { label: 'Temperature', unit: '\u00b0C', color: '#F44336' },
  humidity: { label: 'Humidity', unit: '%', color: '#2196F3' },
  co2: { label: 'CO2', unit: 'ppm', color: '#FF9800' },
  pressure: { label: 'Pressure', unit: 'hPa', color: '#9C27B0' },
  gas_resistance: { label: 'Gas Resistance', unit: 'k\u03a9', color: '#4CAF50' },
  gas: { label: 'Gas', unit: 'k\u03a9', color: '#66BB6A' },
  illuminance: { label: 'Illuminance', unit: 'lux', color: '#FFD700' },
  motion: { label: 'Motion', unit: '', color: '#03A9F4' },
  presence: { label: 'Presence', unit: '', color: '#7C4DFF' },
  vibration: { label: 'Vibration', unit: '', color: '#FF5722' },
  water_leak: { label: 'Water Leak', unit: '', color: '#00BCD4' },
  door: { label: 'Door', unit: '', color: '#607D8B' },
  contact: { label: 'Contact', unit: '', color: '#78909C' },
  soil_moisture: { label: 'Soil Moisture', unit: '%', color: '#8D6E63' },
  soil_temperature: { label: 'Soil Temp', unit: '\u00b0C', color: '#A1887F' },
};

// ── Binary channels (display Active/Inactive instead of numeric value) ─

export const BINARY_CHANNELS = new Set([
  'motion', 'presence', 'vibration', 'water_leak', 'door', 'contact',
]);

// ── Sensor category classification ──────────────────────────────────

export type SensorCategory =
  | 'environment'
  | 'light'
  | 'motion_presence'
  | 'binary'
  | 'agriculture'
  | 'unknown';

export const SENSOR_CATEGORIES: Record<SensorCategory, { label: string; color: string }> = {
  environment: { label: 'Environment', color: '#2196F3' },
  agriculture: { label: 'Agriculture', color: '#8D6E63' },
  light: { label: 'Light', color: '#FFD700' },
  motion_presence: { label: 'Motion / Presence', color: '#7C4DFF' },
  binary: { label: 'Binary Sensors', color: '#00BCD4' },
  unknown: { label: 'Other', color: '#9E9E9E' },
};

export const CATEGORY_ORDER: SensorCategory[] = [
  'environment',
  'agriculture',
  'light',
  'motion_presence',
  'binary',
  'unknown',
];

/**
 * Classify a device into a sensor category based on its spatial.yaml `type`
 * field (comma-separated) and declared channels.
 */
export function classifyDevice(spatialType: string, channels: string[]): SensorCategory {
  const types = spatialType.toLowerCase().split(',').map(t => t.trim());

  // Agriculture: soil sensors
  if (types.some(t => t === 'soil')) return 'agriculture';

  // Binary: water_leak, door, contact
  if (types.some(t => ['water_leak', 'door', 'contact'].includes(t))) return 'binary';

  // Pure motion/presence/vibration (not combined with temp_humidity or illuminance)
  const isMotionType = types.some(t => ['motion', 'presence', 'vibration'].includes(t));
  const hasEnvType = types.some(t => ['temp_humidity', 'illuminance', 'generic_sensor', 'bme680', 'mhz19c'].includes(t));
  if (isMotionType && !hasEnvType) return 'motion_presence';

  // Pure illuminance (not combined with other sensor types)
  if (types.includes('illuminance') && !types.includes('temp_humidity') && !types.includes('presence')) {
    return 'light';
  }

  // Environment: temp_humidity, bme680, mhz19c, generic_sensor, or multi-sensor with env channels
  if (types.some(t => ['temp_humidity', 'bme680', 'mhz19c', 'generic_sensor'].includes(t))) {
    return 'environment';
  }

  // Fallback: classify by channels
  if (channels.some(c => ['temperature', 'humidity', 'co2', 'pressure', 'gas', 'gas_resistance'].includes(c))) {
    return 'environment';
  }
  if (channels.some(c => c === 'illuminance')) return 'light';
  if (channels.some(c => ['motion', 'presence', 'vibration'].includes(c))) return 'motion_presence';
  if (channels.some(c => ['water_leak', 'door', 'contact'].includes(c))) return 'binary';

  return 'unknown';
}

// ── Window / period option constants ────────────────────────────────

export const WINDOW_OPTIONS = [
  { value: 'raw', label: 'Raw' },
  { value: '1h', label: '1 Hour' },
  { value: '1d', label: '1 Day' },
] as const;

export const HEATMAP_PERIOD_OPTIONS = [
  { value: 'hour', label: 'Hour' },
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
] as const;

export const POWER_MODE_LABELS: Record<string, string> = {
  ALWAYS_ON: 'Always On',
  DEEP_SLEEP: 'Deep Sleep',
  ULTRA_LOW: 'Ultra Low',
  LIGHT_SLEEP: 'Light Sleep',
};

// ── Helper functions ────────────────────────────────────────────────

export function getChannelMeta(channel: string) {
  return CHANNEL_CONFIG[channel] ?? { label: channel, unit: '', color: '#9E9E9E' };
}

export function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

export function formatFullTimestamp(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function timeAgo(ts: string | null): string {
  if (!ts) return 'N/A';
  const diff = Date.now() - new Date(ts).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ago`;
}

export function getBatteryColor(pct: number): string {
  if (pct > 60) return '#4CAF50';
  if (pct > 30) return '#FF9800';
  return '#F44336';
}

export function isOnline(lastHeartbeat: string | null): boolean {
  if (!lastHeartbeat) return false;
  const diff = Date.now() - new Date(lastHeartbeat).getTime();
  return diff < 5 * 60 * 1000; // 5 minutes
}

export function heatmapCellColor(count: number, maxCount: number): string {
  if (maxCount <= 0) return 'rgba(59,130,246,0.05)';
  const ratio = Math.min(count / maxCount, 1);
  const opacity = 0.05 + ratio * 0.95;
  return `rgba(59,130,246,${opacity.toFixed(2)})`;
}
