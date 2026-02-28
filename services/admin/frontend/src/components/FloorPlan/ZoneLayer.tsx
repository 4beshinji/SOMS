import type { ZoneGeometry } from '@soms/types';

interface ZoneLayerProps {
  zones: Record<string, ZoneGeometry>;
  selectedZone: string | null;
  onZoneClick: (zoneId: string) => void;
}

const ZONE_COLORS: Record<string, string> = {
  main: '#3b82f6',
  kitchen: '#f59e0b',
  entrance: '#10b981',
  meeting_room_a: '#8b5cf6',
};

function getZoneColor(zoneId: string, alpha: number = 0.15): string {
  const hex = ZONE_COLORS[zoneId] || '#6b7280';
  // Convert hex to rgba
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export default function ZoneLayer({ zones, selectedZone, onZoneClick }: ZoneLayerProps) {
  return (
    <g className="zone-layer">
      {Object.entries(zones).map(([zoneId, geom]) => {
        const points = geom.polygon.map(p => p.join(',')).join(' ');
        const isSelected = selectedZone === zoneId;

        // Calculate centroid for label
        const cx = geom.polygon.reduce((s, p) => s + p[0], 0) / geom.polygon.length;
        const cy = geom.polygon.reduce((s, p) => s + p[1], 0) / geom.polygon.length;

        return (
          <g key={zoneId} role="button" aria-label={`Zone: ${geom.display_name}`} onClick={() => onZoneClick(zoneId)} style={{ cursor: 'pointer' }}>
            <polygon
              points={points}
              fill={getZoneColor(zoneId, isSelected ? 0.3 : 0.15)}
              stroke={ZONE_COLORS[zoneId] || '#6b7280'}
              strokeWidth={isSelected ? 0.15 : 0.08}
              strokeDasharray={isSelected ? 'none' : '0.2,0.1'}
            />
            <text
              x={cx}
              y={cy}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize="0.5"
              fill={ZONE_COLORS[zoneId] || '#6b7280'}
              fontWeight={isSelected ? 'bold' : 'normal'}
              style={{ pointerEvents: 'none' }}
            >
              {geom.display_name}
            </text>
          </g>
        );
      })}
    </g>
  );
}
