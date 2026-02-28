import { useState, useMemo } from 'react';
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
  useZoneOverview,
  useSensorTimeSeries,
  type ZoneSnapshot,
  type TimeSeriesPoint,
} from '../../hooks/useAnalytics';
import {
  WINDOW_OPTIONS,
  getChannelMeta,
  formatTimestamp,
  formatFullTimestamp,
} from '../../utils/channelConfig';

export default function TimeSeriesSection() {
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
