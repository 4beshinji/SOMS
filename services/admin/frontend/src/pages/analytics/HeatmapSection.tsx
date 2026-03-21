import { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  useZoneOverview,
  useHeatmap,
  type ZoneSnapshot,
  type HeatmapData,
} from '../../hooks/useAnalytics';
import {
  HEATMAP_PERIOD_OPTIONS,
  formatFullTimestamp,
  heatmapCellColor,
} from '../../utils/channelConfig';
import { useZoneName } from '../../hooks/useZoneNames';

export default function HeatmapSection() {
  const { data: zones } = useZoneOverview();
  const [period, setPeriod] = useState('hour');
  const [selectedZone, setSelectedZone] = useState<string>('');
  const zoneName = useZoneName();

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
                {zoneName(z)}
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
                <h4 className="font-semibold text-[var(--gray-900)] text-lg">
                  {zoneName(hm.zone)}
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
