import { motion } from 'framer-motion';
import { useZoneOverview, type ZoneSnapshot } from '../../hooks/useAnalytics';
import { getChannelMeta, timeAgo } from '../../utils/channelConfig';

export default function ZoneOverviewSection() {
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
