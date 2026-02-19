import { motion } from 'framer-motion';
import type { ZoneGeometry, LiveSpatialData } from '../../types/spatial';

interface PersonLayerProps {
  zones: Record<string, ZoneGeometry>;
  liveData: LiveSpatialData[];
  showObjects: boolean;
}

function pixelToZoneCoord(
  px: number[],
  imageSize: number[],
  zone: ZoneGeometry,
): [number, number] | null {
  if (px.length < 2 || imageSize[0] === 0 || imageSize[1] === 0) return null;

  // Normalize pixel to 0-1 range
  const nx = px[0] / imageSize[0];
  const ny = px[1] / imageSize[1];

  // Map to zone bounding box
  const xs = zone.polygon.map(p => p[0]);
  const ys = zone.polygon.map(p => p[1]);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);

  const x = minX + nx * (maxX - minX);
  const y = minY + ny * (maxY - minY);

  return [x, y];
}

export default function PersonLayer({ zones, liveData, showObjects }: PersonLayerProps) {
  return (
    <g className="person-layer">
      {liveData.map(data => {
        const zone = zones[data.zone];
        if (!zone) return null;

        return (
          <g key={data.zone}>
            {/* Person dots */}
            {data.persons.map((person, idx) => {
              const coord = pixelToZoneCoord(
                person.center_px,
                data.image_size,
                zone,
              );
              if (!coord) return null;
              const [x, y] = coord;

              return (
                <g key={`person-${idx}`}>
                  {/* Pulse ring */}
                  <motion.circle
                    cx={x}
                    cy={y}
                    r={0.2}
                    fill="none"
                    stroke="#3b82f6"
                    strokeWidth={0.03}
                    initial={{ r: 0.15, opacity: 0.8 }}
                    animate={{ r: 0.4, opacity: 0 }}
                    transition={{ duration: 1.5, repeat: Infinity }}
                  />
                  {/* Person dot */}
                  <circle
                    cx={x}
                    cy={y}
                    r={0.15}
                    fill="#3b82f6"
                    opacity={0.9}
                    stroke="white"
                    strokeWidth={0.04}
                  />
                </g>
              );
            })}

            {/* Object markers */}
            {showObjects && data.objects.map((obj, idx) => {
              const coord = pixelToZoneCoord(
                obj.center_px,
                data.image_size,
                zone,
              );
              if (!coord) return null;
              const [x, y] = coord;

              return (
                <g key={`obj-${idx}`}>
                  <rect
                    x={x - 0.1}
                    y={y - 0.1}
                    width={0.2}
                    height={0.2}
                    fill="#f59e0b"
                    opacity={0.7}
                    rx={0.03}
                  />
                  <text
                    x={x}
                    y={y + 0.35}
                    textAnchor="middle"
                    fontSize="0.2"
                    fill="#92400e"
                    style={{ pointerEvents: 'none' }}
                  >
                    {obj.class_name}
                  </text>
                </g>
              );
            })}
          </g>
        );
      })}
    </g>
  );
}
