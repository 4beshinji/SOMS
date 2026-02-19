import type { DevicePosition, CameraConfig } from '../../types/spatial';

interface DeviceLayerProps {
  devices: Record<string, DevicePosition>;
  cameras: Record<string, CameraConfig>;
  sensorData?: Record<string, Record<string, number>>; // device_id -> {channel: value}
}

function tempColor(temp: number | undefined): string {
  if (temp === undefined) return '#6b7280';
  if (temp < 18) return '#3b82f6'; // blue (cold)
  if (temp > 26) return '#ef4444'; // red (hot)
  return '#10b981'; // green (comfortable)
}

function co2Color(co2: number | undefined): string {
  if (co2 === undefined) return '#6b7280';
  if (co2 > 1000) return '#ef4444'; // red
  if (co2 > 800) return '#f59e0b';  // yellow
  return '#10b981'; // green
}

export default function DeviceLayer({ devices, cameras, sensorData }: DeviceLayerProps) {
  return (
    <g className="device-layer">
      {/* Sensor devices */}
      {Object.entries(devices).map(([deviceId, dev]) => {
        const [x, y] = dev.position;
        const data = sensorData?.[deviceId] || {};
        const temp = data['temperature'];
        const co2 = data['co2'];
        const color = temp !== undefined ? tempColor(temp) : co2Color(co2);

        return (
          <g key={deviceId}>
            <circle
              cx={x}
              cy={y}
              r={0.3}
              fill={color}
              opacity={0.8}
              stroke="white"
              strokeWidth={0.05}
            />
            <text
              x={x}
              y={y + 0.55}
              textAnchor="middle"
              fontSize="0.28"
              fill="#374151"
              style={{ pointerEvents: 'none' }}
            >
              {deviceId}
            </text>
            {temp !== undefined && (
              <text
                x={x}
                y={y + 0.08}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize="0.22"
                fill="white"
                fontWeight="bold"
                style={{ pointerEvents: 'none' }}
              >
                {temp.toFixed(1)}
              </text>
            )}
          </g>
        );
      })}

      {/* Cameras */}
      {Object.entries(cameras).map(([camId, cam]) => {
        const [x, y] = cam.position;
        return (
          <g key={camId}>
            <rect
              x={x - 0.2}
              y={y - 0.2}
              width={0.4}
              height={0.4}
              rx={0.05}
              fill="#7c3aed"
              opacity={0.8}
              stroke="white"
              strokeWidth={0.05}
            />
            <text
              x={x}
              y={y + 0.55}
              textAnchor="middle"
              fontSize="0.25"
              fill="#7c3aed"
              style={{ pointerEvents: 'none' }}
            >
              {camId}
            </text>
          </g>
        );
      })}
    </g>
  );
}
