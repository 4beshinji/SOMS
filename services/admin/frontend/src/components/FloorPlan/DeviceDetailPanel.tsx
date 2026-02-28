import type { DevicePosition } from '@soms/types';

interface DeviceDetailPanelProps {
  deviceId: string;
  device?: DevicePosition;
  sensorData?: Record<string, number>;
  onClose: () => void;
  onDelete?: () => void;
}

const CHANNEL_UNITS: Record<string, string> = {
  temperature: '°C',
  humidity: '%',
  co2: 'ppm',
  pressure: 'hPa',
  voc: '',
  light: 'lux',
  noise: 'dB',
  pm25: 'µg/m³',
};

const CHANNEL_LABELS: Record<string, string> = {
  temperature: 'Temperature',
  humidity: 'Humidity',
  co2: 'CO₂',
  pressure: 'Pressure',
  voc: 'VOC',
  light: 'Light',
  noise: 'Noise',
  pm25: 'PM2.5',
};

function statusColor(channel: string, value: number): string {
  switch (channel) {
    case 'temperature':
      if (value < 18 || value > 28) return 'text-red-500';
      if (value < 20 || value > 26) return 'text-amber-500';
      return 'text-emerald-500';
    case 'humidity':
      if (value < 30 || value > 70) return 'text-red-500';
      if (value < 40 || value > 60) return 'text-amber-500';
      return 'text-emerald-500';
    case 'co2':
      if (value > 1000) return 'text-red-500';
      if (value > 800) return 'text-amber-500';
      return 'text-emerald-500';
    default:
      return 'text-[var(--gray-700)]';
  }
}

export default function DeviceDetailPanel({
  deviceId,
  device,
  sensorData,
  onClose,
  onDelete,
}: DeviceDetailPanelProps) {
  const channels = device?.channels ?? [];
  const hasData = sensorData && Object.keys(sensorData).length > 0;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-[var(--gray-200)] p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-[var(--gray-700)] truncate">
          {deviceId}
        </h3>
        <button
          onClick={onClose}
          aria-label="Close device detail panel"
          className="text-xs text-[var(--gray-400)] hover:text-[var(--gray-600)]"
        >
          close
        </button>
      </div>

      {/* Device info */}
      <div className="space-y-1 text-xs text-[var(--gray-600)] mb-3">
        {device && (
          <>
            <p>type: <span className="font-medium">{device.type}</span></p>
            <p>zone: <span className="font-medium">{device.zone}</span></p>
            <p>
              position: ({device.position[0].toFixed(1)}, {device.position[1].toFixed(1)})
            </p>
            {channels.length > 0 && (
              <p>channels: {channels.join(', ')}</p>
            )}
          </>
        )}
      </div>

      {/* Sensor values */}
      {hasData ? (
        <div className="border-t border-[var(--gray-100)] pt-3">
          <h4 className="text-xs font-medium text-[var(--gray-500)] mb-2">
            sensor data
          </h4>
          <div className="space-y-1.5">
            {Object.entries(sensorData).map(([channel, value]) => (
              <div
                key={channel}
                className="flex items-center justify-between"
              >
                <span className="text-xs text-[var(--gray-600)]">
                  {CHANNEL_LABELS[channel] ?? channel}
                </span>
                <span className={`text-sm font-mono font-medium ${statusColor(channel, value)}`}>
                  {value.toFixed(1)}
                  <span className="text-[10px] ml-0.5 text-[var(--gray-400)]">
                    {CHANNEL_UNITS[channel] ?? ''}
                  </span>
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="border-t border-[var(--gray-100)] pt-3">
          <p className="text-xs text-[var(--gray-400)] italic">
            No data
          </p>
        </div>
      )}

      {/* Delete button (only for DB-stored devices) */}
      {onDelete && (
        <div className="border-t border-[var(--gray-100)] pt-3 mt-3">
          <button
            onClick={onDelete}
            aria-label={`Delete device ${deviceId}`}
            className="w-full px-2 py-1.5 text-xs text-red-600 bg-red-50 rounded-md hover:bg-red-100 transition-colors"
          >
            Delete device
          </button>
        </div>
      )}
    </div>
  );
}
