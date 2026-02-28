import { useState } from 'react';
import {
  useLLMActivity,
  useEvents,
  type EventItem,
} from '../../hooks/useAnalytics';
import { formatFullTimestamp } from '../../utils/channelConfig';

export default function LLMActivitySection() {
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
                        evt.severity === 'critical' || evt.event_type.includes('fall')
                          ? 'bg-[var(--error-50)] text-[var(--error-700)]'
                          : /alert|exceeded|spike|tamper/.test(evt.event_type)
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
