import { motion } from 'framer-motion';
import { useEnrichedDeviceStatus, type EnrichedDevice } from '../../hooks/useAnalytics';
import { useZoneName } from '../../hooks/useZoneNames';
import {
  SENSOR_CATEGORIES,
  CATEGORY_ORDER,
  BINARY_CHANNELS,
  POWER_MODE_LABELS,
  getBatteryColor,
  getChannelMeta,
  isOnline,
  timeAgo,
  type SensorCategory,
} from '../../utils/channelConfig';

export default function DeviceStatusSection() {
  const { data: devices, isLoading, isError } = useEnrichedDeviceStatus();
  const zoneName = useZoneName();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-[var(--primary-500)] border-t-transparent" />
      </div>
    );
  }

  if (isError || !devices) {
    return (
      <div className="text-center py-8 text-[var(--gray-500)]">
        Failed to load device data. The wallet service may be unavailable.
      </div>
    );
  }

  if (devices.length === 0) {
    return (
      <div className="text-center py-8 text-[var(--gray-500)]">
        No devices registered yet. Devices will appear once they connect.
      </div>
    );
  }

  // Group devices by sensor category
  const grouped: Partial<Record<SensorCategory, EnrichedDevice[]>> = {};
  for (const d of devices) {
    const key = d.category;
    if (!grouped[key]) grouped[key] = [];
    grouped[key]!.push(d);
  }

  return (
    <div className="space-y-6">
      {CATEGORY_ORDER.filter(cat => grouped[cat]).map(cat => {
        const catMeta = SENSOR_CATEGORIES[cat];
        const groupDevices = grouped[cat]!;
        return (
          <div key={cat}>
            <div className="flex items-center gap-2 mb-3">
              <span
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: catMeta.color }}
              />
              <h3 className="text-sm font-medium text-[var(--gray-500)] uppercase tracking-wider">
                {catMeta.label}
              </h3>
              <span className="text-xs text-[var(--gray-400)]">
                ({groupDevices.length})
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {groupDevices.map((device, i) => (
                <DeviceCard
                  key={device.device_id}
                  device={device}
                  index={i}
                  zoneName={zoneName}
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DeviceCard({
  device,
  index,
  zoneName,
}: {
  device: EnrichedDevice;
  index: number;
  zoneName: (id: string) => string;
}) {
  const online = isOnline(device.last_heartbeat_at);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="bg-white rounded-xl elevation-2 p-5"
    >
      {/* Header: name + status indicator */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="w-2.5 h-2.5 rounded-full flex-shrink-0"
            style={{ backgroundColor: online ? '#4CAF50' : '#F44336' }}
            title={online ? 'Online' : 'Offline'}
            role="img"
            aria-label={online ? 'Online' : 'Offline'}
          />
          <h4 className="font-semibold text-[var(--gray-900)] text-lg truncate">
            {device.label || device.display_name || device.device_id}
          </h4>
        </div>
        {device.spatialType && (
          <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-[var(--gray-100)] text-[var(--gray-600)] flex-shrink-0 ml-2">
            {device.spatialType}
          </span>
        )}
      </div>

      {/* Zone */}
      {device.zone && (
        <p className="text-xs text-[var(--gray-400)] mb-3 truncate">
          {zoneName(device.zone)}
        </p>
      )}

      {/* Sensor readings */}
      {device.channels.length > 0 && (
        <div className="mb-3">
          <span className="text-xs text-[var(--gray-500)] mb-1.5 block font-medium">
            Sensor Data
          </span>
          {device.latestReadings.length > 0 ? (
            <div className="space-y-1">
              {device.latestReadings.map(r => {
                const meta = getChannelMeta(r.channel);
                const isBinary = BINARY_CHANNELS.has(r.channel);
                return (
                  <div key={r.channel} className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span
                        className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ backgroundColor: meta.color }}
                      />
                      <span className="text-xs text-[var(--gray-600)]">{meta.label}</span>
                    </div>
                    <span className="text-xs font-medium text-[var(--gray-900)]">
                      {isBinary ? (
                        <span style={{ color: r.value > 0 ? '#4CAF50' : '#9E9E9E' }}>
                          {r.value > 0 ? 'Active' : 'Inactive'}
                        </span>
                      ) : (
                        <>
                          {r.value.toFixed(1)}
                          {meta.unit && (
                            <span className="text-[var(--gray-400)] ml-0.5">{meta.unit}</span>
                          )}
                        </>
                      )}
                    </span>
                  </div>
                );
              })}
              <div className="text-right">
                <span className="text-[10px] text-[var(--gray-400)]">
                  {timeAgo(device.latestReadings[0].timestamp)}
                </span>
              </div>
            </div>
          ) : (
            <span className="text-xs text-[var(--gray-400)]">No recent data</span>
          )}
        </div>
      )}

      {/* Battery bar */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-[var(--gray-500)]">Battery</span>
          <span className="text-xs font-medium text-[var(--gray-700)]">
            {device.battery_pct !== null ? `${device.battery_pct}%` : 'N/A'}
          </span>
        </div>
        {device.battery_pct !== null ? (
          <div className="w-full h-2 bg-[var(--gray-100)] rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${device.battery_pct}%`,
                backgroundColor: getBatteryColor(device.battery_pct),
              }}
            />
          </div>
        ) : (
          <div className="w-full h-2 bg-[var(--gray-100)] rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-[var(--gray-300)]"
              style={{ width: '100%' }}
            />
          </div>
        )}
      </div>

      {/* Details */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-xs text-[var(--gray-500)]">Last Heartbeat</span>
          <span className="text-xs text-[var(--gray-700)]">
            {timeAgo(device.last_heartbeat_at)}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-[var(--gray-500)]">XP</span>
          <span className="text-xs font-medium text-[var(--primary-600)]">
            {device.xp.toLocaleString()}
          </span>
        </div>
      </div>

      {/* Footer: power mode badge */}
      <div className="mt-3 pt-3 border-t border-[var(--gray-100)]">
        <span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-[var(--gray-50)] text-[var(--gray-500)]">
          {POWER_MODE_LABELS[device.power_mode] || device.power_mode}
        </span>
      </div>
    </motion.div>
  );
}
