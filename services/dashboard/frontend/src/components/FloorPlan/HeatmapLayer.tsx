import type { ZoneGeometry, HeatmapData } from '../../types/spatial';

interface HeatmapLayerProps {
  zones: Record<string, ZoneGeometry>;
  heatmapData: HeatmapData[];
}

function heatColor(value: number, maxValue: number): string {
  if (maxValue === 0) return 'transparent';
  const intensity = Math.min(value / maxValue, 1);
  // Transparent → yellow → red
  if (intensity === 0) return 'transparent';
  const r = 255;
  const g = Math.round(255 * (1 - intensity * 0.8));
  const b = 0;
  return `rgba(${r}, ${g}, ${b}, ${intensity * 0.6})`;
}

export default function HeatmapLayer({ zones, heatmapData }: HeatmapLayerProps) {
  return (
    <g className="heatmap-layer">
      {heatmapData.map(hm => {
        const zone = zones[hm.zone];
        if (!zone || !zone.polygon.length || !hm.cell_counts.length) return null;

        // Calculate zone bounding box
        const xs = zone.polygon.map(p => p[0]);
        const ys = zone.polygon.map(p => p[1]);
        const minX = Math.min(...xs);
        const minY = Math.min(...ys);
        const maxX = Math.max(...xs);
        const maxY = Math.max(...ys);
        const zoneW = maxX - minX;
        const zoneH = maxY - minY;

        const cellW = zoneW / hm.grid_cols;
        const cellH = zoneH / hm.grid_rows;

        // Find max value for color scaling
        const maxVal = Math.max(1, ...hm.cell_counts.flat());

        // Create clip path from zone polygon
        const clipId = `heatmap-clip-${hm.zone}`;
        const points = zone.polygon.map(p => p.join(',')).join(' ');

        return (
          <g key={hm.zone}>
            <defs>
              <clipPath id={clipId}>
                <polygon points={points} />
              </clipPath>
            </defs>
            <g clipPath={`url(#${clipId})`}>
              {hm.cell_counts.map((row, rowIdx) =>
                row.map((count, colIdx) => {
                  if (count === 0) return null;
                  return (
                    <rect
                      key={`${rowIdx}-${colIdx}`}
                      x={minX + colIdx * cellW}
                      y={minY + rowIdx * cellH}
                      width={cellW}
                      height={cellH}
                      fill={heatColor(count, maxVal)}
                    />
                  );
                })
              )}
            </g>
          </g>
        );
      })}
    </g>
  );
}
