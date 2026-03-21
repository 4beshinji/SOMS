import { useSensorLatest } from '../../hooks/useAnalytics';
import { getChannelMeta, formatFullTimestamp } from '../../utils/channelConfig';
import { useZoneName } from '../../hooks/useZoneNames';

export default function LatestReadingsSection() {
  const { data: readings, isLoading } = useSensorLatest();
  const zoneName = useZoneName();

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
                  <td className="px-5 py-2.5 text-[var(--gray-700)]">{zoneName(r.zone)}</td>
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
