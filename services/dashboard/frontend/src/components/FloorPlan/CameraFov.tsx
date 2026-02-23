import type { CameraConfig } from '../../types/spatial';

interface CameraFovProps {
  cameras: Record<string, CameraConfig>;
}

/**
 * Compute the SVG path for a camera's field-of-view sector.
 *
 * Coordinate system: x = right, y = down (SVG default).
 * orientation_deg = 0 → pointing right (+X), increasing CCW in standard math
 * but SVG y-axis is flipped, so we negate the angle for SVG rendering.
 *
 * @param cx  Camera x (meters)
 * @param cy  Camera y (meters)
 * @param orientationDeg  Camera direction (degrees, 0=right, CCW positive)
 * @param fovDeg  Total field of view angle (degrees)
 * @param range  Visualisation range in meters
 */
function fovSectorPath(
  cx: number,
  cy: number,
  orientationDeg: number,
  fovDeg: number,
  range: number,
): string {
  const half = fovDeg / 2;
  // SVG y-axis is inverted — negate for correct visual direction
  const leftRad = (-(orientationDeg - half) * Math.PI) / 180;
  const rightRad = (-(orientationDeg + half) * Math.PI) / 180;

  const x1 = cx + range * Math.cos(leftRad);
  const y1 = cy + range * Math.sin(leftRad);
  const x2 = cx + range * Math.cos(rightRad);
  const y2 = cy + range * Math.sin(rightRad);

  const largeArcFlag = fovDeg > 180 ? 1 : 0;

  return [
    `M ${cx} ${cy}`,
    `L ${x1} ${y1}`,
    `A ${range} ${range} 0 ${largeArcFlag} 0 ${x2} ${y2}`,
    'Z',
  ].join(' ');
}

export default function CameraFov({ cameras }: CameraFovProps) {
  const entries = Object.entries(cameras).filter(([, cam]) => {
    const pos = cam.position;
    return pos && pos.length >= 2 && cam.fov_deg > 0;
  });

  if (entries.length === 0) return null;

  return (
    <g className="camera-fov-layer">
      {entries.map(([camId, cam]) => {
        const [cx, cy] = cam.position;
        const path = fovSectorPath(cx, cy, cam.orientation_deg, cam.fov_deg, 4.0);
        return (
          <g key={camId}>
            {/* FOV sector */}
            <path
              d={path}
              fill="rgba(59,130,246,0.12)"
              stroke="#3b82f6"
              strokeWidth="0.05"
              strokeDasharray="0.2 0.1"
            />
            {/* Camera body dot */}
            <circle cx={cx} cy={cy} r={0.18} fill="#3b82f6" opacity={0.85} />
            {/* Camera label */}
            <text
              x={cx}
              y={cy - 0.28}
              textAnchor="middle"
              fontSize="0.3"
              fill="#93c5fd"
              style={{ pointerEvents: 'none', userSelect: 'none' }}
            >
              {camId}
            </text>
          </g>
        );
      })}
    </g>
  );
}
