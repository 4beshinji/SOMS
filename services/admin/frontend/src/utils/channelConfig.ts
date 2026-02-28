// ── Channel metadata ─────────────────────────────────────────────────

export const CHANNEL_CONFIG: Record<string, { label: string; unit: string; color: string }> = {
  temperature: { label: 'Temperature', unit: '\u00b0C', color: '#F44336' },
  humidity: { label: 'Humidity', unit: '%', color: '#2196F3' },
  co2: { label: 'CO2', unit: 'ppm', color: '#FF9800' },
  pressure: { label: 'Pressure', unit: 'hPa', color: '#9C27B0' },
  gas_resistance: { label: 'Gas Resistance', unit: 'k\u03a9', color: '#4CAF50' },
  illuminance: { label: 'Illuminance', unit: 'lux', color: '#FFD700' },
  motion: { label: 'Motion', unit: '', color: '#03A9F4' },
};

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
