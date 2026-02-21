import { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
  Legend,
  Bar,
  BarChart,
} from 'recharts';
import {
  useSensorTimeSeries,
  useLLMActivity,
  useLLMTimeline,
  useZoneOverview,
  useSensorLatest,
  useEvents,
  useDeviceStatus,
  useHeatmap,
  type ZoneSnapshot,
  type TimeSeriesPoint,
  type EventItem,
  type LLMTimelinePoint,
  type DeviceStatus,
  type HeatmapData,
} from '../hooks/useAnalytics';

// ── Channel metadata ─────────────────────────────────────────────────

const CHANNEL_CONFIG: Record<string, { label: string; unit: string; color: string }> = {
  temperature: { label: 'Temperature', unit: '\u00b0C', color: '#F44336' },
  humidity: { label: 'Humidity', unit: '%', color: '#2196F3' },
  co2: { label: 'CO2', unit: 'ppm', color: '#FF9800' },
  pressure: { label: 'Pressure', unit: 'hPa', color: '#9C27B0' },
  gas_resistance: { label: 'Gas Resistance', unit: 'k\u03a9', color: '#4CAF50' },
  illuminance: { label: 'Illuminance', unit: 'lux', color: '#FFD700' },
  motion: { label: 'Motion', unit: '', color: '#03A9F4' },
};

const WINDOW_OPTIONS = [
  { value: 'raw', label: 'Raw' },
  { value: '1h', label: '1 Hour' },
  { value: '1d', label: '1 Day' },
];

function getChannelMeta(channel: string) {
  return CHANNEL_CONFIG[channel] ?? { label: channel, unit: '', color: '#9E9E9E' };
}

// ── Helpers ──────────────────────────────────────────────────────────

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });
}

