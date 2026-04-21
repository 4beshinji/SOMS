import { useQuery } from '@tanstack/react-query';
import { fetchDeviceHealth, type DeviceHealth } from '../../api/devices';

const STATE_STYLE: Record<string, string> = {
  online: 'bg-[var(--success-50)] text-[var(--success-700)]',
  sleeping: 'bg-[var(--info-50)] text-[var(--info-700)]',
  offline: 'bg-[var(--error-50)] text-[var(--error-700)]',
  unknown: 'bg-[var(--gray-100)] text-[var(--gray-600)]',
};

function batteryColor(pct: number | null): string {
  if (pct === null) return 'var(--gray-300)';
  if (pct > 60) return 'var(--success-500)';
  if (pct > 20) return 'var(--warning-500)';
  return 'var(--error-500)';
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const sec = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

export default function DeviceHealthSection() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['device-health'],
    queryFn: fetchDeviceHealth,
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return <p className="text-sm text-[var(--gray-500)]">Loading device health...</p>;
  }
  if (isError || !data) {
    return <p className="text-sm text-[var(--error-600)]">Brain unavailable. Device health is sourced from the brain's in-memory registry (populated by MQTT heartbeats).</p>;
  }
  if (data.length === 0) {
    return <p className="text-sm text-[var(--gray-500)]">No devices registered yet. Devices appear once they send an MQTT heartbeat.</p>;
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {data.map((d: DeviceHealth) => {
        const stateStyle = STATE_STYLE[d.state] ?? STATE_STYLE.unknown;
        return (
          <div key={d.device_id} className="bg-white rounded-xl border border-[var(--gray-200)] p-4 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <h4 className="font-semibold text-[var(--gray-900)] truncate">{d.device_id}</h4>
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${stateStyle}`}>{d.state}</span>
            </div>
            {d.device_type && (
              <p className="text-xs text-[var(--gray-500)]">{d.device_type}</p>
            )}
            <div className="flex items-center justify-between text-xs text-[var(--gray-500)]">
              <span>Battery</span>
              <span className="font-medium text-[var(--gray-700)]">
                {d.battery_pct !== null ? `${d.battery_pct}%` : 'N/A'}
              </span>
            </div>
            <div className="w-full h-1.5 bg-[var(--gray-100)] rounded-full overflow-hidden">
              {d.battery_pct !== null ? (
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${d.battery_pct}%`, backgroundColor: batteryColor(d.battery_pct) }}
                />
              ) : (
                <div className="h-full rounded-full bg-[var(--gray-300)]" style={{ width: '100%' }} />
              )}
            </div>
            <div className="flex items-center justify-between text-xs text-[var(--gray-500)]">
              <span>Power mode</span>
              <span className="text-[var(--gray-700)]">{d.power_mode}</span>
            </div>
            <div className="flex items-center justify-between text-xs text-[var(--gray-500)]">
              <span>Last seen</span>
              <span className="text-[var(--gray-700)]">{timeAgo(d.last_seen)}</span>
            </div>
            {!d.trusted && (
              <p className="text-[10px] text-[var(--warning-700)]">untrusted — new device</p>
            )}
          </div>
        );
      })}
    </div>
  );
}
