import { motion } from 'framer-motion';
import { useDeviceStatus, type DeviceStatus } from '../../hooks/useAnalytics';
import {
  POWER_MODE_LABELS,
  getBatteryColor,
  isOnline,
  timeAgo,
} from '../../utils/channelConfig';

export default function DeviceStatusSection() {
  const { data: devices, isLoading, isError } = useDeviceStatus();

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

  // Group devices by device_type
  const grouped = devices.reduce<Record<string, DeviceStatus[]>>((acc, d) => {
    const key = d.device_type;
    if (!acc[key]) acc[key] = [];
    acc[key].push(d);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      {Object.entries(grouped).map(([deviceType, groupDevices]) => (
        <div key={deviceType}>
          <h3 className="text-sm font-medium text-[var(--gray-500)] uppercase tracking-wider mb-3">
            {deviceType}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {groupDevices.map((device: DeviceStatus, i: number) => {
              const online = isOnline(device.last_heartbeat_at);

              return (
                <motion.div
                  key={device.device_id}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="bg-white rounded-xl elevation-2 p-5"
                >
                  {/* Header: name + status indicator */}
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: online ? '#4CAF50' : '#F44336' }}
                        title={online ? 'Online' : 'Offline'}
                        role="img"
                        aria-label={online ? 'Online' : 'Offline'}
                      />
                      <h4 className="font-semibold text-[var(--gray-900)] text-lg truncate">
                        {device.display_name || device.device_id}
                      </h4>
                    </div>
                    <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-[var(--gray-100)] text-[var(--gray-600)] flex-shrink-0">
                      {device.device_type}
                    </span>
                  </div>

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
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