function formatFullTimestamp(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString('ja-JP', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function timeAgo(ts: string | null): string {
  if (!ts) return 'N/A';
  const diff = Date.now() - new Date(ts).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ago`;
}

// ── Zone Overview Section ────────────────────────────────────────────

function ZoneOverviewSection() {
  const { data: zones, isLoading, isError } = useZoneOverview();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-[var(--primary-500)] border-t-transparent" />
      </div>
    );
  }

  if (isError || !zones) {
    return (
      <div className="text-center py-8 text-[var(--gray-500)]">
        Failed to load zone data. The sensor service may be unavailable.
      </div>
    );
  }

  if (zones.length === 0) {
    return (
      <div className="text-center py-8 text-[var(--gray-500)]">
        No zone data available yet. Sensors will appear once they start reporting.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {zones.map((zone: ZoneSnapshot, i: number) => (
        <motion.div
          key={zone.zone}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.05 }}
          className="bg-white rounded-xl elevation-2 p-5"
        >
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-semibold text-[var(--gray-900)] text-lg capitalize">
              {zone.zone}
            </h4>
            <span className="text-xs text-[var(--gray-400)]">
              {timeAgo(zone.last_update)}
            </span>
          </div>

          {Object.keys(zone.channels).length === 0 ? (
            <p className="text-sm text-[var(--gray-400)]">No readings</p>
          ) : (
            <div className="space-y-2">
              {Object.entries(zone.channels).map(([ch, val]) => {
                const meta = getChannelMeta(ch);
                return (
                  <div key={ch} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ backgroundColor: meta.color }}
                      />
                      <span className="text-sm text-[var(--gray-600)]">{meta.label}</span>
                    </div>
                    <span className="text-sm font-medium text-[var(--gray-900)] font-[var(--font-mono)]">
                      {typeof val === 'number' ? val.toFixed(1) : val}
                      {meta.unit && (
                        <span className="text-[var(--gray-400)] ml-0.5 text-xs">{meta.unit}</span>
                      )}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          <div className="mt-3 pt-3 border-t border-[var(--gray-100)]">
            <span className="text-xs text-[var(--gray-400)]">
              {zone.event_count} events recorded
            </span>
          </div>
        </motion.div>
      ))}
    </div>
  );
}

// ── Time Series Chart Section ────────────────────────────────────────

function TimeSeriesSection() {
  const { data: zones } = useZoneOverview();

  // Derive available zone names and channels
  const availableZones = useMemo(() => {
    if (!zones || zones.length === 0) return [];
    return zones.map((z: ZoneSnapshot) => z.zone);
  }, [zones]);

  const [selectedZone, setSelectedZone] = useState<string>('');
  const [selectedChannel, setSelectedChannel] = useState<string>('');
  const [selectedWindow, setSelectedWindow] = useState<string>('1h');

  // Auto-select first zone
  const zone = selectedZone || availableZones[0] || '';

  // Get available channels for the selected zone
  const availableChannels = useMemo(() => {
    if (!zones) return [];
    const z = zones.find((s: ZoneSnapshot) => s.zone === zone);
    return z ? Object.keys(z.channels) : [];
  }, [zones, zone]);

  // Auto-select first channel
  const channel = selectedChannel && availableChannels.includes(selectedChannel)
    ? selectedChannel
    : availableChannels[0] || '';

  const {
    data: timeSeries,
    isLoading,
    isError,
  } = useSensorTimeSeries(
    zone || undefined,
    channel || undefined,
    selectedWindow,
  );

  const meta = getChannelMeta(channel);

  const chartData = useMemo(() => {
    if (!timeSeries?.points) return [];
    return timeSeries.points.map((p: TimeSeriesPoint) => ({
      time: formatTimestamp(p.timestamp),
      fullTime: formatFullTimestamp(p.timestamp),
      avg: Number(p.avg.toFixed(2)),
      max: Number(p.max.toFixed(2)),
      min: Number(p.min.toFixed(2)),
      count: p.count,
    }));
  }, [timeSeries]);

  return (
    <div className="bg-white rounded-xl elevation-2 p-6">
      {/* Controls */}
      <div className="flex flex-wrap gap-3 mb-6">
        <div>
          <label className="block text-xs font-medium text-[var(--gray-500)] mb-1">
            Zone
          </label>
          <select
            value={zone}
            onChange={(e) => {
              setSelectedZone(e.target.value);
              setSelectedChannel(''); // reset channel on zone change
            }}
            className="px-3 py-1.5 rounded-lg border border-[var(--gray-300)] bg-white text-sm text-[var(--gray-700)] focus:outline-none focus:border-[var(--primary-500)]"
          >
            {availableZones.length === 0 && (
              <option value="">No zones</option>
            )}
            {availableZones.map((z: string) => (
              <option key={z} value={z}>
                {z}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-[var(--gray-500)] mb-1">
            Channel
          </label>
          <select
            value={channel}
            onChange={(e) => setSelectedChannel(e.target.value)}
            className="px-3 py-1.5 rounded-lg border border-[var(--gray-300)] bg-white text-sm text-[var(--gray-700)] focus:outline-none focus:border-[var(--primary-500)]"
          >
            {availableChannels.length === 0 && (
              <option value="">No channels</option>
            )}
            {availableChannels.map((c: string) => (
              <option key={c} value={c}>
                {getChannelMeta(c).label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-[var(--gray-500)] mb-1">
            Window
          </label>
          <div className="flex gap-1 bg-[var(--gray-100)] rounded-lg p-0.5">
            {WINDOW_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setSelectedWindow(opt.value)}
                className={`px-3 py-1.5 text-xs rounded-md transition-all cursor-pointer ${
                  selectedWindow === opt.value
                    ? 'bg-white text-[var(--primary-600)] shadow-sm font-medium'
                    : 'text-[var(--gray-500)] hover:text-[var(--gray-700)]'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Chart */}
      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-[var(--primary-500)] border-t-transparent" />
        </div>
      ) : isError ? (
        <div className="flex items-center justify-center h-64 text-[var(--gray-500)]">
          Failed to load time series data.
        </div>
      ) : chartData.length === 0 ? (
        <div className="flex items-center justify-center h-64 text-[var(--gray-500)]">
          No data available for the selected zone/channel.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
            <defs>
              <linearGradient id="colorAvg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={meta.color} stopOpacity={0.2} />
                <stop offset="95%" stopColor={meta.color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--gray-200)" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 11, fill: 'var(--gray-500)' }}
              tickLine={false}
              axisLine={{ stroke: 'var(--gray-200)' }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: 'var(--gray-500)' }}
              tickLine={false}
              axisLine={{ stroke: 'var(--gray-200)' }}
              unit={meta.unit ? ` ${meta.unit}` : undefined}
              width={70}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'white',
                border: '1px solid var(--gray-200)',
                borderRadius: '8px',
                fontSize: '12px',
                boxShadow: 'var(--shadow-md)',
              }}
              labelFormatter={(_label, payload) => {
                if (payload && payload.length > 0) {
                  return (payload[0].payload as { fullTime: string }).fullTime;
                }
                return _label;
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: '12px' }}
            />
            <Area
              type="monotone"
              dataKey="avg"
              stroke={meta.color}
              strokeWidth={2}
              fill="url(#colorAvg)"
              name={`Avg ${meta.unit}`}
              dot={false}
              activeDot={{ r: 4, fill: meta.color }}
            />
            <Line
              type="monotone"
              dataKey="max"
              stroke={meta.color}
              strokeWidth={1}
              strokeDasharray="4 4"
              strokeOpacity={0.5}
              name={`Max ${meta.unit}`}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="min"
              stroke={meta.color}
              strokeWidth={1}
              strokeDasharray="4 4"
              strokeOpacity={0.5}
              name={`Min ${meta.unit}`}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// ── Latest Readings Section ──────────────────────────────────────────

