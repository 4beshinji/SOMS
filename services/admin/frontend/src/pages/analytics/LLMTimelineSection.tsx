import { useState, useMemo } from 'react';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Bar,
  BarChart,
  Legend,
} from 'recharts';
import { useLLMTimeline, type LLMTimelinePoint } from '../../hooks/useAnalytics';
import { formatTimestamp, formatFullTimestamp } from '../../utils/channelConfig';

export default function LLMTimelineSection() {
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
