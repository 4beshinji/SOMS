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
} from 'recharts';
import {
  useSensorTimeSeries,
  useLLMActivity,
  useZoneOverview,
  useSensorLatest,
  useEvents,
  type ZoneSnapshot,
  type TimeSeriesPoint,
  type EventItem,
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