function LatestReadingsSection() {
  const { data: readings, isLoading } = useSensorLatest();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-6">
        <div className="inline-block animate-spin rounded-full h-6 w-6 border-4 border-[var(--primary-500)] border-t-transparent" />
      </div>
    );
  }

  if (!readings || readings.length === 0) {
    return (
      <div className="text-sm text-[var(--gray-400)] text-center py-4">
        No recent sensor readings.
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl elevation-2 overflow-hidden">
      <div className="px-5 py-4 border-b border-[var(--gray-200)]">
        <h3 className="font-semibold text-[var(--gray-900)]">Latest Readings</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--gray-50)]">
              <th className="text-left px-5 py-2.5 text-xs font-medium text-[var(--gray-500)] uppercase tracking-wider">
                Zone
              </th>
              <th className="text-left px-5 py-2.5 text-xs font-medium text-[var(--gray-500)] uppercase tracking-wider">
                Channel
              </th>
              <th className="text-right px-5 py-2.5 text-xs font-medium text-[var(--gray-500)] uppercase tracking-wider">
                Value
              </th>
              <th className="text-left px-5 py-2.5 text-xs font-medium text-[var(--gray-500)] uppercase tracking-wider">
                Device
              </th>
              <th className="text-right px-5 py-2.5 text-xs font-medium text-[var(--gray-500)] uppercase tracking-wider">
                Time
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--gray-100)]">
            {readings.map((r, i) => {
              const meta = getChannelMeta(r.channel);
              return (
                <tr key={`${r.zone}-${r.channel}-${i}`} className="hover:bg-[var(--gray-50)] transition-colors">
                  <td className="px-5 py-2.5 text-[var(--gray-700)] capitalize">{r.zone}</td>
                  <td className="px-5 py-2.5">
                    <span className="flex items-center gap-1.5">
                      <span
                        className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ backgroundColor: meta.color }}
                      />
                      <span className="text-[var(--gray-700)]">{meta.label}</span>
                    </span>
                  </td>
                  <td className="px-5 py-2.5 text-right font-medium text-[var(--gray-900)]">
                    {r.value.toFixed(1)}
                    {meta.unit && (
                      <span className="text-[var(--gray-400)] ml-0.5 text-xs">{meta.unit}</span>
                    )}
                  </td>
                  <td className="px-5 py-2.5 text-[var(--gray-500)] text-xs font-mono">
                    {r.device_id ?? '-'}
                  </td>
                  <td className="px-5 py-2.5 text-right text-[var(--gray-400)] text-xs">
                    {formatFullTimestamp(r.timestamp)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── LLM Timeline Section ─────────────────────────────────────────────

function LLMTimelineSection() {
  const [hours, setHours] = useState(24);
  const { data: timeline, isLoading } = useLLMTimeline(hours);

  const hoursOptions = [
    { value: 6, label: '6h' },
    { value: 24, label: '24h' },
    { value: 168, label: '7d' },
  ];

  const chartData = useMemo(() => {
    if (!timeline?.points) return [];
    return timeline.points.map((p: LLMTimelinePoint) => ({
      time: formatTimestamp(p.timestamp),
      fullTime: formatFullTimestamp(p.timestamp),
      cycles: p.cycles,
      tool_calls: p.tool_calls,
      avg_duration: Number(p.avg_duration_sec.toFixed(1)),
    }));
  }, [timeline]);

  return (
    <div className="bg-white rounded-xl elevation-2 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-[var(--gray-900)]">Brain Activity Timeline</h3>
        <div className="flex gap-1 bg-[var(--gray-100)] rounded-lg p-0.5">
          {hoursOptions.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setHours(opt.value)}
              className={`px-3 py-1 text-xs rounded-md transition-all cursor-pointer ${
                hours === opt.value
                  ? 'bg-white text-[var(--primary-600)] shadow-sm font-medium'
                  : 'text-[var(--gray-500)] hover:text-[var(--gray-700)]'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-[var(--primary-500)] border-t-transparent" />
        </div>
      ) : chartData.length === 0 ? (
        <div className="flex items-center justify-center h-64 text-[var(--gray-500)]">
          No Brain activity data available for the selected period.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--gray-200)" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 11, fill: 'var(--gray-500)' }}
              tickLine={false}
              axisLine={{ stroke: 'var(--gray-200)' }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: 'var(--gray-500)' }}
              tickLine={false}
              axisLine={{ stroke: 'var(--gray-200)' }}
              width={40}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'white',
                border: '1px solid var(--gray-200)',
                borderRadius: '8px',
                fontSize: '12px',
                boxShadow: 'var(--shadow-md)',
              }}
              labelFormatter={(_label, payload) => {
                if (payload && payload.length > 0) {
                  return (payload[0].payload as { fullTime: string }).fullTime;
                }
                return _label;
              }}
            />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            <Bar dataKey="cycles" fill="#3B82F6" name="Cycles" radius={[2, 2, 0, 0]} />
            <Bar dataKey="tool_calls" fill="#F59E0B" name="Tool Calls" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// ── LLM Activity Section ─────────────────────────────────────────────

function LLMActivitySection() {
  const [hours, setHours] = useState(24);
  const { data: activity, isLoading, isError } = useLLMActivity(hours);
  const { data: events, isLoading: eventsLoading } = useEvents(undefined, 30);

  const hoursOptions = [
    { value: 1, label: '1h' },
    { value: 6, label: '6h' },
    { value: 24, label: '24h' },
    { value: 168, label: '7d' },
  ];

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className="bg-white rounded-xl elevation-2 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-[var(--gray-900)]">LLM Activity</h3>
          <div className="flex gap-1 bg-[var(--gray-100)] rounded-lg p-0.5">
            {hoursOptions.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setHours(opt.value)}
                className={`px-3 py-1 text-xs rounded-md transition-all cursor-pointer ${
                  hours === opt.value
                    ? 'bg-white text-[var(--primary-600)] shadow-sm font-medium'
                    : 'text-[var(--gray-500)] hover:text-[var(--gray-700)]'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-6">
            <div className="inline-block animate-spin rounded-full h-6 w-6 border-4 border-[var(--primary-500)] border-t-transparent" />
          </div>
        ) : isError || !activity ? (
          <div className="text-sm text-[var(--gray-500)] text-center py-4">
            Failed to load LLM activity data.
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-[var(--gray-50)] rounded-lg p-4 text-center">
              <p className="text-2xl font-bold text-[var(--primary-500)]">
                {activity.cycles}
              </p>
              <p className="text-xs text-[var(--gray-500)] mt-1">Cognitive Cycles</p>
            </div>
            <div className="bg-[var(--gray-50)] rounded-lg p-4 text-center">
              <p className="text-2xl font-bold text-[var(--primary-500)]">
                {activity.total_tool_calls}
              </p>
              <p className="text-xs text-[var(--gray-500)] mt-1">Tool Calls</p>
            </div>
            <div className="bg-[var(--gray-50)] rounded-lg p-4 text-center">
              <p className="text-2xl font-bold text-[var(--primary-500)]">
                {activity.avg_duration_sec.toFixed(1)}s
              </p>
              <p className="text-xs text-[var(--gray-500)] mt-1">Avg Duration</p>
            </div>
          </div>
        )}
      </div>

      {/* Event feed */}
      <div className="bg-white rounded-xl elevation-2 overflow-hidden">
        <div className="px-5 py-4 border-b border-[var(--gray-200)]">
          <h3 className="font-semibold text-[var(--gray-900)]">Recent Events</h3>
        </div>

        {eventsLoading ? (
          <div className="flex items-center justify-center py-6">
            <div className="inline-block animate-spin rounded-full h-6 w-6 border-4 border-[var(--primary-500)] border-t-transparent" />
          </div>
        ) : !events || events.length === 0 ? (
          <div className="text-sm text-[var(--gray-400)] text-center py-6">
            No recent events recorded.
          </div>
        ) : (
          <div className="divide-y divide-[var(--gray-100)] max-h-96 overflow-y-auto">
            {events.map((evt: EventItem, i: number) => (
              <div key={`${evt.timestamp}-${i}`} className="px-5 py-3 hover:bg-[var(--gray-50)] transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                        evt.event_type.includes('alert')
                          ? 'bg-[var(--error-50)] text-[var(--error-700)]'
                          : evt.event_type.includes('change')
                          ? 'bg-[var(--warning-50)] text-[var(--warning-700)]'
                          : 'bg-[var(--info-50)] text-[var(--info-700)]'
                      }`}>
                        {evt.event_type}
                      </span>
                      <span className="text-xs text-[var(--gray-400)] capitalize">
                        {evt.zone}
                      </span>
                    </div>
                    {evt.source_device && (
                      <p className="text-xs text-[var(--gray-500)] font-mono">
                        {evt.source_device}
                      </p>
                    )}
                    {Object.keys(evt.data).length > 0 && (
                      <p className="text-xs text-[var(--gray-500)] mt-1 truncate">
                        {JSON.stringify(evt.data)}
                      </p>
                    )}
                  </div>
                  <span className="text-xs text-[var(--gray-400)] whitespace-nowrap flex-shrink-0">
                    {formatFullTimestamp(evt.timestamp)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Device Status Section ────────────────────────────────────────────

const POWER_MODE_LABELS: Record<string, string> = {
  ALWAYS_ON: 'Always On',
  DEEP_SLEEP: 'Deep Sleep',
  ULTRA_LOW: 'Ultra Low',
  LIGHT_SLEEP: 'Light Sleep',
};

function getBatteryColor(pct: number): string {
  if (pct > 60) return '#4CAF50';
  if (pct > 30) return '#FF9800';
  return '#F44336';
}

function isOnline(lastHeartbeat: string | null): boolean {
  if (!lastHeartbeat) return false;
  const diff = Date.now() - new Date(lastHeartbeat).getTime();
  return diff < 5 * 60 * 1000; // 5 minutes
}

function DeviceStatusSection() {
  const { data: devices, isLoading, isError } = useDeviceStatus();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-[var(--primary-500)] border-t-transparent" />
      </div>
    );
  }

  if (isError || !devices) {
    return (
      <div className="text-center py-8 text-[var(--gray-500)]">
        Failed to load device data. The wallet service may be unavailable.
      </div>
    );
  }

  if (devices.length === 0) {
    return (
      <div className="text-center py-8 text-[var(--gray-500)]">
        No devices registered yet. Devices will appear once they connect.
      </div>
    );
  }

  // Group devices by device_type
  const grouped = devices.reduce<Record<string, DeviceStatus[]>>((acc, d) => {
    const key = d.device_type;
    if (!acc[key]) acc[key] = [];
    acc[key].push(d);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      {Object.entries(grouped).map(([deviceType, groupDevices]) => (
        <div key={deviceType}>
          <h3 className="text-sm font-medium text-[var(--gray-500)] uppercase tracking-wider mb-3">
            {deviceType}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {groupDevices.map((device: DeviceStatus, i: number) => {
              const online = isOnline(device.last_heartbeat_at);

              return (
                <motion.div
                  key={device.device_id}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="bg-white rounded-xl elevation-2 p-5"
                >
                  {/* Header: name + status indicator */}
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: online ? '#4CAF50' : '#F44336' }}
                        title={online ? 'Online' : 'Offline'}
                      />
                      <h4 className="font-semibold text-[var(--gray-900)] text-lg truncate">
                        {device.display_name || device.device_id}
                      </h4>
                    </div>
                    <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-[var(--gray-100)] text-[var(--gray-600)] flex-shrink-0">
                      {device.device_type}
                    </span>
                  </div>

                  {/* Battery bar */}
                  <div className="mb-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-[var(--gray-500)]">Battery</span>
                      <span className="text-xs font-medium text-[var(--gray-700)]">
                        {device.battery_pct !== null ? `${device.battery_pct}%` : 'N/A'}
                      </span>
                    </div>
                    {device.battery_pct !== null ? (
                      <div className="w-full h-2 bg-[var(--gray-100)] rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${device.battery_pct}%`,
                            backgroundColor: getBatteryColor(device.battery_pct),
                          }}
                        />
                      </div>
                    ) : (
                      <div className="w-full h-2 bg-[var(--gray-100)] rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full bg-[var(--gray-300)]"
                          style={{ width: '100%' }}
                        />
                      </div>
                    )}
                  </div>

                  {/* Details */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-[var(--gray-500)]">Last Heartbeat</span>
                      <span className="text-xs text-[var(--gray-700)]">
                        {timeAgo(device.last_heartbeat_at)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-[var(--gray-500)]">XP</span>
                      <span className="text-xs font-medium text-[var(--primary-600)]">
                        {device.xp.toLocaleString()}
                      </span>
                    </div>
                  </div>

                  {/* Footer: power mode badge */}
                  <div className="mt-3 pt-3 border-t border-[var(--gray-100)]">
                    <span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-[var(--gray-50)] text-[var(--gray-500)]">
                      {POWER_MODE_LABELS[device.power_mode] || device.power_mode}
                    </span>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Heatmap Section ──────────────────────────────────────────────────

const HEATMAP_PERIOD_OPTIONS = [
  { value: 'hour', label: 'Hour' },
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
];

function heatmapCellColor(count: number, maxCount: number): string {
  if (maxCount <= 0) return 'rgba(59,130,246,0.05)';
  const ratio = Math.min(count / maxCount, 1);
  const opacity = 0.05 + ratio * 0.95;
  return `rgba(59,130,246,${opacity.toFixed(2)})`;
}

function HeatmapSection() {
  const { data: zones } = useZoneOverview();
  const [period, setPeriod] = useState('hour');
  const [selectedZone, setSelectedZone] = useState<string>('');

  const availableZones = useMemo(() => {
    if (!zones || zones.length === 0) return [];
    return zones.map((z: ZoneSnapshot) => z.zone);
  }, [zones]);

  const {
    data: heatmapData,
    isLoading,
    isError,
  } = useHeatmap(selectedZone || undefined, period);

  // Find global max across all returned heatmaps for consistent color scaling
  const globalMax = useMemo(() => {
    if (!heatmapData || heatmapData.length === 0) return 0;
    let max = 0;
    for (const hm of heatmapData) {
      for (const row of hm.cell_counts) {
        for (const val of row) {
          if (val > max) max = val;
        }
      }
    }
    return max;
  }, [heatmapData]);

  return (
    <div className="bg-white rounded-xl elevation-2 p-6">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-4 mb-6">
        <div>
          <label className="block text-xs font-medium text-[var(--gray-500)] mb-1">
            Zone
          </label>
          <select
            value={selectedZone}
            onChange={(e) => setSelectedZone(e.target.value)}
            className="px-3 py-1.5 rounded-lg border border-[var(--gray-300)] bg-white text-sm text-[var(--gray-700)] focus:outline-none focus:border-[var(--primary-500)]"
          >
            <option value="">All Zones</option>
            {availableZones.map((z: string) => (
              <option key={z} value={z}>
                {z}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-[var(--gray-500)] mb-1">
            Period
          </label>
          <div className="flex gap-1 bg-[var(--gray-100)] rounded-lg p-0.5">
            {HEATMAP_PERIOD_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setPeriod(opt.value)}
                className={`px-3 py-1 text-xs rounded-md transition-all cursor-pointer ${
                  period === opt.value
                    ? 'bg-white text-[var(--primary-600)] shadow-sm font-medium'
                    : 'text-[var(--gray-500)] hover:text-[var(--gray-700)]'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-[var(--primary-500)] border-t-transparent" />
        </div>
      ) : isError ? (
        <div className="text-center py-12 text-[var(--gray-500)]">
          Failed to load heatmap data. The spatial service may be unavailable.
        </div>
      ) : !heatmapData || heatmapData.length === 0 ? (
        <div className="text-center py-12 text-[var(--gray-500)]">
          No heatmap data available for the selected period.
        </div>
      ) : (
        <div className="space-y-8">
          {heatmapData.map((hm: HeatmapData, idx: number) => (
            <motion.div
              key={hm.zone}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.08 }}
            >
              {/* Zone label */}
              <div className="flex items-center justify-between mb-3">
                <h4 className="font-semibold text-[var(--gray-900)] text-lg capitalize">
                  {hm.zone}
                </h4>
                {(hm.period_start || hm.period_end) && (
                  <span className="text-xs text-[var(--gray-400)]">
                    {hm.period_start ? formatFullTimestamp(hm.period_start) : ''}
                    {hm.period_start && hm.period_end ? ' - ' : ''}
                    {hm.period_end ? formatFullTimestamp(hm.period_end) : ''}
                  </span>
                )}
              </div>

              {/* Heatmap grid */}
              <div
                className="inline-grid gap-1"
                style={{
                  gridTemplateColumns: `repeat(${hm.grid_cols}, 1fr)`,
                }}
              >
                {hm.cell_counts.flatMap((row, rowIdx) =>
                  row.map((count, colIdx) => (
                    <motion.div
                      key={`${rowIdx}-${colIdx}`}
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ delay: idx * 0.08 + (rowIdx * hm.grid_cols + colIdx) * 0.005 }}
                      className="w-8 h-8 rounded-sm"
                      style={{ backgroundColor: heatmapCellColor(count, globalMax) }}
                      title={`Row ${rowIdx + 1}, Col ${colIdx + 1}: ${count}`}
                    />
                  )),
                )}
              </div>

              {/* Avg occupancy */}
              <div className="mt-2">
                <span className="text-xs text-[var(--gray-500)]">
                  Avg occupancy: <span className="font-medium text-[var(--gray-700)]">{hm.person_count_avg.toFixed(1)}</span> persons
                </span>
              </div>
            </motion.div>
          ))}

          {/* Legend */}
          <div className="flex items-center gap-3 pt-4 border-t border-[var(--gray-100)]">
            <span className="text-xs text-[var(--gray-500)]">Low</span>
            <div
              className="h-3 rounded-sm flex-1 max-w-48"
              style={{
                background: 'linear-gradient(to right, rgba(59,130,246,0.05), rgba(59,130,246,1))',
              }}
            />
            <span className="text-xs text-[var(--gray-500)]">High</span>
            {globalMax > 0 && (
              <span className="text-xs text-[var(--gray-400)] ml-2">
                (max: {globalMax})
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  return (
    <main className="max-w-6xl mx-auto px-6 py-8">
      {/* Zone Overview */}
      <section className="mb-8">
        <div className="mb-4">
          <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">
            Zone Overview
          </h2>
          <p className="text-[var(--gray-600)]">
            Current sensor readings per zone.
          </p>
        </div>
        <ZoneOverviewSection />
      </section>

      {/* Device Status */}
      <section className="mb-8">
        <div className="mb-4">
          <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">
            Device Status
          </h2>
          <p className="text-[var(--gray-600)]">
            Battery levels, connectivity, and XP for registered devices.
          </p>
        </div>
        <DeviceStatusSection />
      </section>

      {/* Time Series Charts */}
      <section className="mb-8">
        <div className="mb-4">
          <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">
            Sensor Time Series
          </h2>
          <p className="text-[var(--gray-600)]">
            Historical sensor data with configurable aggregation.
          </p>
        </div>
        <TimeSeriesSection />
      </section>

      {/* Brain Activity Timeline */}
      <section className="mb-8">
        <div className="mb-4">
          <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">
            Brain Activity Timeline
          </h2>
          <p className="text-[var(--gray-600)]">
            LLM cognitive cycles and tool usage over time.
          </p>
        </div>
        <LLMTimelineSection />
      </section>

      {/* Occupancy Heatmap */}
      <section className="mb-8">
        <div className="mb-4">
          <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">
            Occupancy Heatmap
          </h2>
          <p className="text-[var(--gray-600)]">
            Spatial occupancy density over time.
          </p>
        </div>
        <HeatmapSection />
      </section>

      {/* Two-column layout: Latest Readings + LLM Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Latest Readings */}
        <section>
          <div className="mb-4">
            <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">
              Sensor Data
            </h2>
            <p className="text-[var(--gray-600)]">
              Latest individual readings.
            </p>
          </div>
          <LatestReadingsSection />
        </section>

        {/* LLM Activity + Events */}
        <section>
          <div className="mb-4">
            <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">
              Brain Activity
            </h2>
            <p className="text-[var(--gray-600)]">
              LLM cognitive cycles and event feed.
            </p>
          </div>
          <LLMActivitySection />
        </section>
      </div>
    </main>
  );
}
